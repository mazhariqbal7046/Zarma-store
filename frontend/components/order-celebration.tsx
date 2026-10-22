"use client";

import { Check, Package, Truck, X } from "lucide-react";
import { useEffect, useState } from "react";

type OrderCreatedDetail = { order?: { id?: string; order_id?: string } | null };

export default function OrderCelebration() {
  const [open, setOpen] = useState(false);
  const [stage, setStage] = useState<"packing" | "shipping" | "confirmed">("packing");
  const [orderId, setOrderId] = useState("");

  useEffect(() => {
    function handleOrderCreated(event: Event) {
      const detail = (event as CustomEvent<OrderCreatedDetail>).detail;
      setOrderId(detail?.order?.id || detail?.order?.order_id || "");
      setStage("packing");
      setOpen(true);
      const shippingTimer = window.setTimeout(() => setStage("shipping"), 1500);
      const confirmedTimer = window.setTimeout(() => setStage("confirmed"), 3400);
      return () => { window.clearTimeout(shippingTimer); window.clearTimeout(confirmedTimer); };
    }
    window.addEventListener("zarma:order-created", handleOrderCreated);
    return () => window.removeEventListener("zarma:order-created", handleOrderCreated);
  }, []);

  if (!open) return null;
  const displayOrderId = orderId ? `#${orderId.slice(0, 8).toUpperCase()}` : "#ZARMA-NEW";
  return <div className="order-celebration-backdrop" role="presentation">
    <section className="order-celebration" role="dialog" aria-modal="true" aria-labelledby="order-celebration-title">
      <button className="order-celebration-close" onClick={() => setOpen(false)} aria-label="Close order confirmation"><X size={18} /></button>
      <div className={`order-scene order-scene-${stage}`} aria-hidden="true"><div className="order-orb" /><div className="order-road"><span /><span /><span /></div><div className="order-box"><Package size={32} /><i /><i /></div><div className="order-van"><Truck size={58} /><b /><b /></div></div>
      <p className="eyebrow accent">Zarma delivery / {stage === "confirmed" ? "01" : "00"}</p>
      <h2 id="order-celebration-title">{stage === "packing" ? "We’re packing your order." : stage === "shipping" ? "Your order is on the way." : "Order confirmed."}</h2>
      <p className="order-celebration-copy">{stage === "packing" ? "Our team is preparing your pieces with care." : stage === "shipping" ? "A Zarma van is carrying your edit to you." : `Thanks for shopping with us. Order ${displayOrderId} is confirmed.`}</p>
      <div className="order-progress" aria-label="Order progress"><span className="is-done"><Package size={14} /> Packed</span><span className={stage === "shipping" || stage === "confirmed" ? "is-done" : ""}><Truck size={14} /> Shipped</span><span className={stage === "confirmed" ? "is-done" : ""}><Check size={14} /> Confirmed</span></div>
      {stage === "confirmed" && <button className="button button-dark order-celebration-action" onClick={() => setOpen(false)}>Continue shopping</button>}
    </section>
  </div>;
}
