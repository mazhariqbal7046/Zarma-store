"use client";

import Link from "next/link";
import { Eye, EyeOff } from "lucide-react";
import { FormEvent, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { backend } from "@/lib/backend-api";

type Mode = "signin" | "signup" | "forgot" | "team";

export default function AuthPage() {
  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const supabase = createClient();
    setLoading(true);
    setError("");
    setMessage("");

    const result = mode === "signin" || mode === "team"
      ? await supabase.auth.signInWithPassword({ email, password })
      : mode === "signup"
        ? await supabase.auth.signUp({ email, password, options: { data: { full_name: fullName }, emailRedirectTo: `${window.location.origin}/auth/callback` } })
        : await supabase.auth.resetPasswordForEmail(email, { redirectTo: `${window.location.origin}/auth/reset` });

    setLoading(false);
    if (result.error) {
      setError(result.error.message);
      return;
    }
    if (mode === "signup" && "session" in result.data && result.data.session) {
      try {
        await backend.customerRegistered({ full_name: fullName || null });
      } catch {
        // Account creation succeeded; n8n delivery remains server-configured and retryable.
      }
    }
    setMessage(mode === "signin" || mode === "team" ? "Signed in successfully." : "Check your email to continue.");
    if (mode === "signin" || mode === "team") window.location.assign("/dashboard");
  }

  return <main className="auth-shell">
    <aside className="auth-visual">
      <Link className="brand auth-visual-brand" href="/"><span className="brand-mark">ZM</span><span>Zarma Store</span></Link>
      <div className="auth-visual-copy"><p className="eyebrow">The Zarma edit</p><h2>Wear what feels like you.</h2><p>Discover considered pieces, save your favourites, and make every order personal.</p></div>
      <div className="auth-visual-orbit"><span>ZM</span></div>
    </aside>
    <section className="auth-panel">
      <Link className="brand auth-brand" href="/"><span className="brand-mark">ZM</span><span>Zarma Store</span></Link>
      <div className="auth-copy"><p className="eyebrow accent">{mode === "team" ? "Zarma team access" : "Your account"}</p><h1>{mode === "signin" ? "Welcome back." : mode === "team" ? "Team sign in." : mode === "signup" ? "Make it yours." : "Reset your password."}</h1><p>{mode === "forgot" ? "We’ll send a secure reset link to your email." : mode === "team" ? "Admin and staff accounts are verified by Supabase roles and open the protected workspace." : "Save favourites, track orders, and get a more personal edit."}</p></div>
      <form className="auth-form" onSubmit={submit}>
        {mode === "signup" && <label>Full name<input required value={fullName} onChange={(event) => setFullName(event.target.value)} autoComplete="name" /></label>}
        <label>Email<input required type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" /></label>
        {mode !== "forgot" && <label>Password<div className="password-field"><input required minLength={8} type={showPassword ? "text" : "password"} value={password} onChange={(event) => setPassword(event.target.value)} autoComplete={mode === "signin" ? "current-password" : "new-password"} /><button type="button" onClick={() => setShowPassword((current) => !current)} aria-label={showPassword ? "Hide password" : "Show password"}>{showPassword ? <EyeOff size={16} /> : <Eye size={16} />}</button></div></label>}
        {error && <p className="auth-error" role="alert">{error}</p>}
        {message && <p className="auth-message" role="status">{message}</p>}
        <button className="button button-dark auth-submit" disabled={loading}>{loading ? "Please wait…" : mode === "signin" || mode === "team" ? "Sign in securely" : mode === "signup" ? "Create customer account" : "Send reset link"}</button>
      </form>
      <div className="auth-links">
        {mode === "signin" && <><button onClick={() => setMode("forgot")}>Forgot password?</button><button onClick={() => setMode("signup")}>Create an account</button><button onClick={() => setMode("team")}>Admin / staff login</button></>}
        {mode === "signup" && <button onClick={() => setMode("signin")}>Already have an account? Sign in</button>}
        {mode === "team" && <><p className="auth-security-note">Team accounts cannot self-register. An administrator must create or invite the account in Supabase.</p><button onClick={() => setMode("signin")}>Back to customer login</button></>}
        {mode === "forgot" && <button onClick={() => setMode("signin")}>Back to sign in</button>}
      </div>
    </section>
  </main>;
}
