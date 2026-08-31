import { NetBadge } from "@/components/Common";
import { money, dmy } from "@/lib/format";
import { useSort, SortTh } from "@/lib/sort";

const chip = (r) => {
  const settledWithoutPayment = r.payment_status === "paid" && !r.last_paid_on;
  const label = settledWithoutPayment ? "Settled" : r.payment_status === "paid" ? "Paid"
    : r.payment_status === "partial" ? "Partial" : "Pending";
  const tone = r.payment_status === "paid" ? "bg-emerald-50 text-emerald-700 border-emerald-200"
    : r.payment_status === "partial" ? "bg-amber-50 text-amber-800 border-amber-200"
    : "bg-red-50 text-red-700 border-red-200";
  return <span className={`text-xs px-2 py-0.5 rounded border ${tone}`}>{label}</span>;
};

const misc = (r) => Number(r.recurring_share || 0) + Number(r.maintenance_share || 0);

const ACCESSORS = {
  flat_number: (r) => r.flat_number,
  owner_name: (r) => r.owner_name,
  water_own_cost: (r) => r.water_own_cost,
  reserve_share: (r) => r.reserve_share,
  water_cost: (r) => r.water_cost,
  misc,
  base_cost: (r) => r.base_cost,
  carry_in: (r) => r.carry_in,
  contributions: (r) => r.contributions,
  received: (r) => r.received,
  net: (r) => r.net,
  last_paid_on: (r) => r.last_paid_on || "",
  last_paid_by: (r) => r.last_paid_by || "",
  payment_status: (r) => r.payment_status,
};

// The water reconciliation report, in the owner's sheet layout.
// Sorted floor -> flat number by default; every heading is click-to-sort.
export const ReconTable = ({ rows, totals, testPrefix, extraHead, extraCell }) => {
  const { sorted, sort, toggle } = useSort(rows, ACCESSORS, "floor");
  const t = totals || {};
  const miscTotal = (t.recurring_total || 0) + (t.maintenance_total || 0);
  const th = (label, key, align) => (
    <SortTh label={label} sortKey={key} sort={sort} toggle={toggle} align={align}
            testId={`${testPrefix}-sort-${key}`} />
  );
  return (
    <div className="overflow-x-auto relative">
      <table className="data-table text-[13px]">
        <thead>
          <tr>
            <th className="text-right">S.No</th>
            {th("Flat No.", "flat_number")}
            {th("Floor", "floor")}
            {th("Owner", "owner_name")}
            {th("Metered cost", "water_own_cost", "right")}
            {th("Non-metered cost (reserve)", "reserve_share", "right")}
            {th("Total water cost", "water_cost", "right")}
            {th("Misc", "misc", "right")}
            {th("Total amount", "base_cost", "right")}
            {th("Bal brought forward", "carry_in", "right")}
            {th("Advance payment paid by", "contributions", "right")}
            {th("Amount paid", "received", "right")}
            {th("Balance to pay / receive", "net")}
            {th("Date of payment", "last_paid_on")}
            {th("Paid by", "last_paid_by")}
            {th("Status", "payment_status")}
            {extraHead}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r, i) => (
            <tr key={r.flat_id} data-testid={`${testPrefix}-row-${r.flat_number}`}>
              <td className="num text-slate-500">{i + 1}</td>
              <td className="font-semibold">{r.flat_number}</td>
              <td className="text-slate-500">{r.floor || "—"}</td>
              <td>{r.owner_name}{r.tenant_name ? <span className="text-slate-500"> ({r.tenant_name} — tenant)</span> : ""}</td>
              <td className="num">{money(r.water_own_cost)}</td>
              <td className="num">{money(r.reserve_share)}</td>
              <td className="num font-semibold">{money(r.water_cost)}</td>
              <td className="num">{money(misc(r))}</td>
              <td className="num font-semibold">{money(r.base_cost)}</td>
              <td className="num" data-testid={`${testPrefix}-carry-${r.flat_number}`}>
                {money(r.carry_in)}
                {!!r.carry_in && r.carry_in_payer && (
                  <span className="block text-[10px] text-slate-400 capitalize">by {r.carry_in_payer}</span>
                )}
              </td>
              <td className="num text-emerald-700">{money(r.contributions)}</td>
              <td className="num">{money(r.received)}</td>
              <td><NetBadge value={r.net} testId={`${testPrefix}-net-${r.flat_number}`} /></td>
              <td className="text-slate-500" data-testid={`${testPrefix}-paydate-${r.flat_number}`}>{dmy(r.last_paid_on)}</td>
              <td className="text-slate-500 capitalize" data-testid={`${testPrefix}-paidby-${r.flat_number}`}>
                {r.last_paid_by || "—"}
              </td>
              <td data-testid={`${testPrefix}-paystatus-${r.flat_number}`}>{chip(r)}</td>
              {extraCell ? extraCell(r) : null}
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="bg-slate-50 font-semibold" data-testid={`${testPrefix}-footer`}>
            <td colSpan={4}>Total Expense · split between {t.flat_count || 0} house{(t.flat_count || 0) === 1 ? "" : "s"}</td>
            <td className="num">{money((t.total_water_spend || 0) - (t.reserve_value || 0))}</td>
            <td className="num">{money(t.reserve_value)}</td>
            <td className="num">{money(t.total_water_spend)}</td>
            <td className="num">{money(miscTotal)}</td>
            <td className="num">{money(t.billable_total)}</td>
            <td className="num">{money(t.total_carry_in)}</td>
            <td className="num text-emerald-700">{money(t.total_contributions)}</td>
            <td className="num">{money(t.total_received)}</td>
            <td colSpan={extraHead ? 5 : 4} className="text-slate-500 font-normal pl-4">
              Exp per head <span className="mono">{money((t.billable_total || 0) / (t.flat_count || 1))}</span>
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
};
