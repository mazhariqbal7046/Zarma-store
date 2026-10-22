"use client";

import Image from "next/image";
import Link from "next/link";
import { ArrowUpRight, Bot, ChevronRight, Menu, Search, ShoppingBag, Sparkles, X } from "lucide-react";
import { useEffect, useState } from "react";
import { backend, BackendApiError } from "@/lib/backend-api";
import { productFromBackend, products, type Product } from "@/lib/products";

const formatPKR = (value: number) => `PKR ${value.toLocaleString("en-PK")}`;

function ProductCard({ product, index, onAdd, onTryOn }: { product: Product; index: number; onAdd: (product: Product) => void; onTryOn: (product: Product) => void }) {
  return <article className={`product-card product-card-3d product-card-stagger-${index % 6}`}><div className="product-image"><Image src={product.image} alt={product.name} fill sizes="(max-width: 768px) 50vw, 22vw" /><button className="tryon-image-action" onClick={() => onTryOn(product)} aria-label={`Try on ${product.name}`}>Try on</button><button className="quick-add" onClick={() => onAdd(product)} aria-label={`Add ${product.name} to cart`}>+</button></div><div className="product-info"><div><p className="eyebrow">{product.category}{product.seller ? ` · ${product.seller}` : ""}</p><h3>{product.name}</h3><button className="tryon-product-button" onClick={() => onTryOn(product)}>Try on this piece</button></div><strong>{formatPKR(product.price)}</strong></div></article>;
}

function TryOnPanel({ catalog, open, initialProductId, onClose }: { catalog: Product[]; open: boolean; initialProductId: string; onClose: () => void }) {
  const [selectedProductId, setSelectedProductId] = useState(catalog[0]?.id ?? "");
  const [photo, setPhoto] = useState<File | null>(null);
  const [jobStatus, setJobStatus] = useState("");
  const [resultUrl, setResultUrl] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (initialProductId) setSelectedProductId(initialProductId);
  }, [initialProductId]);

  async function startTryOn(event: React.FormEvent) {
    event.preventDefault();
    const product = catalog.find((item) => item.id === selectedProductId);
    if (!photo || !product) {
      setError("Select a customer photo and a catalog product first.");
      return;
    }
    setLoading(true);
    setError("");
    setResultUrl("");
    setJobStatus("Uploading your private photo…");
    try {
      const form = new FormData();
      form.append("file", photo);
      const upload = await backend.uploadTryonImage(form) as { id?: string };
      if (!upload.id) throw new Error("The backend did not return an upload ID.");
      setJobStatus("Creating a secure try-on job…");
      const job = await backend.createTryonJob({ upload_id: upload.id, product_id: product.id, garment_category: "upper_body" }) as { id?: string; status?: string; error_message?: string };
      if (!job.id) throw new Error(job.error_message || "The backend did not return a try-on job ID.");
      setJobStatus(`Try-on job ${job.status || "pending"}…`);
      for (let attempt = 0; attempt < 20; attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 3000));
        const current = await backend.tryonJob(job.id) as { status?: string; error_message?: string };
        setJobStatus(`Try-on job ${current.status || "processing"}…`);
        if (current.status === "failed" || current.status === "cancelled") throw new Error(current.error_message || "The try-on provider could not complete this job.");
        if (current.status === "completed") {
          const result = await backend.tryonResult(job.id) as { url?: string };
          if (!result.url) throw new Error("The backend did not return a signed result URL.");
          setResultUrl(result.url);
          setJobStatus("Completed. The result URL is private and temporary.");
          return;
        }
      }
      throw new Error("The try-on job is still processing. Check your try-on history later.");
    } catch (requestError: unknown) {
      setError(requestError instanceof Error ? requestError.message : "Try-on is temporarily unavailable.");
      setJobStatus("");
    } finally {
      setLoading(false);
    }
  }

  if (!open) return null;
  return <div className="tryon-overlay"><section className="tryon-section tryon-modal" id="tryon"><button className="tryon-close" onClick={onClose} aria-label="Close virtual try-on"><X size={20} /></button><div><p className="eyebrow accent">Virtual fitting room</p><h2>See the look<br /><em>before you buy.</em></h2><p>Upload one private photo, choose a real catalog product, and generate your try-on result. Camera access is not used.</p><small>Your photo is securely processed by the backend and the result URL is private and temporary.</small></div><form onSubmit={startTryOn}><label>Upload your photo<input type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => setPhoto(event.target.files?.[0] ?? null)} disabled={loading} required /></label><label>Selected product<select value={selectedProductId} onChange={(event) => setSelectedProductId(event.target.value)} disabled={loading || !catalog.length}>{catalog.length ? catalog.map((product) => <option key={product.id} value={product.id}>{product.name}</option>) : <option>No live products available</option>}</select></label><button className="button button-dark" type="submit" disabled={loading || !catalog.length}>{loading ? "Generating…" : "Generate virtual try-on"}</button>{jobStatus && <p role="status">{jobStatus}</p>}{error && <p role="alert">{error}</p>}{resultUrl && <Image src={resultUrl} alt="Virtual try-on result" width={500} height={650} unoptimized />}</form></section></div>;
}

export default function Home() {
  const [query, setQuery] = useState("");
  const [visibleProducts, setVisibleProducts] = useState<Product[]>(products);
  const [cart, setCart] = useState<Product[]>([]);
  const [chatOpen, setChatOpen] = useState(false);
  const [chatMessage, setChatMessage] = useState("");
  const [chatMessages, setChatMessages] = useState<Array<{ role: "user" | "assistant"; text: string }>>([]);
  const [conversationId, setConversationId] = useState<string>();
  const [chatSending, setChatSending] = useState(false);
  const [searched, setSearched] = useState(false);
  const [catalogStatus, setCatalogStatus] = useState<"loading" | "live" | "preview">("loading");
  const [catalogError, setCatalogError] = useState("");
  const [cartMessage, setCartMessage] = useState("");
  const [tryOnOpen, setTryOnOpen] = useState(false);
  const [tryOnProductId, setTryOnProductId] = useState("");

  useEffect(() => {
    let mounted = true;
    backend.products()
      .then((rows) => {
        if (!mounted) return;
        const liveProducts = rows.map(productFromBackend);
        if (liveProducts.length) {
          setVisibleProducts(liveProducts);
          setCatalogStatus("live");
        } else {
          setCatalogStatus("preview");
        }
      })
      .catch((error: unknown) => {
        if (!mounted) return;
        setCatalogStatus("preview");
        setCatalogError(error instanceof Error ? error.message : "Live catalog is unavailable.");
      });
    return () => { mounted = false; };
  }, []);

  useEffect(() => {
    const revealItems = Array.from(document.querySelectorAll<HTMLElement>("[data-reveal]"));
    if (!("IntersectionObserver" in window)) {
      revealItems.forEach((item) => item.classList.add("is-visible"));
      return;
    }
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.14 });
    revealItems.forEach((item) => observer.observe(item));
    return () => observer.disconnect();
  }, []);

  async function addToCart(product: Product) {
    setCartMessage("");
    if (!product.variantId) {
      setCartMessage("This preview item has no live variant. Load the connected catalog first.");
      return;
    }
    try {
      await backend.addCartItem(product.variantId);
      setCart((current) => current.some((item) => item.id === product.id) ? current : [...current, product]);
      setCartMessage("Added to your bag.");
    } catch (error: unknown) {
      setCartMessage(error instanceof BackendApiError && error.status === 401 ? "Sign in before adding items to your bag." : "Could not update your bag.");
    }
  }

  function openTryOn(product?: Product) {
    setTryOnProductId(product?.id || visibleProducts[0]?.id || "");
    setTryOnOpen(true);
  }

  async function submitSearch(event: React.FormEvent) {
    event.preventDefault();
    const cleanQuery = query.trim();
    if (!cleanQuery) return;
    setSearched(true);
    setCatalogError("");
    try {
      const result = await backend.aiSearch(cleanQuery);
      const rows = [...(result.products ?? []), ...(result.recommendations ?? [])];
      const unique = [...new Map(rows.map((item) => [item.id, item])).values()].map(productFromBackend);
      setVisibleProducts(unique);
      if (!unique.length) setCatalogError("No matching products are available right now.");
    } catch (error: unknown) {
      setCatalogError(error instanceof Error ? error.message : "Search is temporarily unavailable.");
    }
  }

  async function submitChat(event: React.FormEvent) {
    event.preventDefault();
    const cleanMessage = chatMessage.trim();
    if (!cleanMessage || chatSending) return;
    setChatMessage("");
    setChatMessages((current) => [...current, { role: "user", text: cleanMessage }]);
    setChatSending(true);
    try {
      const result = await backend.aiAssistant(cleanMessage, conversationId);
      if (result.conversation_id) setConversationId(result.conversation_id);
      setChatMessages((current) => [...current, { role: "assistant", text: String(result.answer ?? result.message ?? "I could not find a matching answer in the catalog.") }]);
    } catch (error: unknown) {
      const text = error instanceof BackendApiError && error.status === 401 ? "Please sign in to use your saved Zarma AI conversation." : "Zarma AI is temporarily unavailable. Please try again.";
      setChatMessages((current) => [...current, { role: "assistant", text }]);
    } finally {
      setChatSending(false);
    }
  }

  return <main>
    <header className="site-header"><a className="brand" href="#top" aria-label="Zarma Meni Mart home"><span className="brand-mark">ZM</span><span>Zarma Meni Mart</span></a><nav><a href="#shop">Shop</a><a href="#edit">The edit</a><a href="#tryon">Try on</a><a href="#story">Our approach</a></nav><div className="header-tools"><button aria-label="Search" onClick={() => document.getElementById("search")?.focus()}><Search size={18} /></button><Link href="/dashboard" aria-label="Dashboard">Dashboard</Link><Link href="/auth" aria-label="Sign in">Sign in</Link><button className="cart-button" onClick={() => document.getElementById("cart")?.scrollIntoView({ behavior: "smooth" })}><ShoppingBag size={18} /><span className={cart.length ? "cart-badge-pop" : ""}>{cart.length}</span></button><button className="mobile-menu" aria-label="Open menu"><Menu size={20} /></button></div></header>
    <div className="welcome-banner" role="status">Welcome to Zarma Store — thoughtful clothes for every version of you.</div><section className="hero" id="top" data-reveal><div className="hero-copy"><p className="hero-kicker hero-enter hero-enter-1">ZARMA / 01 — THE DAILY EDIT</p><h1 className="hero-enter hero-enter-2">Wear<br /><em>your way.</em></h1><p className="hero-subtitle hero-enter hero-enter-3">Clothes with a point of view, chosen for real life.</p><a className="button button-light hero-enter hero-enter-4" href="#shop">Explore the edit <ArrowUpRight size={16} /></a></div><div className="hero-art"><Image src={products[0].image} alt="Black oxford shirt" fill priority sizes="(max-width: 900px) 100vw, 55vw" /><div className="hero-art-label"><span>New season / 2026</span><strong>Everyday<br />uniforms</strong></div></div></section>
    <section className="search-band" id="shop" data-reveal><div><p className="eyebrow accent">Find your fit</p><h2>Start with a feeling. We’ll find the pieces.</h2></div><form className="smart-search" onSubmit={submitSearch}><Search size={19} /><input id="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Try “black shirt for a wedding”" aria-label="Search products" /><button type="submit">Search</button></form></section>
    <section className="catalog-section" data-reveal><div className="section-heading"><div><p className="eyebrow">{searched ? "Live search results" : catalogStatus === "live" ? "Live Zarma catalog" : "A considered edit"}</p><h2>{searched ? `${visibleProducts.length} pieces for “${query}”` : "The pieces that earn their place."}</h2></div><a href="#catalog">View the edit <ChevronRight size={16} /></a></div>{catalogStatus === "loading" && <div className="catalog-skeletons" aria-label="Loading products">{[1, 2, 3, 4].map((item) => <div className="catalog-skeleton" key={item} />)}</div>}{catalogError && <p className="catalog-notice" role="status">{catalogError}</p>}<div className="product-grid" id="catalog">{visibleProducts.map((product, index) => <ProductCard key={product.id} product={product} index={index} onAdd={addToCart} onTryOn={openTryOn} />)}</div></section>
    <button className="tryon-launcher" onClick={() => openTryOn()} aria-label="Open virtual try-on"><span className="tryon-launcher-dot" /> Try on</button>
    <TryOnPanel catalog={visibleProducts} open={tryOnOpen} initialProductId={tryOnProductId} onClose={() => setTryOnOpen(false)} />
    <section className="ai-section" id="edit" data-reveal><div className="ai-copy"><p className="eyebrow accent">A little help, built in</p><h2>Your personal stylist,<br /><em>always on.</em></h2><p>Tell us where you’re going, what you love, and what you want to spend. Zarma AI turns that into a considered look using only products we actually have.</p><button className="button button-dark" onClick={() => setChatOpen(true)}>Ask Zarma AI <Sparkles size={16} /></button></div><div className="chat-preview"><div className="chat-top"><span><Bot size={17} /> Zarma AI</span><span className="online-dot">Available</span></div><div className="chat-bubble user">I need a black shirt for a wedding under PKR 6,000.</div><div className="chat-bubble assistant">The Noir Oxford Shirt is PKR 4,890 and available in M, L, XL. Want me to build the rest of the look?</div><div className="chat-products">{products.slice(1, 3).map((product) => <div className="mini-product" key={product.id}><Image src={product.image} alt="" width={50} height={50} /><span>{product.name}<small>{formatPKR(product.price)}</small></span></div>)}</div></div></section>
    <section className="story" id="story" data-reveal><p className="eyebrow">Good clothes, less noise.</p><h2>Built around how<br />you actually dress.</h2><p>Useful silhouettes. Honest materials. A calmer way to shop. From Lahore to wherever the day takes you.</p></section>
    {cartMessage && <div className="cart-toast" role="status"><ShoppingBag size={15} /> {cartMessage}</div>}<button className="ai-floating ai-floating-top" onClick={() => setChatOpen(true)} aria-label="Open Ask Zarma AI at top"><Bot size={17} /> Ask Zarma AI</button><button className="ai-floating ai-floating-bottom" onClick={() => setChatOpen(true)} aria-label="Open Ask Zarma AI at bottom"><Bot size={17} /> Ask Zarma AI</button><footer><a className="brand" href="#top"><span className="brand-mark">ZM</span><span>Zarma Meni Mart</span></a><p>© 2026 Zarma Meni Mart. Made for your everyday.</p><div id="cart" className="cart-summary"><ShoppingBag size={16} /> {cart.length ? `${cart.length} item${cart.length > 1 ? "s" : ""} in your bag` : "Your bag is empty"}{cartMessage && <small>{cartMessage}</small>}</div></footer>
    {chatOpen && <div className="chat-modal" role="dialog" aria-modal="true" aria-label="Zarma AI shopping assistant"><div className="chat-modal-head"><span><Bot size={18} /> Zarma AI</span><button onClick={() => setChatOpen(false)} aria-label="Close"><X size={18} /></button></div><div className="chat-modal-body"><p className="chat-bubble assistant">Hi, I’m here to help you find the right look. What are you dressing for?</p>{chatMessages.map((message, index) => <p className={`chat-bubble ${message.role}`} key={`${message.role}-${index}`}>{message.text}</p>)}{chatSending && <p className="chat-bubble assistant">Checking the live catalog…</p>}</div><form onSubmit={submitChat} className="chat-input"><input value={chatMessage} onChange={(e) => setChatMessage(e.target.value)} placeholder="Ask about a look, size, or budget" disabled={chatSending} /><button aria-label="Send" disabled={chatSending}><ArrowUpRight size={17} /></button></form></div>}
  </main>;
}
