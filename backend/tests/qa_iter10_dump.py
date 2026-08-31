import io, os, json, subprocess, requests
from dotenv import dotenv_values
fe = dotenv_values("/app/frontend/.env")
API = fe["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
s = requests.Session()
r = s.post(f"{API}/auth/login", json={"email": "admin@societyhub.com", "password": "admin123"})
tok = r.json().get("access_token") or r.json().get("token")
if tok: s.headers.update({"Authorization": f"Bearer {tok}"})
prop = [p for p in s.get(f"{API}/properties").json() if p.get("kind","maintenance")!="rental"][0]
month = s.get(f"{API}/periods", params={"property_id": prop["id"]}).json()[-1]["month"]
print("PROP", prop["name"], "MONTH", month)
st = s.get(f"{API}/statement", params={"property_id": prop["id"], "month": month}).json()
for row in st["rows"]:
    print({k: row.get(k) for k in ["flat_number","floor","owner_name","water_own_cost","reserve_share","water_cost","recurring_share","maintenance_share","base_cost","carry_in","contributions","received","net","payment_status","last_paid_on"]})
print("TOTALS", json.dumps(st["totals"], indent=None))
pdf = s.get(f"{API}/mis/export", params={"property_id": prop["id"], "month": month, "format": "pdf"}).content
open("/tmp/mis.pdf","wb").write(pdf)
csvt = s.get(f"{API}/mis/export", params={"property_id": prop["id"], "month": month, "format": "csv"}).text
open("/tmp/mis.csv","w").write(csvt)
print(csvt[:2500])
