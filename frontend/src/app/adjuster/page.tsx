"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function AdjusterPage() {
  const router = useRouter();
  const [status, setStatus] = useState("Checking access...");

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      router.replace("/login");
      return;
    }

    fetch(`${API_BASE}/api/v1/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (res) => {
        if (!res.ok) throw new Error("Unauthorized");
        return res.json();
      })
      .then((user) => {
        if (user.role !== "ADJUSTER") {
          router.replace("/claimant");
          return;
        }
        setStatus(`Signed in as ${user.full_name}. Adjuster workspace is ready for Phase 2 policy/regulatory management.`);
      })
      .catch(() => {
        localStorage.removeItem("access_token");
        router.replace("/login");
      });
  }, [router]);

  return (
    <main className="min-h-screen bg-slate-950 text-slate-200 flex items-center justify-center p-6">
      <section className="max-w-xl w-full rounded-3xl border border-slate-800 bg-slate-900/70 p-8 shadow-2xl">
        <h1 className="text-2xl font-bold text-white">Adjuster Workspace</h1>
        <p className="mt-3 text-sm text-slate-400">{status}</p>
        <div className="mt-6 rounded-2xl border border-slate-800 p-4 text-sm text-slate-400">
          Claimant accounts cannot access this workspace. Adjuster-only policy wording and regulatory-document management belongs here and will be wired to protected backend endpoints in Phase 2.
        </div>
      </section>
    </main>
  );
}
