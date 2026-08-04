// OIDC Authorization Code flow with PKCE, implemented directly against the
// browser's crypto API rather than pulling in an OIDC library.
//
// Why by hand: the flow is ~150 lines, the alternatives (oidc-client-ts,
// keycloak-js) are 40-90 KB for the same three requests, and keycloak-js in
// particular hides the redirect handling that is the part worth being able to
// read when a login loop needs debugging.
//
// PKCE (S256) is used because this is a public client — a SPA cannot keep a
// client secret, so the code verifier is what stops an intercepted
// authorization code from being redeemed by anyone else.
//
// Tokens live in memory, with only the refresh token in sessionStorage:
//   - localStorage would survive tab close and is readable by any XSS on the
//     origin for as long as the token is valid;
//   - sessionStorage is scoped to the tab and cleared when it closes, which
//     bounds the exposure without forcing a fresh login on every reload.
// A cookie-based BFF would be stronger still, but needs a server-side session
// store this local-only stack deliberately does not have.

export interface AuthConfig {
  enabled: boolean;
  issuer?: string;
  client_id?: string;
}

export interface UserInfo {
  id: string;
  username: string;
  email: string;
  display_name: string;
  roles: string[];
  authenticated: boolean;
  is_admin: boolean;
  can_write: boolean;
}

interface TokenSet {
  accessToken: string;
  refreshToken?: string;
  // Absolute epoch ms. Storing the deadline rather than expires_in means a
  // backgrounded tab cannot think a long-expired token is still fresh.
  expiresAt: number;
}

const VERIFIER_KEY = 'ntt.pkce.verifier';
const STATE_KEY = 'ntt.pkce.state';
const REFRESH_KEY = 'ntt.auth.refresh';
const RETURN_KEY = 'ntt.auth.returnTo';

// Refresh this far before actual expiry, so an in-flight request is never
// issued with a token that expires while it is on the wire.
const REFRESH_SKEW_MS = 60_000;

let tokens: TokenSet | null = null;
let config: AuthConfig | null = null;
let refreshInFlight: Promise<string | null> | null = null;

// ── PKCE helpers ──────────────────────────────────────────────────────────────

function randomString(bytes = 32): string {
  const buf = new Uint8Array(bytes);
  crypto.getRandomValues(buf);
  return base64url(buf);
}

function base64url(bytes: Uint8Array | ArrayBuffer): string {
  const view = bytes instanceof ArrayBuffer ? new Uint8Array(bytes) : bytes;
  let binary = '';
  view.forEach((b) => (binary += String.fromCharCode(b)));
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

async function challengeFor(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
  return base64url(digest);
}

// ── configuration ─────────────────────────────────────────────────────────────

export async function loadAuthConfig(): Promise<AuthConfig> {
  if (config) return config;
  try {
    const res = await fetch('/api/auth/config');
    config = res.ok ? await res.json() : { enabled: false };
  } catch {
    // Backend unreachable: treat as auth-off so the UI can render an error
    // state instead of a blank page waiting on a login it cannot start.
    config = { enabled: false };
  }
  return config!;
}

const endpoint = (path: string) =>
  `${config!.issuer!.replace(/\/$/, '')}/protocol/openid-connect/${path}`;

// ── login / logout ────────────────────────────────────────────────────────────

export async function login(returnTo?: string): Promise<void> {
  const cfg = await loadAuthConfig();
  if (!cfg.enabled) return;

  const verifier = randomString();
  const state = randomString(16);
  sessionStorage.setItem(VERIFIER_KEY, verifier);
  sessionStorage.setItem(STATE_KEY, state);
  sessionStorage.setItem(RETURN_KEY, returnTo ?? window.location.pathname + window.location.search);

  const params = new URLSearchParams({
    client_id: cfg.client_id!,
    redirect_uri: redirectUri(),
    response_type: 'code',
    scope: 'openid profile email',
    state,
    code_challenge: await challengeFor(verifier),
    code_challenge_method: 'S256',
  });
  window.location.assign(`${endpoint('auth')}?${params}`);
}

export async function logout(): Promise<void> {
  const cfg = await loadAuthConfig();
  const refresh = tokens?.refreshToken ?? sessionStorage.getItem(REFRESH_KEY);
  clearTokens();

  if (!cfg.enabled) {
    window.location.assign('/');
    return;
  }
  // End the Keycloak session too. Without this, "log out" only forgets the
  // token locally and the next login silently reuses the existing SSO session
  // — which looks exactly like logout being broken.
  const params = new URLSearchParams({
    client_id: cfg.client_id!,
    post_logout_redirect_uri: window.location.origin + '/',
  });
  if (refresh) params.set('refresh_token', refresh);
  window.location.assign(`${endpoint('logout')}?${params}`);
}

function redirectUri(): string {
  return window.location.origin + '/';
}

// ── redirect handling ─────────────────────────────────────────────────────────

/**
 * Complete a login if the current URL carries an authorization code.
 * Returns true when a redirect was consumed, so the caller knows to re-check
 * the session rather than immediately bouncing to login again.
 */
export async function handleRedirectCallback(): Promise<boolean> {
  const url = new URL(window.location.href);
  const code = url.searchParams.get('code');
  const state = url.searchParams.get('state');
  const error = url.searchParams.get('error');

  if (error) {
    stripAuthParams();
    throw new Error(url.searchParams.get('error_description') || error);
  }
  if (!code) return false;

  const expectedState = sessionStorage.getItem(STATE_KEY);
  const verifier = sessionStorage.getItem(VERIFIER_KEY);
  sessionStorage.removeItem(STATE_KEY);
  sessionStorage.removeItem(VERIFIER_KEY);

  // State mismatch means this redirect did not originate from our login —
  // the CSRF check the flow exists to provide. Fail rather than exchange it.
  if (!state || state !== expectedState || !verifier) {
    stripAuthParams();
    throw new Error('Login state mismatch. Please try signing in again.');
  }

  await loadAuthConfig();
  const res = await fetch(endpoint('token'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'authorization_code',
      client_id: config!.client_id!,
      code,
      redirect_uri: redirectUri(),
      code_verifier: verifier,
    }),
  });

  stripAuthParams();
  if (!res.ok) throw new Error('Could not complete sign-in.');
  storeTokens(await res.json());

  const returnTo = sessionStorage.getItem(RETURN_KEY);
  sessionStorage.removeItem(RETURN_KEY);
  if (returnTo && returnTo !== window.location.pathname) {
    window.history.replaceState({}, '', returnTo);
  }
  return true;
}

function stripAuthParams(): void {
  // Keep the code out of history and out of any URL the user might copy.
  const url = new URL(window.location.href);
  ['code', 'state', 'session_state', 'iss', 'error', 'error_description'].forEach((p) =>
    url.searchParams.delete(p),
  );
  window.history.replaceState({}, '', url.pathname + url.search);
}

// ── token lifecycle ───────────────────────────────────────────────────────────

function storeTokens(payload: any): void {
  tokens = {
    accessToken: payload.access_token,
    refreshToken: payload.refresh_token,
    expiresAt: Date.now() + (payload.expires_in ?? 300) * 1000,
  };
  if (payload.refresh_token) sessionStorage.setItem(REFRESH_KEY, payload.refresh_token);
}

function clearTokens(): void {
  tokens = null;
  sessionStorage.removeItem(REFRESH_KEY);
}

/** A valid access token, refreshing if needed. Null when not signed in. */
export async function getAccessToken(): Promise<string | null> {
  const cfg = await loadAuthConfig();
  if (!cfg.enabled) return null;

  if (tokens && Date.now() < tokens.expiresAt - REFRESH_SKEW_MS) {
    return tokens.accessToken;
  }
  // Collapse concurrent refreshes: several requests firing at once must not
  // each redeem the refresh token, since Keycloak rotates it and all but the
  // first would fail and log the user out.
  if (!refreshInFlight) {
    refreshInFlight = refreshTokens().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

async function refreshTokens(): Promise<string | null> {
  const refresh = tokens?.refreshToken ?? sessionStorage.getItem(REFRESH_KEY);
  if (!refresh) return null;

  try {
    const res = await fetch(endpoint('token'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        grant_type: 'refresh_token',
        client_id: config!.client_id!,
        refresh_token: refresh,
      }),
    });
    if (!res.ok) {
      clearTokens();
      return null;
    }
    storeTokens(await res.json());
    return tokens!.accessToken;
  } catch {
    clearTokens();
    return null;
  }
}

export function hasSession(): boolean {
  return tokens !== null || sessionStorage.getItem(REFRESH_KEY) !== null;
}

// ── current user ──────────────────────────────────────────────────────────────

export async function fetchMe(): Promise<UserInfo | null> {
  const res = await authFetch('/api/me');
  if (!res.ok) return null;
  return res.json();
}

/**
 * `fetch` with the bearer token attached, retrying once after a refresh.
 *
 * The retry matters: a token can expire between the skew check and the server
 * validating it, and without this the user sees a spurious failure for a
 * session that is still perfectly valid.
 */
export async function authFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const token = await getAccessToken();
  const headers = new Headers(init.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);

  const res = await fetch(input, { ...init, headers });
  if (res.status !== 401 || !token) return res;

  const refreshed = await (refreshInFlight ?? refreshTokens());
  if (!refreshed) return res;
  headers.set('Authorization', `Bearer ${refreshed}`);
  return fetch(input, { ...init, headers });
}
