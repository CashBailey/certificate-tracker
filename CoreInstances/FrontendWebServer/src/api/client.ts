/**
 * API client with automatic token handling.
 */

export const API_URL = import.meta.env.VITE_API_URL || '/api';

function extractApiErrorMessage(errorData: unknown, fallback: string): string {
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

  const message = (errorData as { message?: unknown }).message;
  if (typeof message === 'string' && message.trim()) {
    return message;
  }

  return fallback;
}

// In-memory access token (CRIT-04: never persisted to storage)
let _accessToken: string | null = null;

// Token management functions
export const tokenStorage = {
  getAccessToken: (): string | null => _accessToken,

  setAccessToken: (token: string): void => {
    _accessToken = token;
  },

  // Backward-compat stub: ignores refresh token (now in httpOnly cookie)
  setTokens: (accessToken: string, _refreshToken?: string): void => {
    _accessToken = accessToken;
  },

  // Stub: refresh token is in httpOnly cookie, invisible to JS
  getRefreshToken: (): null => null,

  clearTokens: (): void => {
    const hadToken = _accessToken !== null;
    _accessToken = null;
    // Notify other tabs that this session has ended.
    // Only broadcast when a token was actually cleared to avoid a feedback
    // loop: clearTokens → BroadcastChannel → auth:logout → clearTokens …
    if (hadToken) {
      try {
        const ch = new BroadcastChannel('auth_sync');
        ch.postMessage('logout');
        ch.close();
      } catch {
        // BroadcastChannel not supported — no cross-tab sync in this browser
      }
    }
  },
};

/**
 * Decode a JWT and return the expiry time in milliseconds (Date.now() scale).
 * Does not verify the signature — used only for scheduling client-side refresh.
 *
 * IMPORTANT: Never use this function for access-control decisions. An attacker
 * with XSS could craft a token with an arbitrary `exp` value; this function
 * would return it faithfully. All authorization is
 * enforced server-side on every request. This function's return value is only
 * safe to use for UX timing (e.g., "refresh the token N seconds before expiry").
 */
export function getTokenExpiryMs(token: string): number | null {
  try {
    const base64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    const payload = JSON.parse(atob(base64));
    return typeof payload.exp === 'number' ? payload.exp * 1000 : null;
  } catch {
    return null;
  }
}

// Refresh token promise for deduplication
let refreshPromise: Promise<boolean> | null = null;

/**
 * Attempt to refresh the access token.
 * Returns true if successful, false otherwise.
 */
async function refreshAccessToken(): Promise<boolean> {
  try {
    const response = await fetch(`${API_URL}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
    });

    if (!response.ok) {
      tokenStorage.clearTokens();
      return false;
    }

    const data = await response.json();
    tokenStorage.setAccessToken(data.access_token);
    return true;
  } catch {
    tokenStorage.clearTokens();
    return false;
  }
}

/**
 * Shared refresh entrypoint for the whole tab.
 *
 * Auth bootstrap/proactive refresh and 401-retry paths must all come through
 * the same promise so we do not fan out multiple /auth/refresh calls from one
 * tab when a timer, a page bootstrap, and an in-flight API request overlap.
 */
export function requestAccessTokenRefresh(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = refreshAccessToken().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

/**
 * Auth-aware fetch that returns the raw Response. On 401 it transparently
 * refreshes the access token (deduplicated across concurrent callers) and
 * retries once. Use for non-JSON endpoints — file downloads, blob responses,
 * anything where apiFetch's automatic JSON parsing is wrong.
 *
 * Throws on refresh failure (dispatches auth:logout) so the caller doesn't
 * need to handle 401 itself.
 */
export async function fetchWithAuthRetry(
  endpoint: string,
  options: RequestInit = {},
): Promise<Response> {
  const url = `${API_URL}${endpoint}`;
  const buildHeaders = (): HeadersInit => {
    const t = tokenStorage.getAccessToken();
    const h: Record<string, string> = { ...(options.headers as Record<string, string>) };
    if (t) h['Authorization'] = `Bearer ${t}`;
    return h;
  };

  let response = await fetch(url, { ...options, headers: buildHeaders(), credentials: 'include' });

  if (response.status === 401) {
    const refreshed = await requestAccessTokenRefresh();
    if (refreshed) {
      response = await fetch(url, { ...options, headers: buildHeaders(), credentials: 'include' });
    } else {
      window.dispatchEvent(new CustomEvent('auth:logout'));
      throw new Error('Session expired. Please log in again.');
    }
  }

  return response;
}

/**
 * Main API fetch function with automatic token handling.
 */
export async function apiFetch<T>(
  endpoint: string,
  options: RequestInit = {},
): Promise<T> {
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  const response = await fetchWithAuthRetry(endpoint, { ...options, headers });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(extractApiErrorMessage(errorData, `HTTP error ${response.status}`));
  }

  // Some successful endpoints intentionally return no body (e.g., HTTP 204).
  const responseText = await response.text();
  if (!responseText.trim()) {
    return undefined as T;
  }

  return JSON.parse(responseText) as T;
}
