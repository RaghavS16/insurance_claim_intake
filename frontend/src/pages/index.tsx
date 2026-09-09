import React, { useEffect } from "react";
import { useRouter } from "next/router";
import { getAuthToken, clearAuthToken } from "../lib/auth";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function IndexPage() {
  const router = useRouter();

  useEffect(() => {
    const token = getAuthToken();
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
        } else if (data.role === "ADMIN") {
          router.push("/admin");
        } else {
          clearAuthToken();
          router.push("/login");
        }
      })
      .catch(() => {
        clearAuthToken();
        router.push("/login");
      });
  }, [router]);

  return (
    <div className="min-h-screen bg-canvas flex items-center justify-center font-body selection:bg-primary-fixed selection:text-on-primary-fixed">
      <div className="flex flex-col items-center gap-4 text-center">
        <div className="w-12 h-12 rounded-full bg-surface-alt border border-surface-container-highest flex items-center justify-center shadow-sm">
          <span className="material-symbols-outlined text-voice-active text-2xl animate-spin">
            progress_activity
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-primary text-xl">waves</span>
          <span className="font-headline font-bold text-on-surface">InsureClaimAI</span>
        </div>
        <p className="text-secondary text-xs font-label font-medium tracking-wide">
          Verifying secure session...
        </p>
      </div>
    </div>
  );
}
