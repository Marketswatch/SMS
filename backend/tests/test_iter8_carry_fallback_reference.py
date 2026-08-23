"""Iteration 8 — fix round verification.

1. PUT /api/rentals/payments/{pid} reference enforcement (non-cash needs reference).
2. PUT /api/rentals/payouts/{pid} same, except is_credit=True bypasses.
3. Carry-forward fallback from property master when no bill doc was saved last month,
   guarded by unit_state() (upcoming lease / vacant -> 0).
4. Carry-forward with a saved previous bill (partial -> +, overpay -> -).
5. Regression: statement, bills list, receipt PDF.
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
M1 = "2028-05"          # "previous" month
M2 = "2028-06"          # month whose bill shows the carry-forward


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


def make_unit(admin, **over):
    body = {"name": f"TEST_I8 {TAG} {uuid.uuid4().hex[:4]}", "kind": "flat", "ownership": "own",
            "building_name": f"TEST_Bldg {TAG}", "rent_amount": 10000, "maintenance_amount": 500,
            "tenant_name": "TEST Tenant", "tenant_phone": "9876500011", "rent_due_day": 5,
            "lease_start": f"{M1}-01", "lease_months": 12, "status": "active"}
    body.update(over)
    r = admin.post(f"{API}/rentals/units", json=body, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.fixture(scope="module")
def unit(admin):
    uid = make_unit(admin)
    yield uid
    admin.delete(f"{API}/rentals/units/{uid}", timeout=30)


def bill_for(admin, month, uid):
    r = admin.get(f"{API}/rentals/bills", params={"month": month}, timeout=30)
    assert r.status_code == 200, r.text
    rows = [b for b in r.json() if b["unit_id"] == uid]
    assert rows, f"unit {uid} missing from bills {month}"
    return rows[0]


def clear_payments(admin, uid, month):
    for p in admin.get(f"{API}/rentals/payments", params={"month": month, "unit_id": uid},
                       timeout=30).json():
        admin.delete(f"{API}/rentals/payments/{p['id']}", timeout=30)


# ---------------------------------------------- PUT /payments reference enforcement
class TestUpdatePaymentReference:
    @pytest.fixture()
    def cash_payment(self, admin, unit):
        r = admin.post(f"{API}/rentals/payments", json={
            "unit_id": unit, "month": M2, "date": f"{M2}-08", "rent_paid": 900,
            "maintenance_paid": 0, "adhoc_paid": 0, "mode": "cash", "reference": "", "notes": "TEST",
        }, timeout=30)
        assert r.status_code == 200, r.text
        pid = r.json()["id"]
        yield pid
        admin.delete(f"{API}/rentals/payments/{pid}", timeout=30)

    def _put(self, admin, unit, pid, mode, reference):
        return admin.put(f"{API}/rentals/payments/{pid}", json={
            "unit_id": unit, "month": M2, "date": f"{M2}-08", "rent_paid": 900,
            "maintenance_paid": 0, "adhoc_paid": 0, "mode": mode, "reference": reference,
            "notes": "TEST",
        }, timeout=30)

    @pytest.mark.parametrize("mode", ["upi", "bank"])
    def test_non_cash_empty_reference_rejected(self, admin, unit, cash_payment, mode):
        r = self._put(admin, unit, cash_payment, mode, "")
        assert r.status_code == 400, f"{mode} without reference accepted ({r.status_code})"
        assert "reference number is required" in r.json()["detail"].lower()
        # untouched in db
        rows = admin.get(f"{API}/rentals/payments", params={"month": M2, "unit_id": unit},
                         timeout=30).json()
        got = next(x for x in rows if x["id"] == cash_payment)
        assert got["mode"] == "cash"

    def test_whitespace_reference_rejected(self, admin, unit, cash_payment):
        assert self._put(admin, unit, cash_payment, "upi", "   ").status_code == 400

    def test_non_cash_with_reference_accepted_and_persisted(self, admin, unit, cash_payment):
        ref = f"TEST-UPI-{TAG}"
        r = self._put(admin, unit, cash_payment, "upi", ref)
        assert r.status_code == 200, r.text
        assert r.json()["mode"] == "upi" and r.json()["reference"] == ref
        rows = admin.get(f"{API}/rentals/payments", params={"month": M2, "unit_id": unit},
                         timeout=30).json()
        got = next(x for x in rows if x["id"] == cash_payment)
        assert got["mode"] == "upi" and got["reference"] == ref
        assert "_id" not in got

    def test_cash_without_reference_accepted(self, admin, unit, cash_payment):
        r = self._put(admin, unit, cash_payment, "cash", "")
        assert r.status_code == 200, r.text
        assert r.json()["mode"] == "cash"


# ---------------------------------------------- PUT /payouts reference enforcement
class TestUpdatePayoutReference:
    @pytest.fixture()
    def payout(self, admin, unit):
        r = admin.post(f"{API}/rentals/payouts", json={
            "building_name": f"TEST_Bldg {TAG}", "unit_id": unit, "month": M2, "amount": 500,
            "date": f"{M2}-10", "category": "Maintenance", "note": "TEST", "mode": "cash",
            "reference": "", "is_credit": False, "media": [],
        }, timeout=30)
        assert r.status_code == 200, r.text
        pid = r.json()["id"]
        yield pid
        admin.delete(f"{API}/rentals/payouts/{pid}", timeout=30)

    def _put(self, admin, unit, pid, mode, reference, is_credit=False):
        return admin.put(f"{API}/rentals/payouts/{pid}", json={
            "building_name": f"TEST_Bldg {TAG}", "unit_id": unit, "month": M2, "amount": 500,
            "date": f"{M2}-10", "category": "Maintenance", "note": "TEST", "mode": mode,
            "reference": reference, "is_credit": is_credit, "media": [],
        }, timeout=30)

    @pytest.mark.parametrize("mode", ["upi", "bank"])
    def test_non_cash_empty_reference_rejected(self, admin, unit, payout, mode):
        r = self._put(admin, unit, payout, mode, "")
        assert r.status_code == 400, f"{mode} without reference accepted ({r.status_code})"
        assert "reference number is required" in r.json()["detail"].lower()

    def test_non_cash_with_reference_accepted(self, admin, unit, payout):
        ref = f"TEST-NEFT-{TAG}"
        r = self._put(admin, unit, payout, "bank", ref)
        assert r.status_code == 200, r.text
        assert r.json()["reference"] == ref and r.json()["mode"] == "bank"

    def test_cash_without_reference_accepted(self, admin, unit, payout):
        assert self._put(admin, unit, payout, "cash", "").status_code == 200

    def test_credit_without_reference_accepted(self, admin, unit, payout):
        r = self._put(admin, unit, payout, "bank", "", is_credit=True)
        assert r.status_code == 200, r.text
        assert r.json()["is_credit"] is True


# ---------------------------------------------- carry-forward fallback (no saved bill)
class TestCarryForwardFallback:
    def test_active_unit_no_prev_bill_uses_master(self, admin):
        uid = make_unit(admin)
        try:
            b1 = bill_for(admin, M1, uid)
            assert b1["is_draft"] is True, "no bill should be saved for M1"
            nxt = bill_for(admin, M2, uid)
            assert nxt["carry_forward"] == 10500, nxt
            assert nxt["totals"]["total_to_collect"] == 21000, nxt["totals"]
        finally:
            admin.delete(f"{API}/rentals/units/{uid}", timeout=30)

    def test_fallback_nets_off_payments_recorded_in_prev_month(self, admin):
        uid = make_unit(admin)
        try:
            r = admin.post(f"{API}/rentals/payments", json={
                "unit_id": uid, "month": M1, "date": f"{M1}-05", "rent_paid": 4000,
                "maintenance_paid": 500, "adhoc_paid": 0, "mode": "cash", "reference": "",
                "notes": "TEST",
            }, timeout=30)
            assert r.status_code == 200, r.text
            nxt = bill_for(admin, M2, uid)
            assert nxt["carry_forward"] == 6000, nxt
            assert nxt["totals"]["total_to_collect"] == 16500, nxt["totals"]
        finally:
            clear_payments(admin, uid, M1)
            admin.delete(f"{API}/rentals/units/{uid}", timeout=30)

    def test_fully_paid_prev_month_no_carry(self, admin):
        uid = make_unit(admin)
        try:
            r = admin.post(f"{API}/rentals/payments", json={
                "unit_id": uid, "month": M1, "date": f"{M1}-05", "rent_paid": 10000,
                "maintenance_paid": 500, "adhoc_paid": 0, "mode": "cash", "reference": "",
                "notes": "TEST",
            }, timeout=30)
            assert r.status_code == 200, r.text
            assert bill_for(admin, M2, uid)["carry_forward"] == 0
        finally:
            clear_payments(admin, uid, M1)
            admin.delete(f"{API}/rentals/units/{uid}", timeout=30)

    def test_lease_starting_this_month_gives_zero_carry(self, admin):
        """Lease starts in M2, so M1 had no dues."""
        uid = make_unit(admin, lease_start=f"{M2}-01")
        try:
            nxt = bill_for(admin, M2, uid)
            assert nxt["carry_forward"] == 0, nxt
            assert nxt["totals"]["total_to_collect"] == 10500, nxt["totals"]
        finally:
            admin.delete(f"{API}/rentals/units/{uid}", timeout=30)

    def test_vacant_unit_gives_zero_carry(self, admin):
        uid = make_unit(admin, status="vacant", vacant_since=f"{M1}-01")
        try:
            assert bill_for(admin, M2, uid)["carry_forward"] == 0
        finally:
            admin.delete(f"{API}/rentals/units/{uid}", timeout=30)

    def test_lease_ended_before_prev_month_gives_zero_carry(self, admin):
        uid = make_unit(admin, lease_start="2020-01-01", lease_months=12)
        try:
            assert bill_for(admin, M2, uid)["carry_forward"] == 0
        finally:
            admin.delete(f"{API}/rentals/units/{uid}", timeout=30)

    def test_unit_without_lease_start_created_now_has_no_bogus_dues(self, admin):
        """A unit created today with no lease dates must not show dues for past months."""
        uid = make_unit(admin, lease_start="", lease_months=0)
        try:
            nxt = bill_for(admin, M2, uid)
            assert nxt["carry_forward"] == 0, (
                f"unit with no lease_start shows bogus carry_forward {nxt['carry_forward']}")
        finally:
            admin.delete(f"{API}/rentals/units/{uid}", timeout=30)


# ---------------------------------------------- carry-forward with saved prev bill
class TestCarryForwardSavedBill:
    def test_partial_payment_positive_carry(self, admin):
        uid = make_unit(admin)
        try:
            r = admin.put(f"{API}/rentals/bills", json={
                "unit_id": uid, "month": M1, "rent": 10000, "maintenance": 0,
                "maintenance_payable": None, "carry_forward": 0, "items": [], "notes": "TEST",
            }, timeout=30)
            assert r.status_code == 200 and r.json()["totals"]["total_to_collect"] == 10000
            p = admin.post(f"{API}/rentals/payments", json={
                "unit_id": uid, "month": M1, "date": f"{M1}-05", "rent_paid": 4000,
                "maintenance_paid": 0, "adhoc_paid": 0, "mode": "cash", "reference": "",
                "notes": "TEST",
            }, timeout=30)
            assert p.status_code == 200, p.text
            nxt = bill_for(admin, M2, uid)
            assert nxt["carry_forward"] == 6000, nxt
            assert nxt["totals"]["total_to_collect"] == 16500, nxt["totals"]
        finally:
            clear_payments(admin, uid, M1)
            admin.delete(f"{API}/rentals/units/{uid}", timeout=30)

    def test_overpayment_negative_carry_reduces_next_total(self, admin):
        uid = make_unit(admin)
        try:
            admin.put(f"{API}/rentals/bills", json={
                "unit_id": uid, "month": M1, "rent": 10000, "maintenance": 0,
                "maintenance_payable": None, "carry_forward": 0, "items": [], "notes": "TEST",
            }, timeout=30)
            p = admin.post(f"{API}/rentals/payments", json={
                "unit_id": uid, "month": M1, "date": f"{M1}-05", "rent_paid": 10000,
                "maintenance_paid": 0, "adhoc_paid": 2000, "mode": "cash", "reference": "",
                "notes": "TEST",
            }, timeout=30)
            assert p.status_code == 200, p.text
            nxt = bill_for(admin, M2, uid)
            assert nxt["carry_forward"] == -2000, nxt
            assert nxt["totals"]["total_to_collect"] == 8500, nxt["totals"]
            st = admin.get(f"{API}/rentals/statement", params={"month": M2}, timeout=60)
            assert st.status_code == 200, st.text
            row = next(x for x in st.json()["rows"] if x["unit_id"] == uid)
            assert row["carry_forward"] == -2000 and row["total_to_collect"] == 8500
        finally:
            clear_payments(admin, uid, M1)
            admin.delete(f"{API}/rentals/units/{uid}", timeout=30)


# ---------------------------------------------- regression
class TestRegression:
    def test_bills_list_and_statement(self, admin):
        b = admin.get(f"{API}/rentals/bills", params={"month": M1}, timeout=60)
        assert b.status_code == 200 and isinstance(b.json(), list)
        assert all("_id" not in row for row in b.json())
        s = admin.get(f"{API}/rentals/statement", params={"month": M1}, timeout=60)
        assert s.status_code == 200 and "totals" in s.json()

    def test_receipt_pdf(self, admin, unit):
        p = admin.post(f"{API}/rentals/payments", json={
            "unit_id": unit, "month": M1, "date": f"{M1}-09", "rent_paid": 100,
            "maintenance_paid": 0, "adhoc_paid": 0, "mode": "cash", "reference": "",
            "notes": "TEST",
        }, timeout=30)
        assert p.status_code == 200, p.text
        pid = p.json()["id"]
        rec = admin.get(f"{API}/rentals/payments/{pid}/receipt", timeout=60)
        admin.delete(f"{API}/rentals/payments/{pid}", timeout=30)
        assert rec.status_code == 200 and rec.content[:4] == b"%PDF"

    def test_invalid_month_rejected(self, admin):
        assert admin.get(f"{API}/rentals/bills", params={"month": "2028-13"},
                         timeout=30).status_code == 400

    def test_requires_admin(self):
        r = requests.get(f"{API}/rentals/bills", params={"month": M1}, timeout=30)
        assert r.status_code in (401, 403), r.status_code
