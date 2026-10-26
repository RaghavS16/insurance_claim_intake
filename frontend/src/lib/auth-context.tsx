'use client';

import React, { createContext, useContext, useState, useEffect } from 'react';
import { User, UserRole } from './types';
import { api, clearApiCache } from './api';

const SESSION_HINT_KEY = 'intelliclaim_has_session';

interface AuthContextType {
  user: User | null;
  role: UserRole | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (access: string, user: User) => void;
  logout: () => Promise<void>;
  updateUser: (user: User) => void;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  role: null,
  isAuthenticated: false,
  isLoading: true,
  login: () => {},
  logout: async () => {},
  updateUser: () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [role, setRole] = useState<UserRole | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const publicRoutes = ['/', '/signin', '/signup', '/forgot-password', '/verify-otp', '/reset-password', '/verify-email'];
    const currentPath = typeof window !== 'undefined' ? window.location.pathname : '';
    const isPublicRoute = publicRoutes.some((p) => currentPath === p || currentPath.startsWith(p));
    const hasSessionHint = typeof window !== 'undefined' && !!localStorage.getItem(SESSION_HINT_KEY);

    // Fast-path: Skip silent refresh on public pages when there is no active session hint
    if (!hasSessionHint && isPublicRoute) {
      setIsLoading(false);
      api.setInitialAuthPromise(null);
      return;
    }

    // Restore session on load with a silent POST /api/v1/auth/refresh using HttpOnly cookie
    const restorePromise = api
      .refreshToken()
      .then(async (res) => {
        if (res && res.access_token) {
          // Hydrate user directly from the refresh response payload, avoiding a redundant /auth/me call
          if (res.user && res.user.id && res.user.role) {
            setUser(res.user);
            setRole(res.user.role);
            if (typeof window !== 'undefined') {
              localStorage.setItem(SESSION_HINT_KEY, '1');
            }
            return res.access_token;
          }

          // Fallback to /auth/me if user object was not in the refresh response
          try {
            const me = await api.get<User>('/api/v1/auth/me');
            if (me && me.id && me.role) {
              setUser(me);
              setRole(me.role);
              if (typeof window !== 'undefined') {
                localStorage.setItem(SESSION_HINT_KEY, '1');
              }
              return res.access_token;
            }
          } catch {
            // me endpoint failed
          }
        }
        if (typeof window !== 'undefined') {
          localStorage.removeItem(SESSION_HINT_KEY);
        }
        api.clearTokens();
        clearApiCache();
        setUser(null);
        setRole(null);
        return null;
      })
      .catch(() => {
        if (typeof window !== 'undefined') {
          localStorage.removeItem(SESSION_HINT_KEY);
        }
        api.clearTokens();
        clearApiCache();
        setUser(null);
        setRole(null);
        return null;
      })
      .finally(() => {
        setIsLoading(false);
        api.setInitialAuthPromise(null);
      });

    api.setInitialAuthPromise(restorePromise);
  }, []);

  const login = (access: string, newUser: User) => {
    if (typeof window !== 'undefined') {
      localStorage.setItem(SESSION_HINT_KEY, '1');
    }
    clearApiCache();
    api.setToken(access);
    setUser(newUser);
    setRole(newUser.role);
  };

  const updateUser = (updated: User) => {
    setUser(updated);
    if (updated.role) {
      setRole(updated.role);
    }
  };

  const logout = async () => {
    if (typeof window !== 'undefined') {
      localStorage.removeItem(SESSION_HINT_KEY);
    }
    try {
      await api.post('/api/v1/auth/logout', {}, { credentials: 'include' });
    } catch {
      // Ignore network errors during remote session invalidation
    }
    clearApiCache();
    api.clearTokens();
    setUser(null);
    setRole(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        role,
        isAuthenticated: !!user,
        isLoading,
        login,
        logout,
        updateUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
