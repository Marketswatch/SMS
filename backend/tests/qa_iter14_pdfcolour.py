"""Diagnostic: sample meter-row background colours in the meters PDF."""
import os
import fitz
import requests
from dotenv import dotenv_values

fe = dotenv_values("/app/frontend/.env")
API = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL")).rstrip("/") + "/api"
MONTH = "2026-08"
s = requests.Session()
s.post(f"{API}/auth/login", json={"email": "admin@societyhub.com", "password": "admin123"})
pid = [p for p in s.get(f"{API}/properties").json() if p["name"] == "Sunrise Residency"][0]["id"]
rows = s.get(f"{API}/statement", params={"property_id": pid, "month": MONTH}).json()["rows"]
flat = rows[0]
m = s.post(f"{API}/meters", json={"property_id": pid, "flat_id": flat["flat_id"],
                                  "label": "TEST_M2", "opening": 10})
mid = m.json()["id"]
try:
    stmt = s.get(f"{API}/statement", params={"property_id": pid, "month": MONTH}).json()
    print("meters:", [(x.get("flat_number"), x.get("label")) for x in stmt["meters"]])
    pdf = s.get(f"{API}/reports/pack", params={"property_id": pid, "month": MONTH,
                                              "report": "meters", "format": "pdf"}).content
    doc = fitz.open(stream=pdf, filetype="pdf")
    page = doc[0]
    zoom = 3.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    for x in stmt["meters"]:
        needle = x.get("label")
        hits = page.search_for(needle)
        if not hits:
            print("no hit", needle)
            continue
        r = hits[0]
        ys = int(((r.y0 + r.y1) / 2) * zoom)
        samples = {}
        for dx in (-14, -10, -6, 3, 8):
            xs = int((r.x0 + dx) * zoom)
            samples[dx] = pix.pixel(xs, ys)
        print(f"flat {x.get('flat_number')} meter {needle}: {samples}")
finally:
    print("delete meter:", s.delete(f"{API}/meters/{mid}").status_code)
