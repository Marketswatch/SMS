import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { Plus, Trash2, Pencil, X } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import { PageHeader, Card, Empty } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { money } from "@/lib/format";

const blank = {
  name: "", kind: "flat", address: "", ownership: "own", owner_name: "", building_property_id: "", building_name: "",
  rent_amount: "", maintenance_amount: "", rent_due_day: "5", deposit_amount: "", tenant_name: "", tenant_phone: "",
  lease_start: "", lease_months: "", lease_end: "", vacant_since: "", status: "active", notes: "",
};

export default function Units() {
  const { properties } = useApp();
  const [units, setUnits] = useState([]);
  const [form, setForm] = useState(blank);
  const [editId, setEditId] = useState(null);

  const load = useCallback(async () => {
    const { data } = await api.get("/rentals/units");
    setUnits(data);
  }, []);
  useEffect(() => { load(); }, [load]);

  const submit = async (e) => {
    e.preventDefault();
    const payload = {
      ...form,
      building_property_id: form.building_property_id || null,
      rent_amount: Number(form.rent_amount || 0),
      maintenance_amount: Number(form.maintenance_amount || 0),
      deposit_amount: Number(form.deposit_amount || 0),
      rent_due_day: Number(form.rent_due_day || 5),
      lease_months: Number(form.lease_months || 0),
    };
    try {
      if (editId) await api.put(`/rentals/units/${editId}`, payload);
      else await api.post("/rentals/units", payload);
      toast.success(editId ? "Property updated" : "Property added");
      setForm(blank); setEditId(null); load();
    } catch (err) { toast.error(errMsg(err)); }
  };

  const edit = (u) => {
    setEditId(u.id);
    setForm({
      ...blank, ...u,
      building_property_id: u.building_property_id || "",
      rent_amount: String(u.rent_amount ?? ""), deposit_amount: String(u.deposit_amount ?? ""),
      maintenance_amount: String(u.maintenance_amount ?? ""), lease_months: String(u.lease_months || ""),
      rent_due_day: String(u.rent_due_day ?? 5),
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const del = async (id) => {
    try { await api.delete(`/rentals/units/${id}`); toast.success("Property removed"); load(); }
    catch (e) { toast.error(errMsg(e)); }
  };

  return (
    <div>
      <PageHeader title="Properties" subtitle="Flats, shops and houses you rent out — owned or managed for others." />
      <div className="grid lg:grid-cols-[380px_1fr] gap-6 [&>*]:min-w-0">
        <Card title={editId ? "Edit property" : "Add property"} testId="unit-form-card"
              action={editId && (
                <button onClick={() => { setEditId(null); setForm(blank); }} data-testid="cancel-unit-edit-btn"
                        className="text-slate-400 hover:text-slate-900"><X className="w-4 h-4" /></button>
              )}>
          <form onSubmit={submit} className="space-y-4">
            <div>
              <Label className="label-caps">Property name</Label>
              <Input className="mt-2 h-11" required data-testid="unit-name-input"
                     placeholder="e.g. MG Road Shop"
                     value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="label-caps">Type</Label>
                <Select value={form.kind} onValueChange={(v) => setForm({ ...form, kind: v })}>
                  <SelectTrigger className="mt-2 h-11" data-testid="unit-kind-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {["flat", "shop", "house", "office", "other"].map((k) =>
                      <SelectItem key={k} value={k} className="capitalize">{k}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="label-caps">Ownership</Label>
                <Select value={form.ownership} onValueChange={(v) => setForm({ ...form, ownership: v })}>
                  <SelectTrigger className="mt-2 h-11" data-testid="unit-ownership-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="own">I own it</SelectItem>
                    <SelectItem value="managed">Managed for someone</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            {form.ownership === "managed" && (
              <div>
                <Label className="label-caps">Owner name</Label>
                <Input className="mt-2 h-11" data-testid="unit-owner-input"
                       value={form.owner_name} onChange={(e) => setForm({ ...form, owner_name: e.target.value })} />
              </div>
            )}
            <div>
              <Label className="label-caps">Inside a building you maintain? (optional)</Label>
              <Select value={form.building_property_id || "none"}
                      onValueChange={(v) => setForm({ ...form, building_property_id: v === "none" ? "" : v })}>
                <SelectTrigger className="mt-2 h-11" data-testid="unit-building-select"><SelectValue placeholder="Standalone" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Standalone property</SelectItem>
                  {properties.map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}
                </SelectContent>
              </Select>
              <p className="text-xs text-slate-500 mt-1">Rent stays separate from that building's maintenance split.</p>
            </div>
            {!form.building_property_id && (
              <div>
                <Label className="label-caps">Building / association name</Label>
                <Input className="mt-2 h-11" data-testid="unit-building-name-input"
                       placeholder="e.g. Green Meadows Association"
                       value={form.building_name} onChange={(e) => setForm({ ...form, building_name: e.target.value })} />
                <p className="text-xs text-slate-500 mt-1">Used to match your payouts to the right association.</p>
              </div>
            )}
            <div>
              <Label className="label-caps">Address</Label>
              <Input className="mt-2 h-11" data-testid="unit-address-input"
                     value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
            </div>
            <div className="grid grid-cols-2 gap-3 items-end">
              <div>
                <Label className="label-caps">Monthly rent</Label>
                <Input type="number" inputMode="decimal" className="mt-2 h-12 mono text-lg" data-testid="unit-rent-input"
                       value={form.rent_amount} onChange={(e) => setForm({ ...form, rent_amount: e.target.value })} />
              </div>
              <div>
                <Label className="label-caps">Maintenance / month</Label>
                <Input type="number" inputMode="decimal" className="mt-2 h-12 mono text-lg" data-testid="unit-maintenance-input"
                       value={form.maintenance_amount} onChange={(e) => setForm({ ...form, maintenance_amount: e.target.value })} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3 items-end">
              <div>
                <Label className="label-caps">Security deposit</Label>
                <Input type="number" inputMode="decimal" className="mt-2 h-11 mono" data-testid="unit-deposit-input"
                       value={form.deposit_amount} onChange={(e) => setForm({ ...form, deposit_amount: e.target.value })} />
              </div>
              <div>
                <Label className="label-caps">Due day</Label>
                <Input type="number" inputMode="numeric" min="1" max="28" className="mt-2 h-11 mono"
                       data-testid="unit-due-day-input"
                       value={form.rent_due_day} onChange={(e) => setForm({ ...form, rent_due_day: e.target.value })} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="label-caps">Tenant name</Label>
                <Input className="mt-2 h-11" data-testid="unit-tenant-input"
                       value={form.tenant_name} onChange={(e) => setForm({ ...form, tenant_name: e.target.value })} />
              </div>
              <div>
                <Label className="label-caps">Tenant phone</Label>
                <Input type="tel" inputMode="tel" className="mt-2 h-11 mono" data-testid="unit-tenant-phone-input"
                       value={form.tenant_phone} onChange={(e) => setForm({ ...form, tenant_phone: e.target.value })} />
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3 items-end">
              <div>
                <Label className="label-caps">Lease start</Label>
                <Input type="date" className="mt-2 h-11" data-testid="unit-lease-start-input"
                       value={form.lease_start}
                       onChange={(e) => {
                         const start = e.target.value;
                         let end = form.lease_end;
                         if (start && Number(form.lease_months) > 0) {
                           const d = new Date(start);
                           d.setMonth(d.getMonth() + Number(form.lease_months));
                           d.setDate(d.getDate() - 1);
                           end = d.toISOString().slice(0, 10);
                         }
                         setForm({ ...form, lease_start: start, lease_end: end });
                       }} />
              </div>
              <div>
                <Label className="label-caps">Period (months)</Label>
                <Input type="number" inputMode="numeric" min="0" className="mt-2 h-11 mono" data-testid="unit-lease-months-input"
                       placeholder="11" value={form.lease_months}
                       onChange={(e) => {
                         const months = e.target.value;
                         let end = form.lease_end;
                         if (form.lease_start && Number(months) > 0) {
                           const d = new Date(form.lease_start);
                           d.setMonth(d.getMonth() + Number(months));
                           d.setDate(d.getDate() - 1);
                           end = d.toISOString().slice(0, 10);
                         }
                         setForm({ ...form, lease_months: months, lease_end: end });
                       }} />
              </div>
              <div>
                <Label className="label-caps">Lease end</Label>
                <Input type="date" className="mt-2 h-11" data-testid="unit-lease-end-input"
                       value={form.lease_end} onChange={(e) => setForm({ ...form, lease_end: e.target.value, lease_months: "" })} />
              </div>
            </div>
            <p className="text-xs text-slate-500 -mt-2">
              Enter a period in months and the end date fills itself, or pick the end date from the calendar.
            </p>
            <div>
              <Label className="label-caps">Status</Label>
              <Select value={form.status} onValueChange={(v) => setForm({ ...form, status: v })}>
                <SelectTrigger className="mt-2 h-11" data-testid="unit-status-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="active">Occupied / active lease</SelectItem>
                  <SelectItem value="vacant">Vacant</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {form.status === "vacant" && (
              <div>
                <Label className="label-caps">Vacant since</Label>
                <Input type="date" className="mt-2 h-11" data-testid="unit-vacant-since-input"
                       value={form.vacant_since} onChange={(e) => setForm({ ...form, vacant_since: e.target.value })} />
                <p className="text-xs text-slate-500 mt-1">Used to work out idle days and rent forgone.</p>
              </div>
            )}
            <Button type="submit" data-testid="save-unit-btn" className="w-full h-12 bg-slate-900 text-white">
              <Plus className="w-4 h-4 mr-2" /> {editId ? "Save changes" : "Add property"}
            </Button>
          </form>
        </Card>

        <Card title={`Properties (${units.length})`} testId="units-table-card">
          {!units.length ? <Empty testId="units-empty" title="No properties yet" hint="Add your first rental unit on the left." /> : (
            <div className="overflow-x-auto">
              <table className="data-table">
                  <thead><tr><th>Name</th><th>Type</th><th>Ownership</th><th>Tenant</th>
                    <th className="text-right">Rent</th><th className="text-right">Maint.</th>
                    <th className="text-right">Deposit</th>
                    <th>Lease</th><th>Status</th><th /></tr></thead>
                <tbody>
                  {units.map((u) => (
                    <tr key={u.id} data-testid={`unit-row-${u.name}`}>
                      <td className="font-semibold">{u.name}</td>
                      <td className="capitalize text-slate-500">{u.kind}</td>
                      <td>{u.ownership === "own" ? "Own" : `Managed · ${u.owner_name || "—"}`}</td>
                      <td>{u.tenant_name || "—"}</td>
                      <td className="num">{money(u.rent_amount)}</td>
                      <td className="num">{money(u.maintenance_amount)}</td>
                      <td className="num">{money(u.deposit_amount)}</td>
                      <td className="text-slate-500 text-xs">{u.lease_start || "—"} → {u.lease_end || "—"}
                        {u.lease_months ? <span className="text-slate-400"> ({u.lease_months}m)</span> : null}</td>
                      <td className="capitalize">{u.status}
                        {u.status === "vacant" && u.vacant_since && (
                          <div className="text-[11px] text-slate-500 mono normal-case"
                               data-testid={`unit-vacant-since-${u.name}`}>since {u.vacant_since}</div>
                        )}
                      </td>
                      <td className="text-right">
                        <div className="flex justify-end gap-2">
                          <button onClick={() => edit(u)} data-testid={`edit-unit-${u.name}`}
                                  className="text-slate-400 hover:text-slate-900"><Pencil className="w-4 h-4" /></button>
                          <button onClick={() => del(u.id)} data-testid={`delete-unit-${u.name}`}
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
