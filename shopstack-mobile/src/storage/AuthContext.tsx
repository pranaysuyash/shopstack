/**
 * AuthContext — reactive auth state for the entire app.
 *
 * Motivation (motto_v3 §11 Engineering Standards, §0.14 Feature as Workflow):
 * The original `_layout.tsx` called `getToken()` once on mount inside `useEffect([], [])`.
 * After `login.tsx` called `setToken()` + `router.replace('/')`, the root layout never
 * re-read the token, leaving `isAuthenticated === false` and the stack stuck on `(auth)`.
 *
 * Fix: A single `AuthContext` owns the auth state. Any component (login, register, logout)
 * calls `signIn()` / `signOut()` and the root layout reacts immediately via context.
 */
import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { getToken, setToken as storeToken, deleteToken } from './token';

interface AuthContextValue {
  /** null = still loading, true/false = determined */
  isAuthenticated: boolean | null;
  /** Call after persisting token; updates auth state immediately */
  signIn: (token: string) => Promise<void>;
  /** Call on logout; clears token and flips auth state */
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);

  // Check stored token once on mount
  useEffect(() => {
    getToken().then((token) => setIsAuthenticated(!!token));
  }, []);

  const signIn = useCallback(async (token: string) => {
    await storeToken(token);
    setIsAuthenticated(true);
  }, []);

  const signOut = useCallback(async () => {
    await deleteToken();
    setIsAuthenticated(false);
  }, []);

  return (
    <AuthContext.Provider value={{ isAuthenticated, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
