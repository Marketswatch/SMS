import { useApp } from "@/context/AppContext";
import { useStatement } from "@/hooks/useStatement";
import { PageHeader, Stat, NetBadge, Empty, Card } from "@/components/Common";
import { money, litres, num, monthLabel } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { AlertTriangle, Sparkles } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import { useState } from "react";

export default function Dashboard() {
  const { propertyId, month, properties, bump } = useApp();
  const { statement } = useStatement(propertyId, month);
  const nav = useNavigate();
  const [busy, setBusy] = useState(false);

  const seed = async () => {
    setBusy(true);
    try {
      await api.post("/demo/seed");
      toast.success("Demo building created");
      bump();
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setBusy(false);
    }
  };

  if (!properties.length)
    return (
      <div>
        <PageHeader title="Welcome to SocietyHub" subtitle="Create your first building to begin." />
        <Empty testId="no-property-empty" title="No properties yet"
               hint="Set up a building with its flats, owners, tenants, meters and tanks — or load a demo building with a full month of data to explore the engine.">
          <Button data-testid="goto-setup-btn" onClick={() => nav("/setup")} className="bg-slate-900 text-white">
            Create building
          </Button>
          <Button data-testid="seed-demo-btn" variant="outline" onClick={seed} disabled={busy}>
            <Sparkles className="w-4 h-4 mr-2" /> Load demo data
          </Button>
        </Empty>
      </div>
    );

  const t = statement?.totals;

  return (
    <div>
      <PageHeader title="Dashboard" subtitle={`${statement?.property?.name || ""} · ${monthLabel(month)}`}>
        <Button data-testid="goto-mis-btn" variant="outline" onClick={() => nav("/mis")}>View MIS</Button>
      </PageHeader>

      {statement?.flags?.length > 0 && (
        <div className="mb-6 space-y-2" data-testid="flags-panel">
          {statement.flags.map((f, i) => (
            <div key={i} data-testid={`flag-${f.type}`}
                 className="flex items-start gap-2 bg-amber-50 border border-amber-200 text-amber-900 rounded-md px-3 py-2 text-sm">
              <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" /> <span>{f.message}</span>
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat testId="stat-purchased" label="Water purchased" value={litres(t?.total_litres)}
              sub={`${money(t?.total_water_spend)} spend`} />
        <Stat testId="stat-avg-cost" label="Avg cost / litre" value={`₹${num(t?.avg_cost_per_litre, 4)}`}
              sub="Monthly weighted average" />
        <Stat testId="stat-consumed" label="Consumed" value={litres(t?.total_consumed)}
              sub={`${t?.flat_count || 0} flats metered`} />
        <Stat testId="stat-reserve" label={t?.reserve_litres < 0 ? "Reserve drawdown" : "Reserve in tanks"}
              value={litres(t?.reserve_litres)} tone={t?.reserve_litres < 0 ? "warning" : "default"}
              sub={`${money(t?.reserve_value)} · ${money(t?.reserve_share)} per flat`} />
        <Stat testId="stat-recurring" label="Recurring charges" value={money(t?.recurring_total)}
              sub={`${money(t?.recurring_share)} per flat`} />
        <Stat testId="stat-maintenance" label="One-time maintenance" value={money(t?.maintenance_total)}
              sub={`${money(t?.maintenance_share)} per flat`} />
        <Stat testId="stat-owes" label="Total receivable" value={money(t?.total_owes)} tone="negative"
              sub="Owners owe the pool" />
        <Stat testId="stat-owed" label="Total payable" value={money(t?.total_owed)} tone="positive"
              sub="Pool owes owners" />
      </div>

      <div className="mt-8">
        <Card title="Per-flat position" testId="dashboard-flat-table">
          {!statement?.rows?.length ? (
            <Empty testId="no-flats-empty" title="No flats configured"
                   hint="Add flats with owners and meters in Building Setup.">
              <Button data-testid="dash-goto-setup-btn" onClick={() => nav("/setup")} className="bg-slate-900 text-white">
                Building Setup
              </Button>
            </Empty>
          ) : (
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Flat</th><th>Owner</th><th>Tenant</th>
                    <th className="text-right">Cons. (L)</th><th className="text-right">Water</th>
                    <th className="text-right">Reserve</th><th className="text-right">Recurring</th>
                    <th className="text-right">Maint.</th><th className="text-right">Base cost</th>
                    <th className="text-right">Contributed</th><th className="text-right">Carry-in</th>
                    <th>Position</th>
                  </tr>
                </thead>
                <tbody>
                  {statement.rows.map((r) => (
                    <tr key={r.flat_id} data-testid={`flat-row-${r.flat_number}`}>
                      <td className="font-semibold">{r.flat_number}</td>
                      <td>{r.owner_name}</td>
                      <td className="text-slate-500">{r.tenant_name || "—"}</td>
                      <td className="num">{num(r.consumption)}</td>
                      <td className="num">{money(r.water_own_cost)}</td>
                      <td className="num">{money(r.reserve_share)}</td>
                      <td className="num">{money(r.recurring_share)}</td>
                      <td className="num">{money(r.maintenance_share)}</td>
                      <td className="num font-semibold">{money(r.base_cost)}</td>
                      <td className="num text-emerald-700">{money(r.contributions)}</td>
                      <td className="num">{money(r.carry_in)}</td>
                      <td><NetBadge value={r.net} testId={`net-badge-${r.flat_number}`} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
