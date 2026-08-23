export const MODES = [
  { value: "cash", label: "Cash" },
  { value: "upi", label: "UPI" },
  { value: "bank", label: "Bank Transfer" },
];

export const modeLabel = (v) => MODES.find((m) => m.value === v)?.label || v || "—";
