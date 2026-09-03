import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { Trash2, HandCoins, Lock, MessageCircle, Send } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import { PageHeader, Card, Stat, Empty } from "@/components/Common";
import { ReconTable } from "@/components/ReconTable";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { money, monthLabel, num, dmy } from "@/lib/format";
import { duesMessage, openWhatsApp, openSms } from "@/lib/notify";
import { BulkReminders } from "@/components/BulkReminders";
import { useStatement } from "@/hooks/useStatement";

export default function Reconcile() {
  const { propertyId, month, locked, bump, setMonth } = useApp();
  const [payments, setPayments] = useState([]);
  const [flats, setFlats] = useState([]);
  const [tick, setTick] = useState(0);
  const { statement } = useStatement(propertyId, month, tick);
  const [form, setForm] = useState({ flat_id: "", amount: "", date: `${month}-01`, payer_type: "owner", direction: "received", mode: "cash", reference: "", notes: "" });
  const [refund, setRefund] = useState(null);   // { flat_id, flat_number, credit, amount, date, mode, reference }

  const load = useCallback(async () => {
    if (!propertyId) return;
    const [p, f] = await Promise.all([
      api.get("/payments", { params: { property_id: propertyId, month } }),
      api.get("/flats", { params: { property_id: propertyId } }),
    ]);
    setPayments(p.data); setFlats(f.data);
  }, [propertyId, month]);

  useEffect(() => { load(); setForm((s) => ({ ...s, date: `${month}-01` })); }, [load, month]);

  const add = async (e) => {
    e.preventDefault();
    try {
      await api.post("/payments", {
        property_id: propertyId, month, flat_id: form.flat_id, amount: Number(form.amount || 0),
        date: form.date, payer_type: form.payer_type, direction: form.direction,
        mode: form.mode, reference: form.reference, notes: form.notes,
      });
      toast.success(form.direction === "received" ? "Payment recorded" : "Payout recorded");
      setForm({ ...form, amount: "", reference: "", notes: "" });
      load(); setTick((t) => t + 1);
    } catch (err) { toast.error(errMsg(err)); }
  };

  const saveRefund = async () => {
    try {
      await api.post("/payments", {
        property_id: propertyId, month, flat_id: refund.flat_id, amount: Number(refund.amount || 0),
        date: refund.date, payer_type: "owner", direction: "payout",
        mode: refund.mode, reference: refund.reference,
        notes: `Credit paid back${Number(refund.amount) < refund.credit ? " (part payment)" : ""}`,
      });
      toast.success(`${money(Number(refund.amount))} paid back to flat ${refund.flat_number}`);
      setRefund(null);
      load(); setTick((t) => t + 1);
    } catch (err) { toast.error(errMsg(err)); }
  };

  const del = async (id) => {
    try { await api.delete(`/payments/${id}`); load(); setTick((t) => t + 1); } catch (e) { toast.error(errMsg(e)); }
  };

  const doReset = async () => {
    try {
      const { data } = await api.post("/periods/reset", null, { params: { property_id: propertyId, month } });
      toast.success(`${monthLabel(month)} locked. ${monthLabel(data.new_month)} is now open.`);
      bump(); setTick((t) => t + 1);
      setTimeout(() => setMonth(data.new_month), 400);
    } catch (e) { toast.error(errMsg(e)); }
  };

  const flatName = (id) => flats.find((f) => f.id === id)?.number || "—";
  const t = statement?.totals;
  const msgFor = (r) => duesMessage({
    building: statement?.property?.name || "Society",
    flat: r.flat_number, monthName: monthLabel(month), row: r,
  });

  return (
    <div>
      <PageHeader title="Reconciliation" subtitle={`${statement?.property?.name || ""} · per-owner settlement · ${monthLabel(month)}`}>
        {statement?.rows?.length > 0 && <BulkReminders rows={statement.rows} buildMessage={msgFor} />}
        {!locked && (
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button data-testid="month-reset-btn" className="bg-slate-900 text-white">
                <Lock className="w-4 h-4 mr-2" /> Close & reset month
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent data-testid="reset-dialog">
              <AlertDialogHeader>
                <AlertDialogTitle>Reset for next month?</AlertDialogTitle>
                <AlertDialogDescription>
                  {monthLabel(month)} will be locked as a permanent historical record. Closing meter readings
                  become next month's opening readings, water purchases reset to zero, and every unsettled
                  balance ({money(t?.total_owes)} receivable / {money(t?.total_owed)} payable) is carried forward.
                  This cannot be undone.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel data-testid="reset-cancel-btn">Cancel</AlertDialogCancel>
                <AlertDialogAction data-testid="reset-confirm-btn" onClick={doReset} className="bg-slate-900">
                  Yes, reset
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        )}
      </PageHeader>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <Stat testId="rec-stat-billable" label="Billable this month" value={money(t?.billable_total)} sub="Water + recurring + repairs" />
        <Stat testId="rec-stat-contrib" label="Advance payment" value={money(t?.total_contributions)} tone="positive" sub="Deducted from their dues" />
        <Stat testId="rec-stat-received" label="Payments received" value={money(t?.total_received)} sub={`Payouts ${money(t?.total_payouts)}`} />
        <Stat testId="rec-stat-net" label="Net position" value={money(t?.net_position)}
              tone={(t?.net_position || 0) > 0 ? "negative" : "positive"}
              sub={`${money(t?.total_owes)} owes · ${money(t?.total_owed)} owed`} />
      </div>

      <Card title="Water reconciliation — owner statement" testId="reconcile-table-card" className="mb-8">
        {!statement?.rows?.length ? <Empty testId="reconcile-empty" title="Nothing to reconcile" hint="Add flats and charges first." /> : (
          <ReconTable rows={statement.rows} totals={t} testPrefix="reconcile"
                      extraHead={<th>Actions</th>}
                      extraCell={(r) => (
                        <td>
                          <div className="flex gap-1.5 items-center">
                            {r.net < -0.005 && !locked && (
                              <button data-testid={`payback-${r.flat_number}`}
                                      title={`Pay back ${money(-r.net)} to flat ${r.flat_number}`}
                                      onClick={() => setRefund({
                                        flat_id: r.flat_id, flat_number: r.flat_number, credit: -r.net,
                                        amount: String((-r.net).toFixed(2)), date: `${month}-01`,
                                        mode: "cash", reference: "",
                                      })}
                                      className="px-2 py-1.5 text-xs border border-violet-300 text-violet-700 rounded hover:bg-violet-50 whitespace-nowrap">
                                Pay back
                              </button>
                            )}
                            {r.owner_phone ? (
                              <>
                                <button title={`WhatsApp ${r.owner_phone}`} aria-label={`Send WhatsApp dues message to ${r.owner_name}`} data-testid={`notify-whatsapp-${r.flat_number}`}
                                        onClick={() => openWhatsApp(r.owner_phone, msgFor(r))}
                                        className="p-2 border border-slate-300 rounded-md hover:bg-emerald-50 hover:border-emerald-300 text-emerald-700">
                                  <MessageCircle className="w-4 h-4" />
                                </button>
                                <button title={`SMS ${r.owner_phone}`} aria-label={`Send SMS dues message to ${r.owner_name}`} data-testid={`notify-sms-${r.flat_number}`}
                                        onClick={() => openSms(r.owner_phone, msgFor(r))}
                                        className="p-2 border border-slate-300 rounded-md hover:bg-slate-100 text-slate-700">
                                  <Send className="w-4 h-4" />
                                </button>
                              </>
                            ) : (
                              <span className="text-xs text-slate-400">Add owner phone</span>
                            )}
                          </div>
                        </td>
                      )} />
        )}
      </Card>

      {refund && (
        <AlertDialog open onOpenChange={(o) => !o && setRefund(null)}>
          <AlertDialogContent data-testid="payback-dialog">
            <AlertDialogHeader>
              <AlertDialogTitle>Pay back credit — flat {refund.flat_number}</AlertDialogTitle>
              <AlertDialogDescription>
                This flat is in credit of <b className="mono">{money(refund.credit)}</b>. Record the full amount
                or a part payment — any balance stays in credit.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="label-caps">Amount paid back</Label>
                  <Input type="number" inputMode="decimal" step="any" className="mt-2 h-11 mono"
                         data-testid="payback-amount-input" value={refund.amount}
                         onChange={(e) => setRefund({ ...refund, amount: e.target.value })} />
                </div>
                <div>
                  <Label className="label-caps">Date of payment</Label>
                  <Input type="date" className="mt-2 h-11" data-testid="payback-date-input"
                         value={refund.date} onChange={(e) => setRefund({ ...refund, date: e.target.value })} />
                </div>
              </div>
              <div>
                <Label className="label-caps">Mode</Label>
                <Select value={refund.mode}
                        onValueChange={(v) => setRefund({ ...refund, mode: v, reference: v === "cash" ? "" : refund.reference })}>
                  <SelectTrigger className="mt-2 h-11" data-testid="payback-mode-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="cash">Cash</SelectItem>
                    <SelectItem value="upi">UPI</SelectItem>
                    <SelectItem value="bank">Bank Transfer</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {refund.mode !== "cash" && (
                <div>
                  <Label className="label-caps">Reference / UPI txn no.</Label>
                  <Input className="mt-2 h-11 mono" data-testid="payback-reference-input"
                         placeholder="UPI ref / bank txn no." value={refund.reference}
                         onChange={(e) => setRefund({ ...refund, reference: e.target.value })} />
                </div>
              )}
            </div>
            <AlertDialogFooter>
              <AlertDialogCancel data-testid="payback-cancel-btn">Cancel</AlertDialogCancel>
              <AlertDialogAction onClick={saveRefund} data-testid="payback-save-btn"
                                 className="bg-violet-700 text-white">Record pay back</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      )}


      <div className="grid lg:grid-cols-[380px_1fr] gap-6 [&>*]:min-w-0">
        <Card title="Record payment / payout" testId="payment-form-card">
          {locked ? <p className="text-sm text-amber-700">This period is locked.</p> : (
            <form onSubmit={add} className="space-y-4">
              <div>
                <Label className="label-caps">Direction</Label>
                <Select value={form.direction} onValueChange={(v) => setForm({ ...form, direction: v })}>
                  <SelectTrigger className="mt-2 h-11" data-testid="payment-direction-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="received">Payment received from flat</SelectItem>
                    <SelectItem value="payout">Payout made to owner</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="label-caps">Flat</Label>
                <Select value={form.flat_id} onValueChange={(v) => setForm({ ...form, flat_id: v })}>
                  <SelectTrigger className="mt-2 h-11" data-testid="payment-flat-select"><SelectValue placeholder="Select flat" /></SelectTrigger>
                  <SelectContent>{flats.map((f) => <SelectItem key={f.id} value={f.id}>{f.number} — {f.owner_name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div>
                <Label className="label-caps">Amount</Label>
                <Input type="number" inputMode="decimal" step="any" required className="mt-2 h-12 mono text-lg"
                       data-testid="payment-amount-input" value={form.amount}
                       onChange={(e) => setForm({ ...form, amount: e.target.value })} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="label-caps">Date</Label>
                  <Input type="date" className="mt-2 h-11" data-testid="payment-date-input"
                         value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
                </div>
                <div>
                  <Label className="label-caps">Paid by</Label>
                  <Select value={form.payer_type} onValueChange={(v) => setForm({ ...form, payer_type: v })}>
                    <SelectTrigger className="mt-2 h-11" data-testid="payment-payer-type-select"><SelectValue /></SelectTrigger>
                    <SelectContent><SelectItem value="owner">Owner</SelectItem><SelectItem value="tenant">Tenant</SelectItem></SelectContent>
                  </Select>
                </div>
              </div>
              <div>
                <Label className="label-caps">Mode</Label>
                <Select value={form.mode}
                        onValueChange={(v) => setForm({ ...form, mode: v, reference: v === "cash" ? "" : form.reference })}>
                  <SelectTrigger className="mt-2 h-11" data-testid="payment-mode-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="cash">Cash</SelectItem>
                    <SelectItem value="upi">UPI</SelectItem>
                    <SelectItem value="bank">Bank Transfer</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {form.mode !== "cash" && (
                <div>
                  <Label className="label-caps">Reference / UPI txn no.</Label>
                  <Input className="mt-2 h-11 mono" required data-testid="payment-reference-input"
                         placeholder="UPI ref / bank txn no." value={form.reference}
                         onChange={(e) => setForm({ ...form, reference: e.target.value })} />
                </div>
              )}

              <div>
                <Label className="label-caps">Notes</Label>
                <Input className="mt-2 h-11" data-testid="payment-notes-input"
                       value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
              </div>
              <Button type="submit" disabled={!form.flat_id} data-testid="save-payment-btn"
                      className="w-full h-12 bg-slate-900 text-white">
                <HandCoins className="w-4 h-4 mr-2" /> Record
              </Button>
            </form>
          )}
        </Card>

        <Card title={`Ledger (${payments.length})`} testId="payments-table-card">
          {!payments.length ? <Empty testId="payments-empty" title="No payments recorded" hint="All payments and payouts are entered manually." /> : (
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead><tr><th className="text-right">S.No</th><th>Date</th><th>Flat</th><th>Type</th><th>Paid by</th><th>Mode</th><th>Reference</th><th className="text-right">Amount</th><th>Notes</th><th /></tr></thead>
                <tbody>
                  {payments.map((p, i) => (
                    <tr key={p.id} data-testid={`payment-row-${p.id}`}>
                      <td className="num text-slate-500">{i + 1}</td>
                      <td>{dmy(p.date)}</td>
                      <td className="font-semibold">{flatName(p.flat_id)}</td>
                      <td>
                        <span className={`text-xs px-2 py-0.5 rounded border ${p.direction === "received"
                          ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                          : "bg-blue-50 text-blue-700 border-blue-200"}`}>
                          {p.direction === "received" ? "Received" : "Payout"}
                        </span>
                      </td>
                      <td className="capitalize text-slate-500">{p.payer_type}</td>
                      <td className="text-slate-500" data-testid={`payment-mode-${p.id}`}>
                        {{ cash: "Cash", upi: "UPI", bank: "Bank Transfer" }[p.mode] || "Cash"}
                      </td>
                      <td className="mono text-xs text-slate-500">{p.reference || "—"}</td>
                      <td className="num">{money(p.amount)}</td>
                      <td className="text-slate-500">{p.notes || "—"}</td>
                      <td className="text-right">
                        {!locked && (
                          <button onClick={() => del(p.id)} data-testid={`delete-payment-${p.id}`}
                                  className="text-slate-400 hover:text-red-600"><Trash2 className="w-4 h-4" /></button>
                        )}
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
