import { useState } from "react";
import { toast } from "sonner";
import { FileDown, FileText, FileSpreadsheet } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import { PageHeader, Card, Stat, Empty } from "@/components/Common";
import { ReconTable } from "@/components/ReconTable";
import { Button } from "@/components/ui/button";
import { money, monthLabel, num, litres } from "@/lib/format";
import { WaterUsageReport } from "@/components/WaterUsageReport";
import { useStatement } from "@/hooks/useStatement";

export default function MIS() {
  const { propertyId, month } = useApp();
  const { statement } = useStatement(propertyId, month);
  const [busy, setBusy] = useState("");

  const download = async (format) => {
    setBusy(format);
    try {
      const res = await api.get("/mis/export", {
        params: { property_id: propertyId, month, format }, responseType: "blob",
      });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `mis-${month}.${format}`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success(`${format.toUpperCase()} downloaded`);
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(""); }
  };

  const t = statement?.totals;

  return (
    <div>
      <PageHeader title="Month-End MIS" subtitle={`${statement?.property?.name || ""} · ${monthLabel(month)} · ${statement?.status || ""}`}>
        <Button variant="outline" onClick={() => download("xlsx")} disabled={busy} data-testid="export-xlsx-btn">
          <FileSpreadsheet className="w-4 h-4 mr-2" /> Excel
        </Button>
        <Button variant="outline" onClick={() => download("csv")} disabled={busy} data-testid="export-csv-btn">
          <FileDown className="w-4 h-4 mr-2" /> CSV
        </Button>
        <Button className="bg-slate-900 text-white" onClick={() => download("pdf")} disabled={busy} data-testid="export-pdf-btn">
          <FileText className="w-4 h-4 mr-2" /> PDF
        </Button>
      </PageHeader>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <Stat testId="mis-stat-water" label="Water spend (lorry + tips)" value={money(t?.total_water_spend)} sub={litres(t?.total_litres)} />
        <Stat testId="mis-stat-regular" label="Regular (recurring)" value={money(t?.recurring_total)} sub={`${money(t?.recurring_share)} / flat`} />
        <Stat testId="mis-stat-adhoc" label="Ad-hoc (repairs)" value={money(t?.maintenance_total)} sub={`${money(t?.maintenance_share)} / flat`} />
        <Stat testId="mis-stat-net" label="Net outstanding" value={money(t?.net_position)}
              tone={(t?.net_position || 0) > 0 ? "negative" : "positive"}
              sub={`${money(t?.total_owes)} receivable · ${money(t?.total_owed)} payable`} />
      </div>

      <Card title="Water reconciliation — owner-wise payable" testId="mis-table-card" className="mb-8">
        {!statement?.rows?.length ? <Empty testId="mis-empty" title="No data for this period" hint="Enter charges and readings to generate the MIS." /> : (
          <ReconTable rows={statement.rows} totals={t} testPrefix="mis" />
        )}
      </Card>

      <WaterUsageReport statement={statement} month={month} />

      <div className="grid lg:grid-cols-2 gap-6">
        <Card title="Water reconciliation" testId="mis-water-card">
          <dl className="divide-y divide-slate-100 text-sm">
            {[
              ["Total litres purchased", litres(t?.total_litres)],
              ["Tanker tips (part of water cost)", money(t?.total_tips)],
              ["Total water spend (lorry + tips)", money(t?.total_water_spend)],
              ["Average cost per litre", `₹${num(t?.avg_cost_per_litre, 4)}`],
              ["Total consumed (all meters)", litres(t?.total_consumed)],
              [t?.reserve_litres < 0 ? "Reserve drawdown" : "Reserve remaining", litres(t?.reserve_litres)],
              ["Reserve value", money(t?.reserve_value)],
              ["Reserve share per flat", money(t?.reserve_share)],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between py-2">
                <dt className="text-slate-600">{k}</dt><dd className="mono font-medium">{v}</dd>
              </div>
            ))}
          </dl>
        </Card>
        <Card title="Charge bifurcation" testId="mis-charges-card">
          <div className="text-sm">
            <div className="label-caps mb-2">Regular / recurring</div>
            {statement?.recurring_items?.length ? statement.recurring_items.map((c) => (
              <div key={c.id} className="flex justify-between py-1.5 border-b border-slate-100">
                <span className="capitalize text-slate-700">{c.charge_type}{c.person_name ? ` · ${c.person_name}` : ""}</span>
                <span className="mono">{money(c.amount)}</span>
              </div>
            )) : <p className="text-slate-400">None</p>}
            <div className="label-caps mt-6 mb-2">Ad-hoc / one-time</div>
            {statement?.adhoc_items?.length ? statement.adhoc_items.map((c) => (
              <div key={c.id} className="flex justify-between py-1.5 border-b border-slate-100">
                <span className="text-slate-700">{c.description}</span>
                <span className="mono">{money(c.amount)}</span>
              </div>
            )) : <p className="text-slate-400">None</p>}
          </div>
        </Card>
      </div>
    </div>
  );
}
