/**
 * Authentication context provider.
 *
 * Auto-logout behaviors managed here:
 *  1. Forced logout via 'auth:logout' window event (existing — triggered by failed refresh)
 *  2. Cross-tab logout sync via BroadcastChannel('auth_sync')
 *  3. Proactive token refresh scheduled before access token expiry
 *  4. Inactivity auto-logout with a 60-second warning modal
 */

import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react';
import type { AuthContextType, LoginCredentials, User } from '../types/auth';
import { tokenStorage, getTokenExpiryMs } from '../api/client';
import * as authApi from '../api/auth';
import { useInactivityLogout } from '../hooks/useInactivityLogout';
import { InactivityWarningModal } from '../components/InactivityWarningModal';

const INACTIVITY_TIMEOUT_MS =
  (Number(import.meta.env.VITE_INACTIVITY_TIMEOUT_MINUTES) || 30) * 60_000;
const INACTIVITY_WARNING_MS = 60_000; // warn 60 s before logout
const PROACTIVE_REFRESH_LEAD_MS = 60_000; // refresh 60 s before token expiry

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showInactivityWarning, setShowInactivityWarning] = useState(false);
  const [warningCountdown, setWarningCountdown] = useState(60);

  const isAuthenticated = !!user;

  // ── Initialize auth state on mount ────────────────────────────────────────
  // useRef guard prevents React StrictMode double-mount from racing two
  // concurrent refresh calls (the first rotates the cookie, the second
  // fails with the stale cookie and clears the session).
  const didInit = useRef(false);
  useEffect(() => {
    if (didInit.current) return;
    didInit.current = true;

    async function initAuth() {
      try {
        // If an in-memory access token survived (e.g. HMR), try it first
        const token = tokenStorage.getAccessToken();
        if (token) {
          try {
            const userData = await authApi.getCurrentUser();
            setUser(userData);
            return;
          } catch {
            // Token invalid -- fall through to silent refresh
          }
        }

        // Attempt silent refresh via httpOnly cookie
        const refreshed = await authApi.refreshToken();
        if (refreshed) {
          const userData = await authApi.getCurrentUser();
          setUser(userData);
        }
      } catch {
        tokenStorage.clearTokens();
      } finally {
        setIsLoading(false);
      }
    }

    initAuth();
  }, []);

  // ── 1. Forced logout via window event ─────────────────────────────────────
  useEffect(() => {
    const handleLogout = () => {
      setUser(null);
      tokenStorage.clearTokens();
    };

    window.addEventListener('auth:logout', handleLogout);
    return () => window.removeEventListener('auth:logout', handleLogout);
  }, []);

  // ── 2. Cross-tab logout sync ───────────────────────────────────────────────
  // Access token is in-memory (per-tab); refresh token is in httpOnly cookie
  // (shared). BroadcastChannel syncs logout to clear in-memory tokens in
  // other tabs immediately.
  //
  // Security note (AUD-36): BroadcastChannel is same-origin by W3C spec.
  // A page on any other origin cannot post to this channel, so no explicit
  // origin check is needed here. The residual risk — an XSS payload on this
  // same origin posting 'logout' to force tab logout — is a
  // denial-of-availability of the current session only (no credential
  // exposure). Defense-in-depth against XSS is provided by the Content
  // Security Policy enforced at the reverse proxy layer (see AUD-22).
  useEffect(() => {
    const channel = new BroadcastChannel('auth_sync');
    const handleMessage = (e: MessageEvent) => {
      if (e.data === 'logout') {
        window.dispatchEvent(new CustomEvent('auth:logout'));
      }
    };
    channel.addEventListener('message', handleMessage);
    return () => {
      channel.removeEventListener('message', handleMessage);
      channel.close();
    };
  }, []);

  // ── 3. Proactive token refresh ─────────────────────────────────────────────
  // After login or any successful refresh, schedule a silent refresh
  // PROACTIVE_REFRESH_LEAD_MS before the access token expires.
  const refreshAuth = useCallback(async (): Promise<boolean> => {
    try {
      const success = await authApi.refreshToken();

      if (success) {
        const userData = await authApi.getCurrentUser();
        setUser(userData);
      } else {
        setUser(null);
      }

      return success;
    } catch {
      setUser(null);
      return false;
    }
  }, []);

  useEffect(() => {
    if (!user) return;

    const token = tokenStorage.getAccessToken();
    const expiryMs = token ? getTokenExpiryMs(token) : null;
    if (!expiryMs) return;

    const msUntilRefresh = expiryMs - Date.now() - PROACTIVE_REFRESH_LEAD_MS;
    if (msUntilRefresh <= 0) {
      // Token is already close to expiry — refresh immediately
      refreshAuth();
      return;
    }

    const timer = setTimeout(refreshAuth, msUntilRefresh);
    return () => clearTimeout(timer);
  }, [user, refreshAuth]);

  // ── 4. Inactivity auto-logout ──────────────────────────────────────────────
  const handleInactivityLogout = useCallback(async () => {
    setShowInactivityWarning(false);
    try {
      await authApi.logout();
    } catch {
      // ignore — tokens are cleared regardless
    }
    setUser(null);
  }, []);

  const { resetTimer } = useInactivityLogout({
    timeoutMs: INACTIVITY_TIMEOUT_MS,
    warningMs: INACTIVITY_WARNING_MS,
    onWarning: (secondsLeft: number) => {
      setShowInactivityWarning(true);
      setWarningCountdown(secondsLeft);
    },
    onLogout: handleInactivityLogout,
    enabled: isAuthenticated,
  });

  const handleStayLoggedIn = useCallback(() => {
    setShowInactivityWarning(false);
    resetTimer();
  }, [resetTimer]);

  // ── Auth actions ───────────────────────────────────────────────────────────
  const login = useCallback(async (credentials: LoginCredentials) => {
    setIsLoading(true);
    setError(null);

    try {
      const userData = await authApi.login(credentials);
      setUser(userData);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Login failed';
      setError(message);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const logout = useCallback(async () => {
    setIsLoading(true);

    try {
      await authApi.logout();
    } finally {
      setUser(null);
      setIsLoading(false);
    }
  }, []);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const value: AuthContextType = {
    user,
    isAuthenticated,
    isLoading,
    error,
    login,
    logout,
    refreshAuth,
    clearError,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
      {isAuthenticated && showInactivityWarning && (
        <InactivityWarningModal
          secondsRemaining={warningCountdown}
          onStayLoggedIn={handleStayLoggedIn}
        />
      )}
    </AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components -- context + hook co-export is intentional; a hook-only edit falls back to a full reload
export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }

  return context;
}
