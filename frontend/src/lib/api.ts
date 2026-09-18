/**
 * Centralized API client for the InsureClaimAI frontend.
 *
 * Provides:
 *  - `API_BASE`     — single source of truth for the backend URL
 *  - `apiFetch`     — authenticated fetch wrapper with 401 handling
 *  - `normalizeList` — normalize paginated or plain list responses
 */

/** Backend origin, configurable via NEXT_PUBLIC_API_URL at build/runtime. */
export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Options accepted by `apiFetch` on top of the standard `RequestInit`. */
export interface ApiFetchOptions extends RequestInit {
  /** Bearer token to inject. Falls back to `getAuthToken()` when omitted. */
  token?: string;
}

/**
 * Authenticated fetch wrapper.
 *
 * - Automatically injects `Authorization: Bearer <token>` when a token is
 *   provided (or resolved from `getAuthToken()`).
 * - On HTTP 401, calls the optional `onUnauthorized` callback (typically
 *   `clearAuthToken(); router.push("/login")`).
 * - On any non-OK response, throws an `Error` with the `detail` field from
 *   the JSON body, or a generic message when the body is not JSON.
 */
export async function apiFetch<T = unknown>(
  path: string,
  { token, ...opts }: ApiFetchOptions = {},
  onUnauthorized?: () => void,
): Promise<T> {
  const headers = new Headers(opts.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(API_BASE + path, { ...opts, headers });

  if (res.status === 401) {
    onUnauthorized?.();
    throw new Error("Authentication expired.");
  }

  if (!res.ok) {
    let detail = `Request failed (${res.status}).`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // body was not JSON — keep generic message
    }
    throw new Error(detail);
  }

  return res.json() as Promise<T>;
}

/**
 * Normalize an API response that may be either a plain array or a paginated
 * envelope `{ items: T[] }`.  Returns an empty array when the value is nullish.
 */
export function normalizeList<T>(
  data: T[] | { items?: T[] } | null | undefined,
): T[] {
  if (!data) return [];
  if (Array.isArray(data)) return data;
  return data.items ?? [];
}
