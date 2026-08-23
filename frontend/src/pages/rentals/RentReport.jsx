import { useState } from "react";
import { toast } from "sonner";
import { FileDown, FileText } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import { useRentRoll } from "@/hooks/useRentRoll";
import { PageHeader, Card, Stat, Empty } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { money, monthLabel } from "@/lib/format";

export default function RentReport() {
  const { rentMonth } = useApp();
  const { roll } = useRentRoll(rentMonth);
  const [busy, setBusy] = useState("");

  const download = async (format) => {
    setBusy(format);
    try {
      const res = await api.get("/rentals/export", {
        params: { month: rentMonth, format }, responseType: "blob",
      });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `rent-roll-${rentMonth}.${format}`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success(`${format.toUpperCase()} downloaded`);
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(""); }
  };

  const t = roll?.totals;
  const owned = roll?.rows?.filter((r) => r.ownership === "own") || [];
  const managed = roll?.rows?.filter((r) => r.ownership === "managed") || [];

  const payoutTable = (rows, testId) => (
    <div className="overflow-x-auto">
      <table className="data-table">
        <thead><tr><th>Property</th><th>Owner</th><th>Tenant</th><th className="text-right">Rent collected</th>
          <th className="text-right">Bills paid</th><th className="text-right">Net to owner</th>
          <th className="text-right">Deposit held</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.unit_id} data-testid={`${testId}-row-${r.name}`}>
              <td className="font-semibold">{r.name}</td>
              <td>{r.ownership === "own" ? "Self" : r.owner_name || "—"}</td>
              <td className="text-slate-500">{r.tenant_name || "—"}</td>
              <td className="num text-emerald-700">{money(r.rent_collected)}</td>
              <td className="num">{money(r.expenses)}</td>
              <td className={`num font-semibold ${r.net_to_owner < 0 ? "text-red-600" : ""}`}>{money(r.net_to_owner)}</td>
              <td className="num">{money(r.deposit_held)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  return (
    <div>
      <PageHeader title="Rent Reports" subtitle={`Rent roll & owner payout · ${monthLabel(rentMonth)}`}>
        <Button variant="outline" onClick={() => download("csv")} disabled={busy} data-testid="rent-export-csv-btn">
          <FileDown className="w-4 h-4 mr-2" /> CSV
        </Button>
        <Button className="bg-slate-900 text-white" onClick={() => download("pdf")} disabled={busy} data-testid="rent-export-pdf-btn">
          <FileText className="w-4 h-4 mr-2" /> PDF
        </Button>
      </PageHeader>

      {!roll?.rows?.length ? (
        <Empty testId="rent-report-empty" title="Nothing to report for this month" hint="Add properties and record rent first." />
      ) : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            <Stat testId="report-stat-due" label="Rent due" value={money(t?.rent_due)} sub={`${t?.unit_count} properties`} />
            <Stat testId="report-stat-collected" label="Collected" value={money(t?.rent_collected)} tone="positive" />
            <Stat testId="report-stat-pending" label="Pending" value={money(t?.pending)} tone="negative"
                  sub={`${money(t?.overdue)} overdue`} />
            <Stat testId="report-stat-net" label="Net to owners" value={money(t?.net_to_owner)}
                  tone={(t?.net_to_owner || 0) < 0 ? "negative" : "positive"} />
          </div>

          {t?.vacant > 0 && (
            <Card title="Vacancy" testId="report-vacancy-card" className="mb-6">
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead><tr><th>Property</th><th>Vacant since</th><th className="text-right">Idle days</th>
                    <th className="text-right">Monthly rent</th><th className="text-right">Rent forgone</th></tr></thead>
                  <tbody>
                    {roll.rows.filter((r) => r.status === "vacant").map((r) => (
                      <tr key={r.unit_id} data-testid={`report-vacancy-row-${r.name}`}>
                        <td className="font-semibold">{r.name}</td>
                        <td className="text-slate-500">{r.vacant_since || "—"}</td>
                        <td className="num">{r.vacant_days}</td>
                        <td className="num">{money(r.rent_amount || 0)}</td>
                        <td className="num font-semibold text-amber-700">{money(r.lost_rent)}</td>
                      </tr>
                    ))}
                    <tr>
                      <td colSpan={2} className="font-semibold text-right">Total</td>
                      <td className="num font-semibold">{t.vacant_days}</td>
                      <td className="num font-semibold">
                        {money(roll.rows.filter((r) => r.status === "vacant")
                          .reduce((s, r) => s + Number(r.rent_amount || 0), 0))}
                      </td>
                      <td className="num font-semibold">{money(t.lost_rent)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          <Card title={`Properties I own (${owned.length})`} testId="report-owned-card" className="mb-6">
            {owned.length ? payoutTable(owned, "owned") : <p className="text-sm text-slate-500">None</p>}
          </Card>

          <Card title={`Managed for others (${managed.length})`} testId="report-managed-card" className="mb-6">
            {managed.length ? payoutTable(managed, "managed") : <p className="text-sm text-slate-500">None</p>}
          </Card>

          <Card title="Paid on behalf of buildings" testId="report-tally-card">
            {roll.building_tally?.length ? (
              <>
                <p className="text-sm text-slate-500 mb-3">
                  Reconcile these against the building's maintenance statement — kept out of rent income here.
                </p>
                <table className="data-table">
                  <thead><tr><th>Building</th><th>Item</th><th>Category</th><th>Date</th><th className="text-right">Amount</th></tr></thead>
                  <tbody>
                    {roll.building_tally.flatMap((b) =>
                      b.items.map((i, n) => (
                        <tr key={`${b.building}-${n}`} data-testid={`report-tally-row-${b.building}-${n}`}>
                          <td className="font-semibold">{b.building}</td>
                          <td>{i.description || "—"}</td>
                          <td className="text-slate-500">{i.category}</td>
                          <td className="text-slate-500">{i.date}</td>
                          <td className="num">{money(i.amount)}</td>
                        </tr>
                      )))}
                    <tr>
                      <td colSpan={4} className="font-semibold text-right">Total</td>
                      <td className="num font-semibold">{money(t?.on_behalf_of_building)}</td>
                    </tr>
                  </tbody>
                </table>
              </>
            ) : <p className="text-sm text-slate-500">Nothing paid on behalf of a building this month.</p>}
          </Card>
        </>
      )}
    </div>
  );
}
