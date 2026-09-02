import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, tokenStore } from "@/lib/api";
import type { PatientProfile, User } from "@/lib/types";

interface AuthState {
  user: User | null;
  profile: PatientProfile | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [profile, setProfile] = useState<PatientProfile | null>(null);
  const [loading, setLoading] = useState(true);

  const loadMe = useCallback(async () => {
    try {
      const me = await api.auth.me();
      setUser(me.user);
      setProfile(me.patient_profile);
    } catch {
      tokenStore.clear();
      setUser(null);
      setProfile(null);
    } finally {
      setLoading(false);
    }
  }, []);

  // Restore the session on load so a refresh does not log the user out.
  useEffect(() => {
    if (tokenStore.access) void loadMe();
    else setLoading(false);
  }, [loadMe]);

  const login = useCallback(async (email: string, password: string) => {
    tokenStore.set(await api.auth.login(email, password));
    setLoading(true);
    await loadMe();
  }, [loadMe]);

  const register = useCallback(async (email: string, password: string, fullName: string) => {
    tokenStore.set(await api.auth.register(email, password, fullName));
    setLoading(true);
    await loadMe();
  }, [loadMe]);

  const logout = useCallback(() => {
    tokenStore.clear();
    setUser(null);
    setProfile(null);
  }, []);

  const value = useMemo(
    () => ({ user, profile, loading, login, register, logout }),
    [user, profile, loading, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
