"use client";
import { useSearchParams, useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";

export function EmailVerificationPage(){
  const params=useSearchParams(),router=useRouter();
  const [email,setEmail]=useState(params.get("email")||"");
  const [otp,setOtp]=useState("");
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState("");
  const [error,setError]=useState("");

  async function verify(e:React.FormEvent){
    e.preventDefault();
    setBusy(true); setError(""); setMessage("");
    try{
      await api("/api/v1/auth/verify-email",{method:"POST",body:JSON.stringify({email,otp})});
      setMessage("Email verified. You can sign in now.");
      setTimeout(()=>router.replace("/login"),700);
    }catch(err:any){setError(err.message||"Verification failed.");}
    finally{setBusy(false);}
  }

  async function resend(){
    setError(""); setMessage("");
    try{
      const r=await api<any>("/api/v1/auth/resend-verification",{method:"POST",body:JSON.stringify({email})});
      setMessage(r.message||"A new verification code has been sent.");
    }catch(err:any){setError(err.message||"Unable to resend the verification code.");}
  }

  return <main className="login-page"><div className="auth-card">
    <div className="auth-brand"><span className="brand-mark">F</span><span>Flowa</span></div>
    <h1 className="auth-title">Verify your email</h1>
    <p className="auth-subtitle">Enter the verification code sent to your email address before signing in.</p>
    <form className="form" onSubmit={verify}>
      <label>Email<input type="email" value={email} onChange={e=>setEmail(e.target.value)} autoComplete="email" required/></label>
      <label>Verification code<input inputMode="numeric" value={otp} onChange={e=>setOtp(e.target.value.replace(/\D/g,"").slice(0,8))} autoComplete="one-time-code" required/></label>
      {error&&<div className="error" role="alert">{error}</div>}
      {message&&<div className="notice" role="status">{message}</div>}
      <button className="btn primary" type="submit" disabled={busy}>{busy?"Verifying…":"Verify email"}</button>
      <button className="btn" type="button" onClick={resend} disabled={!email}>Resend code</button>
      <div className="auth-links"><button className="link-button" type="button" onClick={()=>router.replace("/login")}>Back to sign in</button></div>
    </form>
  </div></main>;
}
