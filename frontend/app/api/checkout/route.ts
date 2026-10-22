import { NextResponse } from "next/server";
import { requireUser } from "@/lib/supabase/server";

type CheckoutItem = { variantId: string; quantity: number };

function isCheckoutItem(value: unknown): value is CheckoutItem {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  return typeof item.variantId === "string" && Number.isInteger(item.quantity) && Number(item.quantity) > 0;
}

export async function POST(request: Request) {
  try {
    const { supabase } = await requireUser();
    const body = await request.json();
    const idempotencyKey = typeof body.idempotencyKey === "string" ? body.idempotencyKey : crypto.randomUUID();
    const addressId = typeof body.addressId === "string" ? body.addressId : null;
    const rawItems: unknown[] = Array.isArray(body.items) ? body.items : [];
    const items: CheckoutItem[] = rawItems.filter(isCheckoutItem);
    if (!addressId || items.length === 0 || items.length !== rawItems.length) {
      return NextResponse.json({ error: "Address and valid items are required" }, { status: 400 });
    }

    const { data, error } = await supabase.rpc("create_order", {
      p_idempotency_key: idempotencyKey,
      p_address_id: addressId,
      p_items: items.map((item) => ({ variant_id: item.variantId, quantity: item.quantity })),
      p_delivery_pkr: Number.isInteger(body.deliveryPkr) ? body.deliveryPkr : 0,
      p_discount_pkr: 0,
    });
    if (error) return NextResponse.json({ error: error.message }, { status: 400 });
    return NextResponse.json({ order: data }, { status: 201 });
  } catch (error) {
    if (error instanceof Error && error.message === "AUTH_REQUIRED") return NextResponse.json({ error: "Sign in required" }, { status: 401 });
    if (error instanceof Error && error.message === "SUPABASE_NOT_CONFIGURED") return NextResponse.json({ error: "Supabase is not configured" }, { status: 503 });
    return NextResponse.json({ error: "Checkout unavailable" }, { status: 500 });
  }
}
