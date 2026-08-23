"""Throwaway seed/cleanup for iteration-5 UI testing. Usage: python qa_iter5_seed.py [seed|clean]"""
import sys
from datetime import date, timedelta

import requests
from dotenv import dotenv_values

API = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
MONTH = date.today().strftime("%Y-%m")


def client():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "admin@societyhub.com", "password": "admin123"}, timeout=40)
    s.headers.update({"Authorization": "Bearer " + r.json()["access_token"]})
    return s


def seed(s):
    u1 = s.post(f"{API}/rentals/units", json={
        "name": "QA UI Flat", "kind": "flat", "ownership": "own", "owner_name": "Self",
        "address": "QA Street 1", "rent_amount": 20000, "rent_due_day": 5, "deposit_amount": 50000,
        "tenant_name": "QA Tenant", "tenant_phone": "9000000001",
        "lease_start": f"{MONTH}-01", "lease_end": "2027-12-31", "status": "active"}, timeout=40).json()
    u2 = s.post(f"{API}/rentals/units", json={
        "name": "QA UI Vacant", "kind": "shop", "ownership": "own", "owner_name": "Self",
        "rent_amount": 30000, "status": "vacant",
        "vacant_since": (date.today() - timedelta(days=100)).isoformat()}, timeout=40).json()
    c = s.post(f"{API}/rentals/collections", json={
        "unit_id": u1["id"], "month": MONTH, "kind": "rent", "amount": 12000,
        "date": f"{MONTH}-07", "mode": "upi", "notes": "QA ui rent"}, timeout=40).json()
    print("unit1", u1["id"], "unit2", u2["id"], "collection", c["id"])


def clean(s):
    for u in s.get(f"{API}/rentals/units", timeout=40).json():
        if u["name"].startswith("QA "):
            print("del", u["name"], s.delete(f"{API}/rentals/units/{u['id']}", timeout=40).status_code)


if __name__ == "__main__":
    c = client()
    (clean if len(sys.argv) > 1 and sys.argv[1] == "clean" else seed)(c)
