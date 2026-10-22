"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";

export default function ResetPasswordPage() {
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const supabase = createClient();
    setError("");
    setMessage("");
    const { error: updateError } = await supabase.auth.updateUser({ password });
    if (updateError) setError(updateError.message);
    else setMessage("Password updated. You can now sign in with it.");
  }

  return <main className="auth-shell"><section className="auth-panel"><Link className="brand auth-brand" href="/"><span className="brand-mark">ZM</span><span>Zarma Store</span></Link><div className="auth-copy"><p className="eyebrow accent">Account security</p><h1>Choose a new password.</h1><p>Use at least eight characters. Your reset link is short-lived.</p></div><form className="auth-form" onSubmit={submit}><label>New password<input required minLength={8} type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" /></label>{error && <p className="auth-error" role="alert">{error}</p>}{message && <p className="auth-message" role="status">{message}</p>}<button className="button button-dark auth-submit">Update password</button></form><div className="auth-links"><Link href="/auth">Back to sign in</Link></div></section></main>;
}
