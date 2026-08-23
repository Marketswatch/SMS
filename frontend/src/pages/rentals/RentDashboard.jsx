import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Sparkles, MessageCircle, Send, AlertTriangle, Home } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import { useRentRoll } from "@/hooks/useRentRoll";
import { PageHeader, Stat, Empty, Card } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { money, monthLabel } from "@/lib/format";
import { openWhatsApp, openSms } from "@/lib/notify";

const statusPill = {
  paid: "bg-emerald-50 text-emerald-700 border-emerald-200",
  pending: "bg-amber-50 text-amber-800 border-amber-200",
  overdue: "bg-red-50 text-red-700 border-red-200",
  vacant: "bg-slate-50 text-slate-500 border-slate-200",
  upcoming: "bg-blue-50 text-blue-700 border-blue-200",
};

export default function RentDashboard() {
  const { rentMonth } = useApp();
  const [tick, setTick] = useState(0);
  const { roll } = useRentRoll(rentMonth, tick);
  const [busy, setBusy] = useState(false);
  const nav = useNavigate();

  const seed = async () => {
    setBusy(true);
    try {
      await api.post("/rentals/demo/seed");
      toast.success("Sample properties added");
      setTick((t) => t + 1);
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  const rentMsg = (r) =>
    [`${r.name} — ${monthLabel(rentMonth)}`,
     `Rent due: Rs.${r.rent_due.toFixed(2)}`,
     `Received: Rs.${r.rent_collected.toFixed(2)}`,
     r.pending > 0 ? `Balance payable: Rs.${r.pending.toFixed(2)} (due ${r.due_date})` : "Status: fully paid",
    ].join("\n");

  const t = roll?.totals;

  if (roll && !roll.rows.length)
    return (
      <div>
        <PageHeader title="Property Management" subtitle="Rent, deposits and bills for units you own or manage." />
        <Empty testId="no-units-empty" title="No properties yet"
               hint="Add the flats, shops or houses you rent out — you can mark each as owned by you or managed for someone else.">
          <Button data-testid="goto-units-btn" onClick={() => nav("/rentals/units")} className="bg-slate-900 text-white">
            Add a property
          </Button>
          <Button data-testid="seed-rentals-btn" variant="outline" onClick={seed} disabled={busy}>
            <Sparkles className="w-4 h-4 mr-2" /> Load sample data
          </Button>
        </Empty>
      </div>
    );

  return (
    <div>
      <PageHeader title="Rent Roll" subtitle={`Collection status · ${monthLabel(rentMonth)}`}>
        <Button variant="outline" onClick={() => nav("/rentals/report")} data-testid="goto-rent-report-btn">Reports</Button>
      </PageHeader>

      {roll?.rows?.some((r) => r.lease_expiring_soon) && (
        <div className="mb-6 flex items-start gap-2 bg-amber-50 border border-amber-200 text-amber-900 rounded-md px-3 py-2 text-sm"
             data-testid="lease-expiry-alert">
          <AlertTriangle className="w-4 h-4 mt-0.5" />
          Lease expiring soon: {roll.rows.filter((r) => r.lease_expiring_soon).map((r) => `${r.name} (${r.lease_end})`).join(", ")}
        </div>
      )}

      {roll?.totals?.vacant > 0 && (
        <div className="mb-6 flex items-start gap-2 bg-slate-100 border border-slate-300 text-slate-700 rounded-md px-3 py-2 text-sm"
             data-testid="vacancy-alert">
          <Home className="w-4 h-4 mt-0.5" />
          <span>
            {roll.totals.vacant} vacant {roll.totals.vacant === 1 ? "property" : "properties"} ·{" "}
            {roll.totals.vacant_days} idle days so far · approx {money(roll.totals.lost_rent)} of rent forgone
          </span>
        </div>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat testId="rent-stat-due" label="Rent due" value={money(t?.rent_due)}
              sub={`${t?.occupied || 0} occupied · ${t?.vacant || 0} vacant${t?.upcoming ? ` · ${t.upcoming} upcoming` : ""}`} />
        <Stat testId="rent-stat-collected" label="Collected" value={money(t?.rent_collected)} tone="positive"
              sub={`${t?.owned_units || 0} owned · ${t?.managed_units || 0} managed`} />
        <Stat testId="rent-stat-pending" label="Pending" value={money(t?.pending)} tone="negative"
              sub={`${money(t?.overdue)} overdue`} />
        <Stat testId="rent-stat-deposit" label="Deposits held" value={money(t?.deposit_held)} sub="Refundable" />
        <Stat testId="rent-stat-expenses" label="Bills paid" value={money(t?.expenses)}
              sub={`${money(t?.on_behalf_of_building)} on behalf of buildings`} />
        <Stat testId="rent-stat-net" label="Net to owners" value={money(t?.net_to_owner)}
              tone={(t?.net_to_owner || 0) < 0 ? "negative" : "positive"} sub="Collected − bills paid" />
        <Stat testId="rent-stat-vacancy" label="Vacancy cost" value={money(t?.lost_rent)}
              tone={(t?.lost_rent || 0) > 0 ? "warning" : "default"}
              sub={`${t?.vacant || 0} vacant · ${t?.vacant_days || 0} idle days`} />
      </div>

      <div className="mt-8">
        <Card title="Unit-wise position" testId="rent-roll-table">
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr><th>Property</th><th>Type</th><th>Ownership</th><th>Tenant</th>
                  <th className="text-right">Rent due</th><th className="text-right">Collected</th>
                  <th className="text-right">Pending</th><th>Status</th><th className="text-right">Deposit held</th>
                  <th className="text-right">Bills</th><th className="text-right">Net to owner</th><th>Remind tenant</th></tr>
              </thead>
              <tbody>
                {roll?.rows?.map((r) => (
                  <tr key={r.unit_id} data-testid={`rent-row-${r.name}`}>
                    <td className="font-semibold">{r.name}
                      {r.building && <span className="text-slate-400 font-normal"> · {r.building}</span>}</td>
                    <td className="capitalize text-slate-500">{r.kind}</td>
                    <td>
                      <span className={`text-xs px-2 py-0.5 rounded border ${r.ownership === "own"
                        ? "bg-slate-900 text-white border-slate-900" : "bg-white text-slate-600 border-slate-300"}`}>
                        {r.ownership === "own" ? "Own" : `Managed${r.owner_name ? ` · ${r.owner_name}` : ""}`}
                      </span>
                    </td>
                    <td>{r.tenant_name || "—"}</td>
                    <td className="num">{money(r.rent_due)}</td>
                    <td className="num text-emerald-700">{money(r.rent_collected)}</td>
                    <td className="num">{r.pending > 0 ? money(r.pending) : r.advance > 0 ? `+${money(r.advance)}` : "—"}</td>
                    <td>
                      <span className={`text-xs px-2 py-0.5 rounded border capitalize ${statusPill[r.status]}`}
                            data-testid={`rent-status-${r.name}`}>{r.status}</span>
                      {r.status === "vacant" && r.vacant_days > 0 && (
                        <div className="text-[11px] text-slate-500 mono mt-0.5" data-testid={`vacant-days-${r.name}`}>
                          {r.vacant_days}d · {money(r.lost_rent)} lost
                        </div>
                      )}
                    </td>
                    <td className="num">{money(r.deposit_held)}</td>
                    <td className="num">{money(r.expenses)}</td>
                    <td className={`num font-semibold ${r.net_to_owner < 0 ? "text-red-600" : ""}`}>{money(r.net_to_owner)}</td>
                    <td>
                      {r.tenant_phone && r.pending > 0 ? (
                        <div className="flex gap-1.5">
                          <button onClick={() => openWhatsApp(r.tenant_phone, rentMsg(r))}
                                  aria-label={`WhatsApp rent reminder to ${r.tenant_name}`}
                                  data-testid={`rent-notify-whatsapp-${r.name}`} title="WhatsApp reminder"
                                  className="p-2.5 border border-slate-300 rounded-md hover:bg-emerald-50 text-emerald-700">
                            <MessageCircle className="w-4 h-4" />
                          </button>
                          <button onClick={() => openSms(r.tenant_phone, rentMsg(r))}
                                  aria-label={`SMS rent reminder to ${r.tenant_name}`}
                                  data-testid={`rent-notify-sms-${r.name}`} title="SMS reminder"
                                  className="p-2.5 border border-slate-300 rounded-md hover:bg-slate-100 text-slate-700">
                            <Send className="w-4 h-4" />
                          </button>
                        </div>
                      ) : <span className="text-xs text-slate-400">{r.pending > 0 ? "No phone" : "—"}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  );
}
