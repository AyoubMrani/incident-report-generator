// Auth state for the app: who is signed in, what they may do, and the
// login/logout actions.
//
// The provider resolves one of three states before rendering children:
//   - auth disabled  -> a synthetic local user, so the whole app works offline
//                       exactly as it did before authentication existed;
//   - signed in      -> the real user from /api/me;
//   - signed out     -> null, and the shell shows the login screen.
//
// Permissions come from /api/me rather than from decoding the token in the
// browser. The backend is the authority on what a role may do, and duplicating
// that logic here would let the two disagree — with the UI's version being the
// one that is trivially bypassed.

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import {
  fetchMe,
  handleRedirectCallback,
  hasSession,
  loadAuthConfig,
  login as startLogin,
  logout as startLogout,
  type UserInfo,
} from './oidc';

interface AuthState {
  user: UserInfo | null;
  loading: boolean;
  error: string | null;
  authEnabled: boolean;
  login: () => void;
  logout: () => void;
  /** True when the user may create or edit reports (analyst/admin). */
  canWrite: boolean;
  isAdmin: boolean;
}

const LOCAL_USER: UserInfo = {
  id: 'local',
  username: 'local',
  email: '',
  display_name: 'Local user',
  roles: [],
  authenticated: false,
  is_admin: true,
  can_write: true,
};

const AuthCtx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [authEnabled, setAuthEnabled] = useState(false);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const cfg = await loadAuthConfig();
        if (cancelled) return;
        setAuthEnabled(cfg.enabled);

        if (!cfg.enabled) {
          // AUTH_DISABLED on the backend: everything stays usable, which is
          // what makes local development and the test suite work unchanged.
          setUser(LOCAL_USER);
          return;
        }

        // Consume a redirect if we are coming back from Keycloak.
        const returned = await handleRedirectCallback();
        if (cancelled) return;

        if (returned || hasSession()) {
          setUser(await fetchMe());
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Sign-in failed');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(() => {
    setError(null);
    void startLogin();
  }, []);

  const logout = useCallback(() => {
    setUser(null);
    void startLogout();
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      error,
      authEnabled,
      login,
      logout,
      canWrite: user?.can_write ?? false,
      isAdmin: user?.is_admin ?? false,
    }),
    [user, loading, error, authEnabled, login, logout],
  );

  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
