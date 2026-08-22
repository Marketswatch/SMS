import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";

export function useStatement(propertyId, month, tick = 0) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!propertyId || !month) return;
    setLoading(true);
    try {
      const res = await api.get("/statement", { params: { property_id: propertyId, month } });
      setData(res.data);
    } finally {
      setLoading(false);
    }
  }, [propertyId, month]);

  useEffect(() => {
    load();
  }, [load, tick]);

  return { statement: data, loading, reload: load };
}
