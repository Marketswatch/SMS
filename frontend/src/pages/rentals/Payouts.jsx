import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { Trash2, Building2, ArrowUpRight } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import { useRentStatement, useCategories } from "@/hooks/useRentStatement";
import { PageHeader, Card, Stat, Empty } from "@/components/Common";
import { CategorySelect } from "@/components/CategorySelect";
import { MediaUpload, MediaThumbs } from "@/components/MediaUpload";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { money, monthLabel } from "@/lib/format";
import { MODES, modeLabel } from "@/lib/modes";

export default function Payouts() {
  const { rentMonth, properties } = useApp();
  const { cats, addCategory } = useCategories();
  const [tick, setTick] = useState(0);
  const { stmt } = useRentStatement(rentMonth, tick);
  const [rows, setRows] = useState([]);
  const blank = { building_property_id: "", building_name: "", unit_id: "", amount: "",
                  date: `${rentMonth}-01`, category: "", note: "", is_credit: false,
                  mode: "bank", reference: "" };
  const [form, setForm] = useState(blank);

  useEffect(() => {
    if (!cats.length) return;
    const pref = cats.find((c) => /maintenance/i.test(c.name)) || cats[0];
    setForm((f) => (f.category ? f : { ...f, category: pref.name }));
  }, [cats]);
  const [media, setMedia] = useState([]);

  const load = useCallback(async () => {
    const { data } = await api.get("/rentals/payouts", { params: { month: rentMonth } });
    setRows(data);
  }, [rentMonth]);
  useEffect(() => { load(); setForm((f) => ({ ...f, date: `${rentMonth}-01` })); }, [load, rentMonth]);

  const submit = async (e) => {
    e.preventDefault();
    try {
      await api.post("/rentals/payouts", {
        ...form, month: rentMonth, amount: Number(form.amount || 0),
        building_property_id: form.building_property_id || null,
        unit_id: form.unit_id || null, media,
      });
      toast.success(form.is_credit ? "Credit recorded against the building" : "Payout recorded");
      setForm({ ...blank, building_property_id: form.building_property_id, building_name: form.building_name,
                category: form.category, date: form.date, mode: form.mode });
      setMedia([]); load(); setTick((t) => t + 1);
    } catch (err) { toast.error(errMsg(err)); }
  };

  const unitName = (id) => stmt?.rows?.find((r) => r.unit_id === id)?.name || "—";
  const buildingLabel = (p) => properties.find((x) => x.id === p.building_property_id)?.name || p.building_name || "Unassigned";
  const t = stmt?.totals;

  return (
    <div>
      <PageHeader title="Payouts to Buildings" subtitle={`What I owe each building / association · ${monthLabel(rentMonth)}`} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <Stat testId="pay-stat-payable" label="Payable to buildings" value={money(t?.building_payable)}
              sub="Maintenance + ad-hoc collected" />
        <Stat testId="pay-stat-paid" label="Paid" value={money(t?.building_paid)} tone="positive" />
        <Stat testId="pay-stat-credits" label="Credits" value={money(t?.building_credits)} tone="warning"
              sub="Bills I / the tenant paid for them" />
        <Stat testId="pay-stat-balance" label="Still to pay" value={money(t?.building_balance)}
              tone={(t?.building_balance || 0) > 0 ? "negative" : "positive"} />
      </div>

      <Card title="Building settlement" testId="settlement-card" className="mb-8">
        {!stmt?.buildings?.length ? (
          <Empty testId="settlement-empty" title="Nothing to settle yet"
                 hint="Enter this month's bills — the maintenance you collect becomes what you owe the building." />
        ) : (
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead><tr><th>Building / association</th><th>Properties</th><th className="text-right">Payable</th>
                <th className="text-right">Paid</th><th className="text-right">Credits</th>
                <th className="text-right">Balance</th></tr></thead>
              <tbody>
                {stmt.buildings.map((b) => (
                  <tr key={b.key} data-testid={`settlement-row-${b.building}`}>
                    <td className="font-semibold">{b.building}</td>
                    <td className="text-slate-500 text-xs">
                      {b.units.map((u) => `${u.name} (${money(u.maintenance_payable + u.adhoc_payable)})`).join(", ") || "—"}
                    </td>
                    <td className="num">{money(b.payable)}</td>
                    <td className="num text-emerald-700">{money(b.paid)}</td>
                    <td className="num text-amber-700">{money(b.credits)}</td>
                    <td className={`num font-semibold ${b.balance > 0 ? "text-red-600" : "text-emerald-700"}`}>{money(b.balance)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className="grid lg:grid-cols-[380px_1fr] gap-6 [&>*]:min-w-0">
        <Card title="Record a payout or credit" testId="payout-form-card">
          <form onSubmit={submit} className="space-y-4">
            <div>
              <Label className="label-caps">Building I maintain here</Label>
              <Select value={form.building_property_id || "none"}
                      onValueChange={(v) => setForm({ ...form, building_property_id: v === "none" ? "" : v })}>
                <SelectTrigger className="mt-2 h-11" data-testid="payout-building-select"><SelectValue placeholder="Outside building" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Not in SocietyHub — type the name</SelectItem>
                  {properties.map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            {!form.building_property_id && (
              <div>
                <Label className="label-caps">Building / association name</Label>
                <Input className="mt-2 h-11" data-testid="payout-building-name-input"
                       value={form.building_name} onChange={(e) => setForm({ ...form, building_name: e.target.value })} />
              </div>
            )}
            <div>
              <Label className="label-caps">For which property (optional)</Label>
              <Select value={form.unit_id || "none"} onValueChange={(v) => setForm({ ...form, unit_id: v === "none" ? "" : v })}>
                <SelectTrigger className="mt-2 h-11" data-testid="payout-unit-select"><SelectValue placeholder="All / not specific" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Not property specific</SelectItem>
                  {stmt?.rows?.map((r) => <SelectItem key={r.unit_id} value={r.unit_id}>{r.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="label-caps">Category</Label>
              <div className="mt-2">
                <CategorySelect value={form.category} cats={cats} addCategory={addCategory}
                                testId="payout-category" onChange={(v) => setForm({ ...form, category: v })} />
              </div>
            </div>
            <div>
              <Label className="label-caps">Amount</Label>
              <Input type="number" inputMode="decimal" step="any" required className="mt-2 h-12 mono text-lg"
                     data-testid="payout-amount-input" value={form.amount}
                     onChange={(e) => setForm({ ...form, amount: e.target.value })} />
            </div>
            <div>
              <Label className="label-caps">Date</Label>
              <Input type="date" className="mt-2 h-11" data-testid="payout-date-input"
                     value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
            </div>
            <div>
              <Label className="label-caps">Payment mode</Label>
              <Select value={form.mode}
                      onValueChange={(v) => setForm({ ...form, mode: v, reference: v === "cash" ? "" : form.reference })}>
                <SelectTrigger className="mt-2 h-11" data-testid="payout-mode-select"><SelectValue /></SelectTrigger>
                <SelectContent>{MODES.map((m) => <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            {form.mode !== "cash" && !form.is_credit && (
              <div>
                <Label className="label-caps">Reference / UPI txn no.</Label>
                <Input className="mt-2 h-11 mono" required data-testid="payout-reference-input"
                       placeholder="UPI ref / bank txn no." value={form.reference}
                       onChange={(e) => setForm({ ...form, reference: e.target.value })} />
              </div>
            )}
            <div className="flex items-center justify-between border border-slate-200 rounded-md px-3 py-2.5">
              <div>
                <div className="text-sm font-medium text-slate-800">This is a credit, not a payout</div>
                <p className="text-xs text-slate-500">A bill I paid for them — set off against my payable</p>
              </div>
              <Switch checked={form.is_credit} data-testid="payout-credit-switch"
                      onCheckedChange={(v) => setForm({ ...form, is_credit: v })} />
            </div>
            <div>
              <Label className="label-caps">Note</Label>
              <Input className="mt-2 h-11" data-testid="payout-note-input"
                     value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
            </div>
            <MediaUpload media={media} setMedia={setMedia} testId="payout-media" category="bill" label="Bill / receipt photo" />
            <Button type="submit" data-testid="save-payout-btn" className="w-full h-12 bg-slate-900 text-white">
              {form.is_credit ? <ArrowUpRight className="w-4 h-4 mr-2" /> : <Building2 className="w-4 h-4 mr-2" />}
              {form.is_credit ? "Record credit" : "Record payout"}
            </Button>
          </form>
        </Card>

        <Card title={`Entries this month (${rows.length})`} testId="payouts-table-card">
          {!rows.length ? <Empty testId="payouts-empty" title="No payouts yet"
                                 hint="Record what you pay the building, and any bill you paid on their behalf as a credit." /> : (
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead><tr><th>Date</th><th>Building</th><th>Property</th><th>Category</th>
                  <th className="text-right">Amount</th><th>Mode</th><th>Reference</th><th>Type</th><th>Bill</th><th /></tr></thead>
                <tbody>
                  {rows.map((p) => (
                    <tr key={p.id} data-testid={`payout-row-${p.id}`}>
                      <td>{p.date}</td>
                      <td className="font-semibold">{buildingLabel(p)}</td>
                      <td className="text-slate-500">{p.unit_id ? unitName(p.unit_id) : "—"}</td>
                      <td>{p.category}{p.note ? <span className="text-slate-400"> · {p.note}</span> : ""}</td>
                      <td className="num">{money(p.amount)}</td>
                      <td className="text-xs text-slate-500">{p.is_credit ? "—" : modeLabel(p.mode)}</td>
                      <td className="mono text-xs text-slate-500" data-testid={`payout-reference-${p.id}`}>{p.reference || "—"}</td>
                      <td>
                        <span className={`text-xs px-2 py-0.5 rounded border ${p.is_credit
                          ? "bg-amber-50 text-amber-800 border-amber-200" : "bg-emerald-50 text-emerald-700 border-emerald-200"}`}>
                          {p.is_credit ? "Credit" : "Paid"}
                        </span>
                      </td>
                      <td><MediaThumbs media={p.media} /></td>
                      <td className="text-right">
                        <button onClick={async () => { await api.delete(`/rentals/payouts/${p.id}`); load(); setTick((x) => x + 1); }}
                                data-testid={`delete-payout-${p.id}`}
                                className="text-slate-400 hover:text-red-600"><Trash2 className="w-4 h-4" /></button>
                      </td>
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
