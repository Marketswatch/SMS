import { Card, Empty } from "@/components/Common";
import { money, num, monthLabel } from "@/lib/format";
import { useSort, SortTh, floorFlatCompare } from "@/lib/sort";

// Water usage charges, grouped Floor -> House -> Meter, with the flat's combined
// total shown once against its block.
export const WaterUsageReport = ({ statement, month, actions }) => {
  const meters = statement?.meters || [];
  const t = statement?.totals;
  const { sorted, sort, toggle } = useSort(meters, {
    flat_number: (m) => m.flat_number,
    owner_name: (m) => m.owner_name,
    label: (m) => m.label,
    opening: (m) => m.opening,
    closing: (m) => m.closing ?? -1,
    consumption: (m) => m.consumption,
    charge: (m) => m.charge,
  }, "floor");

  // build Floor -> Flat -> [meters] while honouring the current sort
  const groups = [];
  const seen = new Map();
  [...sorted].sort((a, b) => (sort.key === "floor" ? floorFlatCompare(a, b) : 0)).forEach((m) => {
    if (!seen.has(m.flat_id)) {
      const g = { flat_id: m.flat_id, flat_number: m.flat_number, floor: m.floor, owner_name: m.owner_name, meters: [] };
      seen.set(m.flat_id, g);
      groups.push(g);
    }
    seen.get(m.flat_id).meters.push(m);
  });

  const th = (label, key, align) => (
    <SortTh label={label} sortKey={key} sort={sort} toggle={toggle} align={align} testId={`meters-sort-${key}`} />
  );

  let sno = 0;
  return (
    <Card testId="water-usage-report" className="mb-8">
      <div className="text-center mb-6">
        <h3 className="text-base md:text-lg font-semibold text-slate-900" data-testid="water-usage-title">
          Water usage charges — as per meter readings · {statement?.property?.name}
        </h3>
        <p className="text-sm text-slate-500 mt-1">For the month of {monthLabel(month)}</p>
        {actions && <div className="flex justify-center gap-2 mt-3">{actions}</div>}
      </div>

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
                  {th("Floor", "floor")}
                  {th("House", "flat_number")}
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
                {groups.map((g) => g.meters.map((m, mi) => {
                  sno += 1;
                  return (
                    <tr key={m.meter_id} data-testid={`water-usage-row-${m.label}`}
                        className={mi === 0 ? "border-t-2 border-slate-200" : ""}>
                      <td className="num text-slate-500">{sno}</td>
                      {mi === 0 && <td className="text-slate-500" rowSpan={g.meters.length}>{g.floor || "—"}</td>}
                      {mi === 0 && <td className="font-semibold" rowSpan={g.meters.length}>{g.flat_number}</td>}
                      {mi === 0 && <td rowSpan={g.meters.length}>{g.owner_name}</td>}
                      <td className="mono">{m.label}</td>
                      <td className="num">{num(m.opening, 2)}</td>
                      <td className="num">{m.closing === null ? "—" : num(m.closing, 2)}</td>
                      <td className={`num ${m.flagged ? "text-amber-600" : ""}`}>
                        {m.flagged ? "0 · flagged" : num(m.consumption, 2)}
                      </td>
                      <td className="num">{money(m.charge)}</td>
                      {mi === 0 && (
                        <td className="num font-semibold" rowSpan={g.meters.length}
                            data-testid={`water-usage-combined-${g.flat_number}`}>
                          {money(g.meters.reduce((s, x) => s + Number(x.charge || 0), 0))}
                        </td>
                      )}
                    </tr>
                  );
                }))}
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
        </>
      )}
    </Card>
  );
};
