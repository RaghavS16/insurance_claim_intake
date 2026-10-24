'use client';

import React, { createContext, useContext, useState, useEffect } from 'react';
import { User, UserRole } from './types';
import { api, clearApiCache } from './api';

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
    // Restore session on load with a silent POST /api/v1/auth/refresh using HttpOnly cookie
    const restorePromise = api
      .refreshToken()
      .then(async (token) => {
        if (token) {
          try {
            const me = await api.get<User>('/api/v1/auth/me');
            if (me && me.id && me.role) {
              setUser(me);
              setRole(me.role);
              return token;
            }
          } catch {
            // me endpoint failed
          }
        }
        api.clearTokens();
        clearApiCache();
        setUser(null);
        setRole(null);
        return null;
      })
      .catch(() => {
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
