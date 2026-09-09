/**
 * Centralized authentication token management for frontend.
 * Provides unified access across localStorage and sessionStorage.
 */

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
