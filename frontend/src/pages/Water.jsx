import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { Truck, Trash2, Save, AlertTriangle, Pencil, X } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import { PageHeader, Card, Stat, Empty } from "@/components/Common";
import { MediaUpload, MediaThumbs, MediaMini } from "@/components/MediaUpload";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { money, litres, num, monthLabel, dmy } from "@/lib/format";
import { useSort, SortTh } from "@/lib/sort";
import { useStatement } from "@/hooks/useStatement";

export default function Water() {
  const { propertyId, month, locked, property } = useApp();
  const [flats, setFlats] = useState([]);
  const [tankers, setTankers] = useState([]);
  const [readings, setReadings] = useState([]);
  const [tick, setTick] = useState(0);
  const { statement } = useStatement(propertyId, month, tick);

  const blank = {
    booking_date: "", date: `${month}-01`, qty_sump: "", qty_syntex: "", amount: "", payer_flat_id: "",
    payer_type: property?.default_payers?.water || "tenant", tips_amount: "", tips_payer_flat_id: "",
    tips_payer_type: property?.default_payers?.tips || "tenant", supplier: "", notes: "",
  };
  const [form, setForm] = useState(blank);
  const [media, setMedia] = useState([]);
  const [editId, setEditId] = useState(null);

  const load = useCallback(async () => {
    if (!propertyId) return;
    const [f, t, r] = await Promise.all([
      api.get("/flats", { params: { property_id: propertyId } }),
      api.get("/tankers", { params: { property_id: propertyId, month } }),
      api.get("/readings", { params: { property_id: propertyId, month } }),
    ]);
    setFlats(f.data); setTankers(t.data); setReadings(r.data);
  }, [propertyId, month]);

  useEffect(() => { load(); setForm(blank); setMedia([]); /* eslint-disable-next-line */ }, [load]);

  const totalQty = Number(form.qty_sump || 0) + Number(form.qty_syntex || 0);
  const totalCost = Number(form.amount || 0) + Number(form.tips_amount || 0);
  const perLitre = totalQty > 0 ? totalCost / totalQty : 0;

  const addTanker = async (e) => {
    e.preventDefault();
    const payload = {
      property_id: propertyId, month, date: form.date, booking_date: form.booking_date || "",
      qty_sump: Number(form.qty_sump || 0), qty_syntex: Number(form.qty_syntex || 0),
      amount: Number(form.amount || 0), payer_flat_id: form.payer_flat_id || null,
      payer_type: form.payer_type, tips_amount: Number(form.tips_amount || 0),
      tips_payer_flat_id: form.tips_payer_flat_id || form.payer_flat_id || null,
      tips_payer_type: form.tips_payer_type, supplier: form.supplier, notes: form.notes, media,
    };
    try {
      if (editId) await api.put(`/tankers/${editId}`, payload);
      else await api.post("/tankers", payload);
      toast.success(editId ? "Tanker updated" : "Tanker purchase recorded");
      setForm(blank); setMedia([]); setEditId(null); load(); setTick((t) => t + 1);
    } catch (err) { toast.error(errMsg(err)); }
  };

  const editTanker = (tk) => {
    setEditId(tk.id);
    setForm({
      booking_date: tk.booking_date || "",
      date: tk.date || `${month}-01`, qty_sump: String(tk.qty_sump ?? ""), qty_syntex: String(tk.qty_syntex ?? ""),
      amount: String(tk.amount ?? ""), payer_flat_id: tk.payer_flat_id || "", payer_type: tk.payer_type || "owner",
      tips_amount: String(tk.tips_amount ?? ""), tips_payer_flat_id: tk.tips_payer_flat_id || "",
      tips_payer_type: tk.tips_payer_type || "owner", supplier: tk.supplier || "", notes: tk.notes || "",
    });
    setMedia(tk.media || []);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const saveReadings = async () => {
    try {
      await api.put("/readings", {
        property_id: propertyId, month,
        readings: readings.map((r) => ({
          meter_id: r.meter_id, opening: Number(r.opening || 0),
          closing: r.closing === "" || r.closing === null ? null : Number(r.closing),
          media: r.media || [],
        })),
      });
      toast.success("Readings saved");
      load(); setTick((t) => t + 1);
    } catch (err) { toast.error(errMsg(err)); }
  };

  const flatName = (id) => flats.find((f) => f.id === id)?.number || "—";
  const t = statement?.totals;

  const { sorted: sortedTankers, sort: tkSort, toggle: tkToggle } = useSort(tankers, {
    booking_date: (tk) => tk.booking_date || "",
    date: (tk) => tk.date || "",
    qty_sump: (tk) => Number(tk.qty_sump || 0),
    qty_syntex: (tk) => Number(tk.qty_syntex || 0),
    total_qty: (tk) => Number(tk.total_qty || 0),
    amount: (tk) => Number(tk.amount || 0),
    tips_amount: (tk) => Number(tk.tips_amount || 0),
    total_cost: (tk) => Number(tk.amount || 0) + Number(tk.tips_amount || 0),
    cost_per_litre: (tk) => (Number(tk.amount || 0) + Number(tk.tips_amount || 0)) / (Number(tk.total_qty) || 1),
    payer: (tk) => flatName(tk.payer_flat_id),
    tips_payer: (tk) => flatName(tk.tips_payer_flat_id || tk.payer_flat_id),
  }, "date");

  const { sorted: sortedReadings, sort: rdSort, toggle: rdToggle } = useSort(readings.map((r) => ({
    ...r, flat_number: flatName(r.flat_id),
  })), {
    label: (r) => r.label,
    flat_number: (r) => r.flat_number,
    opening: (r) => Number(r.opening || 0),
    closing: (r) => (r.closing === "" || r.closing === null ? -1 : Number(r.closing)),
    consumption: (r) => (r.closing === "" || r.closing === null ? -1 : Number(r.closing) - Number(r.opening)),
  }, "floor");

  return (
    <div>
      <PageHeader title="Water" subtitle={`${property?.name || ""} · tanker purchases & meter readings · ${monthLabel(month)}`} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <Stat testId="water-stat-purchased" label="Purchased" value={litres(t?.total_litres)} sub={`${money(t?.total_water_spend)} incl. tips`} />
        <Stat testId="water-stat-avg" label="Avg cost / L" value={`₹${num(t?.avg_cost_per_litre, 4)}`} sub="Weighted average" />
        <Stat testId="water-stat-consumed" label="Consumed" value={litres(t?.total_consumed)} sub="All flats" />
        <Stat testId="water-stat-reserve" label="Reserve" value={litres(t?.reserve_litres)}
              tone={t?.reserve_litres < 0 ? "warning" : "positive"} sub={money(t?.reserve_value)} />
      </div>

      <Tabs defaultValue="tankers">
        <TabsList className="h-auto bg-transparent p-0 gap-2 mb-6">
          <TabsTrigger value="tankers" data-testid="water-tab-tankers"
                       className="data-[state=active]:bg-slate-900 data-[state=active]:text-white border border-slate-200 rounded-md px-3 py-1.5 text-sm">Tanker purchases</TabsTrigger>
          <TabsTrigger value="readings" data-testid="water-tab-readings"
                       className="data-[state=active]:bg-slate-900 data-[state=active]:text-white border border-slate-200 rounded-md px-3 py-1.5 text-sm">Meter readings</TabsTrigger>
        </TabsList>

        <TabsContent value="tankers">
          <div className="grid lg:grid-cols-[minmax(0,400px)_minmax(0,1fr)] gap-6 [&>*]:min-w-0">
            <Card title={editId ? "Edit tanker purchase" : "New tanker purchase"} testId="tanker-form-card"
                  action={editId && (
                    <button onClick={() => { setEditId(null); setForm(blank); setMedia([]); }}
                            data-testid="cancel-tanker-edit-btn"
                            className="text-slate-400 hover:text-slate-900"><X className="w-4 h-4" /></button>
                  )}>
              {locked ? <p className="text-sm text-amber-700">This period is locked.</p> : (
                <form onSubmit={addTanker} className="space-y-4">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label className="label-caps">Booking date</Label>
                      <Input type="date" className="mt-2 h-11" data-testid="tanker-booking-date-input"
                             max={form.date || undefined}
                             value={form.booking_date}
                             onChange={(e) => setForm({ ...form, booking_date: e.target.value })} />
                    </div>
                    <div>
                      <Label className="label-caps">Delivery date</Label>
                      <Input type="date" className="mt-2 h-11" required data-testid="tanker-date-input"
                             min={form.booking_date || undefined}
                             value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
                    </div>
                  </div>
                  <p className="text-xs text-slate-500 -mt-2">
                    Water enters the reserve on the <b>delivery date</b>, which also decides the month this
                    purchase belongs to. Delivery cannot be before booking.
                  </p>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label className="label-caps">To sump (L)</Label>
                      <Input type="number" inputMode="decimal" step="any" className="mt-2 h-12 mono text-lg" data-testid="tanker-sump-input"
                             value={form.qty_sump} onChange={(e) => setForm({ ...form, qty_sump: e.target.value })} />
                    </div>
                    <div>
                      <Label className="label-caps">To syntex (L)</Label>
                      <Input type="number" inputMode="decimal" step="any" className="mt-2 h-12 mono text-lg" data-testid="tanker-syntex-input"
                             value={form.qty_syntex} onChange={(e) => setForm({ ...form, qty_syntex: e.target.value })} />
                    </div>
                  </div>
                  <div className="bg-slate-50 border border-slate-200 rounded-md px-3 py-2 flex justify-between text-sm">
                    <span className="text-slate-500">Total quantity</span>
                    <span className="mono font-semibold" data-testid="tanker-total-qty">{litres(totalQty)}</span>
                  </div>
                  <div>
                    <Label className="label-caps">Lorry amount paid</Label>
                    <Input type="number" inputMode="decimal" step="any" className="mt-2 h-12 mono text-lg" required data-testid="tanker-amount-input"
                           value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
                  </div>
                  <div className="bg-slate-50 border border-slate-200 rounded-md px-3 py-2 flex justify-between text-sm">
                    <span className="text-slate-500">Lorry + tips</span>
                    <span className="mono font-semibold" data-testid="tanker-total-cost">{money(totalCost)}</span>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label className="label-caps">Paid by flat</Label>
                      <Select value={form.payer_flat_id} onValueChange={(v) => setForm({ ...form, payer_flat_id: v })}>
                        <SelectTrigger className="mt-2 h-11" data-testid="tanker-payer-select"><SelectValue placeholder="Flat" /></SelectTrigger>
                        <SelectContent>{flats.map((f) => <SelectItem key={f.id} value={f.id}>{f.number} — {f.owner_name}</SelectItem>)}</SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="label-caps">Paid as</Label>
                      <Select value={form.payer_type} onValueChange={(v) => setForm({ ...form, payer_type: v })}>
                        <SelectTrigger className="mt-2 h-11" data-testid="tanker-payer-type-select"><SelectValue /></SelectTrigger>
                        <SelectContent><SelectItem value="owner">Owner</SelectItem><SelectItem value="tenant">Tenant</SelectItem></SelectContent>
                      </Select>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label className="label-caps">Tips paid to crew</Label>
                      <Input type="number" inputMode="decimal" step="any" className="mt-2 h-11 mono" data-testid="tanker-tips-input"
                             value={form.tips_amount} onChange={(e) => setForm({ ...form, tips_amount: e.target.value })} />
                    </div>
                    <div>
                      <Label className="label-caps">Tips paid by</Label>
                      <Select value={form.tips_payer_flat_id} onValueChange={(v) => setForm({ ...form, tips_payer_flat_id: v })}>
                        <SelectTrigger className="mt-2 h-11" data-testid="tanker-tips-payer-select"><SelectValue placeholder="Same flat" /></SelectTrigger>
                        <SelectContent>{flats.map((f) => <SelectItem key={f.id} value={f.id}>{f.number}</SelectItem>)}</SelectContent>
                      </Select>
                    </div>
                  </div>
                  <div className="bg-slate-50 border border-slate-200 rounded-md px-3 py-2 flex justify-between text-sm">
                    <span className="text-slate-500">Cost per litre <span className="text-slate-400">(incl. tips)</span></span>
                    <span className="mono font-semibold" data-testid="tanker-per-litre">₹{num(perLitre, 4)}</span>
                  </div>
                  <div>
                    <Label className="label-caps">Supplier / notes</Label>
                    <Input className="mt-2 h-11" data-testid="tanker-supplier-input"
                           value={form.supplier} onChange={(e) => setForm({ ...form, supplier: e.target.value })} />
                  </div>
                  <MediaUpload media={media} setMedia={setMedia} testId="tanker-media" />
                  <Button type="submit" data-testid="save-tanker-btn" className="w-full h-12 bg-slate-900 text-white">
                    <Truck className="w-4 h-4 mr-2" /> {editId ? "Save changes" : "Record purchase"}
                  </Button>
                </form>
              )}
            </Card>

            <Card title={`Purchases this month (${tankers.length})`} testId="tankers-table-card">
              {!tankers.length ? (
                <Empty testId="tankers-empty" title="No tanker purchases yet"
                       hint="Record each tanker with the split between sump and syntex; per-litre cost is computed for you." />
              ) : (
                <div className="overflow-x-auto">
                  <table className="data-table">
                    <thead>
                      <tr><th className="text-right">S.No</th>
                        <SortTh label="Booking" sortKey="booking_date" sort={tkSort} toggle={tkToggle} testId="tanker-sort-booking" />
                        <SortTh label="Delivery" sortKey="date" sort={tkSort} toggle={tkToggle} testId="tanker-sort-date" />
                        <SortTh label="Sump" sortKey="qty_sump" sort={tkSort} toggle={tkToggle} align="right" testId="tanker-sort-sump" />
                        <SortTh label="Syntex" sortKey="qty_syntex" sort={tkSort} toggle={tkToggle} align="right" testId="tanker-sort-syntex" />
                        <SortTh label="Total" sortKey="total_qty" sort={tkSort} toggle={tkToggle} align="right" testId="tanker-sort-total" />
                        <SortTh label="Lorry" sortKey="amount" sort={tkSort} toggle={tkToggle} align="right" testId="tanker-sort-amount" />
                        <SortTh label="Tips" sortKey="tips_amount" sort={tkSort} toggle={tkToggle} align="right" testId="tanker-sort-tips" />
                        <SortTh label="Total cost" sortKey="total_cost" sort={tkSort} toggle={tkToggle} align="right" testId="tanker-sort-cost" />
                        <SortTh label="₹/L" sortKey="cost_per_litre" sort={tkSort} toggle={tkToggle} align="right" testId="tanker-sort-perlitre" />
                        <SortTh label="Lorry paid by" sortKey="payer" sort={tkSort} toggle={tkToggle} testId="tanker-sort-payer" />
                        <SortTh label="Tips paid by" sortKey="tips_payer" sort={tkSort} toggle={tkToggle} testId="tanker-sort-tipspayer" />
                        <th>Media</th><th /></tr>
                    </thead>
                    <tbody>
                      {sortedTankers.map((tk, i) => (
                        <tr key={tk.id} data-testid={`tanker-row-${tk.id}`}>
                          <td className="num text-slate-500">{i + 1}</td>
                          <td className="text-slate-500">{dmy(tk.booking_date)}</td>
                          <td>{dmy(tk.date)}</td>
                          <td className="num">{num(tk.qty_sump, 0)}</td>
                          <td className="num">{num(tk.qty_syntex, 0)}</td>
                          <td className="num font-semibold">{num(tk.total_qty, 0)}</td>
                          <td className="num">{money(tk.amount)}</td>
                          <td className="num">{money(tk.tips_amount)}</td>
                          <td className="num font-semibold">{money((tk.amount || 0) + (tk.tips_amount || 0))}</td>
                          <td className="num">{num((((tk.amount || 0) + (tk.tips_amount || 0)) / (tk.total_qty || 1)), 4)}</td>
                          <td>{flatName(tk.payer_flat_id)} <span className="text-xs text-slate-400">({tk.payer_type})</span></td>
                          <td data-testid={`tanker-tips-payer-${tk.id}`}>
                            {tk.tips_amount ? (
                              <>{flatName(tk.tips_payer_flat_id || tk.payer_flat_id)}{" "}
                                <span className="text-xs text-slate-400">({tk.tips_payer_type || tk.payer_type})</span></>
                            ) : <span className="text-slate-400">—</span>}
                          </td>
                          <td><MediaThumbs media={tk.media} /></td>
                          <td className="text-right">
                            {!locked && (
                              <div className="flex justify-end gap-2">
                                <button onClick={() => editTanker(tk)} data-testid={`edit-tanker-${tk.id}`}
                                        className="text-slate-400 hover:text-slate-900">
                                  <Pencil className="w-4 h-4" />
                                </button>
                                <button onClick={async () => { await api.delete(`/tankers/${tk.id}`); load(); setTick((x) => x + 1); }}
                                        data-testid={`delete-tanker-${tk.id}`} className="text-slate-400 hover:text-red-600">
                                  <Trash2 className="w-4 h-4" />
                                </button>
                              </div>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr className="bg-slate-50 font-semibold" data-testid="tankers-footer">
                        <td colSpan={5}>Total Expense · split between {t?.flat_count || 0} house{(t?.flat_count || 0) === 1 ? "" : "s"}</td>
                        <td className="num">{num(t?.total_litres, 0)}</td>
                        <td className="num">{money((t?.total_water_spend || 0) - (t?.total_tips || 0))}</td>
                        <td className="num">{money(t?.total_tips)}</td>
                        <td className="num">{money(t?.total_water_spend)}</td>
                        <td colSpan={5} className="text-slate-500 font-normal">
                          Exp per head <span className="mono">{money((t?.total_water_spend || 0) / (t?.flat_count || 1))}</span>
                        </td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              )}
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="readings">
          <Card title="Meter readings" testId="readings-card"
                action={!locked && (
                  <Button onClick={saveReadings} data-testid="save-readings-btn" className="bg-slate-900 text-white h-9">
                    <Save className="w-4 h-4 mr-2" /> Save readings & photos
                  </Button>
                )}>
            {!readings.length ? (
              <Empty testId="readings-empty" title="No meters registered" hint="Register meters per flat in Building Setup first." />
            ) : (
              <>
                {statement?.flags?.filter((f) => f.type === "meter_rollback").map((f, i) => (
                  <div key={i} data-testid={`reading-flag-${i}`}
                       className="mb-3 flex items-start gap-2 bg-amber-50 border border-amber-200 text-amber-900 rounded-md px-3 py-2 text-sm">
                    <AlertTriangle className="w-4 h-4 mt-0.5" /> {f.message}
                  </div>
                ))}
                <div className="overflow-x-auto">
                  <table className="data-table">
                    <thead><tr><th className="text-right">S.No</th>
                      <SortTh label="Meter" sortKey="label" sort={rdSort} toggle={rdToggle} testId="reading-sort-meter" />
                      <SortTh label="Building / Flat" sortKey="floor" sort={rdSort} toggle={rdToggle} testId="reading-sort-flat" />
                      <SortTh label="Opening" sortKey="opening" sort={rdSort} toggle={rdToggle} align="right" testId="reading-sort-opening" />
                      <SortTh label="Closing" sortKey="closing" sort={rdSort} toggle={rdToggle} align="right" testId="reading-sort-closing" />
                      <SortTh label="Consumption" sortKey="consumption" sort={rdSort} toggle={rdToggle} align="right" testId="reading-sort-consumption" />
                      <th>Meter photo / video</th></tr></thead>
                    <tbody>
                      {sortedReadings.map((r, idx) => {
                        const cons = r.closing !== null && r.closing !== "" ? Number(r.closing) - Number(r.opening) : null;
                        return (
                          <tr key={r.meter_id} data-testid={`reading-row-${r.label}`}>
                            <td className="num text-slate-500">{idx + 1}</td>
                            <td className="font-semibold">{r.label}</td>
                            <td><span className="text-slate-400">{property?.name} / </span>{flatName(r.flat_id)}</td>
                            <td className="text-right">
                              <Input type="number" inputMode="decimal" step="any" disabled={locked}
                                     data-testid={`reading-opening-${r.label}`}
                                     className="h-10 w-28 mono text-right ml-auto" value={r.opening ?? ""}
                                     onChange={(e) => setReadings(readings.map((x, i) => i === idx ? { ...x, opening: e.target.value } : x))} />
                            </td>
                            <td className="text-right">
                              <Input type="number" inputMode="decimal" step="any" disabled={locked}
                                     data-testid={`reading-closing-${r.label}`}
                                     className="h-10 w-28 mono text-right ml-auto" value={r.closing ?? ""}
                                     onChange={(e) => setReadings(readings.map((x, i) => i === idx ? { ...x, closing: e.target.value } : x))} />
                            </td>
                            <td className={`num font-semibold ${cons !== null && cons < 0 ? "text-amber-600" : ""}`}>
                              {cons === null ? "—" : cons < 0 ? "0 · flagged" : num(cons)}
                            </td>
                            <td>
                              {locked ? <MediaThumbs media={r.media} /> : (
                                <MediaMini media={r.media || []} testId={`reading-media-${r.label}`}
                                           setMedia={(fn) => setReadings((prev) => prev.map((x, i) =>
                                             i === idx ? { ...x, media: typeof fn === "function" ? fn(x.media || []) : fn } : x))} />
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
