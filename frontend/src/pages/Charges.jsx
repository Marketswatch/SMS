import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { Plus, Trash2, Wand2, Wrench, Pencil, X } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import { PageHeader, Card, Stat, Empty } from "@/components/Common";
import { MediaUpload, MediaThumbs } from "@/components/MediaUpload";
import { WorkGallery } from "@/components/WorkGallery";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { money, monthLabel, CHARGE_TYPES, dmy } from "@/lib/format";
import { useSort, SortTh } from "@/lib/sort";
import { useStatement } from "@/hooks/useStatement";

export default function Charges() {
  const { propertyId, month, locked, property } = useApp();
  const [flats, setFlats] = useState([]);
  const [charges, setCharges] = useState([]);
  const [tick, setTick] = useState(0);
  const { statement } = useStatement(propertyId, month, tick);

  const [rec, setRec] = useState({ charge_type: "cleaning", person_name: "", amount: "", payer_flat_id: "", payer_type: "tenant", description: "", date: `${month}-01`, billed_flat_id: "" });
  const [job, setJob] = useState({ description: "", amount: "", payer_flat_id: "", payer_type: "owner", date: `${month}-01`, billed_flat_id: "" });
  const [jobMedia, setJobMedia] = useState([]);
  const [recMedia, setRecMedia] = useState([]);
  const [editId, setEditId] = useState(null);

  const load = useCallback(async () => {
    if (!propertyId) return;
    const [f, c] = await Promise.all([
      api.get("/flats", { params: { property_id: propertyId } }),
      api.get("/charges", { params: { property_id: propertyId, month } }),
    ]);
    setFlats(f.data); setCharges(c.data);
  }, [propertyId, month]);

  useEffect(() => {
    load();
    setRec((r) => ({ ...r, date: `${month}-01` }));
    setJob((j) => ({ ...j, date: `${month}-01` }));
  }, [load, month]);

  const flatName = (id) => flats.find((f) => f.id === id)?.number || "Not fronted";

  const submit = async (payload, reset) => {
    try {
      if (editId) await api.put(`/charges/${editId}`, { property_id: propertyId, month, ...payload });
      else await api.post("/charges", { property_id: propertyId, month, ...payload });
      toast.success(editId ? "Charge updated" : "Charge recorded");
      setEditId(null);
      reset(); load(); setTick((t) => t + 1);
    } catch (e) { toast.error(errMsg(e)); }
  };

  const editCharge = (c) => {
    setEditId(c.id);
    if (c.category === "adhoc") {
      setJob({ description: c.description || "", amount: String(c.amount ?? ""),
               payer_flat_id: c.payer_flat_id || "", payer_type: c.payer_type || "owner",
               billed_flat_id: c.billed_flat_id || "",
               date: c.date || `${month}-01` });
      setJobMedia(c.media || []);
    } else {
      setRec({ charge_type: c.charge_type, person_name: c.person_name || "",
               amount: String(c.amount ?? ""), payer_flat_id: c.payer_flat_id || "",
               billed_flat_id: c.billed_flat_id || "",
               payer_type: c.payer_type || "owner", description: c.description || "",
               date: c.date || `${month}-01` });
      setRecMedia(c.media || []);
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const cancelEdit = () => {
    setEditId(null);
    setRec({ ...rec, person_name: "", amount: "", description: "" });
    setJob({ ...job, description: "", amount: "" });
    setRecMedia([]); setJobMedia([]);
  };

  const applyDefaults = async () => {
    try {
      const { data } = await api.post("/charges/apply-defaults", null, { params: { property_id: propertyId, month } });
      toast.success(data.created.length ? `${data.created.length} default charges added` : "All defaults already present");
      load(); setTick((t) => t + 1);
    } catch (e) { toast.error(errMsg(e)); }
  };

  const del = async (id) => {
    try { await api.delete(`/charges/${id}`); load(); setTick((t) => t + 1); } catch (e) { toast.error(errMsg(e)); }
  };

  const recurring = charges.filter((c) => c.category === "recurring");
  const adhoc = charges.filter((c) => c.category === "adhoc");
  const t = statement?.totals;

  const chargeAccessors = {
    charge_type: (c) => c.charge_type,
    description: (c) => c.description || "",
    person_name: (c) => c.person_name || "",
    amount: (c) => Number(c.amount || 0),
    payer: (c) => flatName(c.payer_flat_id),
    payer_type: (c) => c.payer_type || "",
    date: (c) => c.date || "",
  };
  const sorters = {
    recurring: useSort(recurring, chargeAccessors, "date"),
    adhoc: useSort(adhoc, chargeAccessors, "date"),
  };

  const renderTable = (rows, testId) => {
    const { sorted, sort, toggle } = sorters[testId];
    return (
    <div className="overflow-x-auto">
      <table className="data-table">
        <thead><tr><th className="text-right">S.No</th>
          <SortTh label="Type" sortKey="charge_type" sort={sort} toggle={toggle} testId={`${testId}-sort-type`} />
          <SortTh label="Description" sortKey="description" sort={sort} toggle={toggle} testId={`${testId}-sort-desc`} />
          <SortTh label="Person" sortKey="person_name" sort={sort} toggle={toggle} testId={`${testId}-sort-person`} />
          <SortTh label="Amount" sortKey="amount" sort={sort} toggle={toggle} align="right" testId={`${testId}-sort-amount`} />
          <SortTh label="Fronted by" sortKey="payer" sort={sort} toggle={toggle} testId={`${testId}-sort-payer`} />
          <SortTh label="As" sortKey="payer_type" sort={sort} toggle={toggle} testId={`${testId}-sort-as`} />
          <SortTh label="Date" sortKey="date" sort={sort} toggle={toggle} testId={`${testId}-sort-date`} />
          <th>Bill / Work media</th><th /></tr></thead>
        <tbody>
          {sorted.map((c, i) => (
            <tr key={c.id} data-testid={`${testId}-row-${c.id}`}>
              <td className="num text-slate-500">{i + 1}</td>
              <td className="capitalize font-semibold">{c.charge_type}</td>
              <td>{c.description || "—"}
                {c.billed_flat_id && (
                  <span className="ml-1 text-[10px] px-1.5 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-200"
                        data-testid={`charge-flatonly-${c.id}`}>
                    only {flatName(c.billed_flat_id)}
                  </span>
                )}
              </td>
              <td className="text-slate-500">{c.person_name || "—"}</td>
              <td className="num">{money(c.amount)}</td>
              <td>{flatName(c.payer_flat_id)}</td>
              <td className="capitalize text-slate-500">{c.payer_type}</td>
              <td className="text-slate-500">{dmy(c.date)}</td>
              <td>{c.media?.length ? <WorkGallery charge={c} testId={`gallery-btn-${c.id}`} /> : <MediaThumbs media={c.media} showCategory />}</td>
              <td className="text-right">
                {!locked && (
                  <div className="flex justify-end gap-2">
                    <button onClick={() => editCharge(c)} data-testid={`edit-charge-${c.id}`}
                            className="text-slate-400 hover:text-slate-900"><Pencil className="w-4 h-4" /></button>
                    <button onClick={() => del(c.id)} data-testid={`delete-charge-${c.id}`}
                            className="text-slate-400 hover:text-red-600"><Trash2 className="w-4 h-4" /></button>
                  </div>
                )}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="bg-slate-50 font-semibold" data-testid={`${testId}-footer`}>
            <td colSpan={4}>Total Expense · split between {t?.flat_count || 0} house{(t?.flat_count || 0) === 1 ? "" : "s"}</td>
            <td className="num">{money(rows.reduce((s, c) => s + Number(c.amount || 0), 0))}</td>
            <td colSpan={4} className="text-slate-500 font-normal">
              Exp per head{" "}
              <span className="mono">
                {money(rows.reduce((s, c) => s + Number(c.amount || 0), 0) / (t?.flat_count || 1))}
              </span>
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
    );
  };

  return (
    <div>
      <PageHeader title="Charges" subtitle={`${property?.name || ""} · recurring and one-time entries · ${monthLabel(month)}`}>
        {!locked && (
          <Button variant="outline" onClick={applyDefaults} data-testid="apply-defaults-btn">
            <Wand2 className="w-4 h-4 mr-2" /> Auto-fill monthly defaults
          </Button>
        )}
      </PageHeader>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <Stat testId="charges-stat-recurring" label="Recurring total" value={money(t?.recurring_total)} sub={`${money(t?.recurring_share)} / flat`} />
        <Stat testId="charges-stat-adhoc" label="One-time total" value={money(t?.maintenance_total)} sub={`${money(t?.maintenance_share)} / flat`} />
        <Stat testId="charges-stat-tips" label="Tanker tips" value={money(t?.total_tips)} sub="Part of water cost, not recurring" />
        <Stat testId="charges-stat-flats" label="Split across" value={`${t?.flat_count || 0} flats`} sub="One equal share each" />
      </div>

      <Tabs defaultValue="recurring">
        <TabsList className="h-auto bg-transparent p-0 gap-2 mb-6">
          <TabsTrigger value="recurring" data-testid="charges-tab-recurring"
                       className="data-[state=active]:bg-slate-900 data-[state=active]:text-white border border-slate-200 rounded-md px-3 py-1.5 text-sm">Recurring</TabsTrigger>
          <TabsTrigger value="adhoc" data-testid="charges-tab-adhoc"
                       className="data-[state=active]:bg-slate-900 data-[state=active]:text-white border border-slate-200 rounded-md px-3 py-1.5 text-sm">One-time / Repairs</TabsTrigger>
        </TabsList>

        <TabsContent value="recurring">
          <div className="grid lg:grid-cols-[380px_1fr] gap-6 [&>*]:min-w-0">
            <Card title={editId ? "Edit recurring charge" : "Add recurring charge"} testId="recurring-form-card"
                  action={editId && (
                    <button onClick={cancelEdit} data-testid="cancel-charge-edit-btn"
                            className="text-slate-400 hover:text-slate-900"><X className="w-4 h-4" /></button>
                  )}>
              {locked ? <p className="text-sm text-amber-700">This period is locked.</p> : (
                <form className="space-y-4" onSubmit={(e) => {
                  e.preventDefault();
                  submit({
                    charge_type: rec.charge_type, person_name: rec.person_name,
                    amount: Number(rec.amount || 0), payer_flat_id: rec.payer_flat_id || null,
                    payer_type: rec.payer_type, description: rec.description, date: rec.date, media: recMedia,
                    billed_flat_id: rec.billed_flat_id || null,
                  }, () => { setRec({ ...rec, person_name: "", amount: "", description: "" }); setRecMedia([]); });
                }}>
                  <div>
                    <Label className="label-caps">Charge type</Label>
                    <Select value={rec.charge_type} onValueChange={(v) => setRec({ ...rec, charge_type: v, payer_type: property?.default_payers?.[v] || "owner" })}>
                      <SelectTrigger className="mt-2 h-11" data-testid="recurring-type-select"><SelectValue /></SelectTrigger>
                      <SelectContent>{CHARGE_TYPES.map((c) => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label className="label-caps">Person name (maid / sweeper / guard)</Label>
                    <Input className="mt-2 h-11" data-testid="recurring-person-input"
                           value={rec.person_name} onChange={(e) => setRec({ ...rec, person_name: e.target.value })} />
                  </div>
                  <div>
                    <Label className="label-caps">Amount</Label>
                    <Input type="number" inputMode="decimal" step="any" required className="mt-2 h-12 mono text-lg"
                           data-testid="recurring-amount-input"
                           value={rec.amount} onChange={(e) => setRec({ ...rec, amount: e.target.value })} />
                  </div>
                  <div>
                    <Label className="label-caps">Note</Label>
                    <Input className="mt-2 h-11" data-testid="recurring-desc-input"
                           value={rec.description} onChange={(e) => setRec({ ...rec, description: e.target.value })} />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label className="label-caps">Fronted by flat</Label>
                      <Select value={rec.payer_flat_id} onValueChange={(v) => setRec({ ...rec, payer_flat_id: v })}>
                        <SelectTrigger className="mt-2 h-11" data-testid="recurring-payer-select"><SelectValue placeholder="None" /></SelectTrigger>
                        <SelectContent>{flats.map((f) => <SelectItem key={f.id} value={f.id}>{f.number} — {f.owner_name}</SelectItem>)}</SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="label-caps">Paid as</Label>
                      <Select value={rec.payer_type} onValueChange={(v) => setRec({ ...rec, payer_type: v })}>
                        <SelectTrigger className="mt-2 h-11" data-testid="recurring-payer-type-select"><SelectValue /></SelectTrigger>
                        <SelectContent><SelectItem value="owner">Owner</SelectItem><SelectItem value="tenant">Tenant</SelectItem></SelectContent>
                      </Select>
                    </div>
                  </div>
                  <div>
                    <Label className="label-caps">Charge to one flat only</Label>
                    <Select value={rec.billed_flat_id || "split"}
                            onValueChange={(v) => setRec({ ...rec, billed_flat_id: v === "split" ? "" : v })}>
                      <SelectTrigger className="mt-2 h-11" data-testid="recurring-billed-select"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="split">Split between all flats</SelectItem>
                        {flats.map((f) => <SelectItem key={f.id} value={f.id}>Only {f.number} — {f.owner_name}</SelectItem>)}
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-slate-500 mt-1">
                      Pick a flat to charge the full amount to that flat alone — it lands in its
                      Flat-specific column and its owner's total.
                    </p>
                  </div>

                  <div>
                    <Label className="label-caps">Date</Label>
                    <Input type="date" className="mt-2 h-11" data-testid="recurring-date-input"
                           value={rec.date} onChange={(e) => setRec({ ...rec, date: e.target.value })} />
                  </div>
                  <MediaUpload media={recMedia} setMedia={setRecMedia} testId="recurring-media-bill"
                               category="bill" label="Bill / Receipt photo" />
                  <Button type="submit" data-testid="save-recurring-btn" className="w-full h-12 bg-slate-900 text-white">
                    <Plus className="w-4 h-4 mr-2" /> {editId ? "Save changes" : "Add charge"}
                  </Button>
                </form>
              )}
            </Card>
            <Card title={`Recurring entries (${recurring.length})`} testId="recurring-table-card">
              {!recurring.length ? (
                <Empty testId="recurring-empty" title="No recurring charges yet"
                       hint="Use auto-fill to bring in your fixed monthly amounts, then add cleaning and sweeper details." />
              ) : renderTable(recurring, "recurring")}
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="adhoc">
          <div className="grid lg:grid-cols-[380px_1fr] gap-6 [&>*]:min-w-0">
            <Card title={editId ? "Edit maintenance / repair" : "Add one-time maintenance / repair"} testId="adhoc-form-card"
                  action={editId && (
                    <button onClick={cancelEdit} data-testid="cancel-adhoc-edit-btn"
                            className="text-slate-400 hover:text-slate-900"><X className="w-4 h-4" /></button>
                  )}>
              {locked ? <p className="text-sm text-amber-700">This period is locked.</p> : (
                <form className="space-y-4" onSubmit={(e) => {
                  e.preventDefault();
                  submit({
                    charge_type: "maintenance", description: job.description, person_name: "",
                    amount: Number(job.amount || 0), payer_flat_id: job.payer_flat_id || null,
                    payer_type: job.payer_type, date: job.date, media: jobMedia,
                    billed_flat_id: job.billed_flat_id || null,
                  }, () => { setJob({ ...job, description: "", amount: "" }); setJobMedia([]); });
                }}>
                  <div>
                    <Label className="label-caps">Work description</Label>
                    <Textarea className="mt-2 min-h-[90px]" required data-testid="adhoc-desc-input"
                              value={job.description} onChange={(e) => setJob({ ...job, description: e.target.value })} />
                  </div>
                  <div>
                    <Label className="label-caps">Amount</Label>
                    <Input type="number" inputMode="decimal" step="any" required className="mt-2 h-12 mono text-lg"
                           data-testid="adhoc-amount-input"
                           value={job.amount} onChange={(e) => setJob({ ...job, amount: e.target.value })} />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label className="label-caps">Fronted by flat</Label>
                      <Select value={job.payer_flat_id} onValueChange={(v) => setJob({ ...job, payer_flat_id: v })}>
                        <SelectTrigger className="mt-2 h-11" data-testid="adhoc-payer-select"><SelectValue placeholder="None" /></SelectTrigger>
                        <SelectContent>{flats.map((f) => <SelectItem key={f.id} value={f.id}>{f.number} — {f.owner_name}</SelectItem>)}</SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="label-caps">Paid as</Label>
                      <Select value={job.payer_type} onValueChange={(v) => setJob({ ...job, payer_type: v })}>
                        <SelectTrigger className="mt-2 h-11" data-testid="adhoc-payer-type-select"><SelectValue /></SelectTrigger>
                        <SelectContent><SelectItem value="owner">Owner</SelectItem><SelectItem value="tenant">Tenant</SelectItem></SelectContent>
                      </Select>
                    </div>
                  </div>
                  <div>
                    <Label className="label-caps">Charge to one flat only</Label>
                    <Select value={job.billed_flat_id || "split"}
                            onValueChange={(v) => setJob({ ...job, billed_flat_id: v === "split" ? "" : v })}>
                      <SelectTrigger className="mt-2 h-11" data-testid="adhoc-billed-select"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="split">Split between all flats</SelectItem>
                        {flats.map((f) => <SelectItem key={f.id} value={f.id}>Only {f.number} — {f.owner_name}</SelectItem>)}
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-slate-500 mt-1">
                      Charging one flat only? Pick it here — the full amount goes to that flat's
                      Flat-specific column instead of being split.
                    </p>
                  </div>

                  <div>
                    <Label className="label-caps">Date</Label>
                    <Input type="date" className="mt-2 h-11" data-testid="adhoc-date-input"
                           value={job.date} onChange={(e) => setJob({ ...job, date: e.target.value })} />
                  </div>
                  <MediaUpload media={jobMedia} setMedia={setJobMedia} testId="adhoc-media-bill"
                               category="bill" label="Bill / Invoice photo" />
                  <MediaUpload media={jobMedia} setMedia={setJobMedia} testId="adhoc-media-progress"
                               category="in_progress" label="Work in progress photos / video" />
                  <MediaUpload media={jobMedia} setMedia={setJobMedia} testId="adhoc-media-complete"
                               category="completed" label="Work completed photos / video" />
                  <Button type="submit" data-testid="save-adhoc-btn" className="w-full h-12 bg-slate-900 text-white">
                    <Wrench className="w-4 h-4 mr-2" /> {editId ? "Save changes" : "Record work"}
                  </Button>
                </form>
              )}
            </Card>
            <Card title={`One-time entries (${adhoc.length})`} testId="adhoc-table-card">
              {!adhoc.length ? (
                <Empty testId="adhoc-empty" title="No one-time work recorded"
                       hint="Repairs and ad-hoc work are tracked separately from recurring charges." />
              ) : renderTable(adhoc, "adhoc")}
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
