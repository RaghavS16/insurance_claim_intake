"use client";

import React, { useEffect } from "react";
import { useRouter } from "next/navigation";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function RootPage() {
  const router = useRouter();

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      router.push("/login");
      return;
    }

    fetch(`${API_BASE}/api/v1/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => {
        if (!res.ok) throw new Error("Invalid session");
        return res.json();
      })
      .then((data) => {
        if (data.role === "CLAIMANT") {
          router.push("/claimant");
        } else if (data.role === "ADJUSTER") {
          router.push("/adjuster");
        } else {
          localStorage.removeItem("access_token");
          router.push("/login");
        }
      })
      .catch(() => {
        localStorage.removeItem("access_token");
        router.push("/login");
      });
  }, [router]);

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center font-sans">
      <div className="flex flex-col items-center gap-4 text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-cyan-550 border-r-2 border-cyan-500"></div>
        <p className="text-slate-400 text-xs font-semibold tracking-wide uppercase">
          Verifying secure session...
        </p>
      </div>
    </div>
  );
}
