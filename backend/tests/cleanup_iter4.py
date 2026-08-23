"""Remove TEST_* leftovers created by iteration-4 testing from the demo property."""
import os, re, sys
import requests
from dotenv import dotenv_values
from datetime import date

API = (os.environ.get("REACT_APP_BACKEND_URL")
       or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/") + "/api"
MONTH = date.today().strftime("%Y-%m")
c = open("/app/memory/test_credentials.md").read()
email = re.search(r'email.*?`([^`]+)`', c).group(1)
pwd = re.search(r'password.*?`([^`]+)`', c).group(1)
s = requests.Session()
tok = s.post(f"{API}/auth/login", json={"email": email, "password": pwd}).json()["access_token"]
s.headers["Authorization"] = f"Bearer {tok}"

props = s.get(f"{API}/properties").json()
for p in props:
    if p["name"].startswith("TEST_"):
        print("delete property", p["name"], s.delete(f"{API}/properties/{p['id']}").status_code)
demo = next((p for p in props if p["name"] == "Sunrise Residency"), None)
if demo:
    for t in s.get(f"{API}/tankers", params={"property_id": demo["id"], "month": MONTH}).json():
        if "TEST" in (t.get("supplier") or "") or "TEST" in (t.get("notes") or ""):
            print("delete tanker", t["id"], s.delete(f"{API}/tankers/{t['id']}").status_code)
    for ch in s.get(f"{API}/charges", params={"property_id": demo["id"], "month": MONTH}).json():
        if "TEST" in (ch.get("description") or ""):
            print("delete charge", ch["id"], s.delete(f"{API}/charges/{ch['id']}").status_code)

for u in s.get(f"{API}/rentals/units").json():
    if u["name"].startswith("TEST_"):
        print("delete unit", u["name"], s.delete(f"{API}/rentals/units/{u['id']}").status_code)

rr = s.get(f"{API}/rentals/rent-roll", params={"month": MONTH}).json()
print("rent roll totals", rr["totals"])
st = s.get(f"{API}/statement", params={"property_id": demo["id"], "month": MONTH}).json()["totals"]
print("maintenance totals", {k: st[k] for k in ("total_water_spend", "avg_cost_per_litre",
      "recurring_total", "maintenance_total", "billable_total")})
