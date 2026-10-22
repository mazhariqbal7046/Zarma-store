import { NextResponse } from "next/server";
import { requireUser } from "@/lib/supabase/server";

export async function GET() {
  try {
    const { supabase, user } = await requireUser();
    const { data, error } = await supabase
      .from("shopping_carts")
      .select("id,status,cart_items(id,quantity,variant_id,product_variants(id,sku,size,color,price_pkr,products(id,name,slug,active)))")
      .eq("user_id", user.id)
      .eq("status", "active")
      .maybeSingle();
    if (error) return NextResponse.json({ error: "Cart unavailable" }, { status: 500 });
    return NextResponse.json({ cart: data });
  } catch (error) {
    if (error instanceof Error && error.message === "AUTH_REQUIRED") return NextResponse.json({ error: "Sign in required" }, { status: 401 });
    if (error instanceof Error && error.message === "SUPABASE_NOT_CONFIGURED") return NextResponse.json({ error: "Supabase is not configured" }, { status: 503 });
    return NextResponse.json({ error: "Cart unavailable" }, { status: 500 });
  }
}

export async function POST(request: Request) {
  try {
    const { supabase, user } = await requireUser();
    const body = await request.json();
    const variantId = typeof body.variantId === "string" ? body.variantId : "";
    const quantity = Number(body.quantity);
    if (!variantId || !Number.isInteger(quantity) || quantity < 1 || quantity > 99) return NextResponse.json({ error: "Invalid cart item" }, { status: 400 });

    const { data: cart, error: cartError } = await supabase.from("shopping_carts").upsert({ user_id: user.id, status: "active" }, { onConflict: "user_id,status" }).select("id").single();
    if (cartError || !cart) return NextResponse.json({ error: "Cart unavailable" }, { status: 500 });
    const { error } = await supabase.from("cart_items").upsert({ cart_id: cart.id, variant_id: variantId, quantity }, { onConflict: "cart_id,variant_id" });
    if (error) return NextResponse.json({ error: "Could not update cart" }, { status: 400 });
    return NextResponse.json({ ok: true, cartId: cart.id });
  } catch (error) {
    if (error instanceof Error && error.message === "AUTH_REQUIRED") return NextResponse.json({ error: "Sign in required" }, { status: 401 });
    if (error instanceof Error && error.message === "SUPABASE_NOT_CONFIGURED") return NextResponse.json({ error: "Supabase is not configured" }, { status: 503 });
    return NextResponse.json({ error: "Could not update cart" }, { status: 500 });
  }
}
