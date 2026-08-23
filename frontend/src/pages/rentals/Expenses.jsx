import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { Trash2, Pencil, X, ReceiptText } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import { useRentRoll } from "@/hooks/useRentRoll";
import { PageHeader, Card, Stat, Empty } from "@/components/Common";
import { MediaUpload, MediaThumbs } from "@/components/MediaUpload";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { money, monthLabel } from "@/lib/format";

const CATEGORIES = [
  { value: "society_maintenance", label: "Society maintenance" },
  { value: "tax", label: "Property tax" },
  { value: "repair", label: "Repair / upkeep" },
  { value: "utility", label: "Utility bill" },
  { value: "other", label: "Other" },
];

export default function Expenses() {
  const { rentMonth, properties } = useApp();
  const [units, setUnits] = useState([]);
  const [rows, setRows] = useState([]);
  const [tick, setTick] = useState(0);
  const { roll } = useRentRoll(rentMonth, tick);
  const [editId, setEditId] = useState(null);
  const blank = {
    unit_id: "", category: "society_maintenance", description: "", amount: "",
    date: `${rentMonth}-01`, on_behalf_of_building: false, building_property_id: "",
  };
  const [form, setForm] = useState(blank);
  const [media, setMedia] = useState([]);

  const load = useCallback(async () => {
    const [u, e] = await Promise.all([
      api.get("/rentals/units"),
      api.get("/rentals/expenses", { params: { month: rentMonth } }),
    ]);
    setUnits(u.data); setRows(e.data);
  }, [rentMonth]);

  useEffect(() => { load(); setForm((f) => ({ ...f, date: `${rentMonth}-01` })); }, [load, rentMonth]);

  const submit = async (e) => {
    e.preventDefault();
    const payload = {
      ...form, month: rentMonth, amount: Number(form.amount || 0), media,
      building_property_id: form.on_behalf_of_building ? (form.building_property_id || null) : null,
    };
    try {
      if (editId) await api.put(`/rentals/expenses/${editId}`, payload);
      else await api.post("/rentals/expenses", payload);
      toast.success(editId ? "Bill updated" : "Bill recorded");
      setForm({ ...blank, unit_id: form.unit_id }); setMedia([]); setEditId(null);
      load(); setTick((t) => t + 1);
    } catch (err) { toast.error(errMsg(err)); }
  };

  const del = async (id) => {
    try { await api.delete(`/rentals/expenses/${id}`); load(); setTick((t) => t + 1); }
    catch (e) { toast.error(errMsg(e)); }
  };

  const unitName = (id) => units.find((u) => u.id === id)?.name || "—";
  const propName = (id) => properties.find((p) => p.id === id)?.name || "—";
  const t = roll?.totals;

  return (
    <div>
      <PageHeader title="Bills Paid" subtitle={`What you paid out on these properties · ${monthLabel(rentMonth)}`} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <Stat testId="exp-stat-total" label="Bills paid" value={money(t?.expenses)} tone="negative" />
        <Stat testId="exp-stat-onbehalf" label="On behalf of buildings" value={money(t?.on_behalf_of_building)}
              tone="warning" sub="Tallied separately with the building" />
        <Stat testId="exp-stat-collected" label="Rent collected" value={money(t?.rent_collected)} tone="positive" />
        <Stat testId="exp-stat-net" label="Net to owners" value={money(t?.net_to_owner)}
              tone={(t?.net_to_owner || 0) < 0 ? "negative" : "positive"} sub="Collected − bills" />
      </div>

      {roll?.building_tally?.length > 0 && (
        <Card title="Paid on behalf of buildings — tally separately" testId="building-tally-card" className="mb-8">
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead><tr><th>Building</th><th>Items</th><th className="text-right">Amount</th></tr></thead>
              <tbody>
                {roll.building_tally.map((b) => (
                  <tr key={b.building} data-testid={`tally-row-${b.building}`}>
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

      <div className="grid lg:grid-cols-[380px_1fr] gap-6 [&>*]:min-w-0">
        <Card title={editId ? "Edit bill" : "Record a bill paid"} testId="expense-form-card"
              action={editId && (
                <button onClick={() => { setEditId(null); setForm(blank); setMedia([]); }} data-testid="cancel-expense-edit-btn"
                        className="text-slate-400 hover:text-slate-900"><X className="w-4 h-4" /></button>
              )}>
          <form onSubmit={submit} className="space-y-4">
            <div>
              <Label className="label-caps">Property</Label>
              <Select value={form.unit_id} onValueChange={(v) => setForm({ ...form, unit_id: v })}>
                <SelectTrigger className="mt-2 h-11" data-testid="expense-unit-select"><SelectValue placeholder="Select property" /></SelectTrigger>
                <SelectContent>{units.map((u) => <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label className="label-caps">Category</Label>
              <Select value={form.category} onValueChange={(v) => setForm({ ...form, category: v })}>
                <SelectTrigger className="mt-2 h-11" data-testid="expense-category-select"><SelectValue /></SelectTrigger>
                <SelectContent>{CATEGORIES.map((c) => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label className="label-caps">Description</Label>
              <Input className="mt-2 h-11" data-testid="expense-desc-input"
                     value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </div>
            <div>
              <Label className="label-caps">Amount</Label>
              <Input type="number" inputMode="decimal" step="any" required className="mt-2 h-12 mono text-lg"
                     data-testid="expense-amount-input"
                     value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
            </div>
            <div>
              <Label className="label-caps">Date</Label>
              <Input type="date" className="mt-2 h-11" data-testid="expense-date-input"
                     value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
            </div>
            <div className="flex items-center justify-between border border-slate-200 rounded-md px-3 py-2.5">
              <div>
                <div className="text-sm font-medium text-slate-800">Paid on behalf of a building</div>
                <p className="text-xs text-slate-500">Tally this against the building separately</p>
              </div>
              <Switch checked={form.on_behalf_of_building} data-testid="expense-onbehalf-switch"
                      onCheckedChange={(v) => setForm({ ...form, on_behalf_of_building: v })} />
            </div>
            {form.on_behalf_of_building && (
              <div>
                <Label className="label-caps">Which building</Label>
                <Select value={form.building_property_id} onValueChange={(v) => setForm({ ...form, building_property_id: v })}>
                  <SelectTrigger className="mt-2 h-11" data-testid="expense-building-select"><SelectValue placeholder="Select building" /></SelectTrigger>
                  <SelectContent>{properties.map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            )}
            <MediaUpload media={media} setMedia={setMedia} testId="expense-media-bill"
                         category="bill" label="Bill / Receipt photo" />
            <Button type="submit" disabled={!form.unit_id} data-testid="save-expense-btn"
                    className="w-full h-12 bg-slate-900 text-white">
              <ReceiptText className="w-4 h-4 mr-2" /> {editId ? "Save changes" : "Record bill"}
            </Button>
          </form>
        </Card>

        <Card title={`Bills this month (${rows.length})`} testId="expenses-table-card">
          {!rows.length ? <Empty testId="expenses-empty" title="No bills recorded"
                                 hint="Society maintenance, tax and repairs you paid are deducted from that property's rent income." /> : (
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead><tr><th>Date</th><th>Property</th><th>Category</th><th>Description</th>
                  <th className="text-right">Amount</th><th>On behalf of</th><th>Bill</th><th /></tr></thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.id} data-testid={`expense-row-${r.id}`}>
                      <td>{r.date}</td>
                      <td className="font-semibold">{unitName(r.unit_id)}</td>
                      <td className="text-slate-600">{CATEGORIES.find((c) => c.value === r.category)?.label || r.category}</td>
                      <td>{r.description || "—"}</td>
                      <td className="num">{money(r.amount)}</td>
                      <td>{r.on_behalf_of_building
                        ? <span className="text-xs px-2 py-0.5 rounded border bg-amber-50 text-amber-800 border-amber-200">
                            {propName(r.building_property_id)}
                          </span>
                        : <span className="text-slate-300">—</span>}</td>
                      <td><MediaThumbs media={r.media} /></td>
                      <td className="text-right">
                        <div className="flex justify-end gap-2">
                          <button onClick={() => { setEditId(r.id); setForm({ ...r, amount: String(r.amount), building_property_id: r.building_property_id || "" }); setMedia(r.media || []); }}
                                  data-testid={`edit-expense-${r.id}`}
                                  className="text-slate-400 hover:text-slate-900"><Pencil className="w-4 h-4" /></button>
                          <button onClick={() => del(r.id)} data-testid={`delete-expense-${r.id}`}
                                  className="text-slate-400 hover:text-red-600"><Trash2 className="w-4 h-4" /></button>
                        </div>
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
