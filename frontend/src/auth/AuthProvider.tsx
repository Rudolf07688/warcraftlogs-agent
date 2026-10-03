import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
  getMe,
  login as apiLogin,
  logout as apiLogout,
  setCsrfToken,
} from "../api/restClient";
import type { Identity } from "../types";
import { AuthContext } from "./useAuth";

/**
 * Holds the authenticated identity + in-memory CSRF token (feature 006, US2).
 *
 * On mount it calls /api/auth/me to rehydrate the session after a reload (the CSRF token
 * is HMAC-derived server-side, so it's recovered here too). The token lives only in
 * memory — never localStorage — and is pushed into the REST client for unsafe requests.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [loading, setLoading] = useState(true);

  const apply = useCallback((id: Identity | null) => {
    setIdentity(id);
    setCsrfToken(id?.csrf_token ?? null);
  }, []);

  const refresh = useCallback(async () => {
    try {
      apply(await getMe());
    } catch {
      apply(null); // 401 or network error → treat as signed out
    } finally {
      setLoading(false);
    }
  }, [apply]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(
    async (email: string, password: string) => {
      apply(await apiLogin(email, password));
    },
    [apply],
  );

  const logout = useCallback(async () => {
    try {
      await apiLogout();
    } finally {
      apply(null);
    }
  }, [apply]);

  return (
    <AuthContext.Provider value={{ identity, loading, login, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}
