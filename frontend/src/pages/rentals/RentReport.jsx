import { useState } from "react";
import { toast } from "sonner";
import { FileDown, FileText } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import { useRentStatement } from "@/hooks/useRentStatement";
import { PageHeader, Card, Stat, Empty } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { money, monthLabel } from "@/lib/format";

export default function RentReport() {
  const { rentMonth } = useApp();
  const { stmt } = useRentStatement(rentMonth);
  const [busy, setBusy] = useState("");

  const download = async (format) => {
    setBusy(format);
    try {
      const res = await api.get("/rentals/export", { params: { month: rentMonth, format }, responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = `properties-${rentMonth}.${format}`; a.click();
      URL.revokeObjectURL(url);
      toast.success(`${format.toUpperCase()} downloaded`);
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(""); }
  };

  const t = stmt?.totals;
  const owned = stmt?.rows?.filter((r) => r.ownership === "own") || [];
  const managed = stmt?.rows?.filter((r) => r.ownership === "managed") || [];
  const vacant = stmt?.rows?.filter((r) => r.status === "vacant") || [];

  const table = (rows, testId) => (
    <div className="overflow-x-auto">
      <table className="data-table">
        <thead><tr><th>Property</th><th>Tenant</th><th className="text-right">Rent</th><th className="text-right">Maint.</th>
          <th className="text-right">Ad-hoc</th><th className="text-right">To collect</th>
          <th className="text-right">Received</th><th className="text-right">Balance</th>
          <th className="text-right">Deposit held</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.unit_id} data-testid={`${testId}-row-${r.name}`}>
              <td className="font-semibold">{r.name}</td>
              <td className="text-slate-500">{r.tenant_name || "—"}</td>
              <td className="num">{money(r.billed_rent)}</td>
              <td className="num">{money(r.billed_maintenance)}</td>
              <td className="num">{money(r.adhoc_collect)}</td>
              <td className="num font-semibold">{money(r.total_to_collect)}</td>
              <td className="num text-emerald-700">{money(r.collected)}</td>
              <td className={`num font-semibold ${r.balance > 0 ? "text-red-600" : ""}`}>{money(r.balance)}</td>
              <td className="num">{money(r.deposit_held)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  return (
    <div>
      <PageHeader title="Property Reports" subtitle={`Collections & building settlement · ${monthLabel(rentMonth)}`}>
        <Button variant="outline" onClick={() => download("csv")} disabled={busy} data-testid="rent-export-csv-btn">
          <FileDown className="w-4 h-4 mr-2" /> CSV
        </Button>
        <Button className="bg-slate-900 text-white" onClick={() => download("pdf")} disabled={busy} data-testid="rent-export-pdf-btn">
          <FileText className="w-4 h-4 mr-2" /> PDF
        </Button>
      </PageHeader>

      {!stmt?.rows?.length ? (
        <Empty testId="rent-report-empty" title="Nothing to report" hint="Add properties and enter this month's bills first." />
      ) : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            <Stat testId="report-stat-due" label="To collect" value={money(t.total_to_collect)} sub={`${t.unit_count} properties`} />
            <Stat testId="report-stat-collected" label="Collected" value={money(t.collected)} tone="positive" />
            <Stat testId="report-stat-pending" label="Balance" value={money(t.balance)} tone="negative"
                  sub={`${money(t.overdue)} overdue`} />
            <Stat testId="report-stat-net" label="Still to pay buildings" value={money(t.building_balance)}
                  tone={(t.building_balance || 0) > 0 ? "negative" : "positive"} />
          </div>

          <Card title={`Properties I own (${owned.length})`} testId="report-owned-card" className="mb-6">
            {owned.length ? table(owned, "owned") : <p className="text-sm text-slate-500">None</p>}
          </Card>
          <Card title={`Managed for others (${managed.length})`} testId="report-managed-card" className="mb-6">
            {managed.length ? table(managed, "managed") : <p className="text-sm text-slate-500">None</p>}
          </Card>

          <Card title="Building / association settlement" testId="report-settlement-card" className="mb-6">
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead><tr><th>Building</th><th className="text-right">Payable</th><th className="text-right">Paid</th>
                  <th className="text-right">Credits</th><th className="text-right">Balance</th></tr></thead>
                <tbody>
                  {stmt.buildings.map((b) => (
                    <tr key={b.key} data-testid={`report-settlement-row-${b.building}`}>
                      <td className="font-semibold">{b.building}</td>
                      <td className="num">{money(b.payable)}</td>
                      <td className="num text-emerald-700">{money(b.paid)}</td>
                      <td className="num text-amber-700">{money(b.credits)}</td>
                      <td className={`num font-semibold ${b.balance > 0 ? "text-red-600" : "text-emerald-700"}`}>{money(b.balance)}</td>
                    </tr>
                  ))}
                  <tr>
                    <td className="font-semibold text-right">Total</td>
                    <td className="num font-semibold">{money(t.building_payable)}</td>
                    <td className="num font-semibold">{money(t.building_paid)}</td>
                    <td className="num font-semibold">{money(t.building_credits)}</td>
                    <td className="num font-semibold">{money(t.building_balance)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </Card>

          {vacant.length > 0 && (
            <Card title="Vacancy" testId="report-vacancy-card">
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead><tr><th>Property</th><th>Vacant since</th><th className="text-right">Idle days</th>
                    <th className="text-right">Monthly rent</th><th className="text-right">Rent forgone</th></tr></thead>
                  <tbody>
                    {vacant.map((r) => (
                      <tr key={r.unit_id} data-testid={`report-vacancy-row-${r.name}`}>
                        <td className="font-semibold">{r.name}</td>
                        <td className="text-slate-500">{r.vacant_since || "—"}</td>
                        <td className="num">{r.vacant_days}</td>
                        <td className="num">{money(r.rent_amount)}</td>
                        <td className="num font-semibold text-amber-700">{money(r.lost_rent)}</td>
                      </tr>
                    ))}
                    <tr>
                      <td colSpan={2} className="font-semibold text-right">Total</td>
                      <td className="num font-semibold">{t.vacant_days}</td>
                      <td className="num font-semibold">{money(vacant.reduce((s, r) => s + r.rent_amount, 0))}</td>
                      <td className="num font-semibold">{money(t.lost_rent)}</td>
                    </tr>
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
