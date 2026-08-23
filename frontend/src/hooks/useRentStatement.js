import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";

export function useRentStatement(month, tick = 0) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!month) return;
    setLoading(true);
    try {
      const res = await api.get("/rentals/statement", { params: { month } });
      setData(res.data);
    } finally {
      setLoading(false);
    }
  }, [month]);

  useEffect(() => { load(); }, [load, tick]);
  return { stmt: data, loading, reload: load };
}

export function useCategories() {
  const [cats, setCats] = useState([]);
  const load = useCallback(async () => {
    const { data } = await api.get("/rentals/categories");
    setCats(data);
  }, []);
  useEffect(() => { load(); }, [load]);

  const add = async (name) => {
    const { data } = await api.post("/rentals/categories", { name });
    await load();
    return data;
  };
  return { cats, addCategory: add, reloadCategories: load };
}
