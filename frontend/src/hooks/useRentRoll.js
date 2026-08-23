import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";

export function useRentRoll(month, tick = 0) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!month) return;
    setLoading(true);
    try {
      const res = await api.get("/rentals/rent-roll", { params: { month } });
      setData(res.data);
    } finally {
      setLoading(false);
    }
  }, [month]);

  useEffect(() => { load(); }, [load, tick]);
  return { roll: data, loading, reload: load };
}
