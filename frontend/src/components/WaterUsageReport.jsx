import { Card, Empty } from "@/components/Common";
import { money, num, monthLabel } from "@/lib/format";
import { useSort, SortTh } from "@/lib/sort";

const ACCESSORS = {
  flat_number: (m) => m.flat_number,
  owner_name: (m) => m.owner_name,
  label: (m) => m.label,
  opening: (m) => m.opening,
  closing: (m) => m.closing ?? -1,
  consumption: (m) => m.consumption,
  charge: (m) => m.charge,
};

// "Water Usage Charges — As per Water Meter Readings": one row per meter, sorted
// floor -> flat by default, with the combined charge per flat and the reserve split.
export const WaterUsageReport = ({ statement, month }) => {
  const meters = statement?.meters || [];
  const t = statement?.totals;
  const { sorted, sort, toggle } = useSort(meters, ACCESSORS, "floor");

  const combined = meters.reduce((acc, m) => {
    acc[m.flat_id] = (acc[m.flat_id] || 0) + Number(m.charge || 0);
    return acc;
  }, {});

  const th = (label, key, align) => (
    <SortTh label={label} sortKey={key} sort={sort} toggle={toggle} align={align} testId={`meters-sort-${key}`} />
  );

  return (
    <Card title={`Water usage charges — as per meter readings · ${monthLabel(month)}`}
          testId="water-usage-report" className="mb-8">
      {!meters.length ? (
        <Empty testId="water-usage-empty" title="No meters recorded"
               hint="Register meters per flat and enter readings to build this report." />
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th className="text-right">S.No</th>
                  {th("House", "flat_number")}
                  {th("Floor", "floor")}
                  {th("Owner", "owner_name")}
                  {th("Meter number", "label")}
                  {th("Starting unit", "opening", "right")}
                  {th("Ending unit", "closing", "right")}
                  {th("Consumed units", "consumption", "right")}
                  {th("Water charges", "charge", "right")}
                  <th className="text-right">Total Amount</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((m, i) => (
                  <tr key={m.meter_id} data-testid={`water-usage-row-${m.label}`}>
                    <td className="num text-slate-500">{i + 1}</td>
                    <td className="font-semibold">{m.flat_number}</td>
                    <td className="text-slate-500">{m.floor || "—"}</td>
                    <td>{m.owner_name}</td>
                    <td className="mono">{m.label}</td>
                    <td className="num">{num(m.opening, 2)}</td>
                    <td className="num">{m.closing === null ? "—" : num(m.closing, 2)}</td>
                    <td className={`num ${m.flagged ? "text-amber-600" : ""}`}>
                      {m.flagged ? "0 · flagged" : num(m.consumption, 2)}
                    </td>
                    <td className="num">{money(m.charge)}</td>
                    <td className="num font-semibold" data-testid={`water-usage-combined-${m.flat_number}`}>                      {money(combined[m.flat_id])}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="bg-slate-50 font-semibold" data-testid="water-usage-footer">
                  <td colSpan={7}>Total units consumed (as per meter)</td>
                  <td className="num">{num(t?.total_consumed, 2)}</td>
                  <td className="num" colSpan={2}>{money(t?.metered_charges)}</td>
                </tr>
              </tfoot>
            </table>
          </div>

          <div className="grid sm:grid-cols-2 gap-x-10 mt-6 text-sm">
            {[
              ["Total lorries this month", num(t?.tanker_count, 0)],
              ["Total water received", `${num(t?.total_litres, 2)} L`],
              ["Total water cost (lorry + tips)", money(t?.total_water_spend)],
              ["Cost per litre of water", `₹${num(t?.avg_cost_per_litre, 4)}`],
              ["Total water charges (as per meter)", money(t?.metered_charges)],
              ["Total non-metered consumption", `${num(t?.reserve_litres, 2)} L`],
              ["Total non-metered cost", money(t?.reserve_value)],
              [`Non-metered cost · split between ${t?.flat_count || 0} house${(t?.flat_count || 0) === 1 ? "" : "s"} — per house share`,
               money(t?.reserve_share)],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between gap-4 py-2 border-b border-slate-100">
                <span className="text-slate-600">{k}</span><span className="mono font-medium">{v}</span>
              </div>
            ))}
          </div>
          <p className="text-xs text-slate-500 mt-3">
            The non-metered per-house share is added into each flat's water charge in the main calculation.
          </p>
        </>
      )}
    </Card>
  );
};
