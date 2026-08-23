const digits = (p) => String(p || "").replace(/\D/g, "");

export const waNumber = (phone) => {
  const d = digits(phone);
  if (!d) return "";
  return d.length === 10 ? `91${d}` : d;
};

export const duesMessage = ({ building, flat, monthName, row }) => {
  const fmt = (n) => `Rs.${Math.abs(Number(n || 0)).toFixed(2)}`;
  const lines = [
    `${building} - Flat ${flat} - ${monthName}`,
    `Water: ${fmt(row.water_cost)}`,
    `Recurring share: ${fmt(row.recurring_share)}`,
    `Maintenance share: ${fmt(row.maintenance_share)}`,
    `Total payable: ${fmt(row.base_cost)}`,
  ];
  if (Number(row.contributions)) lines.push(`Amount you fronted: ${fmt(row.contributions)}`);
  if (Number(row.carry_in)) lines.push(`Carried over: ${fmt(row.carry_in)}`);
  if (Number(row.received)) lines.push(`Paid so far: ${fmt(row.received)}`);
  lines.push(
    Number(row.net) > 0
      ? `Balance payable: ${fmt(row.net)}`
      : Number(row.net) < 0
        ? `Amount owed to you: ${fmt(row.net)}`
        : "Balance: settled"
  );
  return lines.join("\n");
};

export const openWhatsApp = (phone, message) => {
  const n = waNumber(phone);
  window.open(`https://wa.me/${n}?text=${encodeURIComponent(message)}`, "_blank", "noopener");
};

export const openSms = (phone, message) => {
  window.location.href = `sms:${digits(phone)}?&body=${encodeURIComponent(message)}`;
};
