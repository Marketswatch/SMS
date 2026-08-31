import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";

import { FLOORS } from "@/lib/format";

const floorRank = (f) => {
  const i = FLOORS.findIndex((x) => x.toLowerCase() === String(f || "").trim().toLowerCase());
  return i === -1 ? (f ? 90 : 99) : i;
};

const flatRank = (n) => {
  const digits = String(n ?? "").replace(/\D/g, "");
  return digits ? Number(digits) : 0;
};

// Default order everywhere: floor (ground upward), then flat number.
export const floorFlatCompare = (a, b) => {
  const fa = floorRank(a.floor), fb = floorRank(b.floor);
  if (fa !== fb) return fa - fb;
  const na = flatRank(a.flat_number ?? a.number), nb = flatRank(b.flat_number ?? b.number);
  if (na !== nb) return na - nb;
  return String(a.flat_number ?? a.number ?? "").localeCompare(String(b.flat_number ?? b.number ?? ""));
};

/**
 * Click-to-sort for any report table.
 * `accessors` maps a column key to a value getter; "floor" sorts floor -> flat by default.
 */
export const useSort = (rows, accessors, initialKey = "floor") => {
  const [sort, setSort] = useState({ key: initialKey, dir: "asc" });

  const sorted = useMemo(() => {
    const list = [...(rows || [])];
    if (sort.key === "floor") {
      list.sort(floorFlatCompare);
    } else {
      const get = accessors[sort.key] || ((r) => r[sort.key]);
      list.sort((a, b) => {
        const va = get(a), vb = get(b);
        if (typeof va === "number" && typeof vb === "number") return va - vb;
        return String(va ?? "").localeCompare(String(vb ?? ""), undefined, { numeric: true });
      });
    }
    if (sort.dir === "desc") list.reverse();
    return list;
  }, [rows, sort, accessors]);

  const toggle = (key) =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" }));

  return { sorted, sort, toggle };
};

export const SortTh = ({ label, sortKey, sort, toggle, align = "left", className = "", testId }) => {
  const active = sort.key === sortKey;
  const Icon = !active ? ChevronsUpDown : sort.dir === "asc" ? ArrowUp : ArrowDown;
  return (
    <th className={`${align === "right" ? "text-right" : "text-left"} ${className}`}>
      <button type="button" onClick={() => toggle(sortKey)}
              data-testid={testId || `sort-${sortKey}`}
              title={`Sort by ${label}`}
              className={`inline-flex items-center gap-1 hover:text-slate-900 transition-colors ${
                align === "right" ? "flex-row-reverse" : ""} ${active ? "text-slate-900" : ""}`}>
        <span>{label}</span>
        <Icon className={`w-3 h-3 shrink-0 ${active ? "opacity-90" : "opacity-30"}`} />
      </button>
    </th>
  );
};
