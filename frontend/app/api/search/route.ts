import { NextResponse } from "next/server";

export async function POST(request: Request) {
  const { query } = await request.json();
  if (typeof query !== "string" || query.trim().length < 2) return NextResponse.json({ error: "Enter at least two characters." }, { status: 400 });
  const response = await fetch(`${(process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000").replace(/\/$/, "")}/api/v1/ai/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query: query.trim() }),
    cache: "no-store",
  });
  const payload = await response.json().catch(() => ({ error: "Search unavailable" }));
  return NextResponse.json(payload, { status: response.status });
}
