import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { Plus, Trash2, Save, X, MessageCircle, Send } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import { useCategories } from "@/hooks/useRentStatement";
import { PageHeader, Card, Stat, Empty } from "@/components/Common";
import { CategorySelect } from "@/components/CategorySelect";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { money, monthLabel, plainAmt } from "@/lib/format";
import { openWhatsApp, openSms } from "@/lib/notify";

const calc = (b) => {
  const items = b.items || [];
  const collect = items.filter((i) => i.direction === "collect").reduce((s, i) => s + Number(i.amount || 0), 0);
  const paid = items.filter((i) => i.direction === "tenant_paid").reduce((s, i) => s + Number(i.amount || 0), 0);
  const total = Number(b.rent || 0) + Number(b.maintenance || 0) + collect - paid;
  return { collect, paid, total };
};

export default function Bills() {
  const { rentMonth } = useApp();
  const { cats, addCategory } = useCategories();
  const [bills, setBills] = useState([]);
  const [openId, setOpenId] = useState(null);
  const [draft, setDraft] = useState(null);

  const load = useCallback(async () => {
    const { data } = await api.get("/rentals/bills", { params: { month: rentMonth } });
    setBills(data);
  }, [rentMonth]);
  useEffect(() => { load(); setOpenId(null); setDraft(null); }, [load]);

  const open = (b) => {
    setOpenId(b.unit_id);
    setDraft({
      unit_id: b.unit_id, month: rentMonth, rent: String(b.rent ?? ""), maintenance: String(b.maintenance ?? ""),
      maintenance_payable: b.maintenance_payable === null || b.maintenance_payable === undefined ? "" : String(b.maintenance_payable),
      items: (b.items || []).map((i) => ({ ...i, amount: String(i.amount) })), notes: b.notes || "",
    });
  };

  const save = async () => {
    try {
      await api.put("/rentals/bills", {
        unit_id: draft.unit_id, month: rentMonth, rent: Number(draft.rent || 0),
        maintenance: Number(draft.maintenance || 0),
        maintenance_payable: draft.maintenance_payable === "" ? null : Number(draft.maintenance_payable),
        items: draft.items.map((i) => ({ ...i, amount: Number(i.amount || 0) })), notes: draft.notes,
      });
      toast.success("Bill saved");
      setOpenId(null); setDraft(null); load();
    } catch (e) { toast.error(errMsg(e)); }
  };

  const addItem = () => setDraft({
    ...draft,
    items: [...draft.items, { category: cats[0]?.name || "Other", note: "", amount: "", direction: "collect", pay_to_building: false }],
  });
  const setItem = (idx, patch) =>
    setDraft({ ...draft, items: draft.items.map((it, i) => (i === idx ? { ...it, ...patch } : it)) });

  const billMessage = (b) => {
    const t = b.totals;
    const lines = [`${b.unit_name} — ${monthLabel(rentMonth)}`, "",
                   `Rent: ${plainAmt(t.rent)}`,
                   `Maintenance: ${plainAmt(t.maintenance)}`];
    (b.items || []).filter((i) => i.direction === "collect")
      .forEach((i) => lines.push(`${i.category}${i.note ? ` (${i.note})` : ""}: ${plainAmt(i.amount)}`));
    (b.items || []).filter((i) => i.direction === "tenant_paid")
      .forEach((i) => lines.push(`Less — paid by you${i.note ? ` (${i.note})` : ` (${i.category})`}: ${plainAmt(i.amount)}`));
    lines.push("", `Total payable: ${plainAmt(t.total_to_collect)}`);
    return lines.join("\n");
  };

  const totals = bills.reduce((a, b) => ({
    rent: a.rent + b.totals.rent, maint: a.maint + b.totals.maintenance,
    adhoc: a.adhoc + b.totals.adhoc_collect, less: a.less + b.totals.tenant_paid_on_my_behalf,
    total: a.total + b.totals.total_to_collect,
  }), { rent: 0, maint: 0, adhoc: 0, less: 0, total: 0 });

  return (
    <div>
      <PageHeader title="Monthly Bills" subtitle={`What each tenant owes · ${monthLabel(rentMonth)}`} />

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 mb-8">
        <Stat testId="bill-stat-rent" label="Rent" value={money(totals.rent)} />
        <Stat testId="bill-stat-maint" label="Maintenance" value={money(totals.maint)} />
        <Stat testId="bill-stat-adhoc" label="Ad-hoc to collect" value={money(totals.adhoc)} />
        <Stat testId="bill-stat-less" label="Paid by tenants for me" value={money(totals.less)} tone="warning" />
        <Stat testId="bill-stat-total" label="Total to collect" value={money(totals.total)} tone="positive" />
      </div>

      {!bills.length ? (
        <Empty testId="bills-empty" title="No properties yet" hint="Add properties first — their rent flows in here automatically." />
      ) : (
        <div className="space-y-4">
          {bills.map((b) => {
            const editing = openId === b.unit_id;
            const live = editing ? calc(draft) : null;
            return (
              <Card key={b.unit_id} testId={`bill-card-${b.unit_name}`}
                    title={`${b.unit_name}${b.tenant_name ? ` · ${b.tenant_name}` : ""}`}
                    action={
                      <div className="flex items-center gap-2">
                        {!editing && (
                          <>
                            <span className="mono text-sm font-semibold" data-testid={`bill-total-${b.unit_name}`}>
                              {money(b.totals.total_to_collect)}
                            </span>
                            {b.is_draft && <span data-testid={`bill-draft-chip-${b.unit_name}`} className="text-xs px-2 py-0.5 rounded border bg-amber-50 text-amber-800 border-amber-200">not saved</span>}
                            {b.tenant_phone && (
                              <>
                                <button onClick={() => openWhatsApp(b.tenant_phone, billMessage(b))}
                                        data-testid={`bill-whatsapp-${b.unit_name}`} title="Send bill on WhatsApp"
                                        className="p-2 border border-slate-300 rounded-md text-emerald-700 hover:bg-emerald-50">
                                  <MessageCircle className="w-4 h-4" />
                                </button>
                                <button onClick={() => openSms(b.tenant_phone, billMessage(b))}
                                        data-testid={`bill-sms-${b.unit_name}`} title="Send bill by SMS"
                                        className="p-2 border border-slate-300 rounded-md text-slate-700 hover:bg-slate-100">
                                  <Send className="w-4 h-4" />
                                </button>
                              </>
                            )}
                            <Button variant="outline" className="h-9" onClick={() => open(b)}
                                    data-testid={`bill-edit-${b.unit_name}`}>Edit bill</Button>
                          </>
                        )}
                        {editing && (
                          <>
                            <Button className="h-9 bg-slate-900 text-white" onClick={save} data-testid={`bill-save-${b.unit_name}`}>
                              <Save className="w-4 h-4 mr-2" /> Save
                            </Button>
                            <button onClick={() => { setOpenId(null); setDraft(null); }} data-testid={`bill-cancel-${b.unit_name}`}
                                    className="text-slate-400 hover:text-slate-900"><X className="w-4 h-4" /></button>
                          </>
                        )}
                      </div>
                    }>
                {!editing ? (
                  <div className="flex flex-wrap gap-x-8 gap-y-2 text-sm">
                    <span>Rent <b className="mono">{money(b.totals.rent)}</b></span>
                    <span>Maintenance <b className="mono">{money(b.totals.maintenance)}</b></span>
                    <span>Ad-hoc <b className="mono">{money(b.totals.adhoc_collect)}</b></span>
                    <span className="text-amber-700">Less paid by tenant <b className="mono">{money(b.totals.tenant_paid_on_my_behalf)}</b></span>
                    {(b.items || []).length > 0 && (
                      <span className="text-slate-500">{b.items.length} ad-hoc item{b.items.length > 1 ? "s" : ""}</span>
                    )}
                  </div>
                ) : (
                  <div className="space-y-4">
                    <div className="grid sm:grid-cols-3 gap-3">
                      <div>
                        <Label className="label-caps">Rent (from master)</Label>
                        <Input type="number" inputMode="decimal" className="mt-2 h-11 mono" data-testid="bill-rent-input"
                               value={draft.rent} onChange={(e) => setDraft({ ...draft, rent: e.target.value })} />
                      </div>
                      <div>
                        <Label className="label-caps">Maintenance to collect</Label>
                        <Input type="number" inputMode="decimal" className="mt-2 h-11 mono" data-testid="bill-maintenance-input"
                               value={draft.maintenance} onChange={(e) => setDraft({ ...draft, maintenance: e.target.value })} />
                      </div>
                      <div>
                        <Label className="label-caps">Payable to building</Label>
                        <Input type="number" inputMode="decimal" className="mt-2 h-11 mono" data-testid="bill-payable-input"
                               placeholder={draft.maintenance || "same as collected"}
                               value={draft.maintenance_payable}
                               onChange={(e) => setDraft({ ...draft, maintenance_payable: e.target.value })} />
                        <p className="text-xs text-slate-500 mt-1">Blank = same as collected</p>
                      </div>
                    </div>

                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <div className="label-caps">Ad-hoc items</div>
                        <Button variant="outline" className="h-8" onClick={addItem} data-testid="bill-add-item-btn">
                          <Plus className="w-3.5 h-3.5 mr-1.5" /> Add item
                        </Button>
                      </div>
                      {!draft.items.length && <p className="text-sm text-slate-500">No ad-hoc items this month.</p>}
                      <div className="space-y-3">
                        {draft.items.map((it, idx) => (
                          <div key={idx} className="border border-slate-200 rounded-md p-3 grid sm:grid-cols-12 gap-3 items-end"
                               data-testid={`bill-item-${idx}`}>
                            <div className="sm:col-span-3">
                              <Label className="label-caps">Category</Label>
                              <div className="mt-2">
                                <CategorySelect value={it.category} cats={cats} addCategory={addCategory}
                                                testId={`bill-item-category-${idx}`}
                                                onChange={(v) => setItem(idx, { category: v })} />
                              </div>
                            </div>
                            <div className="sm:col-span-3">
                              <Label className="label-caps">Note</Label>
                              <Input className="mt-2 h-11" data-testid={`bill-item-note-${idx}`} value={it.note}
                                     onChange={(e) => setItem(idx, { note: e.target.value })} />
                            </div>
                            <div className="sm:col-span-2">
                              <Label className="label-caps">Amount</Label>
                              <Input type="number" inputMode="decimal" className="mt-2 h-11 mono"
                                     data-testid={`bill-item-amount-${idx}`} value={it.amount}
                                     onChange={(e) => setItem(idx, { amount: e.target.value })} />
                            </div>
                            <div className="sm:col-span-2">
                              <Label className="label-caps">Type</Label>
                              <Select value={it.direction} onValueChange={(v) => setItem(idx, { direction: v })}>
                                <SelectTrigger className="mt-2 h-11" data-testid={`bill-item-direction-${idx}`}><SelectValue /></SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="collect">To collect</SelectItem>
                                  <SelectItem value="tenant_paid">Paid by tenant for me</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>
                            <div className="sm:col-span-2 flex items-center justify-between gap-2">
                              <label className="text-xs text-slate-600">
                                Building
                                <Switch className="ml-2" checked={!!it.pay_to_building}
                                        data-testid={`bill-item-building-${idx}`}
                                        onCheckedChange={(v) => setItem(idx, { pay_to_building: v })} />
                              </label>
                              <button onClick={() => setDraft({ ...draft, items: draft.items.filter((_, i) => i !== idx) })}
                                      data-testid={`bill-item-remove-${idx}`}
                                      className="text-slate-400 hover:text-red-600"><Trash2 className="w-4 h-4" /></button>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="flex items-center justify-between bg-slate-50 border border-slate-200 rounded-md px-4 py-3">
                      <span className="text-sm text-slate-600">
                        Rent + maintenance + ad-hoc {money(live.collect)} − paid by tenant {money(live.paid)}
                      </span>
                      <span className="mono text-lg font-semibold" data-testid="bill-live-total">{money(live.total)}</span>
                    </div>
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
