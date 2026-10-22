"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { adminBackend, backend, sellerBackend } from "@/lib/backend-api";
import { createClient } from "@/lib/supabase/client";

type JsonValue = unknown;

function pretty(value: JsonValue) {
  return JSON.stringify(value, null, 2);
}

function Section({ title, value }: { title: string; value: JsonValue }) {
  return <section className="dashboard-card"><h2>{title}</h2><pre>{pretty(value)}</pre></section>;
}

function PaymentHistory({ orders }: { orders: JsonValue }) {
  const rows = Array.isArray(orders) ? orders.flatMap((order) => {
    if (!order || typeof order !== "object") return [];
    const payments = (order as { payments?: unknown }).payments;
    return Array.isArray(payments) ? payments.map((payment) => ({ order, payment })) : [];
  }) : [];
  return <section className="dashboard-card payment-history"><div className="payment-history-heading"><div><p className="eyebrow accent">Secure payment history</p><h2>Payments</h2></div><span>{rows.length} record{rows.length === 1 ? "" : "s"}</span></div>{rows.length ? <div className="payment-list">{rows.map(({ order, payment }, index) => { const item = payment && typeof payment === "object" ? payment as Record<string, unknown> : {}; const source = order && typeof order === "object" ? order as Record<string, unknown> : {}; return <div className="payment-row" key={String(item.id || `${source.id || "order"}-${index}`)}><div><strong>{String(item.provider || "Payment")}</strong><small>Order {String(item.order_id || source.id || "—")}</small></div><span className={`payment-status payment-status-${String(item.status || "pending")}`}>{String(item.status || "pending")}</span><small>{item.verified_at ? `Verified ${new Date(String(item.verified_at)).toLocaleDateString()}` : "Awaiting verification"}</small></div>; })}</div> : <p className="payment-empty">No payments yet. Your verified JazzCash, Easypaisa, or cash-on-delivery payment records will appear here.</p>}</section>;
}

function PaymentPanel() {
  const [orderId, setOrderId] = useState("");
  const [provider, setProvider] = useState<"jazzcash" | "easypaisa">("jazzcash");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  async function initiate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setMessage("");
    try {
      const result = await backend.initiatePayment({ order_id: orderId, provider, idempotency_key: crypto.randomUUID() }) as { checkout_url?: string; status?: string };
      setMessage(result.checkout_url ? `Payment initialized: ${result.status || "pending"}` : `Payment response: ${result.status || "received"}`);
      if (result.checkout_url) window.location.assign(result.checkout_url);
    } catch (error: unknown) {
      setMessage(error instanceof Error ? error.message : "Payment provider is unavailable.");
    } finally {
      setLoading(false);
    }
  }

  return <section className="dashboard-card payment-panel"><h2>Payment provider</h2><p>Payment starts only through the secure backend. No card, wallet or merchant secret is stored in the browser.</p><form onSubmit={initiate}><input required placeholder="Order ID" value={orderId} onChange={(event) => setOrderId(event.target.value)} /><select value={provider} onChange={(event) => setProvider(event.target.value as "jazzcash" | "easypaisa")}><option value="jazzcash">JazzCash</option><option value="easypaisa">Easypaisa</option></select><button className="button button-dark" type="submit" disabled={loading}>{loading ? "Checking…" : "Start payment"}</button></form>{message && <p role="status">{message}</p>}</section>;
}

function ProductManagement({ role }: { role: string }) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [price, setPrice] = useState("");
  const [description, setDescription] = useState("");
  const [sellerId, setSellerId] = useState("");
  const [sku, setSku] = useState("");
  const [size, setSize] = useState("M");
  const [color, setColor] = useState("");
  const [quantity, setQuantity] = useState("0");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setMessage("");
    try {
      const product = await sellerBackend.createProduct({ name, slug, description: description || null, price_pkr: Number(price), ...(role === "admin" ? { seller_id: sellerId } : {}) }) as { id?: string };
      if (!product.id) throw new Error("The backend did not return a product ID.");
      await sellerBackend.addVariant(product.id, { sku, size, color, price_pkr: Number(price), quantity: Number(quantity) });
      setMessage("Product and first variant created successfully.");
      setName(""); setSlug(""); setPrice(""); setDescription(""); setSellerId(""); setSku(""); setColor(""); setQuantity("0");
    } catch (error: unknown) {
      setMessage(error instanceof Error ? error.message : "Product creation failed.");
    } finally {
      setLoading(false);
    }
  }

  return <section className="dashboard-card product-management"><h2>{role === "admin" ? "Admin product studio" : "Seller product studio"}</h2><p>{role === "admin" ? "Create products for an approved seller." : "Create products only for your own approved store."}</p><form onSubmit={create}><input required minLength={2} placeholder="Product name" value={name} onChange={(event) => setName(event.target.value)} /><input required pattern="[a-z0-9]+(?:-[a-z0-9]+)*" placeholder="slug-like-name" value={slug} onChange={(event) => setSlug(event.target.value)} /><input required type="number" min="0" placeholder="Price PKR" value={price} onChange={(event) => setPrice(event.target.value)} /><textarea placeholder="Description" value={description} onChange={(event) => setDescription(event.target.value)} />{role === "admin" && <input required placeholder="Approved seller ID" value={sellerId} onChange={(event) => setSellerId(event.target.value)} />}<input required placeholder="Variant SKU" value={sku} onChange={(event) => setSku(event.target.value)} /><div className="product-form-row"><input required placeholder="Size" value={size} onChange={(event) => setSize(event.target.value)} /><input required placeholder="Color" value={color} onChange={(event) => setColor(event.target.value)} /><input required type="number" min="0" placeholder="Stock" value={quantity} onChange={(event) => setQuantity(event.target.value)} /></div><button className="button button-dark" type="submit" disabled={loading}>{loading ? "Creating…" : "Create product"}</button></form>{message && <p role="status">{message}</p>}</section>;
}

export default function DashboardPage() {
  const [profile, setProfile] = useState<Record<string, unknown> | null>(null);
  const [sections, setSections] = useState<Record<string, JsonValue>>({});
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [businessName, setBusinessName] = useState("");
  const [phone, setPhone] = useState("");
  const [description, setDescription] = useState("");
  const [applicationMessage, setApplicationMessage] = useState("");

  useEffect(() => {
    let mounted = true;
    async function load() {
      try {
        const { data: { session } } = await createClient().auth.getSession();
        if (!session) {
          setError("Please sign in to open your dashboard.");
          return;
        }
        const currentProfile = await backend.profile() as Record<string, unknown>;
        if (!mounted) return;
        setProfile(currentProfile);
        const role = String(currentProfile.role || "customer");
        if (role === "admin") {
          const results = await Promise.allSettled([adminBackend.analytics(), adminBackend.customers(), adminBackend.orders(), adminBackend.sellerApplications(), adminBackend.transactions(), adminBackend.withdrawals()]);
          setSections({ analytics: results[0].status === "fulfilled" ? results[0].value : "Unavailable", customers: results[1].status === "fulfilled" ? results[1].value : "Unavailable", orders: results[2].status === "fulfilled" ? results[2].value : "Unavailable", sellerApplications: results[3].status === "fulfilled" ? results[3].value : "Unavailable", transactions: results[4].status === "fulfilled" ? results[4].value : "Unavailable", withdrawals: results[5].status === "fulfilled" ? results[5].value : "Unavailable" });
        } else if (role === "seller") {
          const results = await Promise.allSettled([sellerBackend.earnings(), backend.sellerApplications(), backend.wallet(), backend.notifications()]);
          setSections({ earnings: results[0].status === "fulfilled" ? results[0].value : "Unavailable", applications: results[1].status === "fulfilled" ? results[1].value : "Unavailable", wallet: results[2].status === "fulfilled" ? results[2].value : "Unavailable", notifications: results[3].status === "fulfilled" ? results[3].value : "Unavailable" });
        } else if (role === "staff") {
          const notifications = await backend.notifications().catch(() => []);
          setSections({ access: "Staff workspace — admin-assigned permissions apply.", notifications });
        } else {
          const results = await Promise.allSettled([backend.orders(), backend.wishlist(), backend.wallet(), backend.notifications()]);
          setSections({ orders: results[0].status === "fulfilled" ? results[0].value : "Unavailable", wishlist: results[1].status === "fulfilled" ? results[1].value : "Unavailable", wallet: results[2].status === "fulfilled" ? results[2].value : "Unavailable", notifications: results[3].status === "fulfilled" ? results[3].value : "Unavailable" });
        }
      } catch (loadError: unknown) {
        if (mounted) setError(loadError instanceof TypeError ? "The backend is unavailable. Please refresh and try again." : loadError instanceof Error ? loadError.message : "Please sign in to open your dashboard.");
      } finally {
        if (mounted) setLoading(false);
      }
    }
    void load();
    return () => { mounted = false; };
  }, []);

  async function applyAsSeller(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setApplicationMessage("");
    try {
      await backend.applyAsSeller({ business_name: businessName, phone, description: description || null });
      setApplicationMessage("Seller application submitted. Admin approval is required before publishing products.");
    } catch (submitError: unknown) {
      setApplicationMessage(submitError instanceof Error ? submitError.message : "Seller application failed.");
    }
  }

  const role = String(profile?.role || "customer");
  const management = !loading && !error && (role === "seller" || role === "admin") ? <ProductManagement role={role} /> : null;
  return <main className="dashboard-shell"><header className="dashboard-header"><Link className="brand" href="/"><span className="brand-mark">ZM</span><span>Zarma Store</span></Link><Link href="/">Back to store</Link></header><section className="dashboard-intro"><p className="eyebrow accent">Zarma dashboard</p><h1>{loading ? "Loading your workspace…" : `${role.charAt(0).toUpperCase()}${role.slice(1)} workspace`}</h1><p>{profile ? `Signed-in account: ${String(profile.email || profile.user_id || "authenticated user")}` : "Your role-protected account area."}</p></section>{error && <p className="dashboard-error" role="alert">{error} — <Link href="/auth">Sign in</Link></p>}{!error && <div className="dashboard-grid">{Object.entries(sections).map(([title, value]) => <Section key={title} title={title} value={value} />)}</div>}{!loading && !error && role === "customer" && <PaymentHistory orders={sections.orders} />}{management}{!loading && !error && role === "customer" && <><section className="dashboard-card seller-application"><h2>Apply as a seller</h2><p>Applications are reviewed by an admin. Approval is required before publishing products.</p><form onSubmit={applyAsSeller}><input required minLength={2} placeholder="Business name" value={businessName} onChange={(event) => setBusinessName(event.target.value)} /><input required minLength={7} placeholder="Phone" value={phone} onChange={(event) => setPhone(event.target.value)} /><textarea maxLength={2000} placeholder="Describe your store" value={description} onChange={(event) => setDescription(event.target.value)} /><button className="button button-dark" type="submit">Submit seller application</button></form>{applicationMessage && <p role="status">{applicationMessage}</p>}</section><PaymentPanel /></>}</main>;
}
