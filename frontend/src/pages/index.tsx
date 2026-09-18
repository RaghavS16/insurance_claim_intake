import React, { useEffect } from "react";
import { useRouter } from "next/router";
import { verifySessionOrRedirect, redirectByRole } from "../lib/auth";

export default function IndexPage() {
  const router = useRouter();

  useEffect(() => {
    verifySessionOrRedirect(router, {
      onSuccess: (user) => redirectByRole(user.role as string, router),
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
