import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, MessageCircle, Send, Home } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { useRentStatement } from "@/hooks/useRentStatement";
import { PageHeader, Stat, Empty, Card } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { money, monthLabel, plainAmt } from "@/lib/format";
import { openWhatsApp, openSms } from "@/lib/notify";

const pill = {
  paid: "bg-emerald-50 text-emerald-700 border-emerald-200",
  pending: "bg-amber-50 text-amber-800 border-amber-200",
  overdue: "bg-red-50 text-red-700 border-red-200",
  vacant: "bg-slate-50 text-slate-500 border-slate-200",
  upcoming: "bg-blue-50 text-blue-700 border-blue-200",
};

export default function RentDashboard() {
  const { rentMonth } = useApp();
  const { stmt } = useRentStatement(rentMonth);
  const nav = useNavigate();

  const msg = (r) => [`${r.name} — ${monthLabel(rentMonth)}`,
    `Rent ${plainAmt(r.billed_rent)} + maintenance ${plainAmt(r.billed_maintenance)}` +
      (r.adhoc_collect ? ` + ad-hoc ${plainAmt(r.adhoc_collect)}` : "") +
      (r.tenant_paid_on_my_behalf ? ` − paid by you ${plainAmt(r.tenant_paid_on_my_behalf)}` : ""),
    `Total payable: ${plainAmt(r.total_to_collect)}`,
    `Received: ${plainAmt(r.collected)}`,
    r.balance > 0 ? `Balance: ${plainAmt(r.balance)} (due ${r.due_date})` : "Status: settled"].join("\n");

  const t = stmt?.totals;

  if (stmt && !stmt.rows.length)
    return (
      <div>
        <PageHeader title="Property Management" subtitle="Rent, maintenance and payouts for the properties you own or manage." />
        <Empty testId="no-units-empty" title="No properties yet"
               hint="Add each property with its rent, maintenance and deposit — bills and collections follow from there.">
          <Button data-testid="goto-units-btn" onClick={() => nav("/rentals/units")} className="bg-slate-900 text-white">
            Add a property
          </Button>
        </Empty>
      </div>
    );

  return (
    <div>
      <PageHeader title="Rent Roll" subtitle={`Bill, collection and payout position · ${monthLabel(rentMonth)}`}>
        <Button variant="outline" onClick={() => nav("/rentals/bills")} data-testid="goto-bills-btn">Monthly bills</Button>
        <Button variant="outline" onClick={() => nav("/rentals/report")} data-testid="goto-rent-report-btn">Reports</Button>
      </PageHeader>

      {t?.bills_missing > 0 && (
        <div className="mb-6 flex items-start gap-2 bg-amber-50 border border-amber-200 text-amber-900 rounded-md px-3 py-2 text-sm"
             data-testid="bills-missing-alert">
          <AlertTriangle className="w-4 h-4 mt-0.5" />
          {t.bills_missing} propert{t.bills_missing === 1 ? "y has" : "ies have"} no bill saved for this month — the figures
          shown are drafts from the master until you save them.
        </div>
      )}
      {t?.vacant > 0 && (
        <div className="mb-6 flex items-start gap-2 bg-slate-100 border border-slate-300 text-slate-700 rounded-md px-3 py-2 text-sm"
             data-testid="vacancy-alert">
          <Home className="w-4 h-4 mt-0.5" />
          {t.vacant} vacant · {t.vacant_days} idle days · approx {money(t.lost_rent)} of rent forgone
        </div>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat testId="rent-stat-due" label="To collect" value={money(t?.total_to_collect)}
              sub={`${t?.occupied || 0} occupied · ${t?.vacant || 0} vacant`} />
        <Stat testId="rent-stat-collected" label="Collected" value={money(t?.collected)} tone="positive"
              sub={`Rent ${money(t?.rent_paid)} · maint ${money(t?.maintenance_paid)}`} />
        <Stat testId="rent-stat-pending" label="Balance" value={money(t?.balance)} tone="negative"
              sub={`${money(t?.overdue)} overdue`} />
        <Stat testId="rent-stat-deposit" label="Deposits held" value={money(t?.deposit_held)} sub="Refundable" />
        <Stat testId="rent-stat-payable" label="Owed to buildings" value={money(t?.building_payable)}
              sub={`Paid ${money(t?.building_paid)} · credits ${money(t?.building_credits)}`} />
        <Stat testId="rent-stat-settle" label="Still to pay buildings" value={money(t?.building_balance)}
              tone={(t?.building_balance || 0) > 0 ? "negative" : "positive"} />
      </div>

      <div className="mt-8">
        <Card title="Property-wise position" testId="rent-roll-table">
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr><th>Property</th><th>Tenant</th><th className="text-right">Rent</th>
                  <th className="text-right">Maint.</th><th className="text-right">Ad-hoc</th>
                  <th className="text-right">Less paid by tenant</th><th className="text-right">To collect</th>
                  <th className="text-right">Received</th><th className="text-right">Balance</th>
                  <th>Status</th><th className="text-right">Owed to building</th><th>Remind</th></tr>
              </thead>
              <tbody>
                {stmt?.rows?.map((r) => (
                  <tr key={r.unit_id} data-testid={`rent-row-${r.name}`}>
                    <td className="font-semibold">{r.name}
                      {r.building && <span className="text-slate-400 font-normal"> · {r.building}</span>}</td>
                    <td>{r.tenant_name || "—"}</td>
                    <td className="num">{money(r.billed_rent)}</td>
                    <td className="num">{money(r.billed_maintenance)}</td>
                    <td className="num">{money(r.adhoc_collect)}</td>
                    <td className="num text-amber-700">{money(r.tenant_paid_on_my_behalf)}</td>
                    <td className="num font-semibold">{money(r.total_to_collect)}</td>
                    <td className="num text-emerald-700">{money(r.collected)}</td>
                    <td className={`num font-semibold ${r.balance > 0 ? "text-red-600" : ""}`}>{money(r.balance)}</td>
                    <td>
                      <span className={`text-xs px-2 py-0.5 rounded border capitalize ${pill[r.status]}`}
                            data-testid={`rent-status-${r.name}`}>{r.status}</span>
                      {r.status === "vacant" && r.vacant_days > 0 && (
                        <div className="text-[11px] text-slate-500 mono mt-0.5" data-testid={`vacant-days-${r.name}`}>
                          {r.vacant_days}d · {money(r.lost_rent)} lost
                        </div>
                      )}
                    </td>
                    <td className="num">{money(r.maintenance_payable_to_building + r.adhoc_payable_to_building)}</td>
                    <td>
                      {r.tenant_phone && r.balance > 0 ? (
                        <div className="flex gap-1.5">
                          <button onClick={() => openWhatsApp(r.tenant_phone, msg(r))} title="WhatsApp"
                                  aria-label={`WhatsApp ${r.tenant_name}`} data-testid={`rent-notify-whatsapp-${r.name}`}
                                  className="p-2.5 border border-slate-300 rounded-md text-emerald-700 hover:bg-emerald-50">
                            <MessageCircle className="w-4 h-4" />
                          </button>
                          <button onClick={() => openSms(r.tenant_phone, msg(r))} title="SMS"
                                  aria-label={`SMS ${r.tenant_name}`} data-testid={`rent-notify-sms-${r.name}`}
                                  className="p-2.5 border border-slate-300 rounded-md text-slate-700 hover:bg-slate-100">
                            <Send className="w-4 h-4" />
                          </button>
                        </div>
                      ) : <span className="text-xs text-slate-400">{r.balance > 0 ? "No phone" : "—"}</span>}
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
