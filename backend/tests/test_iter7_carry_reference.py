"""Iteration 7 — editable bill amounts + carry-forward + payment mode/reference rules.

Covers: BillIn.carry_forward persistence, automatic carry-forward on next month's draft
(dues and advance credit), require_reference() on collections and payouts, mode/reference
in list responses, and regression on statement / receipt / export.
"""
import os
import uuid

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
API = f"{base_url.rstrip('/')}/api"

ADMIN = {"email": "admin@societyhub.com", "password": "admin123"}
TAG = uuid.uuid4().hex[:6]
M1 = "2027-03"
M2 = "2027-04"


def login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login failed {r.status_code}: {r.text[:300]}")
    tok = r.json().get("token") or r.json().get("access_token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def admin():
    return login(ADMIN)


@pytest.fixture(scope="module")
def unit(admin):
    r = admin.post(f"{API}/rentals/units", json={
        "name": f"TEST_Carry {TAG}", "kind": "flat", "ownership": "own",
        "building_name": f"TEST_Bldg {TAG}", "rent_amount": 10000, "maintenance_amount": 500,
        "tenant_name": "TEST Tenant", "tenant_phone": "9876500011", "rent_due_day": 5,
    }, timeout=30)
    assert r.status_code == 200, r.text
    uid = r.json()["id"]
    yield uid
    admin.delete(f"{API}/rentals/units/{uid}", timeout=30)


def bill_for(admin, month, uid):
    r = admin.get(f"{API}/rentals/bills", params={"month": month}, timeout=30)
    assert r.status_code == 200, r.text
    rows = [b for b in r.json() if b["unit_id"] == uid]
    assert rows, f"unit {uid} missing from bills {month}"
    return rows[0]


# ------------------------------------------------------- editable bill + carry field
class TestBillEditAndCarry:
    def test_draft_uses_master_amounts_and_zero_carry(self, admin, unit):
        b = bill_for(admin, M1, unit)
        assert b["is_draft"] is True
        assert b["rent"] == 10000
        assert b["maintenance"] == 500
        assert b["carry_forward"] == 0
        assert b["totals"]["total_to_collect"] == 10500
        assert "_id" not in b

    def test_edit_and_persist_amounts_with_carry(self, admin, unit):
        r = admin.put(f"{API}/rentals/bills", json={
            "unit_id": unit, "month": M1, "rent": 10000, "maintenance": 0,
            "maintenance_payable": None, "carry_forward": 250, "items": [], "notes": "TEST_edit",
        }, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["is_draft"] is False
        assert d["totals"]["carry_forward"] == 250
        assert d["totals"]["total_to_collect"] == 10250
        # persisted
        b = bill_for(admin, M1, unit)
        assert b["is_draft"] is False
        assert b["rent"] == 10000 and b["carry_forward"] == 250
        assert b["totals"]["total_to_collect"] == 10250

    def test_waive_carry_to_zero(self, admin, unit):
        r = admin.put(f"{API}/rentals/bills", json={
            "unit_id": unit, "month": M1, "rent": 10000, "maintenance": 0,
            "maintenance_payable": None, "carry_forward": 0, "items": [], "notes": "TEST_edit",
        }, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["totals"]["total_to_collect"] == 10000
        assert bill_for(admin, M1, unit)["carry_forward"] == 0


# ------------------------------------------------------- carry-forward end to end
class TestCarryForwardEndToEnd:
    @pytest.fixture(autouse=True)
    def m1_bill(self, admin, unit):
        """Month M1 billed at rent 10000, no maintenance, no carry."""
        r = admin.put(f"{API}/rentals/bills", json={
            "unit_id": unit, "month": M1, "rent": 10000, "maintenance": 0,
            "maintenance_payable": None, "carry_forward": 0, "items": [], "notes": "TEST_carry",
        }, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["totals"]["total_to_collect"] == 10000

    def _clear_payments(self, admin, unit, month):
        for p in admin.get(f"{API}/rentals/payments",
                           params={"month": month, "unit_id": unit}, timeout=30).json():
            admin.delete(f"{API}/rentals/payments/{p['id']}", timeout=30)

    def test_partial_payment_carries_dues(self, admin, unit):
        self._clear_payments(admin, unit, M1)
        r = admin.post(f"{API}/rentals/payments", json={
            "unit_id": unit, "month": M1, "date": f"{M1}-05", "rent_paid": 4000,
            "maintenance_paid": 0, "adhoc_paid": 0, "mode": "cash", "reference": "", "notes": "TEST",
        }, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["total"] == 4000

        nxt = bill_for(admin, M2, unit)
        assert nxt["is_draft"] is True
        assert nxt["carry_forward"] == 6000, nxt
        assert nxt["totals"]["carry_forward"] == 6000
        # 10000 rent + 500 maintenance master + 6000 dues
        assert nxt["totals"]["total_to_collect"] == 16500, nxt["totals"]

    def test_overpayment_carries_negative_advance(self, admin, unit):
        self._clear_payments(admin, unit, M1)
        r = admin.post(f"{API}/rentals/payments", json={
            "unit_id": unit, "month": M1, "date": f"{M1}-05", "rent_paid": 10000,
            "maintenance_paid": 0, "adhoc_paid": 2000, "mode": "cash", "reference": "", "notes": "TEST",
        }, timeout=30)
        assert r.status_code == 200, r.text

        nxt = bill_for(admin, M2, unit)
        assert nxt["carry_forward"] == -2000, nxt
        assert nxt["totals"]["total_to_collect"] == 8500, nxt["totals"]

    def test_statement_exposes_carry_forward(self, admin, unit):
        r = admin.get(f"{API}/rentals/statement", params={"month": M2}, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        row = next(x for x in data["rows"] if x["unit_id"] == unit)
        assert row["carry_forward"] == -2000
        assert row["total_to_collect"] == 8500
        assert "carry_forward" in data["totals"]

    def test_carry_cleared_when_month_settled(self, admin, unit):
        self._clear_payments(admin, unit, M1)
        r = admin.post(f"{API}/rentals/payments", json={
            "unit_id": unit, "month": M1, "date": f"{M1}-05", "rent_paid": 10000,
            "maintenance_paid": 0, "adhoc_paid": 0, "mode": "cash", "reference": "", "notes": "TEST",
        }, timeout=30)
        assert r.status_code == 200, r.text
        assert bill_for(admin, M2, unit)["carry_forward"] == 0


# ------------------------------------------------------- reference rules: collections
class TestCollectionReference:
    def test_non_cash_without_reference_rejected(self, admin, unit):
        for mode in ("upi", "bank"):
            r = admin.post(f"{API}/rentals/payments", json={
                "unit_id": unit, "month": M2, "date": f"{M2}-05", "rent_paid": 1000,
                "maintenance_paid": 0, "adhoc_paid": 0, "mode": mode, "reference": "", "notes": "TEST",
            }, timeout=30)
            assert r.status_code == 400, f"{mode}: {r.status_code} {r.text[:200]}"
            assert "reference number is required" in r.json()["detail"].lower()

    def test_whitespace_reference_rejected(self, admin, unit):
        r = admin.post(f"{API}/rentals/payments", json={
            "unit_id": unit, "month": M2, "date": f"{M2}-05", "rent_paid": 1000,
            "maintenance_paid": 0, "adhoc_paid": 0, "mode": "upi", "reference": "   ", "notes": "TEST",
        }, timeout=30)
        assert r.status_code == 400, r.text

    def test_non_cash_with_reference_succeeds_and_is_listed(self, admin, unit):
        ref = f"TEST-UPI-{TAG}"
        r = admin.post(f"{API}/rentals/payments", json={
            "unit_id": unit, "month": M2, "date": f"{M2}-06", "rent_paid": 1500,
            "maintenance_paid": 0, "adhoc_paid": 0, "mode": "upi", "reference": ref, "notes": "TEST",
        }, timeout=30)
        assert r.status_code == 200, r.text
        pid = r.json()["id"]
        assert r.json()["mode"] == "upi" and r.json()["reference"] == ref

        rows = admin.get(f"{API}/rentals/payments", params={"month": M2, "unit_id": unit}, timeout=30).json()
        got = next(x for x in rows if x["id"] == pid)
        assert got["mode"] == "upi" and got["reference"] == ref
        assert "_id" not in got
        admin.delete(f"{API}/rentals/payments/{pid}", timeout=30)

    def test_cash_without_reference_succeeds(self, admin, unit):
        r = admin.post(f"{API}/rentals/payments", json={
            "unit_id": unit, "month": M2, "date": f"{M2}-07", "rent_paid": 800,
            "maintenance_paid": 0, "adhoc_paid": 0, "mode": "cash", "reference": "", "notes": "TEST",
        }, timeout=30)
        assert r.status_code == 200, r.text
        pid = r.json()["id"]
        assert r.json()["mode"] == "cash"
        admin.delete(f"{API}/rentals/payments/{pid}", timeout=30)

    def test_update_payment_enforces_reference(self, admin, unit):
        r = admin.post(f"{API}/rentals/payments", json={
            "unit_id": unit, "month": M2, "date": f"{M2}-08", "rent_paid": 900,
            "maintenance_paid": 0, "adhoc_paid": 0, "mode": "cash", "reference": "", "notes": "TEST",
        }, timeout=30)
        assert r.status_code == 200, r.text
        pid = r.json()["id"]
        upd = admin.put(f"{API}/rentals/payments/{pid}", json={
            "unit_id": unit, "month": M2, "date": f"{M2}-08", "rent_paid": 900,
            "maintenance_paid": 0, "adhoc_paid": 0, "mode": "upi", "reference": "", "notes": "TEST",
        }, timeout=30)
        admin.delete(f"{API}/rentals/payments/{pid}", timeout=30)
        assert upd.status_code == 400, (
            f"PUT /payments allowed a non-cash payment without a reference (got {upd.status_code})")


# ------------------------------------------------------- reference rules: payouts
class TestPayoutReference:
    def test_non_cash_payout_without_reference_rejected(self, admin, unit):
        r = admin.post(f"{API}/rentals/payouts", json={
            "building_name": f"TEST_Bldg {TAG}", "unit_id": unit, "month": M2, "amount": 500,
            "date": f"{M2}-10", "category": "Maintenance", "note": "TEST", "mode": "bank",
            "reference": "", "is_credit": False, "media": [],
        }, timeout=30)
        assert r.status_code == 400, r.text
        assert "reference number is required" in r.json()["detail"].lower()

    def test_non_cash_payout_with_reference_succeeds(self, admin, unit):
        ref = f"TEST-NEFT-{TAG}"
        r = admin.post(f"{API}/rentals/payouts", json={
            "building_name": f"TEST_Bldg {TAG}", "unit_id": unit, "month": M2, "amount": 500,
            "date": f"{M2}-10", "category": "Maintenance", "note": "TEST", "mode": "bank",
            "reference": ref, "is_credit": False, "media": [],
        }, timeout=30)
        assert r.status_code == 200, r.text
        pid = r.json()["id"]
        rows = admin.get(f"{API}/rentals/payouts", params={"month": M2}, timeout=30).json()
        got = next(x for x in rows if x["id"] == pid)
        assert got["mode"] == "bank" and got["reference"] == ref
        assert "_id" not in got
        admin.delete(f"{API}/rentals/payouts/{pid}", timeout=30)

    def test_cash_payout_without_reference_succeeds(self, admin, unit):
        r = admin.post(f"{API}/rentals/payouts", json={
            "building_name": f"TEST_Bldg {TAG}", "unit_id": unit, "month": M2, "amount": 300,
            "date": f"{M2}-11", "category": "Maintenance", "note": "TEST", "mode": "cash",
            "reference": "", "is_credit": False, "media": [],
        }, timeout=30)
        assert r.status_code == 200, r.text
        admin.delete(f"{API}/rentals/payouts/{r.json()['id']}", timeout=30)

    def test_credit_without_reference_succeeds(self, admin, unit):
        r = admin.post(f"{API}/rentals/payouts", json={
            "building_name": f"TEST_Bldg {TAG}", "unit_id": unit, "month": M2, "amount": 400,
            "date": f"{M2}-12", "category": "Repair", "note": "TEST credit", "mode": "bank",
            "reference": "", "is_credit": True, "media": [],
        }, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["is_credit"] is True
        admin.delete(f"{API}/rentals/payouts/{r.json()['id']}", timeout=30)


# ------------------------------------------------------- regression
class TestRegression:
    def test_statement_and_export_and_receipt(self, admin, unit):
        s = admin.get(f"{API}/rentals/statement", params={"month": M1}, timeout=60)
        assert s.status_code == 200, s.text

        csv_r = admin.get(f"{API}/rentals/export", params={"month": M1, "format": "csv"}, timeout=60)
        assert csv_r.status_code == 200 and "text/csv" in csv_r.headers.get("content-type", "")

        pdf_r = admin.get(f"{API}/rentals/export", params={"month": M1, "format": "pdf"}, timeout=90)
        assert pdf_r.status_code == 200 and pdf_r.content[:4] == b"%PDF"

        p = admin.post(f"{API}/rentals/payments", json={
            "unit_id": unit, "month": M1, "date": f"{M1}-09", "rent_paid": 100,
            "maintenance_paid": 0, "adhoc_paid": 0, "mode": "cash", "reference": "", "notes": "TEST",
        }, timeout=30)
        assert p.status_code == 200, p.text
        rec = admin.get(f"{API}/rentals/payments/{p.json()['id']}/receipt", timeout=60)
        admin.delete(f"{API}/rentals/payments/{p.json()['id']}", timeout=30)
        assert rec.status_code == 200 and rec.content[:4] == b"%PDF"

    def test_invalid_month_rejected(self, admin):
        r = admin.get(f"{API}/rentals/bills", params={"month": "2027-13"}, timeout=30)
        assert r.status_code == 400, r.text

    def test_bills_requires_admin(self):
        r = requests.get(f"{API}/rentals/bills", params={"month": M1}, timeout=30)
        assert r.status_code in (401, 403), r.status_code
