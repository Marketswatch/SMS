import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { Plus, Trash2, Pencil, X, Wallet } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import { useRentRoll } from "@/hooks/useRentRoll";
import { PageHeader, Card, Stat, Empty } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { money, monthLabel } from "@/lib/format";

const KINDS = [
  { value: "rent", label: "Rent received" },
  { value: "deposit", label: "Deposit received" },
  { value: "deposit_refund", label: "Deposit refunded" },
  { value: "deposit_deduction", label: "Deposit deduction" },
];

export default function Collections() {
  const { rentMonth } = useApp();
  const [units, setUnits] = useState([]);
  const [rows, setRows] = useState([]);
  const [tick, setTick] = useState(0);
  const { roll } = useRentRoll(rentMonth, tick);
  const [editId, setEditId] = useState(null);
  const blank = { unit_id: "", kind: "rent", amount: "", date: `${rentMonth}-01`, mode: "upi", notes: "" };
  const [form, setForm] = useState(blank);

  const load = useCallback(async () => {
    const [u, c] = await Promise.all([
      api.get("/rentals/units"),
      api.get("/rentals/collections", { params: { month: rentMonth } }),
    ]);
    setUnits(u.data); setRows(c.data);
  }, [rentMonth]);

  useEffect(() => { load(); setForm((f) => ({ ...f, date: `${rentMonth}-01` })); }, [load, rentMonth]);

  const submit = async (e) => {
    e.preventDefault();
    const payload = { ...form, month: rentMonth, amount: Number(form.amount || 0) };
    try {
      if (editId) await api.put(`/rentals/collections/${editId}`, payload);
      else await api.post("/rentals/collections", payload);
      toast.success(editId ? "Entry updated" : "Entry recorded");
      setForm({ ...blank, unit_id: form.unit_id, kind: form.kind }); setEditId(null);
      load(); setTick((t) => t + 1);
    } catch (err) { toast.error(errMsg(err)); }
  };

  const del = async (id) => {
    try { await api.delete(`/rentals/collections/${id}`); load(); setTick((t) => t + 1); }
    catch (e) { toast.error(errMsg(e)); }
  };

  const unitName = (id) => units.find((u) => u.id === id)?.name || "—";
  const t = roll?.totals;

  return (
    <div>
      <PageHeader title="Rent & Deposits" subtitle={`Money received from tenants · ${monthLabel(rentMonth)}`} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <Stat testId="coll-stat-due" label="Rent due" value={money(t?.rent_due)} />
        <Stat testId="coll-stat-collected" label="Rent collected" value={money(t?.rent_collected)} tone="positive" />
        <Stat testId="coll-stat-pending" label="Still pending" value={money(t?.pending)} tone="negative" />
        <Stat testId="coll-stat-deposit" label="Deposits held" value={money(t?.deposit_held)} />
      </div>

      <div className="grid lg:grid-cols-[380px_1fr] gap-6 [&>*]:min-w-0">
        <Card title={editId ? "Edit entry" : "Record money received"} testId="collection-form-card"
              action={editId && (
                <button onClick={() => { setEditId(null); setForm(blank); }} data-testid="cancel-collection-edit-btn"
                        className="text-slate-400 hover:text-slate-900"><X className="w-4 h-4" /></button>
              )}>
          <form onSubmit={submit} className="space-y-4">
            <div>
              <Label className="label-caps">Property</Label>
              <Select value={form.unit_id} onValueChange={(v) => setForm({ ...form, unit_id: v })}>
                <SelectTrigger className="mt-2 h-11" data-testid="collection-unit-select"><SelectValue placeholder="Select property" /></SelectTrigger>
                <SelectContent>{units.map((u) => <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label className="label-caps">Entry type</Label>
              <Select value={form.kind} onValueChange={(v) => setForm({ ...form, kind: v })}>
                <SelectTrigger className="mt-2 h-11" data-testid="collection-kind-select"><SelectValue /></SelectTrigger>
                <SelectContent>{KINDS.map((k) => <SelectItem key={k.value} value={k.value}>{k.label}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label className="label-caps">Amount</Label>
              <Input type="number" inputMode="decimal" step="any" required className="mt-2 h-12 mono text-lg"
                     data-testid="collection-amount-input"
                     value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="label-caps">Date</Label>
                <Input type="date" className="mt-2 h-11" data-testid="collection-date-input"
                       value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
              </div>
              <div>
                <Label className="label-caps">Mode</Label>
                <Select value={form.mode} onValueChange={(v) => setForm({ ...form, mode: v })}>
                  <SelectTrigger className="mt-2 h-11" data-testid="collection-mode-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {["upi", "bank", "cash", "cheque"].map((m) =>
                      <SelectItem key={m} value={m} className="uppercase">{m}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div>
              <Label className="label-caps">Notes</Label>
              <Input className="mt-2 h-11" data-testid="collection-notes-input"
                     value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
            </div>
            <Button type="submit" disabled={!form.unit_id} data-testid="save-collection-btn"
                    className="w-full h-12 bg-slate-900 text-white">
              <Wallet className="w-4 h-4 mr-2" /> {editId ? "Save changes" : "Record"}
            </Button>
          </form>
        </Card>

        <Card title={`Entries this month (${rows.length})`} testId="collections-table-card">
          {!rows.length ? <Empty testId="collections-empty" title="Nothing recorded yet"
                                 hint="Record rent as it comes in; deposits are tracked across all months." /> : (
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead><tr><th>Date</th><th>Property</th><th>Type</th><th className="text-right">Amount</th>
                  <th>Mode</th><th>Notes</th><th /></tr></thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.id} data-testid={`collection-row-${r.id}`}>
                      <td>{r.date}</td>
                      <td className="font-semibold">{unitName(r.unit_id)}</td>
                      <td>
                        <span className={`text-xs px-2 py-0.5 rounded border ${r.kind === "rent"
                          ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                          : r.kind === "deposit" ? "bg-blue-50 text-blue-700 border-blue-200"
                            : "bg-amber-50 text-amber-800 border-amber-200"}`}>
                          {KINDS.find((k) => k.value === r.kind)?.label || r.kind}
                        </span>
                      </td>
                      <td className="num">{money(r.amount)}</td>
                      <td className="uppercase text-slate-500 text-xs">{r.mode}</td>
                      <td className="text-slate-500">{r.notes || "—"}</td>
                      <td className="text-right">
                        <div className="flex justify-end gap-2">
                          <button onClick={() => { setEditId(r.id); setForm({ ...r, amount: String(r.amount) }); }}
                                  data-testid={`edit-collection-${r.id}`}
                                  className="text-slate-400 hover:text-slate-900"><Pencil className="w-4 h-4" /></button>
                          <button onClick={() => del(r.id)} data-testid={`delete-collection-${r.id}`}
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
