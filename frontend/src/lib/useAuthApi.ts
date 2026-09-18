/**
 * `useAuthApi` — React hook providing a stable authenticated API caller.
 *
 * Replaces the identical `useCallback(() => fetch(API + path, { ...Bearer }), [router])`
 * pattern that was duplicated inside `adjuster.tsx` and every protected page.
 *
 * Usage:
 *   const api = useAuthApi();
 *   const data = await api<MyType>("/api/v1/...");
 */

import { useCallback } from "react";
import { useRouter } from "next/router";
import { getAuthToken, clearAuthToken } from "./auth";
import { apiFetch, API_BASE } from "./api";
import type { ApiFetchOptions } from "./api";

/**
 * Returns a stable `api(path, opts?)` async function that:
 *  - Reads the current auth token on every call (never captures a stale one).
 *  - Injects the `Authorization: Bearer` header automatically.
 *  - Redirects to `/login` and throws on 401.
 *  - Throws with the server's `detail` message on any non-OK response.
 */
export function useAuthApi() {
  const router = useRouter();

  return useCallback(
    async <T = unknown>(
      path: string,
      opts: Omit<ApiFetchOptions, "token"> = {},
    ): Promise<T> => {
      const token = getAuthToken() ?? undefined;
      return apiFetch<T>(
        path,
        { ...opts, token },
        () => {
          clearAuthToken();
          void router.push("/login");
        },
      );
    },
    [router],
  );
}

/**
 * Convenience: same as `useAuthApi()` but the returned function prepends
 * `API_BASE` only when the path is relative. Useful when code passes full URLs.
 * Re-exported so callers can access `API_BASE` without a separate import.
 */
export { API_BASE };
