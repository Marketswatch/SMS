import { useApp } from "@/context/AppContext";
import { useStatement } from "@/hooks/useStatement";
import { PageHeader, Card, Stat, NetBadge, Empty } from "@/components/Common";
import { money, litres, num, monthLabel } from "@/lib/format";

export default function MyDues() {
  const { propertyId, month } = useApp();
  const { statement } = useStatement(propertyId, month);
  const row = statement?.rows?.[0];

  return (
    <div>
      <PageHeader title="My Dues" subtitle={`${statement?.property?.name || ""} · ${monthLabel(month)}`} />
      {!row ? (
        <Empty testId="my-dues-empty" title="No statement for this period"
               hint="Your flat is not linked to this login yet, or the month has no data. Contact your society admin." />
      ) : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            <Stat testId="my-consumption" label="My water consumption" value={litres(row.consumption)}
                  sub={`@ ₹${num(statement.totals.avg_cost_per_litre, 4)} / L`} />
            <Stat testId="my-water-cost" label="My water cost" value={money(row.water_cost)}
                  sub={`incl. ${money(row.reserve_share)} reserve share`} />
            <Stat testId="my-total" label="Total payable" value={money(row.base_cost)} sub="Water + recurring + repairs" />
            <Stat testId="my-net" label="Balance" value={money(Math.abs(row.net))}
                  tone={row.net > 0 ? "negative" : "positive"} sub={row.net > 0 ? "You owe" : "You are owed"} />
          </div>

          <Card title={`Flat ${row.flat_number} — statement`} testId="my-statement-card" className="mb-6">
            <dl className="divide-y divide-slate-100 text-sm">
              {[
                ["Owner", row.owner_name],
                ["Tenant", row.tenant_name || "—"],
                ["Water — own consumption", money(row.water_own_cost)],
                ["Water — reserve share", money(row.reserve_share)],
                ["Recurring share", money(row.recurring_share)],
                ["Maintenance share", money(row.maintenance_share)],
                ["Total base cost", money(row.base_cost)],
                ["Amounts fronted by you", money(row.contributions)],
                ["Carried over from last month", money(row.carry_in)],
                ["Paid by tenant", money(row.received_by_tenant)],
                ["Paid by owner", money(row.received_by_owner)],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between py-2">
                  <dt className="text-slate-600">{k}</dt><dd className="mono font-medium">{v}</dd>
                </div>
              ))}
            </dl>
            <div className="mt-4 flex items-center justify-between border-t border-slate-200 pt-4">
              <span className="font-display font-semibold text-slate-800">Net position</span>
              <NetBadge value={row.net} testId="my-net-badge" />
            </div>
          </Card>

          <Card title="My meters" testId="my-meters-card">
            <table className="data-table">
              <thead><tr><th>Meter</th><th className="text-right">Opening</th><th className="text-right">Closing</th><th className="text-right">Consumption</th></tr></thead>
              <tbody>
                {statement.meters.map((m) => (
                  <tr key={m.meter_id} data-testid={`my-meter-${m.label}`}>
                    <td className="font-semibold">{m.label}</td>
                    <td className="num">{num(m.opening, 0)}</td>
                    <td className="num">{m.closing === null ? "—" : num(m.closing, 0)}</td>
                    <td className="num">{num(m.consumption)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </>
      )}
    </div>
  );
}
