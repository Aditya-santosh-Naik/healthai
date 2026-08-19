import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api, clearToken, getToken, setToken } from "@/api/client";
import type { ProfileOut, TokenResponse } from "@/api/types";

interface AuthState {
  ready: boolean;
  authenticated: boolean;
  profile: ProfileOut | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshProfile: () => Promise<ProfileOut | null>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [profile, setProfile] = useState<ProfileOut | null>(null);

  /** 409 means "authenticated but onboarding not finished" -- not an error. */
  const refreshProfile = useCallback(async (): Promise<ProfileOut | null> => {
    try {
      const p = await api.get<ProfileOut>("/api/profile");
      setProfile(p);
      return p;
    } catch {
      setProfile(null);
      return null;
    }
  }, []);

  useEffect(() => {
    async function restore() {
      if (!getToken()) {
        setReady(true);
        return;
      }
      try {
        await api.get("/api/auth/me");
        setAuthenticated(true);
        await refreshProfile();
      } catch {
        clearToken();
        setAuthenticated(false);
      } finally {
        setReady(true);
      }
    }
    void restore();
  }, [refreshProfile]);

  const login = useCallback(
    async (email: string, password: string) => {
      const res = await api.post<TokenResponse>("/api/auth/login", { email, password });
      setToken(res.access_token);
      setAuthenticated(true);
      await refreshProfile();
    },
    [refreshProfile],
  );

  const register = useCallback(async (email: string, password: string) => {
    const res = await api.post<TokenResponse>("/api/auth/register", { email, password });
    setToken(res.access_token);
    setAuthenticated(true);
    setProfile(null);
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setAuthenticated(false);
    setProfile(null);
  }, []);

  const value = useMemo(
    () => ({ ready, authenticated, profile, login, register, logout, refreshProfile }),
    [ready, authenticated, profile, login, register, logout, refreshProfile],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
