import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { Plus, Trash2, Wand2, Wrench } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import { PageHeader, Card, Stat, Empty } from "@/components/Common";
import { MediaUpload, MediaThumbs } from "@/components/MediaUpload";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { money, monthLabel, CHARGE_TYPES } from "@/lib/format";
import { useStatement } from "@/hooks/useStatement";

export default function Charges() {
  const { propertyId, month, locked, property } = useApp();
  const [flats, setFlats] = useState([]);
  const [charges, setCharges] = useState([]);
  const [tick, setTick] = useState(0);
  const { statement } = useStatement(propertyId, month, tick);

  const [rec, setRec] = useState({ charge_type: "cleaning", person_name: "", amount: "", payer_flat_id: "", payer_type: "tenant", description: "", date: `${month}-01` });
  const [job, setJob] = useState({ description: "", amount: "", payer_flat_id: "", payer_type: "owner", date: `${month}-01` });
  const [jobMedia, setJobMedia] = useState([]);
  const [recMedia, setRecMedia] = useState([]);

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
      await api.post("/charges", { property_id: propertyId, month, ...payload });
      toast.success("Charge recorded");
      reset(); load(); setTick((t) => t + 1);
    } catch (e) { toast.error(errMsg(e)); }
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

  const renderTable = (rows, testId) => (
    <div className="overflow-x-auto">
      <table className="data-table">
        <thead><tr><th>Type</th><th>Description</th><th>Person</th><th className="text-right">Amount</th>
          <th>Fronted by</th><th>As</th><th>Date</th><th>Bill / Work media</th><th /></tr></thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.id} data-testid={`${testId}-row-${c.id}`}>
              <td className="capitalize font-semibold">{c.charge_type}</td>
              <td>{c.description || "—"}</td>
              <td className="text-slate-500">{c.person_name || "—"}</td>
              <td className="num">{money(c.amount)}</td>
              <td>{flatName(c.payer_flat_id)}</td>
              <td className="capitalize text-slate-500">{c.payer_type}</td>
              <td className="text-slate-500">{c.date || "—"}</td>
              <td><MediaThumbs media={c.media} showCategory /></td>
              <td className="text-right">
                {!locked && (
                  <button onClick={() => del(c.id)} data-testid={`delete-charge-${c.id}`}
                          className="text-slate-400 hover:text-red-600"><Trash2 className="w-4 h-4" /></button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

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
            <Card title="Add recurring charge" testId="recurring-form-card">
              {locked ? <p className="text-sm text-amber-700">This period is locked.</p> : (
                <form className="space-y-4" onSubmit={(e) => {
                  e.preventDefault();
                  submit({
                    charge_type: rec.charge_type, person_name: rec.person_name,
                    amount: Number(rec.amount || 0), payer_flat_id: rec.payer_flat_id || null,
                    payer_type: rec.payer_type, description: rec.description, date: rec.date, media: recMedia,
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
                    <Label className="label-caps">Date</Label>
                    <Input type="date" className="mt-2 h-11" data-testid="recurring-date-input"
                           value={rec.date} onChange={(e) => setRec({ ...rec, date: e.target.value })} />
                  </div>
                  <MediaUpload media={recMedia} setMedia={setRecMedia} testId="recurring-media-bill"
                               category="bill" label="Bill / Receipt photo" />
                  <Button type="submit" data-testid="save-recurring-btn" className="w-full h-12 bg-slate-900 text-white">
                    <Plus className="w-4 h-4 mr-2" /> Add charge
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
            <Card title="Add one-time maintenance / repair" testId="adhoc-form-card">
              {locked ? <p className="text-sm text-amber-700">This period is locked.</p> : (
                <form className="space-y-4" onSubmit={(e) => {
                  e.preventDefault();
                  submit({
                    charge_type: "maintenance", description: job.description, person_name: "",
                    amount: Number(job.amount || 0), payer_flat_id: job.payer_flat_id || null,
                    payer_type: job.payer_type, date: job.date, media: jobMedia,
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
                    <Wrench className="w-4 h-4 mr-2" /> Record work
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
