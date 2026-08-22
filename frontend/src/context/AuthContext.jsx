import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // null = checking, false = anon

  const check = useCallback(async () => {
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
    } catch {
      setUser(false);
    }
  }, []);

  useEffect(() => {
    check();
  }, [check]);

  const login = async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    if (data.access_token) localStorage.setItem("sh_token", data.access_token);
    setUser(data);
    return data;
  };

  const logout = async () => {
    try {
      await api.post("/auth/logout");
    } catch {}
    localStorage.removeItem("sh_token");
    setUser(false);
  };

  const isAdmin = user && (user.role === "admin" || user.role === "super_admin");

  return <AuthCtx.Provider value={{ user, login, logout, isAdmin, refresh: check }}>{children}</AuthCtx.Provider>;
}

export const useAuth = () => useContext(AuthCtx);
