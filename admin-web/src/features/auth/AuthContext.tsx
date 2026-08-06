import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

type AuthState = {
  token: string | null;
  role: string | null;
  setSession: (token: string, role: string) => void;
  logout: () => void;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem("iq_token"));
  const [role, setRole] = useState<string | null>(() => localStorage.getItem("iq_role"));

  const value = useMemo<AuthState>(
    () => ({
      token,
      role,
      setSession: (t, r) => {
        localStorage.setItem("iq_token", t);
        localStorage.setItem("iq_role", r);
        setToken(t);
        setRole(r);
      },
      logout: () => {
        localStorage.removeItem("iq_token");
        localStorage.removeItem("iq_role");
        setToken(null);
        setRole(null);
      },
    }),
    [token, role],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
