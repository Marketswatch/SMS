"""Seed / teardown a UI test property with a carry-forward for iteration 7 frontend tests.

Usage: python qa_iter7_seed.py seed | clean
"""
import os
import sys

import requests
from dotenv import dotenv_values

BASE = (os.environ.get("REACT_APP_BACKEND_URL")
        or dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE}/api"
NAME = "TEST_UI Carry"
M1, M2 = "2027-03", "2027-04"


def session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "admin@societyhub.com", "password": "admin123"}, timeout=30)
    r.raise_for_status()
    tok = r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


def find(s):
    for u in s.get(f"{API}/rentals/units", timeout=30).json():
        if u["name"] == NAME:
            return u["id"]
    return None


def seed():
    s = session()
    uid = find(s)
    if not uid:
        uid = s.post(f"{API}/rentals/units", json={
            "name": NAME, "kind": "flat", "ownership": "own", "building_name": "TEST_UI Assoc",
            "rent_amount": 10000, "maintenance_amount": 500, "deposit_amount": 20000,
            "tenant_name": "TEST UI Tenant", "tenant_phone": "9876500022", "rent_due_day": 5,
        }, timeout=30).json()["id"]
    s.put(f"{API}/rentals/bills", json={"unit_id": uid, "month": M1, "rent": 10000, "maintenance": 0,
                                        "maintenance_payable": None, "carry_forward": 0,
                                        "items": [], "notes": "TEST_ui"}, timeout=30).raise_for_status()
    for p in s.get(f"{API}/rentals/payments", params={"month": M1, "unit_id": uid}, timeout=30).json():
        s.delete(f"{API}/rentals/payments/{p['id']}", timeout=30)
    s.post(f"{API}/rentals/payments", json={"unit_id": uid, "month": M1, "date": f"{M1}-05",
                                            "rent_paid": 4000, "maintenance_paid": 0, "adhoc_paid": 0,
                                            "mode": "cash", "reference": "", "notes": "TEST_ui"},
           timeout=30).raise_for_status()
    b = [x for x in s.get(f"{API}/rentals/bills", params={"month": M2}, timeout=30).json() if x["unit_id"] == uid][0]
    print("seeded", uid, "carry", b["carry_forward"], "total", b["totals"]["total_to_collect"])


def clean():
    s = session()
    uid = find(s)
    if uid:
        s.delete(f"{API}/rentals/units/{uid}", timeout=30)
    print("cleaned", uid)


if __name__ == "__main__":
    (clean if len(sys.argv) > 1 and sys.argv[1] == "clean" else seed)()
