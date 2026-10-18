import { User, Policy, Claim, Adjuster, KnowledgeDocument, AuditEvent } from './types';

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  (typeof window !== 'undefined' ? '' : 'http://127.0.0.1:8000');

// In-memory access token storage (never written to localStorage or cookies on client)
let inMemoryAccessToken: string | null = null;

class ApiClient {
  public getToken(): string | null {
    return inMemoryAccessToken;
  }

  public setToken(access: string | null, _refresh?: string) {
    inMemoryAccessToken = access;
  }

  public clearTokens() {
    inMemoryAccessToken = null;
  }

  async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${API_BASE}${endpoint}`;
    const token = this.getToken();

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

    const res = await fetch(url, { ...options, headers, credentials: 'include' });

    if (res.status === 401 && !endpoint.includes('/auth/login') && !endpoint.includes('/auth/refresh') && !endpoint.includes('/auth/logout')) {
      try {
        const refreshRes = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
        });
        if (refreshRes.ok) {
          const data = await refreshRes.json();
          this.setToken(data.access_token);
          headers['Authorization'] = `Bearer ${data.access_token}`;
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
        } else {
          this.clearTokens();
        }
      } catch {
        this.clearTokens();
      }
    }

    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      let msg = `Request failed with status ${res.status}`;
      if (typeof errorData.detail === 'string') {
        msg = errorData.detail;
      } else if (Array.isArray(errorData.detail)) {
        msg = errorData.detail.map((d: any) => d.msg || JSON.stringify(d)).join('; ');
      } else if (errorData.message) {
        msg = errorData.message;
      } else if (errorData.error?.message) {
        msg = errorData.error.message;
      }
      throw new Error(msg);
    }

    // Check if response is empty (e.g. 204 No Content)
    const text = await res.text();
    if (!text) return {} as T;
    try {
      return JSON.parse(text) as T;
    } catch {
      return text as unknown as T;
    }
  }

  get<T>(endpoint: string): Promise<T> {
    return this.request<T>(endpoint, { method: 'GET' });
  }

  post<T>(endpoint: string, body?: any, options?: RequestInit): Promise<T> {
    const isFormData = typeof FormData !== 'undefined' && body instanceof FormData;
    return this.request<T>(endpoint, {
      ...options,
      method: 'POST',
      body: isFormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
    });
  }

  put<T>(endpoint: string, body?: any, options?: RequestInit): Promise<T> {
    const isFormData = typeof FormData !== 'undefined' && body instanceof FormData;
    return this.request<T>(endpoint, {
      ...options,
      method: 'PUT',
      body: isFormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
    });
  }

  patch<T>(endpoint: string, body?: any, options?: RequestInit): Promise<T> {
    return this.request<T>(endpoint, {
      ...options,
      method: 'PATCH',
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  delete<T>(endpoint: string, options?: RequestInit): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'DELETE' });
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
