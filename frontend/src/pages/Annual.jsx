import { useEffect, useState } from "react";
import { toast } from "sonner";
import { FileDown, FileText } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import { PageHeader, Card, Stat, NetBadge, Empty } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { money, num, litres, monthLabel } from "@/lib/format";

export default function Annual() {
  const { propertyId, month } = useApp();
  const [year, setYear] = useState(Number((month || "").slice(0, 4)) || new Date().getFullYear());
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState("");

  useEffect(() => {
    if (!propertyId) return;
    api.get("/annual", { params: { property_id: propertyId, year } }).then(({ data }) => setData(data));
  }, [propertyId, year]);

  const download = async (format) => {
    setBusy(format);
    try {
      const res = await api.get("/annual/export", {
        params: { property_id: propertyId, year, format }, responseType: "blob",
      });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `annual-${year}.${format}`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success(`${format.toUpperCase()} downloaded`);
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(""); }
  };

  const years = Array.from({ length: 5 }, (_, i) => new Date().getFullYear() - 2 + i);
  const t = data?.totals;

  return (
    <div>
      <PageHeader title="Annual Statement" subtitle={`${data?.property?.name || ""} · year-to-date per owner`}>
        <Select value={String(year)} onValueChange={(v) => setYear(Number(v))}>
          <SelectTrigger className="h-10 w-[110px]" data-testid="annual-year-select"><SelectValue /></SelectTrigger>
          <SelectContent>{years.map((y) => <SelectItem key={y} value={String(y)}>{y}</SelectItem>)}</SelectContent>
        </Select>
        <Button variant="outline" onClick={() => download("csv")} disabled={busy} data-testid="annual-export-csv-btn">
          <FileDown className="w-4 h-4 mr-2" /> CSV
        </Button>
        <Button className="bg-slate-900 text-white" onClick={() => download("pdf")} disabled={busy} data-testid="annual-export-pdf-btn">
          <FileText className="w-4 h-4 mr-2" /> PDF
        </Button>
      </PageHeader>

      {!data?.months?.length ? (
        <Empty testId="annual-empty" title={`No months recorded in ${year}`}
               hint="Once a month has water, charges or readings entered it appears in the annual statement." />
      ) : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            <Stat testId="annual-stat-months" label="Months recorded" value={String(t.months_recorded)}
                  sub={`${data.rows.length} flats`} />
            <Stat testId="annual-stat-water" label="Water spend" value={money(t.water_spend)} sub={litres(t.litres)} />
            <Stat testId="annual-stat-billed" label="Total billed" value={money(t.billable_total)}
                  sub={`Recurring ${money(t.recurring_total)} · repairs ${money(t.maintenance_total)}`} />
            <Stat testId="annual-stat-closing" label="Closing position" value={money(t.closing_position)}
                  tone={t.closing_position > 0 ? "negative" : "positive"} sub={`Collected ${money(t.received)}`} />
          </div>

          <Card title={`Per-owner summary — ${year}`} testId="annual-owner-card" className="mb-6">
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead><tr><th className="text-right">S.No</th><th>Flat</th><th>Owner</th><th className="text-right">Consumption (L)</th>
                  <th className="text-right">Water</th><th className="text-right">Recurring</th>
                  <th className="text-right">Repairs</th><th className="text-right">Total billed</th>
                  <th className="text-right">Fronted</th><th className="text-right">Paid</th>
                  <th>Closing balance</th></tr></thead>
                <tbody>
                  {data.rows.map((r, i) => (
                    <tr key={r.flat_id} data-testid={`annual-row-${r.flat_number}`}>
                      <td className="num text-slate-500">{i + 1}</td>
                      <td className="font-semibold">{r.flat_number}</td>
                      <td>{r.owner_name}</td>
                      <td className="num">{num(r.consumption)}</td>
                      <td className="num">{money(r.water_cost)}</td>
                      <td className="num">{money(r.recurring)}</td>
                      <td className="num">{money(r.maintenance)}</td>
                      <td className="num font-semibold">{money(r.billable)}</td>
                      <td className="num text-emerald-700">{money(r.contributions)}</td>
                      <td className="num">{money(r.received)}</td>
                      <td><NetBadge value={r.closing_balance} testId={`annual-net-${r.flat_number}`} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <Card title="Month by month" testId="annual-months-card">
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead><tr><th className="text-right">S.No</th><th>Month</th><th>Status</th><th className="text-right">Litres</th>
                  <th className="text-right">Water spend</th><th className="text-right">Avg ₹/L</th>
                  <th className="text-right">Recurring</th><th className="text-right">Repairs</th>
                  <th className="text-right">Billed</th><th className="text-right">Collected</th></tr></thead>
                <tbody>
                  {data.months.map((m, i) => (
                    <tr key={m.month} data-testid={`annual-month-${m.month}`}>
                      <td className="num text-slate-500">{i + 1}</td>
                      <td className="font-semibold">{monthLabel(m.month)}</td>
                      <td>
                        <span className={`text-xs px-2 py-0.5 rounded border ${m.status === "locked"
                          ? "bg-slate-900 text-white border-slate-900" : "bg-emerald-50 text-emerald-700 border-emerald-200"}`}>
                          {m.status}
                        </span>
                      </td>
                      <td className="num">{num(m.litres, 0)}</td>
                      <td className="num">{money(m.water_spend)}</td>
                      <td className="num">{num(m.avg_cost_per_litre, 4)}</td>
                      <td className="num">{money(m.recurring_total)}</td>
                      <td className="num">{money(m.maintenance_total)}</td>
                      <td className="num font-semibold">{money(m.billable_total)}</td>
                      <td className="num">{money(m.received)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
