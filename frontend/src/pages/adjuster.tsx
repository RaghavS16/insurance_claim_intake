import React, { useEffect, useState } from "react";
import { useRouter } from "next/router";
import Link from "next/link";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function AdjusterPage() {
  const router = useRouter();
  const [currentUser, setCurrentUser] = useState<any>(null);

  useEffect(() => {
    const savedToken = localStorage.getItem("access_token");
    if (!savedToken) {
      router.push("/login");
      return;
    }

    fetch(`${API_BASE}/api/v1/auth/me`, {
      headers: { Authorization: `Bearer ${savedToken}` },
    })
      .then((res) => {
        if (!res.ok) throw new Error("Unauthorized");
        return res.json();
      })
      .then((data) => {
        if (data.role !== "ADJUSTER" && data.role !== "ADMIN") {
          router.push("/claimant");
          return;
        }
        setCurrentUser(data);
      })
      .catch(() => {
        localStorage.removeItem("access_token");
        router.push("/login");
      });
  }, [router]);

  const handleLogout = () => {
    localStorage.removeItem("access_token");
    router.push("/login");
  };

  return (
    <div className="min-h-screen bg-canvas font-body text-on-surface flex flex-col antialiased selection:bg-primary-fixed selection:text-on-primary-fixed">
      {/* Top App Bar */}
      <header className="bg-canvas border-b border-surface-container-highest px-6 py-4 flex justify-between items-center sticky top-0 z-30">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-primary text-2xl">waves</span>
          <h1 className="font-headline text-lg font-bold text-on-surface">InsureClaimAI Adjuster Portal</h1>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-secondary font-label">{currentUser?.name || currentUser?.email}</span>
          <button
            onClick={handleLogout}
            className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-surface border border-outline-variant hover:bg-surface-container text-secondary hover:text-error transition-colors flex items-center gap-1"
          >
            <span className="material-symbols-outlined text-sm">logout</span>
            <span>Sign Out</span>
          </button>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 max-w-4xl mx-auto w-full p-8 flex flex-col items-center justify-center text-center">
        <div className="w-16 h-16 rounded-full bg-secondary-container flex items-center justify-center text-voice-active mb-4 shadow-sm">
          <span className="material-symbols-outlined text-3xl">assignment_turned_in</span>
        </div>
        <h2 className="font-headline text-2xl font-bold text-on-surface mb-2">Adjuster Review Queue</h2>
        <p className="font-body text-sm text-secondary max-w-md mb-6 leading-relaxed">
          Welcome to the Adjuster Portal. Claims filed by claimants via the Kinetic Voice intake agent will be automatically queued and assigned here.
        </p>
        <div className="flex gap-3">
          <Link
            href="/claimant"
            className="bg-voice-active hover:bg-primary-container text-white font-label text-xs font-semibold px-5 py-2.5 rounded-lg transition-colors shadow-sm"
          >
            Go to Claimant Intake
          </Link>
        </div>
      </main>
    </div>
  );
}
