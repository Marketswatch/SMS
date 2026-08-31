import { NetBadge } from "@/components/Common";
import { money, dmy } from "@/lib/format";

const chip = (r) => {
  const settledWithoutPayment = r.payment_status === "paid" && !r.last_paid_on;
  const label = settledWithoutPayment ? "Settled" : r.payment_status === "paid" ? "Paid"
    : r.payment_status === "partial" ? "Partial" : "Pending";
  const tone = r.payment_status === "paid" ? "bg-emerald-50 text-emerald-700 border-emerald-200"
    : r.payment_status === "partial" ? "bg-amber-50 text-amber-800 border-amber-200"
    : "bg-red-50 text-red-700 border-red-200";
  return <span className={`text-xs px-2 py-0.5 rounded border ${tone}`}>{label}</span>;
};

// The water reconciliation report, in the owner's sheet layout.
export const ReconTable = ({ rows, totals, testPrefix, extraHead, extraCell }) => {
  const misc = (r) => Number(r.recurring_share || 0) + Number(r.maintenance_share || 0);
  const t = totals || {};
  const miscTotal = (t.recurring_total || 0) + (t.maintenance_total || 0);
  return (
    <div className="overflow-x-auto relative">
      <table className="data-table text-[13px]">
        <thead>
          <tr>
            <th className="text-right">S.No</th><th>Flat No.</th><th>Floor</th><th>Owner</th>
            <th className="text-right">Metered cost</th><th className="text-right">Non-metered cost (reserve)</th>
            <th className="text-right">Total water cost</th><th className="text-right">Misc</th>
            <th className="text-right">Total amount</th><th className="text-right">Bal brought forward</th>
            <th className="text-right">Advance paid (fronting)</th><th className="text-right">Amount paid</th>
            <th>Balance to pay / receive</th><th>Date of payment</th><th>Status</th>
            {extraHead}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
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
              <td className="num">{money(r.carry_in)}</td>
              <td className="num text-emerald-700">{money(r.contributions)}</td>
              <td className="num">{money(r.received)}</td>
              <td><NetBadge value={r.net} testId={`${testPrefix}-net-${r.flat_number}`} /></td>
              <td className="text-slate-500" data-testid={`${testPrefix}-paydate-${r.flat_number}`}>{dmy(r.last_paid_on)}</td>
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
            <td colSpan={extraHead ? 4 : 3} className="text-slate-500 font-normal pl-4">
              Exp per head <span className="mono">{money((t.billable_total || 0) / (t.flat_count || 1))}</span>
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
};
