/**
 * Centralized authentication token management for frontend.
 * Provides unified access across localStorage and sessionStorage.
 */

import type { NextRouter } from "next/router";
import { API_BASE } from "./api";

export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("access_token") || sessionStorage.getItem("access_token") || null;
}

export function setAuthToken(token: string, rememberMe = true): void {
  if (typeof window === "undefined") return;
  // Always persist in localStorage to allow cross-page navigation & tabs
  localStorage.setItem("access_token", token);
  sessionStorage.setItem("access_token", token);
  if (rememberMe) {
    localStorage.setItem("remember_me", "true");
  } else {
    localStorage.removeItem("remember_me");
  }
}

export function clearAuthToken(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem("access_token");
  localStorage.removeItem("remember_me");
  sessionStorage.removeItem("access_token");
  localStorage.removeItem("active_claim_ticket_id");
}

// ---------------------------------------------------------------------------
// Role-based routing helpers
// ---------------------------------------------------------------------------

/** Maps a user role string to its canonical dashboard route. */
const ROLE_ROUTES: Record<string, string> = {
  CLAIMANT: "/claimant",
  ADJUSTER: "/adjuster",
  ADMIN: "/admin",
};

/**
 * Navigate to the dashboard page that matches `role`.
 * Falls back to `/login` (with token cleared) for unknown roles.
 */
export function redirectByRole(role: string, router: NextRouter): void {
  const route = ROLE_ROUTES[role];
  if (route) {
    router.push(route);
  } else {
    clearAuthToken();
    router.push("/login");
  }
}

/**
 * Verify the current session by calling `/api/v1/auth/me`.
 *
 * - If there is no token, immediately redirects to `/login`.
 * - If the server returns 401 / errors, clears the token and redirects to `/login`.
 * - If `requiredRole` is provided and the user's role does not match, redirects to
 *   the user's own dashboard.
 * - On success, calls `onSuccess(user)` with the decoded user profile.
 *
 * Returns a cleanup no-op so it can be used directly in `useEffect`.
 */
export function verifySessionOrRedirect(
  router: NextRouter,
  options: {
    requiredRole?: string;
    onSuccess: (user: Record<string, unknown>) => void;
    onFinally?: () => void;
  },
): void {
  const token = getAuthToken();
  if (!token) {
    router.push("/login");
    options.onFinally?.();
    return;
  }

  fetch(`${API_BASE}/api/v1/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  })
    .then((res) => {
      if (!res.ok) throw new Error("Unauthorized");
      return res.json() as Promise<Record<string, unknown>>;
    })
    .then((user) => {
      const role = user.role as string | undefined;
      if (options.requiredRole && role !== options.requiredRole) {
        redirectByRole(role ?? "", router);
        return;
      }
      options.onSuccess(user);
    })
    .catch(() => {
      clearAuthToken();
      router.push("/login");
    })
    .finally(() => {
      options.onFinally?.();
    });
}
