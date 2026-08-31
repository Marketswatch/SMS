import { Card, Empty } from "@/components/Common";
import { money, num, monthLabel } from "@/lib/format";

// "Water Usage Charges — As per Water Meter Readings": one row per meter, grouped by flat,
// with the combined charge per owner and the non-metered (reserve) split at the bottom.
export const WaterUsageReport = ({ statement, month }) => {
  const meters = statement?.meters || [];
  const rows = statement?.rows || [];
  const t = statement?.totals;

  const groups = rows
    .map((r) => ({ row: r, meters: meters.filter((m) => m.flat_id === r.flat_id) }))
    .filter((g) => g.meters.length);

  return (
    <Card title={`Water usage charges — as per meter readings · ${monthLabel(month)}`}
          testId="water-usage-report" className="mb-8">
      {!groups.length ? (
        <Empty testId="water-usage-empty" title="No meters recorded"
               hint="Register meters per flat and enter readings to build this report." />
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr><th className="text-right">S.No</th><th>House</th><th>Floor</th><th>Owner</th><th>Meter number</th>
                  <th className="text-right">Starting unit</th><th className="text-right">Ending unit</th>
                  <th className="text-right">Consumed units</th><th className="text-right">Water charges</th>
                  <th className="text-right">Combined</th></tr>
              </thead>
              <tbody>
                {groups.map((g, gi) =>
                  g.meters.map((m, mi) => (
                    <tr key={m.meter_id} data-testid={`water-usage-row-${m.label}`}>
                      {mi === 0 && <td className="num text-slate-500" rowSpan={g.meters.length}>{gi + 1}</td>}
                      {mi === 0 && <td className="font-semibold" rowSpan={g.meters.length}>{g.row.flat_number}</td>}
                      {mi === 0 && <td className="text-slate-500" rowSpan={g.meters.length}>{g.row.floor || "—"}</td>}
                      {mi === 0 && <td rowSpan={g.meters.length}>{g.row.owner_name}</td>}
                      <td className="mono">{m.label}</td>
                      <td className="num">{num(m.opening, 2)}</td>
                      <td className="num">{m.closing === null ? "—" : num(m.closing, 2)}</td>
                      <td className={`num ${m.flagged ? "text-amber-600" : ""}`}>
                        {m.flagged ? "0 · flagged" : num(m.consumption, 2)}
                      </td>
                      <td className="num">{money(m.charge)}</td>
                      {mi === 0 && (
                        <td className="num font-semibold" rowSpan={g.meters.length}
                            data-testid={`water-usage-combined-${g.row.flat_number}`}>
                          {money(g.meters.reduce((s, x) => s + Number(x.charge || 0), 0))}
                        </td>
                      )}
                    </tr>
                  ))
                )}
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
