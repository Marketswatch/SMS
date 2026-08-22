import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

const AppCtx = createContext(null);

const thisMonth = () => new Date().toISOString().slice(0, 7);

export function AppProvider({ children }) {
  const { user } = useAuth();
  const [properties, setProperties] = useState([]);
  const [propertyId, setPropertyId] = useState(localStorage.getItem("sh_prop") || "");
  const [periods, setPeriods] = useState([]);
  const [month, setMonth] = useState(thisMonth());
  const [tick, setTick] = useState(0);

  const bump = useCallback(() => setTick((t) => t + 1), []);

  const loadProperties = useCallback(async () => {
    const { data } = await api.get("/properties");
    setProperties(data);
    setPropertyId((cur) => (cur && data.some((p) => p.id === cur) ? cur : data[0]?.id || ""));
  }, []);

  useEffect(() => {
    if (user) loadProperties();
  }, [user, loadProperties, tick]);

  useEffect(() => {
    if (!propertyId) return;
    localStorage.setItem("sh_prop", propertyId);
    api.get("/periods", { params: { property_id: propertyId } }).then(({ data }) => {
      setPeriods(data);
      setMonth((m) => (data.some((p) => p.month === m) ? m : data[data.length - 1]?.month || thisMonth()));
    });
  }, [propertyId, tick]);

  const property = properties.find((p) => p.id === propertyId) || null;
  const period = periods.find((p) => p.month === month) || null;
  const locked = period?.status === "locked";

  return (
    <AppCtx.Provider
      value={{ properties, property, propertyId, setPropertyId, periods, month, setMonth, locked, bump, loadProperties }}
    >
      {children}
    </AppCtx.Provider>
  );
}

export const useApp = () => useContext(AppCtx);
