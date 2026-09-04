import { createContext, useCallback, useContext, useEffect, useState } from "react";
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
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [account, setAccount] = useState<AccountOut | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const acc = await api.getAccount();
      setAccount(acc);
    } catch {
      setAccount(null);
    }
  }, []);

  useEffect(() => {
    refresh().finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    await api.login(email, password);
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
