"use client";
import { useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { assertWebAuthnSupport, prepareCreationOptions, serializeCredential } from "@/lib/webauthn";

export function AdjusterOnboardingPage(){
  const params=useSearchParams(),router=useRouter();
  const token=params.get("token")||"";
  const [info,setInfo]=useState<any>(null);
  const [password,setPassword]=useState(""),[confirm,setConfirm]=useState(""),[step,setStep]=useState<"loading"|"form"|"passkey"|"done"|"error">("loading");
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  useEffect(()=>{
    if(!token){setStep("error");setError("Invitation token is missing.");return;}
    api<any>("/api/v1/auth/onboarding/adjuster/"+encodeURIComponent(token),{skipAuth:true}).then(x=>{setInfo(x);setStep("form")}).catch(e=>{setError(e.message||"Invitation is invalid or expired.");setStep("error")});
  },[token]);

  async function accept(){
    setBusy(true);setError("");
    try{
      const r=await api<any>("/api/v1/auth/onboarding/adjuster/accept",{method:"POST",skipAuth:true,body:JSON.stringify({token,password,confirm_password:confirm})});
      localStorage.setItem("access_token",r.setup_access_token);
      setStep("passkey");
    }catch(e:any){setError(e.message||"Unable to complete onboarding.");}
    finally{setBusy(false);}
  }

  async function registerPasskey(){
    setBusy(true);setError("");
    try{
      if(window.isSecureContext===false) throw Error("Passkey setup requires HTTPS or localhost. Open the secure application URL.");
      assertWebAuthnSupport();
      const options=await api<any>("/api/v1/auth/passkey/registration/options",{method:"POST"});
      const credential=await navigator.credentials.create({publicKey:prepareCreationOptions(options.public_key)});
      if(!credential)throw Error("Passkey registration was cancelled.");
      await api("/api/v1/auth/passkey/registration/verify",{method:"POST",body:JSON.stringify({challenge_id:options.challenge_id,credential:serializeCredential(credential as PublicKeyCredential)})});
      localStorage.removeItem("access_token");
      setStep("done");
    }catch(e:any){setError(e.message||"Unable to register your passkey.");}
    finally{setBusy(false);}
  }

  return <main className="login-page"><div className="auth-card onboarding-card">
    <div className="auth-brand"><span className="brand-mark">F</span><span>Flowa</span></div>
    {step==="loading"&&<><h1 className="auth-title">Loading invitation</h1><p className="auth-subtitle">Checking your secure invitation…</p></>}
    {step==="error"&&<><h1 className="auth-title">Invitation unavailable</h1><p className="auth-subtitle">{error}</p><a className="btn primary" href="/login">Return to sign in</a></>}
    {step==="form"&&<><h1 className="auth-title">Set up your adjuster account</h1><p className="auth-subtitle">Welcome {info?.name}. Create your password first, then register a passkey.</p><form className="form" onSubmit={e=>{e.preventDefault();accept()}}><label>Email<input value={info?.email||""} readOnly/></label><label>Password<input type="password" value={password} onChange={e=>setPassword(e.target.value)} autoComplete="new-password" minLength={8} required/></label><label>Confirm password<input type="password" value={confirm} onChange={e=>setConfirm(e.target.value)} autoComplete="new-password" minLength={8} required/></label>{error&&<div className="error" role="alert">{error}</div>}<button className="btn primary" disabled={busy}>{busy?"Creating account…":"Continue to passkey setup"}</button></form></>}
    {step==="passkey"&&<><h1 className="auth-title">Register your passkey</h1><p className="auth-subtitle">Use your device biometrics, security key, or platform passkey. Keep this tab on the same secure domain used for your organization. Operational access is enabled only after this step.</p>{error&&<div className="error" role="alert">{error}</div>}<button className="btn primary" onClick={registerPasskey} disabled={busy}>{busy?"Waiting for your device…":"Register passkey"}</button></>}
    {step==="done"&&<><h1 className="auth-title">You’re all set</h1><p className="auth-subtitle">Your adjuster account is activated. Sign in with the passkey you just registered.</p><button className="btn primary" onClick={()=>router.replace("/login")}>Continue to sign in</button></>}
  </div></main>;
}
