'use client';

import React, { createContext, useContext, useState, useEffect } from 'react';
import { User, UserRole } from './types';
import { api } from './api';

interface AuthContextType {
  user: User | null;
  role: UserRole | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (access: string, user: User, refresh?: string) => void;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  role: null,
  isAuthenticated: false,
  isLoading: true,
  login: () => {},
  logout: async () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [role, setRole] = useState<UserRole | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
    if (!token) {
      setUser(null);
      setRole(null);
      setIsLoading(false);
      return;
    }

    // Call /api/v1/auth/me to verify real session on live backend
    api.get<User>('/api/v1/auth/me')
      .then((me) => {
        if (me && me.id && me.role) {
          setUser(me);
          setRole(me.role);
          localStorage.setItem('snow_user', JSON.stringify(me));
          localStorage.setItem('snow_role', me.role);
        } else {
          api.clearTokens();
          setUser(null);
          setRole(null);
        }
      })
      .catch(() => {
        api.clearTokens();
        setUser(null);
        setRole(null);
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, []);

  const login = (access: string, newUser: User, refresh?: string) => {
    api.setToken(access, refresh);
    localStorage.setItem('snow_user', JSON.stringify(newUser));
    localStorage.setItem('snow_role', newUser.role);
    setUser(newUser);
    setRole(newUser.role);
  };

  const logout = async () => {
    try {
      await api.post('/api/v1/auth/logout');
    } catch {}
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
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
