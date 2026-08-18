"use client";
import React, { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function AdjusterPage() {
  const router = useRouter();

  useEffect(() => {
    const savedToken = localStorage.getItem("access_token");
    if (!savedToken) {
      router.push("/login");
    }
  }, [router]);

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center text-slate-400 font-sans selection:bg-cyan-500 selection:text-white">
      Adjuster workflow arrives in Phase 2.
    </div>
  );
}
