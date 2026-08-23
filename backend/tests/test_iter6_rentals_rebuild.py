"""Iteration 6 — rebuilt property/rentals module.

Covers: property master + lease-end helper, category master, bill upsert/draft/totals,
collection segregation, deposits isolation, payouts + credits, statement math,
export CSV/PDF, receipt PDF, overview reconciliation, access control.
"""
import io
import os
import re
import zlib
import base64
import uuid

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE = base_url.rstrip("/")
API = f"{BASE}/api"

ADMIN = {"email": "admin@societyhub.com", "password": "admin123"}
RESIDENT = {"email": "tenant1@societyhub.com", "password": "demo123"}

MONTH = "2026-07"
TAG = uuid.uuid4().hex[:6]
QA_BUILDING = f"QA Assoc {TAG}"


def login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login failed {r.status_code}: {r.text[:300]}")
    tok = r.json().get("token") or r.json().get("access_token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="session")
def admin():
    return login(ADMIN)


@pytest.fixture(scope="session")
def resident():
    return login(RESIDENT)


@pytest.fixture(scope="session")
def qa_unit(admin):
    """QA property: rent 40000, maintenance 2500, deposit 100000."""
    payload = {
        "name": f"QA Prop {TAG}", "kind": "flat", "ownership": "own",
        "building_name": QA_BUILDING,
        "rent_amount": 40000, "maintenance_amount": 2500, "deposit_amount": 100000,
        "rent_due_day": 5, "tenant_name": "QA Tenant", "tenant_phone": "9999900000",
        "lease_start": "2026-01-01", "lease_months": 11, "status": "active",
    }
    r = admin.post(f"{API}/rentals/units", json=payload, timeout=30)
    assert r.status_code == 200, r.text[:300]
    unit = r.json()
    yield unit
    admin.delete(f"{API}/rentals/units/{unit['id']}", timeout=30)


def pdf_text(data: bytes) -> str:
    """Extract visible text from a simple reportlab PDF (no external deps)."""
    out = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S):
        raw = m.group(1).strip(b"\r\n")
        for dec in (lambda b: zlib.decompress(b),
                    lambda b: zlib.decompress(base64.a85decode(b, adobe=True)),
                    lambda b: b):
            try:
                txt = dec(raw)
                break
            except Exception:
                txt = None
        if not txt:
            continue
        for tm in re.finditer(rb"\((.*?)\)\s*Tj", txt, re.S):
            out.append(tm.group(1).decode("latin-1", "ignore"))
    return " ".join(out)


# ------------------------------------------------------- property master
class TestPropertyMaster:
    def test_lease_end_autocompute_on_create(self, qa_unit):
        assert qa_unit["lease_end"] == "2026-11-30", qa_unit
        assert qa_unit["rent_amount"] == 40000
        assert qa_unit["maintenance_amount"] == 2500
        assert qa_unit["deposit_amount"] == 100000
        assert "_id" not in qa_unit

    def test_lease_end_helper(self, admin):
        r = admin.get(f"{API}/rentals/lease-end", params={"start": "2026-01-01", "months": 11}, timeout=30)
        assert r.status_code == 200
        assert r.json()["lease_end"] == "2026-11-30"

    def test_lease_end_helper_bad_input(self, admin):
        r = admin.get(f"{API}/rentals/lease-end", params={"start": "garbage", "months": 3}, timeout=30)
        assert r.status_code == 400, r.text[:200]
        r2 = admin.get(f"{API}/rentals/lease-end", params={"start": "2026-01-01", "months": 0}, timeout=30)
        assert r2.status_code == 400

    def test_manual_end_date_without_months(self, admin, qa_unit):
        body = {"name": qa_unit["name"], "ownership": "own", "building_name": QA_BUILDING,
                "rent_amount": 40000, "maintenance_amount": 2500, "deposit_amount": 100000,
                "rent_due_day": 5, "tenant_name": "QA Tenant", "tenant_phone": "9999900000",
                "lease_start": "2026-01-01", "lease_months": 0, "lease_end": "2027-03-15",
                "status": "active"}
        r = admin.put(f"{API}/rentals/units/{qa_unit['id']}", json=body, timeout=30)
        assert r.status_code == 200
        assert r.json()["lease_end"] == "2027-03-15"
        # restore
        body.update({"lease_months": 11, "lease_end": ""})
        r = admin.put(f"{API}/rentals/units/{qa_unit['id']}", json=body, timeout=30)
        assert r.json()["lease_end"] == "2026-11-30"

    def test_unknown_unit_404(self, admin):
        r = admin.put(f"{API}/rentals/units/507f1f77bcf86cd799439011",
                      json={"name": "x"}, timeout=30)
        assert r.status_code == 404

    def test_bad_kind_and_ownership(self, admin):
        r = admin.post(f"{API}/rentals/units", json={"name": "QA bad", "kind": "castle"}, timeout=30)
        assert r.status_code == 400
        r = admin.post(f"{API}/rentals/units", json={"name": "QA bad", "ownership": "rented"}, timeout=30)
        assert r.status_code == 400


# ---------------------------------------------------------- category master
class TestCategories:
    def test_defaults_seeded(self, admin):
        r = admin.get(f"{API}/rentals/categories", timeout=30)
        assert r.status_code == 200
        names = [c["name"] for c in r.json()]
        for expected in ["Repair", "Water tanker", "Common electricity", "Painting",
                         "Genset charges", "STP charges", "Property tax", "Other"]:
            assert expected in names, names

    def test_add_and_dedupe(self, admin):
        name = f"QA Cat {TAG}"
        r = admin.post(f"{API}/rentals/categories", json={"name": name}, timeout=30)
        assert r.status_code == 200
        cid = r.json()["id"]
        # case-insensitive duplicate returns same doc
        r2 = admin.post(f"{API}/rentals/categories", json={"name": name.upper()}, timeout=30)
        assert r2.status_code == 200
        assert r2.json()["id"] == cid
        listed = [c["name"] for c in admin.get(f"{API}/rentals/categories", timeout=30).json()]
        assert listed.count(name) == 1
        assert admin.delete(f"{API}/rentals/categories/{cid}", timeout=30).status_code == 200

    def test_blank_rejected(self, admin):
        r = admin.post(f"{API}/rentals/categories", json={"name": "   "}, timeout=30)
        assert r.status_code == 400


# ------------------------------------------------------------------- bills
class TestBills:
    def test_draft_prefilled_from_master(self, admin, qa_unit):
        r = admin.get(f"{API}/rentals/bills", params={"month": MONTH}, timeout=30)
        assert r.status_code == 200
        row = next(b for b in r.json() if b["unit_id"] == qa_unit["id"])
        assert row["is_draft"] is True
        assert row["rent"] == 40000 and row["maintenance"] == 2500
        assert row["totals"]["total_to_collect"] == 42500
        assert row["tenant_name"] == "QA Tenant"

    def test_upsert_with_adhoc_and_totals(self, admin, qa_unit):
        body = {
            "unit_id": qa_unit["id"], "month": MONTH, "rent": 40000, "maintenance": 2500,
            "maintenance_payable": None,
            "items": [
                {"category": "Water tanker", "note": "2 tankers", "amount": 3000,
                 "direction": "collect", "pay_to_building": True},
                {"category": "Common electricity", "note": "paid at office", "amount": 1200,
                 "direction": "tenant_paid", "pay_to_building": True},
            ],
            "notes": "QA bill",
        }
        r = admin.put(f"{API}/rentals/bills", json=body, timeout=30)
        assert r.status_code == 200, r.text[:300]
        t = r.json()["totals"]
        assert t["adhoc_collect"] == 3000
        assert t["tenant_paid_on_my_behalf"] == 1200
        assert t["total_to_collect"] == 44300  # 40000+2500+3000-1200

        # re-open shows saved values (upsert, not duplicate)
        again = admin.get(f"{API}/rentals/bills", params={"month": MONTH}, timeout=30).json()
        mine = [b for b in again if b["unit_id"] == qa_unit["id"]]
        assert len(mine) == 1
        assert mine[0]["is_draft"] is False
        assert mine[0]["totals"]["total_to_collect"] == 44300
        assert len(mine[0]["items"]) == 2
        assert mine[0]["items"][0]["note"] == "2 tankers"

    def test_bad_month(self, admin, qa_unit):
        r = admin.get(f"{API}/rentals/bills", params={"month": "2026-13"}, timeout=30)
        assert r.status_code == 400
        r = admin.put(f"{API}/rentals/bills", json={"unit_id": qa_unit["id"], "month": "junk"}, timeout=30)
        assert r.status_code == 400

    def test_bill_unknown_unit_404(self, admin):
        r = admin.put(f"{API}/rentals/bills",
                      json={"unit_id": "507f1f77bcf86cd799439011", "month": MONTH}, timeout=30)
        assert r.status_code == 404


# ------------------------------------------------- collections / segregation
class TestCollections:
    payment_id = None

    def test_statement_before_collection(self, admin, qa_unit):
        st = admin.get(f"{API}/rentals/statement", params={"month": MONTH}, timeout=30).json()
        row = next(r for r in st["rows"] if r["unit_id"] == qa_unit["id"])
        assert row["total_to_collect"] == 44300
        assert row["collected"] == 0
        assert row["balance"] == 44300
        assert row["rent_outstanding"] == 40000
        assert row["maintenance_outstanding"] == 2500
        assert row["adhoc_outstanding"] == 1800  # 3000 - 1200

    def test_record_split_payment(self, admin, qa_unit):
        r = admin.post(f"{API}/rentals/payments", json={
            "unit_id": qa_unit["id"], "month": MONTH, "date": f"{MONTH}-06",
            "rent_paid": 40000, "maintenance_paid": 2500, "adhoc_paid": 0,
            "mode": "upi", "reference": "QA-UPI-1", "notes": "QA collection"}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        p = r.json()
        assert p["total"] == 42500
        TestCollections.payment_id = p["id"]

        st = admin.get(f"{API}/rentals/statement", params={"month": MONTH}, timeout=30).json()
        row = next(x for x in st["rows"] if x["unit_id"] == qa_unit["id"])
        assert row["rent_paid"] == 40000
        assert row["maintenance_paid"] == 2500
        assert row["adhoc_paid"] == 0
        assert row["collected"] == 42500
        assert row["balance"] == 1800
        assert row["adhoc_outstanding"] == 1800
        assert row["status"] in ("pending", "overdue")

    def test_receipt_pdf(self, admin):
        pid = TestCollections.payment_id
        assert pid, "no payment recorded"
        r = admin.get(f"{API}/rentals/payments/{pid}/receipt", timeout=60)
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF", r.content[:20]
        txt = pdf_text(r.content)
        assert "Payment Receipt" in txt
        assert "Rent" in txt and "Maintenance" in txt and "Ad-hoc" in txt
        assert "40,000.00" in txt and "2,500.00" in txt and "42,500.00" in txt

    def test_receipt_unknown_404(self, admin):
        r = admin.get(f"{API}/rentals/payments/507f1f77bcf86cd799439011/receipt", timeout=30)
        assert r.status_code == 404

    def test_delete_payment_reverses(self, admin, qa_unit):
        pid = TestCollections.payment_id
        assert admin.delete(f"{API}/rentals/payments/{pid}", timeout=30).status_code == 200
        st = admin.get(f"{API}/rentals/statement", params={"month": MONTH}, timeout=30).json()
        row = next(x for x in st["rows"] if x["unit_id"] == qa_unit["id"])
        assert row["collected"] == 0
        assert row["balance"] == 44300
        # re-create for downstream building/overview tests
        r = admin.post(f"{API}/rentals/payments", json={
            "unit_id": qa_unit["id"], "month": MONTH, "date": f"{MONTH}-06",
            "rent_paid": 40000, "maintenance_paid": 2500, "adhoc_paid": 0, "mode": "upi",
            "reference": "QA-UPI-2"}, timeout=30)
        TestCollections.payment_id = r.json()["id"]

    def test_cleanup_payment(self, admin):
        # leave DB clean at end of class; re-added by payout class if needed
        pass


# ---------------------------------------------------------------- deposits
class TestDeposits:
    def test_deposit_separate_from_bill(self, admin, qa_unit):
        r = admin.post(f"{API}/rentals/deposits", json={
            "unit_id": qa_unit["id"], "month": "2026-01", "kind": "deposit",
            "amount": 100000, "date": "2026-01-01", "mode": "bank", "notes": "QA deposit"}, timeout=30)
        assert r.status_code == 200
        d1 = r.json()["id"]
        r = admin.post(f"{API}/rentals/deposits", json={
            "unit_id": qa_unit["id"], "month": "2026-03", "kind": "deposit_deduction",
            "amount": 5000, "date": "2026-03-01", "notes": "QA damage"}, timeout=30)
        d2 = r.json()["id"]

        st = admin.get(f"{API}/rentals/statement", params={"month": MONTH}, timeout=30).json()
        row = next(x for x in st["rows"] if x["unit_id"] == qa_unit["id"])
        assert row["deposit_held"] == 95000  # accumulates across ALL months
        assert row["deposit_expected"] == 100000
        # deposits must NOT touch the monthly bill or collected
        assert row["total_to_collect"] == 44300
        assert row["collected"] == 42500

        for did in (d1, d2):
            assert admin.delete(f"{API}/rentals/deposits/{did}", timeout=30).status_code == 200

    def test_bad_deposit_kind(self, admin, qa_unit):
        r = admin.post(f"{API}/rentals/deposits", json={
            "unit_id": qa_unit["id"], "month": MONTH, "kind": "bribe",
            "amount": 10, "date": f"{MONTH}-01"}, timeout=30)
        assert r.status_code == 400


# ----------------------------------------------------------------- payouts
class TestPayouts:
    ids = []

    def test_building_payable_and_credits(self, admin, qa_unit):
        st = admin.get(f"{API}/rentals/statement", params={"month": MONTH}, timeout=30).json()
        b = next(x for x in st["buildings"] if x["building"] == QA_BUILDING)
        assert b["payable"] == 5500     # maintenance 2500 + adhoc-to-building 3000
        assert b["credits"] == 1200     # tenant paid common electricity on my behalf
        assert b["paid"] == 0
        assert b["balance"] == 4300

    def test_payout_and_credit_payout(self, admin):
        r = admin.post(f"{API}/rentals/payouts", json={
            "building_name": QA_BUILDING, "month": MONTH, "amount": 2000,
            "date": f"{MONTH}-10", "category": "Maintenance", "note": "QA payout",
            "mode": "bank", "reference": "QA-NEFT-1"}, timeout=30)
        assert r.status_code == 200
        TestPayouts.ids.append(r.json()["id"])
        r = admin.post(f"{API}/rentals/payouts", json={
            "building_name": QA_BUILDING, "month": MONTH, "amount": 900,
            "date": f"{MONTH}-11", "category": "Common electricity",
            "note": "QA bill I paid for them", "is_credit": True}, timeout=30)
        assert r.status_code == 200
        TestPayouts.ids.append(r.json()["id"])

        st = admin.get(f"{API}/rentals/statement", params={"month": MONTH}, timeout=30).json()
        b = next(x for x in st["buildings"] if x["building"] == QA_BUILDING)
        assert b["payable"] == 5500
        assert b["paid"] == 2000
        assert b["credits"] == 2100          # 1200 tenant + 900 credit payout
        assert b["balance"] == 5500 - 2000 - 2100
        assert b["balance"] == 1400

    def test_arithmetic_chain_matches_spec(self, admin, qa_unit):
        """User's manual chain, minus the 2000 non-credit payout."""
        st = admin.get(f"{API}/rentals/statement", params={"month": MONTH}, timeout=30).json()
        row = next(x for x in st["rows"] if x["unit_id"] == qa_unit["id"])
        b = next(x for x in st["buildings"] if x["building"] == QA_BUILDING)
        assert (row["total_to_collect"], row["collected"], row["balance"],
                row["adhoc_outstanding"]) == (44300, 42500, 1800, 1800)
        assert (b["payable"], b["credits"]) == (5500, 2100)
        assert b["balance"] == 3400 - 2000  # spec 3400 without my extra 2000 payout

    def test_payout_bad_month(self, admin):
        r = admin.post(f"{API}/rentals/payouts", json={
            "building_name": QA_BUILDING, "month": "nope", "amount": 10, "date": "2026-07-01"}, timeout=30)
        assert r.status_code == 400

    def test_payout_delete(self, admin):
        for pid in TestPayouts.ids:
            assert admin.delete(f"{API}/rentals/payouts/{pid}", timeout=30).status_code == 200
        st = admin.get(f"{API}/rentals/statement", params={"month": MONTH}, timeout=30).json()
        b = next(x for x in st["buildings"] if x["building"] == QA_BUILDING)
        assert b["paid"] == 0 and b["credits"] == 1200


# --------------------------------------------------------------- statuses
class TestStatuses:
    def test_vacant_bills_zero(self, admin, qa_unit):
        base = {"name": qa_unit["name"], "ownership": "own", "building_name": QA_BUILDING,
                "rent_amount": 40000, "maintenance_amount": 2500, "deposit_amount": 100000,
                "rent_due_day": 5, "tenant_name": "QA Tenant", "tenant_phone": "9999900000",
                "lease_start": "2026-01-01", "lease_months": 11}
        admin.put(f"{API}/rentals/units/{qa_unit['id']}",
                  json={**base, "status": "vacant", "vacant_since": "2026-06-01"}, timeout=30)
        st = admin.get(f"{API}/rentals/statement", params={"month": MONTH}, timeout=30).json()
        row = next(x for x in st["rows"] if x["unit_id"] == qa_unit["id"])
        assert row["status"] == "vacant"
        assert row["total_to_collect"] == 0
        assert row["billed_rent"] == 0 and row["billed_maintenance"] == 0
        assert row["vacant_days"] > 0 and row["lost_rent"] > 0
        assert row["maintenance_payable_to_building"] == 0

        # upcoming lease
        admin.put(f"{API}/rentals/units/{qa_unit['id']}",
                  json={**base, "lease_start": "2027-01-01", "status": "active"}, timeout=30)
        st = admin.get(f"{API}/rentals/statement", params={"month": MONTH}, timeout=30).json()
        row = next(x for x in st["rows"] if x["unit_id"] == qa_unit["id"])
        assert row["status"] == "upcoming"
        assert row["total_to_collect"] == 0

        # restore active
        admin.put(f"{API}/rentals/units/{qa_unit['id']}", json={**base, "status": "active"}, timeout=30)
        st = admin.get(f"{API}/rentals/statement", params={"month": MONTH}, timeout=30).json()
        row = next(x for x in st["rows"] if x["unit_id"] == qa_unit["id"])
        assert row["total_to_collect"] == 44300

    def test_paid_status(self, admin, qa_unit):
        r = admin.post(f"{API}/rentals/payments", json={
            "unit_id": qa_unit["id"], "month": MONTH, "date": f"{MONTH}-07",
            "adhoc_paid": 1800, "mode": "cash"}, timeout=30)
        pid = r.json()["id"]
        st = admin.get(f"{API}/rentals/statement", params={"month": MONTH}, timeout=30).json()
        row = next(x for x in st["rows"] if x["unit_id"] == qa_unit["id"])
        assert row["balance"] == 0
        assert row["status"] == "paid"
        assert row["adhoc_paid"] == 1800
        admin.delete(f"{API}/rentals/payments/{pid}", timeout=30)


# ---------------------------------------------------------------- exports
class TestExports:
    def test_csv(self, admin, qa_unit):
        r = admin.get(f"{API}/rentals/export", params={"month": MONTH, "format": "csv"}, timeout=60)
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")
        body = r.text
        assert qa_unit["name"] in body
        assert QA_BUILDING in body
        assert "44300" in body.replace(".0", "")
        assert "Building,Payable,Paid,Credits,Balance" in body

    def test_pdf(self, admin, qa_unit):
        r = admin.get(f"{API}/rentals/export", params={"month": MONTH, "format": "pdf"}, timeout=90)
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"
        txt = pdf_text(r.content)
        assert "Property Statement" in txt
        assert "Owed to buildings" in txt

    def test_export_bad_month(self, admin):
        r = admin.get(f"{API}/rentals/export", params={"month": "20-1", "format": "csv"}, timeout=30)
        assert r.status_code == 400


# --------------------------------------------------------------- overview
class TestOverview:
    def test_reconciles_with_statement(self, admin):
        st = admin.get(f"{API}/rentals/statement", params={"month": MONTH}, timeout=60).json()
        ov = admin.get(f"{API}/overview", params={"month": MONTH}, timeout=60)
        assert ov.status_code == 200, ov.text[:300]
        o = ov.json()
        assert len(o["rentals"]["rows"]) == len(st["rows"])
        assert o["rentals"]["totals"]["collected"] == st["totals"]["collected"]
        assert o["combined"]["rent_collected"] == st["totals"]["rent_collected"]
        assert o["combined"]["rent_pending"] == st["totals"]["pending"]
        m_out = o["combined"]["maintenance_outstanding"]
        assert round(o["combined"]["still_to_collect"], 2) == round(m_out + st["totals"]["pending"], 2)
        assert round(o["combined"]["money_in"], 2) == round(
            o["combined"]["maintenance_collected"] + st["totals"]["rent_collected"], 2)
        assert o["combined"]["deposits_held"] == st["totals"]["deposit_held"]

    def test_overview_bad_month(self, admin):
        r = admin.get(f"{API}/overview", params={"month": "bad"}, timeout=30)
        assert r.status_code in (400, 422)


# ---------------------------------------------------------- access control
class TestAccessControl:
    ENDPOINTS = [
        ("get", "/rentals/units", None),
        ("get", "/rentals/categories", None),
        ("get", "/rentals/bills", {"month": MONTH}),
        ("get", "/rentals/statement", {"month": MONTH}),
        ("get", "/rentals/rent-roll", {"month": MONTH}),
        ("get", "/rentals/payments", None),
        ("get", "/rentals/deposits", None),
        ("get", "/rentals/payouts", None),
        ("get", "/rentals/export", {"month": MONTH, "format": "csv"}),
        ("get", "/rentals/lease-end", {"start": "2026-01-01", "months": 3}),
        ("get", "/overview", {"month": MONTH}),
    ]

    @pytest.mark.parametrize("method,path,params", ENDPOINTS)
    def test_resident_forbidden(self, resident, method, path, params):
        r = getattr(resident, method)(f"{API}{path}", params=params, timeout=30)
        assert r.status_code == 403, f"{path} -> {r.status_code}"

    def test_resident_forbidden_writes(self, resident, qa_unit):
        r = resident.post(f"{API}/rentals/payments", json={
            "unit_id": qa_unit["id"], "month": MONTH, "date": f"{MONTH}-01", "rent_paid": 1}, timeout=30)
        assert r.status_code == 403
        r = resident.put(f"{API}/rentals/bills", json={"unit_id": qa_unit["id"], "month": MONTH}, timeout=30)
        assert r.status_code == 403

    def test_unauthenticated_401(self):
        r = requests.get(f"{API}/rentals/statement", params={"month": MONTH}, timeout=30)
        assert r.status_code == 401


# ------------------------------------------------------------- final cleanup
def test_zz_cleanup(admin, qa_unit):
    """Delete the QA bill/payment rows; unit teardown handles cascade."""
    pays = admin.get(f"{API}/rentals/payments", params={"unit_id": qa_unit["id"]}, timeout=30).json()
    for p in pays:
        admin.delete(f"{API}/rentals/payments/{p['id']}", timeout=30)
    bills = admin.get(f"{API}/rentals/bills", params={"month": MONTH}, timeout=30).json()
    for b in bills:
        if b["unit_id"] == qa_unit["id"] and b.get("id"):
            admin.delete(f"{API}/rentals/bills/{b['id']}", timeout=30)
    payouts = admin.get(f"{API}/rentals/payouts", params={"month": MONTH}, timeout=30).json()
    for p in payouts:
        if (p.get("building_name") or "") == QA_BUILDING:
            admin.delete(f"{API}/rentals/payouts/{p['id']}", timeout=30)
