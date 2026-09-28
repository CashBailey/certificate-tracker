/**
 * Authentication API functions.
 */

import { API_URL, apiFetch, requestAccessTokenRefresh, tokenStorage } from './client';
import type { LoginCredentials, TokenResponse, User } from '../types/auth';

function extractErrorMessage(errorData: unknown, fallback: string): string {
  if (!errorData || typeof errorData !== 'object') {
    return fallback;
  }

  const detail = (errorData as { detail?: unknown }).detail;
  if (typeof detail === 'string' && detail.trim()) {
    return detail;
  }

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === 'string') return item;
        if (item && typeof item === 'object' && 'msg' in item && typeof item.msg === 'string') {
          return item.msg;
        }
        return '';
      })
      .filter(Boolean);

    if (messages.length > 0) {
      return messages.join(' ');
    }
  }

  return fallback;
}

/**
 * Login with email and password.
 */
export async function login(credentials: LoginCredentials): Promise<User> {
  // Login endpoint doesn't need auth header
  const response = await fetch(`${API_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(credentials),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(extractErrorMessage(errorData, 'Login failed'));
  }

  const tokens: TokenResponse = await response.json();
  tokenStorage.setAccessToken(tokens.access_token);

  // Fetch user info
  return getCurrentUser();
}

/**
 * Get current authenticated user.
 */
export async function getCurrentUser(): Promise<User> {
  return apiFetch<User>('/auth/me');
}

/**
 * Refresh the access token.
 */
export async function refreshToken(): Promise<boolean> {
  return requestAccessTokenRefresh();
}

/**
 * Logout the current user.
 */
export async function logout(): Promise<void> {
  try {
    await apiFetch('/auth/logout', { method: 'POST' });
  } catch {
    // The authenticated revocation path may fail after the access token or DB
    // is unavailable. Still ask the server to expire the httpOnly cookie so a
    // later page load cannot silently restore the browser session.
    await fetch(`${API_URL}/auth/clear-session`, {
      method: 'POST',
      credentials: 'include',
    }).catch(() => undefined);
  } finally {
    tokenStorage.clearTokens();
  }
}

/**
 * Request a password reset email for the given address.
 * Always resolves (server never reveals whether the address is registered).
 */
export async function forgotPassword(email: string): Promise<void> {
  await apiFetch('/auth/forgot-password', {
    method: 'POST',
    body: JSON.stringify({ email }),
  });
}

/**
 * Complete a password reset using the one-time token from the reset email.
 */
export async function resetPassword(token: string, newPassword: string): Promise<void> {
  await apiFetch('/auth/reset-password', {
    method: 'POST',
    body: JSON.stringify({ token, new_password: newPassword }),
  });
}
