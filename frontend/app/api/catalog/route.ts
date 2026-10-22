import { NextResponse } from "next/server";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const backendUrl = (process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
  const backendQuery = new URLSearchParams();
  const query = url.searchParams.get("q")?.trim();
  const category = url.searchParams.get("category_id")?.trim() || url.searchParams.get("category")?.trim();
  if (query) backendQuery.set("q", query);
  if (category) backendQuery.set("category_id", category);
  const response = await fetch(`${backendUrl}/api/v1/products${backendQuery.size ? `?${backendQuery}` : ""}`, { cache: "no-store" });
  const payload = await response.json().catch(() => ({ error: "Catalog unavailable" }));
  return NextResponse.json(payload, { status: response.status, headers: { "Cache-Control": "public, max-age=60, stale-while-revalidate=300" } });
}
