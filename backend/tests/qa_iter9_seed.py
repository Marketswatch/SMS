"""Iteration 9 QA seed: floors, meter readings, tankers (incl. differing tips payer),
charges and a partial payment for the current maintenance period."""
import requests, json
from dotenv import dotenv_values

BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
API = BASE + "/api"
M = "2026-08"
s = requests.Session()
s.post(f"{API}/auth/login", json={"email": "admin@societyhub.com", "password": "admin123"})
p = [x for x in s.get(f"{API}/properties").json() if x.get("kind", "maintenance") != "rental"][0]
pid = p["id"]
flats = s.get(f"{API}/flats", params={"property_id": pid}).json()
floors = {"101": "Ground", "102": "Ground", "201": "First", "202": "First"}
for f in flats:
    body = {k: f.get(k) or "" for k in ["property_id", "number", "owner_name", "owner_phone",
                                        "tenant_name", "tenant_phone"]}
    body["owner_user_id"] = f.get("owner_user_id")
    body["tenant_user_id"] = f.get("tenant_user_id")
    body["floor"] = floors.get(f["number"], "Ground")
    r = s.put(f"{API}/flats/{f['id']}", json=body)
    print("floor", f["number"], r.status_code, r.json().get("floor"))

fid = {f["number"]: f["id"] for f in flats}

# meter readings
rd = s.get(f"{API}/readings", params={"property_id": pid, "month": M}).json()
inc = {"Meter 101": 120, "Meter 102": 90, "Meter 201": 150, "Meter 202": 60}
rows = [{"meter_id": x["meter_id"], "opening": x["opening"],
         "closing": x["opening"] + inc.get(x["label"], 100), "media": []} for x in rd]
r = s.put(f"{API}/readings", json={"property_id": pid, "month": M, "rows": rows})
print("readings", r.status_code, str(r.json())[:120])

# tankers
for t in [
    {"date": f"{M}-05", "qty_sump": 6000, "qty_syntex": 0, "amount": 1400,
     "payer_flat_id": fid["101"], "payer_type": "owner", "tips_amount": 100,
     "tips_payer_flat_id": fid["201"], "tips_payer_type": "tenant", "supplier": "Krishna Water"},
    {"date": f"{M}-18", "qty_sump": 6000, "qty_syntex": 0, "amount": 1400,
     "payer_flat_id": fid["202"], "payer_type": "owner", "tips_amount": 100,
     "tips_payer_flat_id": fid["102"], "tips_payer_type": "owner", "supplier": "Krishna Water"},
]:
    t.update({"property_id": pid, "month": M})
    r = s.post(f"{API}/tankers", json=t)
    print("tanker", r.status_code, r.json().get("id"))

# charges
for c in [{"charge_type": "cleaning", "description": "Maid August", "amount": 2000,
           "date": f"{M}-02", "payer_flat_id": fid["101"], "payer_type": "owner"},
          {"charge_type": "maintenance", "description": "Motor repair", "amount": 3000,
           "date": f"{M}-10", "payer_flat_id": fid["201"], "payer_type": "owner"}]:
    c.update({"property_id": pid, "month": M})
    r = s.post(f"{API}/charges", json=c)
    print("charge", r.status_code, str(r.json())[:80])

# one payment -> partial/paid chip + payment date
r = s.post(f"{API}/payments", json={"property_id": pid, "month": M, "flat_id": fid["102"],
                                    "amount": 500, "date": f"{M}-20", "mode": "upi",
                                    "payer_type": "owner", "direction": "receipt",
                                    "notes": "QA seed"})
print("payment", r.status_code, str(r.json())[:120])

st = s.get(f"{API}/statement", params={"property_id": pid, "month": M}).json()
print(json.dumps(st["totals"], indent=0))
for x in st["rows"]:
    print(x["flat_number"], x["floor"], x["net"], x["payment_status"], x["last_paid_on"])
