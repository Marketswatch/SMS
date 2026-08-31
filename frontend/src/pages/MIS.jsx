import { useState } from "react";
import { toast } from "sonner";
import { FileDown, FileText, FileSpreadsheet, MessageCircle } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import { PageHeader, Card, Stat, Empty } from "@/components/Common";
import { ReconTable } from "@/components/ReconTable";
import { Button } from "@/components/ui/button";
import { money, monthLabel, num, litres } from "@/lib/format";
import { WaterUsageReport } from "@/components/WaterUsageReport";
import { useStatement } from "@/hooks/useStatement";

const PACK_REPORTS = [
  ["meters", "Water usage charges — as per meter readings"],
  ["purchases", "Total water purchases for the month"],
  ["recurring", "Recurring entries — monthly report"],
  ["reconciliation", "Water reconciliation — owner statement"],
];

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

  const downloadPack = async (report, format) => {
    setBusy(`${report}-${format}`);
    try {
      const res = await api.get("/reports/pack", {
        params: { property_id: propertyId, month, report, format }, responseType: "blob",
      });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${report === "all" ? "month-end-pack" : report}-${month}.${format}`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success(format === "zip" ? "Pack downloaded" : `${report === "all" ? "Pack" : "Report"} ${format.toUpperCase()} downloaded`);
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(""); }
  };

  const shareOnWhatsApp = async () => {
    await downloadPack("all", "zip");
    const t2 = statement?.totals;
    const msg = [
      `*${statement?.property?.name || "Building"} — month-end report pack*`,
      monthLabel(month),
      "",
      `Water purchased: ${num(t2?.total_litres, 0)} L · ${money(t2?.total_water_spend)}`,
      `Recurring: ${money(t2?.recurring_total)} · Repairs: ${money(t2?.maintenance_total)}`,
      `Total billed: ${money(t2?.billable_total)} · Per house: ${money((t2?.billable_total || 0) / (t2?.flat_count || 1))}`,
      "",
      "Reports attached: water usage as per meter readings, water purchases, recurring entries and the owner reconciliation statement.",
    ].join("\n");
    window.open(`https://wa.me/?text=${encodeURIComponent(msg)}`, "_blank", "noopener");
    toast.info("Files downloaded — attach them in the WhatsApp window that just opened");
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

      <Card title="Month-end owner pack" testId="report-pack-card" className="mb-8">
        <p className="text-sm text-slate-600 mb-4">
          Colour-coded PDFs (and WhatsApp-ready images) of the four owner reports, each sorted by floor
          then flat number. Download, then share with the owners or your building WhatsApp group.
        </p>
        <div className="flex flex-wrap gap-2 mb-5">
          <Button className="bg-slate-900 text-white" disabled={!!busy} data-testid="pack-combined-pdf-btn"
                  onClick={() => downloadPack("all", "pdf")}>
            <FileText className="w-4 h-4 mr-2" /> Combined PDF (all 4 reports)
          </Button>
          <Button variant="outline" disabled={!!busy} data-testid="pack-zip-btn"
                  onClick={() => downloadPack("all", "zip")}>
            <FileDown className="w-4 h-4 mr-2" /> Zip — every report as PDF + image
          </Button>
          <Button variant="outline" disabled={!!busy} data-testid="pack-whatsapp-btn"
                  onClick={shareOnWhatsApp}>
            <MessageCircle className="w-4 h-4 mr-2 text-emerald-700" /> Share on WhatsApp
          </Button>
        </div>
        <div className="grid sm:grid-cols-2 gap-3">
          {PACK_REPORTS.map(([key, label]) => (
            <div key={key} className="flex items-center justify-between gap-3 border border-slate-200 rounded-md px-3 py-2.5">
              <span className="text-sm">{label}</span>
              <div className="flex gap-1.5 shrink-0">
                <button onClick={() => downloadPack(key, "pdf")} disabled={!!busy}
                        data-testid={`pack-${key}-pdf-btn`} title="Download PDF"
                        className="px-2.5 py-1.5 text-xs border border-slate-300 rounded hover:bg-slate-100">PDF</button>
                <button onClick={() => downloadPack(key, "png")} disabled={!!busy}
                        data-testid={`pack-${key}-png-btn`} title="Download image for WhatsApp"
                        className="px-2.5 py-1.5 text-xs border border-slate-300 rounded hover:bg-slate-100">Image</button>
              </div>
            </div>
          ))}
        </div>
      </Card>

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
