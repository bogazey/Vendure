import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { api } from "../services/api";
import type { AccountOut } from "../types/commercial";
import { track } from "../lib/analytics";

interface AuthContextValue {
  account: AccountOut | null;
  loading: boolean;
  /** Re-fetches /api/account - call after anything that can change plan,
   * usage, or subscription state (checkout return, admin grant, etc). */
  refresh: () => Promise<void>;
  login: (email: string, password: string, rememberMe?: boolean) => Promise<void>;
  signup: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [account, setAccount] = useState<AccountOut | null>(null);
  const [loading, setLoading] = useState(true);
  // StrictMode (dev only) invokes effects twice - without this guard the
  // bootstrap below would fire two concurrent /api/account requests on
  // first mount. The ref survives that double-invoke (only the effect body
  // re-runs, not the component's state), so the second pass is a no-op.
  const bootstrapped = useRef(false);

  const refresh = useCallback(async () => {
    try {
      // request()'s own 401-handling (see services/api.ts) transparently
      // retries this via /api/auth/refresh first if the short-lived access
      // token has simply expired - so this only actually clears `account`
      // when there is truly no valid session left (expired refresh token,
      // logged out, revoked, disabled account, etc).
      const acc = await api.getAccount();
      setAccount(acc);
    } catch {
      setAccount(null);
    }
  }, []);

  useEffect(() => {
    if (bootstrapped.current) return;
    bootstrapped.current = true;
    refresh().finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = useCallback(async (email: string, password: string, rememberMe: boolean = false) => {
    await api.login(email, password, rememberMe);
    await refresh();
    track("login");
  }, [refresh]);

  const signup = useCallback(async (email: string, password: string) => {
    await api.signup(email, password);
    await refresh();
    track("signup");
  }, [refresh]);

  const logout = useCallback(async () => {
    await api.logout().catch(() => undefined);
    setAccount(null);
  }, []);

  return (
    <AuthContext.Provider value={{ account, loading, refresh, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
