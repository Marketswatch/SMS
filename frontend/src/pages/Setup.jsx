import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { Plus, Trash2, Building2, Gauge, Droplet } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import { PageHeader, Card, Empty } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { money } from "@/lib/format";

const PAYER_KEYS = ["water", "cleaning", "sweeper", "security", "electricity", "misc", "maintenance", "tips"];
const RECURRING_KEYS = ["security", "electricity", "cleaning", "sweeper"];

export default function Setup() {
  const { propertyId, property, properties, bump, loadProperties, setPropertyId } = useApp();
  const [flats, setFlats] = useState([]);
  const [meters, setMeters] = useState([]);
  const [tanks, setTanks] = useState([]);
  const [users, setUsers] = useState([]);

  const [newProp, setNewProp] = useState({ name: "", address: "" });
  const [flat, setFlat] = useState({ number: "", owner_name: "", owner_user_id: "", tenant_name: "", tenant_user_id: "" });
  const [meter, setMeter] = useState({ flat_id: "", label: "", opening: "" });
  const [tank, setTank] = useState({ name: "", tank_type: "sump", capacity: "" });
  const [payers, setPayers] = useState({});
  const [recur, setRecur] = useState({});

  const load = useCallback(async () => {
    if (!propertyId) return;
    const [f, m, t, u] = await Promise.all([
      api.get("/flats", { params: { property_id: propertyId } }),
      api.get("/meters", { params: { property_id: propertyId } }),
      api.get("/tanks", { params: { property_id: propertyId } }),
      api.get("/users"),
    ]);
    setFlats(f.data); setMeters(m.data); setTanks(t.data); setUsers(u.data);
  }, [propertyId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (property) { setPayers(property.default_payers || {}); setRecur(property.recurring_defaults || {}); }
  }, [property]);

  const createProperty = async (e) => {
    e.preventDefault();
    try {
      const { data } = await api.post("/properties", newProp);
      toast.success("Building created");
      setNewProp({ name: "", address: "" });
      await loadProperties();
      setPropertyId(data.id);
      bump();
    } catch (err) { toast.error(errMsg(err)); }
  };

  const saveConfig = async () => {
    try {
      await api.put(`/properties/${propertyId}`, {
        name: property.name, address: property.address,
        default_payers: payers,
        recurring_defaults: Object.fromEntries(RECURRING_KEYS.map((k) => [k, Number(recur[k] || 0)])),
      });
      toast.success("Configuration saved");
      bump();
    } catch (err) { toast.error(errMsg(err)); }
  };

  const addFlat = async (e) => {
    e.preventDefault();
    try {
      await api.post("/flats", {
        property_id: propertyId, number: flat.number, owner_name: flat.owner_name,
        owner_user_id: flat.owner_user_id || null, tenant_name: flat.tenant_name,
        tenant_user_id: flat.tenant_user_id || null,
      });
      setFlat({ number: "", owner_name: "", owner_user_id: "", tenant_name: "", tenant_user_id: "" });
      toast.success("Flat added");
      load();
    } catch (err) { toast.error(errMsg(err)); }
  };

  const addMeter = async (e) => {
    e.preventDefault();
    try {
      await api.post("/meters", { property_id: propertyId, flat_id: meter.flat_id,
        label: meter.label, opening: Number(meter.opening || 0) });
      setMeter({ flat_id: "", label: "", opening: "" });
      toast.success("Meter registered");
      load();
    } catch (err) { toast.error(errMsg(err)); }
  };

  const addTank = async (e) => {
    e.preventDefault();
    try {
      await api.post("/tanks", { property_id: propertyId, name: tank.name,
        tank_type: tank.tank_type, capacity: Number(tank.capacity || 0) });
      setTank({ name: "", tank_type: "sump", capacity: "" });
      toast.success("Tank registered");
      load();
    } catch (err) { toast.error(errMsg(err)); }
  };

  const del = async (path, id) => {
    try { await api.delete(`${path}/${id}`); load(); bump(); } catch (err) { toast.error(errMsg(err)); }
  };

  return (
    <div>
      <PageHeader title="Building Setup" subtitle="Flats, owners, tenants, meters, tanks and charge defaults." />

      <Tabs defaultValue={properties.length ? "flats" : "building"}>
        <TabsList className="h-auto flex-wrap bg-transparent p-0 gap-2 mb-6">
          {["building", "flats", "meters", "tanks", "defaults"].map((k) => (
            <TabsTrigger key={k} value={k} data-testid={`setup-tab-${k}`}
                         className="capitalize data-[state=active]:bg-slate-900 data-[state=active]:text-white border border-slate-200 rounded-md px-3 py-1.5 text-sm">
              {k}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="building">
          <div className="grid lg:grid-cols-2 gap-6">
            <Card title="Create a building" testId="create-property-card">
              <form onSubmit={createProperty} className="space-y-4">
                <div>
                  <Label className="label-caps">Building name</Label>
                  <Input className="mt-2 h-11" required data-testid="property-name-input"
                         value={newProp.name} onChange={(e) => setNewProp({ ...newProp, name: e.target.value })} />
                </div>
                <div>
                  <Label className="label-caps">Address</Label>
                  <Input className="mt-2 h-11" data-testid="property-address-input"
                         value={newProp.address} onChange={(e) => setNewProp({ ...newProp, address: e.target.value })} />
                </div>
                <Button type="submit" data-testid="create-property-btn" className="bg-slate-900 text-white h-11">
                  <Building2 className="w-4 h-4 mr-2" /> Create building
                </Button>
              </form>
            </Card>
            <Card title="Properties" testId="property-list-card">
              {!properties.length ? <p className="text-sm text-slate-500">No buildings yet.</p> : (
                <table className="data-table">
                  <thead><tr><th>Name</th><th>Address</th><th /></tr></thead>
                  <tbody>
                    {properties.map((p) => (
                      <tr key={p.id} data-testid={`property-row-${p.id}`}>
                        <td className="font-semibold">{p.name}</td>
                        <td className="text-slate-500">{p.address || "—"}</td>
                        <td className="text-right">
                          <button onClick={() => del("/properties", p.id)} data-testid={`delete-property-${p.id}`}
                                  className="text-slate-400 hover:text-red-600"><Trash2 className="w-4 h-4" /></button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="flats">
          <div className="grid lg:grid-cols-[380px_1fr] gap-6">
            <Card title="Add flat" testId="add-flat-card">
              <form onSubmit={addFlat} className="space-y-4">
                <div>
                  <Label className="label-caps">Flat number</Label>
                  <Input className="mt-2 h-11" required data-testid="flat-number-input"
                         value={flat.number} onChange={(e) => setFlat({ ...flat, number: e.target.value })} />
                </div>
                <div>
                  <Label className="label-caps">Owner name</Label>
                  <Input className="mt-2 h-11" required data-testid="flat-owner-input"
                         value={flat.owner_name} onChange={(e) => setFlat({ ...flat, owner_name: e.target.value })} />
                </div>
                <div>
                  <Label className="label-caps">Owner login (optional)</Label>
                  <Select value={flat.owner_user_id} onValueChange={(v) => setFlat({ ...flat, owner_user_id: v === "none" ? "" : v })}>
                    <SelectTrigger className="mt-2 h-11" data-testid="flat-owner-user-select"><SelectValue placeholder="No login" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">No login</SelectItem>
                      {users.filter((u) => u.role === "owner").map((u) => (
                        <SelectItem key={u.id} value={u.id}>{u.name} ({u.email})</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="label-caps">Current tenant</Label>
                  <Input className="mt-2 h-11" data-testid="flat-tenant-input"
                         value={flat.tenant_name} onChange={(e) => setFlat({ ...flat, tenant_name: e.target.value })} />
                </div>
                <div>
                  <Label className="label-caps">Tenant login (optional)</Label>
                  <Select value={flat.tenant_user_id} onValueChange={(v) => setFlat({ ...flat, tenant_user_id: v === "none" ? "" : v })}>
                    <SelectTrigger className="mt-2 h-11" data-testid="flat-tenant-user-select"><SelectValue placeholder="No login" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">No login</SelectItem>
                      {users.filter((u) => u.role === "resident").map((u) => (
                        <SelectItem key={u.id} value={u.id}>{u.name} ({u.email})</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <Button type="submit" data-testid="add-flat-btn" className="bg-slate-900 text-white h-11 w-full">
                  <Plus className="w-4 h-4 mr-2" /> Add flat
                </Button>
              </form>
            </Card>
            <Card title={`Flats (${flats.length})`} testId="flats-table-card">
              {!flats.length ? <Empty testId="flats-empty" title="No flats yet" hint="Each flat is one equal share of common costs." /> : (
                <div className="overflow-x-auto">
                  <table className="data-table">
                    <thead><tr><th>Flat</th><th>Owner</th><th>Tenant</th><th className="text-right">Meters</th><th /></tr></thead>
                    <tbody>
                      {flats.map((f) => (
                        <tr key={f.id} data-testid={`flat-config-row-${f.number}`}>
                          <td className="font-semibold">{f.number}</td>
                          <td>{f.owner_name}</td>
                          <td className="text-slate-500">{f.tenant_name || "—"}</td>
                          <td className="num">{meters.filter((m) => m.flat_id === f.id).length}</td>
                          <td className="text-right">
                            <button onClick={() => del("/flats", f.id)} data-testid={`delete-flat-${f.number}`}
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

        <TabsContent value="meters">
          <div className="grid lg:grid-cols-[380px_1fr] gap-6">
            <Card title="Register water meter" testId="add-meter-card">
              <form onSubmit={addMeter} className="space-y-4">
                <div>
                  <Label className="label-caps">Flat</Label>
                  <Select value={meter.flat_id} onValueChange={(v) => setMeter({ ...meter, flat_id: v })}>
                    <SelectTrigger className="mt-2 h-11" data-testid="meter-flat-select"><SelectValue placeholder="Select flat" /></SelectTrigger>
                    <SelectContent>
                      {flats.map((f) => <SelectItem key={f.id} value={f.id}>{f.number} — {f.owner_name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="label-caps">Meter label</Label>
                  <Input className="mt-2 h-11" required data-testid="meter-label-input"
                         value={meter.label} onChange={(e) => setMeter({ ...meter, label: e.target.value })} />
                </div>
                <div>
                  <Label className="label-caps">Current reading (opening)</Label>
                  <Input className="mt-2 h-11 mono" type="number" inputMode="decimal" step="any" data-testid="meter-opening-input"
                         value={meter.opening} onChange={(e) => setMeter({ ...meter, opening: e.target.value })} />
                </div>
                <Button type="submit" disabled={!meter.flat_id} data-testid="add-meter-btn" className="bg-slate-900 text-white h-11 w-full">
                  <Gauge className="w-4 h-4 mr-2" /> Register meter
                </Button>
              </form>
            </Card>
            <Card title={`Meters (${meters.length})`} testId="meters-table-card">
              {!meters.length ? <Empty testId="meters-empty" title="No meters" hint="Multiple meters per flat are allowed; consumption is consolidated per flat." /> : (
                <table className="data-table">
                  <thead><tr><th>Label</th><th>Flat</th><th className="text-right">Opening</th><th /></tr></thead>
                  <tbody>
                    {meters.map((m) => (
                      <tr key={m.id} data-testid={`meter-row-${m.label}`}>
                        <td className="font-semibold">{m.label}</td>
                        <td>{flats.find((f) => f.id === m.flat_id)?.number || "—"}</td>
                        <td className="num">{m.opening}</td>
                        <td className="text-right">
                          <button onClick={() => del("/meters", m.id)} data-testid={`delete-meter-${m.label}`}
                                  className="text-slate-400 hover:text-red-600"><Trash2 className="w-4 h-4" /></button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="tanks">
          <div className="grid lg:grid-cols-[380px_1fr] gap-6">
            <Card title="Register tank" testId="add-tank-card">
              <form onSubmit={addTank} className="space-y-4">
                <div>
                  <Label className="label-caps">Tank name</Label>
                  <Input className="mt-2 h-11" required data-testid="tank-name-input"
                         value={tank.name} onChange={(e) => setTank({ ...tank, name: e.target.value })} />
                </div>
                <div>
                  <Label className="label-caps">Type</Label>
                  <Select value={tank.tank_type} onValueChange={(v) => setTank({ ...tank, tank_type: v })}>
                    <SelectTrigger className="mt-2 h-11" data-testid="tank-type-select"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="sump">Sump</SelectItem>
                      <SelectItem value="syntex">Syntex</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="label-caps">Capacity (litres)</Label>
                  <Input className="mt-2 h-11 mono" type="number" inputMode="decimal" data-testid="tank-capacity-input"
                         value={tank.capacity} onChange={(e) => setTank({ ...tank, capacity: e.target.value })} />
                </div>
                <Button type="submit" data-testid="add-tank-btn" className="bg-slate-900 text-white h-11 w-full">
                  <Droplet className="w-4 h-4 mr-2" /> Register tank
                </Button>
              </form>
            </Card>
            <Card title={`Tanks (${tanks.length})`} testId="tanks-table-card">
              {!tanks.length ? <Empty testId="tanks-empty" title="No tanks" hint="Register your sump and syntex tanks." /> : (
                <table className="data-table">
                  <thead><tr><th>Name</th><th>Type</th><th className="text-right">Capacity</th><th /></tr></thead>
                  <tbody>
                    {tanks.map((t) => (
                      <tr key={t.id} data-testid={`tank-row-${t.name}`}>
                        <td className="font-semibold">{t.name}</td>
                        <td className="capitalize">{t.tank_type}</td>
                        <td className="num">{t.capacity}</td>
                        <td className="text-right">
                          <button onClick={() => del("/tanks", t.id)} data-testid={`delete-tank-${t.name}`}
                                  className="text-slate-400 hover:text-red-600"><Trash2 className="w-4 h-4" /></button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="defaults">
          <div className="grid lg:grid-cols-2 gap-6">
            <Card title="Default payer per charge type" testId="payer-defaults-card">
              <p className="text-sm text-slate-500 mb-4">Who is normally responsible. Overridable on any single entry.</p>
              <div className="space-y-3">
                {PAYER_KEYS.map((k) => (
                  <div key={k} className="flex items-center justify-between gap-4">
                    <span className="text-sm capitalize text-slate-700">{k}</span>
                    <Select value={payers[k] || "owner"} onValueChange={(v) => setPayers({ ...payers, [k]: v })}>
                      <SelectTrigger className="h-10 w-36" data-testid={`payer-default-${k}`}><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="owner">Owner</SelectItem>
                        <SelectItem value="tenant">Tenant</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                ))}
              </div>
            </Card>
            <Card title="Fixed monthly recurring amounts" testId="recurring-defaults-card">
              <p className="text-sm text-slate-500 mb-4">Auto-populated into each new month; override per month in Charges.</p>
              <div className="space-y-3">
                {RECURRING_KEYS.map((k) => (
                  <div key={k} className="flex items-center justify-between gap-4">
                    <span className="text-sm capitalize text-slate-700">{k}</span>
                    <Input className="h-10 w-36 mono" type="number" inputMode="decimal" data-testid={`recurring-default-${k}`}
                           value={recur[k] ?? ""} onChange={(e) => setRecur({ ...recur, [k]: e.target.value })} />
                  </div>
                ))}
                <div className="pt-2 text-xs text-slate-500">
                  Total per month: <span className="mono">{money(RECURRING_KEYS.reduce((s, k) => s + Number(recur[k] || 0), 0))}</span>
                </div>
              </div>
            </Card>
            <div>
              <Button onClick={saveConfig} data-testid="save-config-btn" className="bg-slate-900 text-white h-11">
                Save configuration
              </Button>
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
