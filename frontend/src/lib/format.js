export const money = (n) =>
  (n < 0 ? "-" : "") +
  "₹" +
  Math.abs(Number(n || 0)).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const plainAmt = (n) =>
  "Rs." + Math.abs(Number(n || 0)).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const litres = (n) =>
  Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 }) + " L";

export const num = (n, d = 2) =>
  Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d });

// Every date shown anywhere in SocietyHub is DD-MM-YYYY.
export const dmy = (d) => {
  if (!d) return "—";
  const s = String(d).slice(0, 10);
  const [y, m, dd] = s.split("-");
  return y && m && dd ? `${dd}-${m}-${y}` : s;
};

export const monthLabel = (m) => {
  if (!m) return "";
  const [y, mm] = m.split("-");
  return new Date(Number(y), Number(mm) - 1, 1).toLocaleString("en-IN", { month: "long", year: "numeric" });
};

export const FLOORS = ["Ground", "First", "Second", "Third", "Fourth", "Fifth"];

export const CHARGE_TYPES = [
  { value: "cleaning", label: "Cleaning / Maid", person: true },
  { value: "sweeper", label: "Sweeper", person: true },
  { value: "security", label: "Building Security", person: true },
  { value: "electricity", label: "Common Electricity", person: false },
  { value: "misc", label: "Miscellaneous", person: false },
];
