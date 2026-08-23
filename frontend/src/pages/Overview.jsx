import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import { PageHeader, Card, Stat, Empty } from "@/components/Common";
import { Input } from "@/components/ui/input";
import { money, monthLabel } from "@/lib/format";

export default function Overview() {
  const { month, rentMonth, mode } = useApp();
  const [m, setM] = useState((mode === "rentals" ? rentMonth : month) || new Date().toISOString().slice(0, 7));
  const [data, setData] = useState(null);
  const nav = useNavigate();

  useEffect(() => {
    if (!m) return;
    api.get("/overview", { params: { month: m } }).then(({ data }) => setData(data)).catch(() => setData(null));
  }, [m]);

  const c = data?.combined;
  const mt = data?.maintenance?.totals;
  const rt = data?.rentals?.totals;

  return (
    <div>
      <PageHeader title="Combined Overview" subtitle={`Maintenance dues and rent income · ${monthLabel(m)}`}>
        <Input type="month" value={m} onChange={(e) => setM(e.target.value)}
               data-testid="overview-month-input" className="h-10 w-[160px] mono" />
      </PageHeader>

      {!data ? (
        <Empty testId="overview-empty" title="Nothing recorded for this month"
               hint="Once a building period or a rental entry exists for the month it shows up here." />
      ) : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <Stat testId="ov-stat-in" label="Money in" value={money(c.money_in)} tone="positive"
                  sub={`Rent ${money(c.rent_collected)} · maintenance ${money(c.maintenance_collected)}`} />
            <Stat testId="ov-stat-out" label="Money out" value={money(c.money_out)} tone="negative"
                  sub={`${money(c.paid_on_behalf_of_buildings)} on behalf of buildings`} />
            <Stat testId="ov-stat-tocollect" label="Still to collect" value={money(c.still_to_collect)} tone="negative"
                  sub={`Maintenance ${money(c.maintenance_outstanding)} · rent ${money(c.rent_pending)}`} />
            <Stat testId="ov-stat-deposits" label="Deposits held" value={money(c.deposits_held)}
                  sub={c.lost_rent_vacancy ? `${money(c.lost_rent_vacancy)} lost to vacancy` : "Refundable"} />
          </div>

          <div className="grid lg:grid-cols-2 gap-6 mt-8 [&>*]:min-w-0">
            <Card title="Maintenance — buildings" testId="overview-maintenance-card">
              {!data.maintenance.buildings.length ? (
                <p className="text-sm text-slate-500">No building period for this month.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="data-table">
                    <thead><tr><th>Building</th><th className="text-right">Flats</th>
                      <th className="text-right">Billed</th><th className="text-right">Collected</th>
                      <th className="text-right">Outstanding</th></tr></thead>
                    <tbody>
                      {data.maintenance.buildings.map((b) => (
                        <tr key={b.property_id} data-testid={`overview-building-${b.name}`}
                            className="cursor-pointer" onClick={() => nav("/mis")}>
                          <td className="font-semibold">{b.name}
                            {b.status === "locked" && <span className="text-slate-400 font-normal"> · locked</span>}</td>
                          <td className="num">{b.flats}</td>
                          <td className="num">{money(b.billable)}</td>
                          <td className="num text-emerald-700">{money(b.collected)}</td>
                          <td className="num text-red-600">{money(b.outstanding)}</td>
                        </tr>
                      ))}
                      <tr>
                        <td colSpan={2} className="font-semibold text-right">Total</td>
                        <td className="num font-semibold">{money(mt.billable)}</td>
                        <td className="num font-semibold">{money(mt.collected)}</td>
                        <td className="num font-semibold">{money(mt.outstanding)}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              )}
            </Card>

            <Card title="Rentals — properties" testId="overview-rentals-card">
              {!data.rentals.rows.length ? (
                <p className="text-sm text-slate-500">No rental properties yet.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="data-table">
                    <thead><tr><th>Property</th><th>Status</th><th className="text-right">Rent due</th>
                      <th className="text-right">Collected</th><th className="text-right">Net to owner</th></tr></thead>
                    <tbody>
                      {data.rentals.rows.map((r) => (
                        <tr key={r.unit_id} data-testid={`overview-unit-${r.name}`}
                            className="cursor-pointer" onClick={() => nav("/rentals")}>
                          <td className="font-semibold">{r.name}</td>
                          <td className="capitalize text-slate-500">{r.status}</td>
                          <td className="num">{money(r.rent_due)}</td>
                          <td className="num text-emerald-700">{money(r.rent_collected)}</td>
                          <td className={`num ${r.net_to_owner < 0 ? "text-red-600" : ""}`}>{money(r.net_to_owner)}</td>
                        </tr>
                      ))}
                      <tr>
                        <td colSpan={2} className="font-semibold text-right">Total</td>
                        <td className="num font-semibold">{money(rt.rent_due)}</td>
                        <td className="num font-semibold">{money(rt.rent_collected)}</td>
                        <td className="num font-semibold">{money(rt.net_to_owner)}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </div>

          {data.rentals.building_tally?.length > 0 && (
            <Card title="Paid on behalf of buildings — reconcile against maintenance" testId="overview-tally-card"
                  className="mt-6">
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead><tr><th>Building</th><th>Items</th><th className="text-right">Amount</th></tr></thead>
                  <tbody>
                    {data.rentals.building_tally.map((b) => (
                      <tr key={b.building} data-testid={`overview-tally-${b.building}`}>
                        <td className="font-semibold">{b.building}</td>
                        <td className="text-slate-500">{b.items.map((i) => i.description).join("; ")}</td>
                        <td className="num font-semibold">{money(b.amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
