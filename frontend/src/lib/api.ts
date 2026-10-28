import { User } from './types';

const API_BASE =
  typeof window !== 'undefined'
    ? ''
    : (process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000');

// In-memory access token storage (never written to localStorage or cookies on client)
let inMemoryAccessToken: string | null = null;
let refreshPromise: Promise<{ access_token: string; user?: User } | null> | null = null;
let initialAuthPromise: Promise<any> | null = null;

class ApiClient {
  private etagCache = new Map<string, { etag: string; data: any }>();

  public getToken(): string | null {
    return inMemoryAccessToken;
  }

  public setToken(access: string | null) {
    inMemoryAccessToken = access;
  }

  public setInitialAuthPromise(promise: Promise<any> | null) {
    initialAuthPromise = promise;
  }

  public clearCache() {
    this.etagCache.clear();
  }

  public clearTokens() {
    inMemoryAccessToken = null;
    this.clearCache();
  }

  public async refreshToken(): Promise<{ access_token: string; user?: User } | null> {
    if (refreshPromise) {
      return refreshPromise;
    }
    refreshPromise = (async () => {
      try {
        const refreshRes = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
        });
        if (refreshRes.ok) {
          const data = await refreshRes.json();
          this.setToken(data.access_token);
          return { access_token: data.access_token as string, user: data.user as User | undefined };
        } else {
          this.clearTokens();
          return null;
        }
      } catch {
        this.clearTokens();
        return null;
      } finally {
        refreshPromise = null;
      }
    })();
    return refreshPromise;
  }

  async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const isAuthEndpoint =
      endpoint.includes('/auth/login') ||
      endpoint.includes('/auth/signup') ||
      endpoint.includes('/auth/refresh') ||
      endpoint.includes('/auth/logout') ||
      endpoint.includes('/auth/forgot-password') ||
      endpoint.includes('/auth/verify-otp') ||
      endpoint.includes('/auth/reset-password') ||
      endpoint.includes('/auth/verify-email') ||
      endpoint.includes('/auth/resend-verification');

    // If an initial session restoration is underway on page load, await it before making protected calls
    if (!isAuthEndpoint && !this.getToken() && initialAuthPromise) {
      try {
        await initialAuthPromise;
      } catch {
        // Proceed even if initial auth check failed
      }
    }

    const url = `${API_BASE}${endpoint}`;
    const token = this.getToken();
    const isGet = (options.method || 'GET').toUpperCase() === 'GET';

    const headers: Record<string, string> = {
      ...(options.headers as Record<string, string>),
    };

    const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData;
    if (!isFormData && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const cached = isGet ? this.etagCache.get(url) : undefined;
    if (cached?.etag && !headers['If-None-Match']) {
      headers['If-None-Match'] = cached.etag;
    }

    const res = await fetch(url, { ...options, headers, credentials: 'include' });

    if (res.status === 304 && cached) {
      return cached.data as T;
    }

    if (res.status === 401 && !isAuthEndpoint) {
      const refreshResult = await this.refreshToken();
      const newAccessToken = typeof refreshResult === 'string' ? refreshResult : refreshResult?.access_token;
      if (newAccessToken) {
        headers['Authorization'] = `Bearer ${newAccessToken}`;
        const retryRes = await fetch(url, { ...options, headers, credentials: 'include' });
        if (!retryRes.ok) {
          const errorData = await retryRes.json().catch(() => ({}));
          let msg = `Request failed with status ${retryRes.status}`;
          if (typeof errorData.detail === 'string') {
            msg = errorData.detail;
          } else if (Array.isArray(errorData.detail)) {
            msg = errorData.detail.map((d: any) => d.msg || JSON.stringify(d)).join('; ');
          } else if (errorData.message) {
            msg = errorData.message;
          }
          throw new Error(msg);
        }
        return (await retryRes.json()) as T;
      }
    }

    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      let msg = `Request failed with status ${res.status}`;
      if (Array.isArray(errorData.error?.details) && errorData.error.details.length > 0) {
        msg = errorData.error.details.map((d: any) => `${d.field ? d.field + ': ' : ''}${d.msg || JSON.stringify(d)}`).join('; ');
      } else if (Array.isArray(errorData.details) && errorData.details.length > 0) {
        msg = errorData.details.map((d: any) => `${d.field ? d.field + ': ' : ''}${d.msg || JSON.stringify(d)}`).join('; ');
      } else if (typeof errorData.detail === 'string') {
        msg = errorData.detail;
      } else if (Array.isArray(errorData.detail)) {
        msg = errorData.detail.map((d: any) => d.msg || JSON.stringify(d)).join('; ');
      } else if (errorData.error?.message) {
        msg = errorData.error.message;
      } else if (errorData.message) {
        msg = errorData.message;
      }
      throw new Error(msg);
    }

    // Check if response is empty (e.g. 204 No Content)
    const text = await res.text();
    let data: T;
    if (!text) {
      data = {} as T;
    } else {
      try {
        data = JSON.parse(text) as T;
      } catch {
        data = text as unknown as T;
      }
    }

    const etag = res.headers.get('ETag');
    if (isGet && etag && res.ok) {
      this.etagCache.set(url, { etag, data });
    }

    return data;
  }

  get<T>(endpoint: string, options?: RequestInit): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'GET' });
  }

  async post<T>(endpoint: string, body?: any, options?: RequestInit): Promise<T> {
    const isFormData = typeof FormData !== 'undefined' && body instanceof FormData;
    const res = await this.request<T>(endpoint, {
      ...options,
      method: 'POST',
      body: isFormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
    });
    this.clearCache();
    return res;
  }

  async put<T>(endpoint: string, body?: any, options?: RequestInit): Promise<T> {
    const isFormData = typeof FormData !== 'undefined' && body instanceof FormData;
    const res = await this.request<T>(endpoint, {
      ...options,
      method: 'PUT',
      body: isFormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
    });
    this.clearCache();
    return res;
  }

  async patch<T>(endpoint: string, body?: any, options?: RequestInit): Promise<T> {
    const res = await this.request<T>(endpoint, {
      ...options,
      method: 'PATCH',
      body: body ? JSON.stringify(body) : undefined,
    });
    this.clearCache();
    return res;
  }

  async delete<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const res = await this.request<T>(endpoint, { ...options, method: 'DELETE' });
    this.clearCache();
    return res;
  }

  async downloadFile(endpoint: string, filename: string): Promise<void> {
    const url = `${API_BASE}${endpoint}`;
    const token = this.getToken();
    const headers: Record<string, string> = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const res = await fetch(url, { headers, credentials: 'include' });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      let msg = `Download failed with status ${res.status}`;
      if (typeof err.detail === 'string') msg = err.detail;
      else if (err.error?.message) msg = err.error.message;
      else if (err.message) msg = err.message;
      throw new Error(msg);
    }

    const blob = await res.blob();
    const blobUrl = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(blobUrl);
    document.body.removeChild(a);
  }
}

export const api = new ApiClient();
export const clearApiCache = () => api.clearCache();

