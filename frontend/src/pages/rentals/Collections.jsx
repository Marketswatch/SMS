import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { Wallet, Trash2, FileText, MessageCircle, Wand2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import { useRentStatement } from "@/hooks/useRentStatement";
import { PageHeader, Card, Stat, Empty } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { money, monthLabel, plainAmt } from "@/lib/format";
import { openWhatsApp } from "@/lib/notify";

const DEP_KINDS = [
  { value: "deposit", label: "Deposit received" },
  { value: "deposit_refund", label: "Deposit refunded" },
  { value: "deposit_deduction", label: "Deposit deduction" },
];

export default function Collections() {
  const { rentMonth } = useApp();
  const [tick, setTick] = useState(0);
  const { stmt } = useRentStatement(rentMonth, tick);
  const [payments, setPayments] = useState([]);
  const [deposits, setDeposits] = useState([]);
  const blank = { unit_id: "", date: `${rentMonth}-01`, rent_paid: "", maintenance_paid: "", adhoc_paid: "", mode: "upi", notes: "" };
  const [form, setForm] = useState(blank);
  const [dep, setDep] = useState({ unit_id: "", kind: "deposit", amount: "", date: `${rentMonth}-01`, mode: "bank", notes: "" });

  const load = useCallback(async () => {
    const [p, d] = await Promise.all([
      api.get("/rentals/payments", { params: { month: rentMonth } }),
      api.get("/rentals/deposits"),
    ]);
    setPayments(p.data); setDeposits(d.data);
  }, [rentMonth]);

  useEffect(() => {
    load();
    setForm((f) => ({ ...f, date: `${rentMonth}-01` }));
    setDep((f) => ({ ...f, date: `${rentMonth}-01` }));
  }, [load, rentMonth]);

  const row = stmt?.rows?.find((r) => r.unit_id === form.unit_id);

  const autofill = () => {
    if (!row) return;
    setForm({ ...form, rent_paid: String(row.rent_outstanding), maintenance_paid: String(row.maintenance_outstanding),
              adhoc_paid: String(Math.max(row.adhoc_outstanding, 0)) });
    toast.success("Filled from what's outstanding");
  };

  const total = Number(form.rent_paid || 0) + Number(form.maintenance_paid || 0) + Number(form.adhoc_paid || 0);

  const submit = async (e) => {
    e.preventDefault();
    try {
      await api.post("/rentals/payments", {
        unit_id: form.unit_id, month: rentMonth, date: form.date,
        rent_paid: Number(form.rent_paid || 0), maintenance_paid: Number(form.maintenance_paid || 0),
        adhoc_paid: Number(form.adhoc_paid || 0), mode: form.mode, notes: form.notes,
      });
      toast.success("Collection recorded and allocated");
      setForm({ ...blank, unit_id: form.unit_id, date: form.date });
      load(); setTick((t) => t + 1);
    } catch (err) { toast.error(errMsg(err)); }
  };

  const submitDep = async (e) => {
    e.preventDefault();
    try {
      await api.post("/rentals/deposits", { ...dep, month: rentMonth, amount: Number(dep.amount || 0) });
      toast.success("Deposit entry recorded");
      setDep({ ...dep, amount: "", notes: "" });
      load(); setTick((t) => t + 1);
    } catch (err) { toast.error(errMsg(err)); }
  };

  const unitName = (id) => stmt?.rows?.find((r) => r.unit_id === id)?.name || "—";
  const unitOf = (id) => stmt?.rows?.find((r) => r.unit_id === id);

  const receipt = async (p) => {
    try {
      const res = await api.get(`/rentals/payments/${p.id}/receipt`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = `receipt-${p.month}.pdf`; a.click();
      URL.revokeObjectURL(url);
      toast.success("Receipt downloaded");
    } catch (e) { toast.error(errMsg(e)); }
  };

  const shareReceipt = (p) => {
    const u = unitOf(p.unit_id);
    openWhatsApp(u?.tenant_phone, [`${u?.name} — ${monthLabel(p.month)}`,
      `Received ${plainAmt(p.total)} on ${p.date} (${String(p.mode).toUpperCase()})`,
      `Rent ${plainAmt(p.rent_paid)} · Maintenance ${plainAmt(p.maintenance_paid)} · Ad-hoc ${plainAmt(p.adhoc_paid)}`,
      "Thank you."].join("\n"));
  };

  const t = stmt?.totals;

  return (
    <div>
      <PageHeader title="Collections" subtitle={`Money received, split by head · ${monthLabel(rentMonth)}`} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <Stat testId="col-stat-tocollect" label="To collect" value={money(t?.total_to_collect)} />
        <Stat testId="col-stat-collected" label="Collected" value={money(t?.collected)} tone="positive"
              sub={`Rent ${money(t?.rent_paid)} · maint ${money(t?.maintenance_paid)} · ad-hoc ${money(t?.adhoc_paid)}`} />
        <Stat testId="col-stat-balance" label="Balance" value={money(t?.balance)} tone="negative"
              sub={`${money(t?.overdue)} overdue`} />
        <Stat testId="col-stat-deposit" label="Deposits held" value={money(t?.deposit_held)} />
      </div>

      <Tabs defaultValue="rent">
        <TabsList className="h-auto bg-transparent p-0 gap-2 mb-6">
          <TabsTrigger value="rent" data-testid="collections-tab-rent"
                       className="data-[state=active]:bg-slate-900 data-[state=active]:text-white border border-slate-200 rounded-md px-3 py-1.5 text-sm">Rent & maintenance</TabsTrigger>
          <TabsTrigger value="deposit" data-testid="collections-tab-deposit"
                       className="data-[state=active]:bg-slate-900 data-[state=active]:text-white border border-slate-200 rounded-md px-3 py-1.5 text-sm">Deposits</TabsTrigger>
        </TabsList>

        <TabsContent value="rent">
          <div className="grid lg:grid-cols-[380px_1fr] gap-6 [&>*]:min-w-0">
            <Card title="Record a collection" testId="collection-form-card">
              <form onSubmit={submit} className="space-y-4">
                <div>
                  <Label className="label-caps">Property</Label>
                  <Select value={form.unit_id} onValueChange={(v) => setForm({ ...form, unit_id: v })}>
                    <SelectTrigger className="mt-2 h-11" data-testid="collection-unit-select"><SelectValue placeholder="Select property" /></SelectTrigger>
                    <SelectContent>
                      {stmt?.rows?.map((r) => <SelectItem key={r.unit_id} value={r.unit_id}>{r.name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                {row && (
                  <div className="bg-slate-50 border border-slate-200 rounded-md px-3 py-2 text-xs space-y-1" data-testid="collection-outstanding">
                    <div className="flex justify-between"><span>Rent outstanding</span><span className="mono">{money(row.rent_outstanding)}</span></div>
                    <div className="flex justify-between"><span>Maintenance outstanding</span><span className="mono">{money(row.maintenance_outstanding)}</span></div>
                    <div className="flex justify-between"><span>Ad-hoc outstanding</span><span className="mono">{money(row.adhoc_outstanding)}</span></div>
                    <Button type="button" variant="outline" className="h-8 w-full mt-1" onClick={autofill} data-testid="collection-autofill-btn">
                      <Wand2 className="w-3.5 h-3.5 mr-1.5" /> Fill from outstanding
                    </Button>
                  </div>
                )}
                <div className="grid grid-cols-3 gap-2">
                  {[["rent_paid", "Rent"], ["maintenance_paid", "Maint."], ["adhoc_paid", "Ad-hoc"]].map(([k, lbl]) => (
                    <div key={k}>
                      <Label className="label-caps">{lbl}</Label>
                      <Input type="number" inputMode="decimal" step="any" className="mt-2 h-12 mono"
                             data-testid={`collection-${k}-input`} value={form[k]}
                             onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
                    </div>
                  ))}
                </div>
                <div className="bg-slate-50 border border-slate-200 rounded-md px-3 py-2 flex justify-between text-sm">
                  <span className="text-slate-500">Total received</span>
                  <span className="mono font-semibold" data-testid="collection-total">{money(total)}</span>
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
                      <SelectContent>{["upi", "bank", "cash", "cheque"].map((m) => <SelectItem key={m} value={m} className="uppercase">{m}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                </div>
                <div>
                  <Label className="label-caps">Notes</Label>
                  <Input className="mt-2 h-11" data-testid="collection-notes-input"
                         value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
                </div>
                <Button type="submit" disabled={!form.unit_id || total <= 0} data-testid="save-collection-btn"
                        className="w-full h-12 bg-slate-900 text-white">
                  <Wallet className="w-4 h-4 mr-2" /> Record collection
                </Button>
              </form>
            </Card>

            <div className="space-y-6">
              <Card title="Position per property" testId="collection-position-card">
                {!stmt?.rows?.length ? <Empty testId="position-empty" title="No properties yet" hint="Add properties first." /> : (
                  <div className="overflow-x-auto">
                    <table className="data-table">
                      <thead><tr><th>Property</th><th className="text-right">To collect</th>
                        <th className="text-right">Rent in</th><th className="text-right">Maint. in</th>
                        <th className="text-right">Ad-hoc in</th><th className="text-right">Balance</th><th>Status</th></tr></thead>
                      <tbody>
                        {stmt.rows.map((r) => (
                          <tr key={r.unit_id} data-testid={`position-row-${r.name}`}>
                            <td className="font-semibold">{r.name}</td>
                            <td className="num">{money(r.total_to_collect)}</td>
                            <td className="num text-emerald-700">{money(r.rent_paid)}</td>
                            <td className="num text-emerald-700">{money(r.maintenance_paid)}</td>
                            <td className="num text-emerald-700">{money(r.adhoc_paid)}</td>
                            <td className={`num font-semibold ${r.balance > 0 ? "text-red-600" : ""}`}>{money(r.balance)}</td>
                            <td><span className="text-xs capitalize text-slate-500">{r.status}</span></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>

              <Card title={`Collections this month (${payments.length})`} testId="collections-table-card">
                {!payments.length ? <Empty testId="collections-empty" title="Nothing collected yet" hint="Record money as it comes in." /> : (
                  <div className="overflow-x-auto">
                    <table className="data-table">
                      <thead><tr><th>Date</th><th>Property</th><th className="text-right">Rent</th>
                        <th className="text-right">Maint.</th><th className="text-right">Ad-hoc</th>
                        <th className="text-right">Total</th><th>Mode</th><th /></tr></thead>
                      <tbody>
                        {payments.map((p) => (
                          <tr key={p.id} data-testid={`payment-row-${p.id}`}>
                            <td>{p.date}</td>
                            <td className="font-semibold">{unitName(p.unit_id)}</td>
                            <td className="num">{money(p.rent_paid)}</td>
                            <td className="num">{money(p.maintenance_paid)}</td>
                            <td className="num">{money(p.adhoc_paid)}</td>
                            <td className="num font-semibold">{money(p.total)}</td>
                            <td className="uppercase text-xs text-slate-500">{p.mode}</td>
                            <td className="text-right">
                              <div className="flex justify-end gap-2">
                                <button onClick={() => receipt(p)} data-testid={`receipt-btn-${p.id}`} title="Receipt PDF"
                                        className="text-slate-400 hover:text-slate-900"><FileText className="w-4 h-4" /></button>
                                {unitOf(p.unit_id)?.tenant_phone && (
                                  <button onClick={() => shareReceipt(p)} data-testid={`receipt-share-${p.id}`} title="Send on WhatsApp"
                                          className="text-slate-400 hover:text-emerald-700"><MessageCircle className="w-4 h-4" /></button>
                                )}
                                <button onClick={async () => { await api.delete(`/rentals/payments/${p.id}`); load(); setTick((x) => x + 1); }}
                                        data-testid={`delete-payment-${p.id}`}
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
        </TabsContent>

        <TabsContent value="deposit">
          <div className="grid lg:grid-cols-[380px_1fr] gap-6 [&>*]:min-w-0">
            <Card title="Deposit entry" testId="deposit-form-card">
              <form onSubmit={submitDep} className="space-y-4">
                <div>
                  <Label className="label-caps">Property</Label>
                  <Select value={dep.unit_id} onValueChange={(v) => setDep({ ...dep, unit_id: v })}>
                    <SelectTrigger className="mt-2 h-11" data-testid="deposit-unit-select"><SelectValue placeholder="Select property" /></SelectTrigger>
                    <SelectContent>{stmt?.rows?.map((r) => <SelectItem key={r.unit_id} value={r.unit_id}>{r.name}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="label-caps">Entry type</Label>
                  <Select value={dep.kind} onValueChange={(v) => setDep({ ...dep, kind: v })}>
                    <SelectTrigger className="mt-2 h-11" data-testid="deposit-kind-select"><SelectValue /></SelectTrigger>
                    <SelectContent>{DEP_KINDS.map((k) => <SelectItem key={k.value} value={k.value}>{k.label}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="label-caps">Amount</Label>
                  <Input type="number" inputMode="decimal" step="any" required className="mt-2 h-12 mono text-lg"
                         data-testid="deposit-amount-input" value={dep.amount}
                         onChange={(e) => setDep({ ...dep, amount: e.target.value })} />
                </div>
                <div>
                  <Label className="label-caps">Date</Label>
                  <Input type="date" className="mt-2 h-11" data-testid="deposit-date-input"
                         value={dep.date} onChange={(e) => setDep({ ...dep, date: e.target.value })} />
                </div>
                <div>
                  <Label className="label-caps">Notes</Label>
                  <Input className="mt-2 h-11" data-testid="deposit-notes-input"
                         value={dep.notes} onChange={(e) => setDep({ ...dep, notes: e.target.value })} />
                </div>
                <Button type="submit" disabled={!dep.unit_id} data-testid="save-deposit-btn"
                        className="w-full h-12 bg-slate-900 text-white">Record deposit entry</Button>
              </form>
            </Card>
            <Card title={`Deposit ledger (${deposits.length})`} testId="deposits-table-card">
              {!deposits.length ? <Empty testId="deposits-empty" title="No deposit entries" hint="Deposits are tracked across all months." /> : (
                <div className="overflow-x-auto">
                  <table className="data-table">
                    <thead><tr><th>Date</th><th>Property</th><th>Type</th><th className="text-right">Amount</th><th>Notes</th><th /></tr></thead>
                    <tbody>
                      {deposits.map((d) => (
                        <tr key={d.id} data-testid={`deposit-row-${d.id}`}>
                          <td>{d.date}</td>
                          <td className="font-semibold">{unitName(d.unit_id)}</td>
                          <td>{DEP_KINDS.find((k) => k.value === d.kind)?.label || d.kind}</td>
                          <td className="num">{money(d.amount)}</td>
                          <td className="text-slate-500">{d.notes || "—"}</td>
                          <td className="text-right">
                            <button onClick={async () => { await api.delete(`/rentals/deposits/${d.id}`); load(); setTick((x) => x + 1); }}
                                    data-testid={`delete-deposit-${d.id}`}
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
        </TabsContent>
      </Tabs>
    </div>
  );
}
