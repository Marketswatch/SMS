"""One-off cleanup of iteration-3 test artifacts."""
import os
import requests
from dotenv import dotenv_values

API = (os.environ.get("REACT_APP_BACKEND_URL")
       or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/") + "/api"
s = requests.Session()
r = s.post(f"{API}/auth/login", json={"email": "admin@societyhub.com", "password": "admin123"}, timeout=30)
tok = r.json().get("access_token") or r.json().get("token")
if tok:
    s.headers["Authorization"] = f"Bearer {tok}"

props = s.get(f"{API}/properties", timeout=30).json()
by_name = {p["name"]: p["id"] for p in props}
sun = by_name["Sunrise Residency"]
month = [p for p in s.get(f"{API}/periods", params={"property_id": sun}, timeout=30).json()
         if p["status"] == "open"][0]["month"]

# 1. TEST flats in any building
for pid in by_name.values():
    for f in s.get(f"{API}/flats", params={"property_id": pid}, timeout=30).json():
        if f["number"].startswith("TEST_"):
            print("delete flat", f["number"], s.delete(f"{API}/flats/{f['id']}", timeout=30).status_code)

# 2. TEST charges in Sunrise open month
for c in s.get(f"{API}/charges", params={"property_id": sun, "month": month}, timeout=30).json():
    if "TEST_" in (c.get("description") or ""):
        print("delete charge", c["description"], s.delete(f"{API}/charges/{c['id']}", timeout=30).status_code)

# 3. restore demo owner phones
want = {"101": "9876500101", "102": "9876500102", "201": "9876500101", "202": "9876500102"}
for f in s.get(f"{API}/flats", params={"property_id": sun}, timeout=30).json():
    if f["number"] in want and f.get("owner_phone") != want[f["number"]]:
        body = {k: f.get(k) for k in ("property_id", "number", "owner_name", "owner_user_id",
                                      "tenant_name", "tenant_user_id", "tenant_phone")}
        body["owner_phone"] = want[f["number"]]
        print("restore phone", f["number"], s.put(f"{API}/flats/{f['id']}", json=body, timeout=30).status_code)

# 4. clear reading media
rows = s.get(f"{API}/readings", params={"property_id": sun, "month": month}, timeout=30).json()
if any(r.get("media") for r in rows):
    payload = {"property_id": sun, "month": month, "readings": [
        {"meter_id": r["meter_id"], "opening": r["opening"], "closing": r["closing"], "media": []} for r in rows]}
    print("clear reading media", s.put(f"{API}/readings", json=payload, timeout=30).status_code)

st = s.get(f"{API}/statement", params={"property_id": sun, "month": month}, timeout=60).json()["totals"]
print("post-cleanup totals:", {k: st[k] for k in
      ("total_water_spend", "avg_cost_per_litre", "recurring_total", "maintenance_total", "billable_total")})
