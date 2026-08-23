"""Iteration 4 backend suite — rentals module, annual statement, tanker/charge editing.

Modules covered:
  * /api/rentals/units, /collections, /expenses  (CRUD)
  * /api/rentals/rent-roll  (math, status logic, deposits across months, building tally)
  * /api/rentals/export     (csv + pdf)
  * /api/annual + /api/annual/export
  * PUT /api/tankers/{id}, PUT /api/charges/{id}
  * isolation: rentals admin-only, rentals never touch /api/statement
"""
import os
import re
import calendar
from datetime import date, timedelta
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
API = base_url.rstrip("/") + "/api"
CRED_PATH = Path("/app/memory/test_credentials.md")
MONTH = date.today().strftime("%Y-%m")
TODAY = date.today()


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login failed for {email}: {r.status_code} {r.text[:300]}")
    s.headers.update({"Authorization": f"Bearer {r.json().get('access_token')}"})
    return s


def _admin_creds():
    content = CRED_PATH.read_text(encoding="utf-8")
    e = re.search(r'(?im)^\s*(?:[-*]\s*)?(?:\*\*)?email(?:\*\*)?\s*:\s*`?([^`\s]+)', content)
    p = re.search(r'(?im)^\s*(?:[-*]\s*)?(?:\*\*)?password(?:\*\*)?\s*:\s*`?([^`\s]+)', content)
    if not e or not p:
        pytest.skip("credentials not parseable")
    return e.group(1), p.group(1)


@pytest.fixture(scope="module")
def admin():
    e, p = _admin_creds()
    return _login(e, p)


@pytest.fixture(scope="module")
def resident():
    return _login("tenant1@societyhub.com", "demo123")


@pytest.fixture(scope="module")
def demo_property(admin):
    r = admin.get(f"{API}/properties", timeout=30)
    assert r.status_code == 200, r.text
    props = [p for p in r.json() if p["name"] == "Sunrise Residency"]
    if not props:
        pytest.skip("Sunrise Residency demo property missing")
    return props[0]


@pytest.fixture(scope="module")
def created():
    return {"units": [], "collections": [], "expenses": []}


@pytest.fixture(scope="module", autouse=True)
def cleanup(admin, created):
    yield
    for cid in created["collections"]:
        admin.delete(f"{API}/rentals/collections/{cid}", timeout=30)
    for eid in created["expenses"]:
        admin.delete(f"{API}/rentals/expenses/{eid}", timeout=30)
    for uid in created["units"]:
        admin.delete(f"{API}/rentals/units/{uid}", timeout=30)


def _row(rr, name):
    return next((r for r in rr["rows"] if r["name"] == name), None)


# ------------------------------------------------------- seeded demo baseline
class TestRentalSeededBaseline:
    def test_demo_seed_idempotent(self, admin):
        r = admin.post(f"{API}/rentals/demo/seed", timeout=60)
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

    def test_seeded_units_present(self, admin):
        r = admin.get(f"{API}/rentals/units", timeout=30)
        assert r.status_code == 200, r.text
        names = [u["name"] for u in r.json()]
        for expected in ["Sunrise 101 (own)", "MG Road Shop", "Whitefield House"]:
            assert expected in names
        managed = next(u for u in r.json() if u["name"] == "Whitefield House")
        assert managed["ownership"] == "managed"
        assert managed["owner_name"] == "Suresh Iyer (friend)"
        assert "_id" not in managed and isinstance(managed["id"], str)

    def test_rent_roll_baseline_math(self, admin):
        """Assert on the 3 seeded rows only (other tests may add units concurrently)."""
        r = admin.get(f"{API}/rentals/rent-roll", params={"month": MONTH}, timeout=30)
        assert r.status_code == 200, r.text
        rr = r.json()
        seeded = [_row(rr, n) for n in ["Sunrise 101 (own)", "MG Road Shop", "Whitefield House"]]
        assert all(seeded)
        assert sum(x["rent_due"] for x in seeded) == 86000
        assert sum(x["rent_collected"] for x in seeded) == 38000
        assert sum(x["pending"] for x in seeded) == 48000
        assert sum(x["deposit_held"] for x in seeded) == 250000
        assert round(sum(x["expenses"] for x in seeded), 2) == 15614.38
        assert sum(x["on_behalf_of_building"] for x in seeded) == 4614.38
        assert round(sum(x["net_to_owner"] for x in seeded), 2) == 22385.62
        assert _row(rr, "Sunrise 101 (own)")["status"] == "paid"        # 18000/18000
        assert _row(rr, "MG Road Shop")["status"] == "overdue"          # 20000/42000
        assert _row(rr, "Whitefield House")["status"] == "overdue"      # 0/26000
        assert rr["totals"]["overdue"] >= 48000
        t = rr["totals"]
        assert t["owned_units"] >= 2 and t["managed_units"] >= 1

    def test_building_tally_present(self, admin, demo_property):
        rr = admin.get(f"{API}/rentals/rent-roll", params={"month": MONTH}, timeout=30).json()
        tally = {b["building"]: b for b in rr["building_tally"]}
        assert "Sunrise Residency" in tally
        items = tally["Sunrise Residency"]["items"]
        seeded = next(i for i in items
                      if i["description"] == "Sunrise maintenance paid for flat 101")
        assert seeded["amount"] == 4614.38
        assert seeded["category"] == "society_maintenance"

    def test_deposit_accumulates_across_months(self, admin):
        """Deposits were booked in Jan/Mar; must still show for the current month."""
        rr = admin.get(f"{API}/rentals/rent-roll", params={"month": MONTH}, timeout=30).json()
        assert _row(rr, "Sunrise 101 (own)")["deposit_held"] == 100000
        assert _row(rr, "Whitefield House")["deposit_held"] == 150000
        prev = (TODAY.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        rr_prev = admin.get(f"{API}/rentals/rent-roll", params={"month": prev}, timeout=30).json()
        assert _row(rr_prev, "Sunrise 101 (own)")["deposit_held"] == 100000


# ------------------------------------------------------------------ units CRUD
class TestUnitsCRUD:
    def test_create_update_delete_unit(self, admin, created):
        payload = {"name": "TEST_Unit_A", "kind": "shop", "ownership": "managed",
                   "owner_name": "TEST Owner", "rent_amount": 10000, "rent_due_day": 3,
                   "deposit_amount": 20000, "tenant_name": "TEST Tenant",
                   "tenant_phone": "9000000001", "lease_start": f"{MONTH}-01",
                   "lease_end": "2027-12-31", "status": "active"}
        r = admin.post(f"{API}/rentals/units", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        u = r.json()
        created["units"].append(u["id"])
        assert u["name"] == "TEST_Unit_A" and u["ownership"] == "managed"
        assert u["rent_amount"] == 10000

        # GET verifies persistence
        lst = admin.get(f"{API}/rentals/units", timeout=30).json()
        assert any(x["id"] == u["id"] and x["owner_name"] == "TEST Owner" for x in lst)

        # UPDATE
        payload["rent_amount"] = 12500
        payload["tenant_name"] = "TEST Tenant 2"
        up = admin.put(f"{API}/rentals/units/{u['id']}", json=payload, timeout=30)
        assert up.status_code == 200, up.text
        assert up.json()["rent_amount"] == 12500
        lst = admin.get(f"{API}/rentals/units", timeout=30).json()
        got = next(x for x in lst if x["id"] == u["id"])
        assert got["rent_amount"] == 12500 and got["tenant_name"] == "TEST Tenant 2"

    def test_invalid_kind_and_ownership_rejected(self, admin):
        bad = {"name": "TEST_bad", "kind": "spaceship"}
        assert admin.post(f"{API}/rentals/units", json=bad, timeout=30).status_code == 400
        bad2 = {"name": "TEST_bad2", "ownership": "leased"}
        assert admin.post(f"{API}/rentals/units", json=bad2, timeout=30).status_code == 400

    def test_update_unknown_unit_404(self, admin):
        r = admin.put(f"{API}/rentals/units/64b7f3c2b1a2c3d4e5f60000",
                      json={"name": "TEST_ghost"}, timeout=30)
        assert r.status_code == 404, r.text

    def test_invalid_objectid_400(self, admin):
        assert admin.put(f"{API}/rentals/units/not-an-id", json={"name": "x"},
                         timeout=30).status_code == 400

    def test_delete_unit_cascades_children(self, admin):
        u = admin.post(f"{API}/rentals/units", json={
            "name": "TEST_Cascade", "rent_amount": 5000, "status": "active",
            "lease_start": f"{MONTH}-01", "lease_end": "2030-01-01"}, timeout=30).json()
        c = admin.post(f"{API}/rentals/collections", json={
            "unit_id": u["id"], "month": MONTH, "kind": "rent", "amount": 500,
            "date": f"{MONTH}-02"}, timeout=30).json()
        e = admin.post(f"{API}/rentals/expenses", json={
            "unit_id": u["id"], "month": MONTH, "category": "repair", "amount": 100,
            "date": f"{MONTH}-02"}, timeout=30).json()
        assert admin.delete(f"{API}/rentals/units/{u['id']}", timeout=30).status_code == 200
        cols = admin.get(f"{API}/rentals/collections", params={"month": MONTH}, timeout=30).json()
        exps = admin.get(f"{API}/rentals/expenses", params={"month": MONTH}, timeout=30).json()
        assert all(x["id"] != c["id"] for x in cols)
        assert all(x["id"] != e["id"] for x in exps)
        assert all(u["id"] != x["id"] for x in admin.get(f"{API}/rentals/units", timeout=30).json())


# ------------------------------------------------- collections & status logic
class TestCollectionsAndStatus:
    @pytest.fixture(scope="class")
    def unit(self, admin, created):
        u = admin.post(f"{API}/rentals/units", json={
            "name": "TEST_StatusUnit", "kind": "flat", "ownership": "own",
            "rent_amount": 10000, "rent_due_day": 1, "deposit_amount": 50000,
            "tenant_name": "TEST T", "tenant_phone": "9000000009",
            "lease_start": "2026-01-01", "lease_end": "2030-01-01", "status": "active"},
            timeout=30).json()
        created["units"].append(u["id"])
        return u

    def test_unpaid_past_due_is_overdue(self, admin, unit):
        rr = admin.get(f"{API}/rentals/rent-roll", params={"month": MONTH}, timeout=30).json()
        row = _row(rr, "TEST_StatusUnit")
        assert row["rent_due"] == 10000 and row["rent_collected"] == 0
        assert row["pending"] == 10000
        expected = "overdue" if row["due_date"] < TODAY.isoformat() else "pending"
        assert row["status"] == expected

    def test_partial_then_full_payment_marks_paid(self, admin, unit, created):
        c1 = admin.post(f"{API}/rentals/collections", json={
            "unit_id": unit["id"], "month": MONTH, "kind": "rent", "amount": 4000,
            "date": f"{MONTH}-02", "mode": "upi"}, timeout=30)
        assert c1.status_code == 200, c1.text
        c1 = c1.json()
        created["collections"].append(c1["id"])
        rr = admin.get(f"{API}/rentals/rent-roll", params={"month": MONTH}, timeout=30).json()
        row = _row(rr, "TEST_StatusUnit")
        assert row["rent_collected"] == 4000 and row["pending"] == 6000
        assert row["status"] in ("overdue", "pending")

        # edit the entry up to full rent -> paid
        upd = admin.put(f"{API}/rentals/collections/{c1['id']}", json={
            "unit_id": unit["id"], "month": MONTH, "kind": "rent", "amount": 10000,
            "date": f"{MONTH}-02", "mode": "upi"}, timeout=30)
        assert upd.status_code == 200, upd.text
        assert upd.json()["amount"] == 10000
        rr = admin.get(f"{API}/rentals/rent-roll", params={"month": MONTH}, timeout=30).json()
        row = _row(rr, "TEST_StatusUnit")
        assert row["rent_collected"] == 10000 and row["pending"] == 0
        assert row["status"] == "paid"

    def test_overpayment_shows_advance_not_negative(self, admin, unit, created):
        extra = admin.post(f"{API}/rentals/collections", json={
            "unit_id": unit["id"], "month": MONTH, "kind": "rent", "amount": 2500,
            "date": f"{MONTH}-03"}, timeout=30).json()
        created["collections"].append(extra["id"])
        rr = admin.get(f"{API}/rentals/rent-roll", params={"month": MONTH}, timeout=30).json()
        row = _row(rr, "TEST_StatusUnit")
        assert row["rent_collected"] == 12500
        assert row["pending"] == 0
        assert row["advance"] == 2500
        assert row["status"] == "paid"
        assert admin.delete(f"{API}/rentals/collections/{extra['id']}",
                            timeout=30).status_code == 200
        created["collections"].remove(extra["id"])

    def test_deposit_refund_and_deduction_math(self, admin, unit, created):
        ids = []
        for kind, amt in [("deposit", 50000), ("deposit_refund", 12000),
                          ("deposit_deduction", 3000)]:
            r = admin.post(f"{API}/rentals/collections", json={
                "unit_id": unit["id"], "month": MONTH, "kind": kind, "amount": amt,
                "date": f"{MONTH}-04"}, timeout=30)
            assert r.status_code == 200, r.text
            ids.append(r.json()["id"])
            created["collections"].append(r.json()["id"])
        rr = admin.get(f"{API}/rentals/rent-roll", params={"month": MONTH}, timeout=30).json()
        row = _row(rr, "TEST_StatusUnit")
        assert row["deposit_held"] == 35000
        assert row["deposit_expected"] == 50000
        # deposits must not be counted as rent
        assert row["rent_collected"] == 10000

    def test_unknown_collection_kind_rejected(self, admin, unit):
        r = admin.post(f"{API}/rentals/collections", json={
            "unit_id": unit["id"], "month": MONTH, "kind": "bribe", "amount": 1,
            "date": f"{MONTH}-01"}, timeout=30)
        assert r.status_code == 400, r.text

    def test_vacant_status_when_lease_not_covering_month(self, admin, created):
        u = admin.post(f"{API}/rentals/units", json={
            "name": "TEST_ExpiredLease", "rent_amount": 9000, "status": "active",
            "lease_start": "2024-01-01", "lease_end": "2024-06-30"}, timeout=30).json()
        created["units"].append(u["id"])
        rr = admin.get(f"{API}/rentals/rent-roll", params={"month": MONTH}, timeout=30).json()
        row = _row(rr, "TEST_ExpiredLease")
        assert row["status"] == "vacant" and row["rent_due"] == 0

    def test_vacant_status_when_unit_status_vacant(self, admin, created):
        u = admin.post(f"{API}/rentals/units", json={
            "name": "TEST_VacantUnit", "rent_amount": 9000, "status": "vacant",
            "lease_start": "2026-01-01", "lease_end": "2030-01-01"}, timeout=30).json()
        created["units"].append(u["id"])
        rr = admin.get(f"{API}/rentals/rent-roll", params={"month": MONTH}, timeout=30).json()
        row = _row(rr, "TEST_VacantUnit")
        assert row["status"] == "vacant" and row["rent_due"] == 0

    def test_lease_expiring_soon_flag(self, admin, created):
        nxt = (TODAY.replace(day=28) + timedelta(days=7))
        end = date(nxt.year, nxt.month, calendar.monthrange(nxt.year, nxt.month)[1] - 1)
        u = admin.post(f"{API}/rentals/units", json={
            "name": "TEST_ExpiringSoon", "rent_amount": 7000, "status": "active",
            "lease_start": "2026-01-01", "lease_end": end.isoformat()}, timeout=30).json()
        created["units"].append(u["id"])
        rr = admin.get(f"{API}/rentals/rent-roll", params={"month": MONTH}, timeout=30).json()
        assert _row(rr, "TEST_ExpiringSoon")["lease_expiring_soon"] is True
        far = _row(rr, "MG Road Shop")
        assert far["lease_expiring_soon"] is False


# -------------------------------------------------------- expenses / isolation
class TestExpensesAndIsolation:
    @pytest.fixture(scope="class")
    def unit(self, admin, created, demo_property):
        u = admin.post(f"{API}/rentals/units", json={
            "name": "TEST_ExpenseUnit", "rent_amount": 20000, "rent_due_day": 5,
            "building_property_id": demo_property["id"], "status": "active",
            "lease_start": "2026-01-01", "lease_end": "2030-01-01"}, timeout=30).json()
        created["units"].append(u["id"])
        admin.post(f"{API}/rentals/collections", json={
            "unit_id": u["id"], "month": MONTH, "kind": "rent", "amount": 20000,
            "date": f"{MONTH}-05"}, timeout=30)
        return u

    def test_expense_reduces_net_to_owner(self, admin, unit, created):
        e = admin.post(f"{API}/rentals/expenses", json={
            "unit_id": unit["id"], "month": MONTH, "category": "repair",
            "description": "TEST plumbing", "amount": 3000, "date": f"{MONTH}-07",
            "media": [{"path": "x.jpg", "category": "bill"}]}, timeout=30)
        assert e.status_code == 200, e.text
        e = e.json()
        created["expenses"].append(e["id"])
        assert e["media"] and e["media"][0]["category"] == "bill"
        rr = admin.get(f"{API}/rentals/rent-roll", params={"month": MONTH}, timeout=30).json()
        row = _row(rr, "TEST_ExpenseUnit")
        assert row["expenses"] == 3000
        assert row["net_to_owner"] == 17000

        upd = admin.put(f"{API}/rentals/expenses/{e['id']}", json={
            "unit_id": unit["id"], "month": MONTH, "category": "tax",
            "description": "TEST tax", "amount": 5000, "date": f"{MONTH}-07"}, timeout=30)
        assert upd.status_code == 200, upd.text
        assert upd.json()["category"] == "tax" and upd.json()["amount"] == 5000
        rr = admin.get(f"{API}/rentals/rent-roll", params={"month": MONTH}, timeout=30).json()
        assert _row(rr, "TEST_ExpenseUnit")["net_to_owner"] == 15000

    def test_on_behalf_of_building_tally(self, admin, unit, created, demo_property):
        before = admin.get(f"{API}/rentals/rent-roll", params={"month": MONTH},
                           timeout=30).json()
        base = next(b["amount"] for b in before["building_tally"]
                    if b["building"] == "Sunrise Residency")
        e = admin.post(f"{API}/rentals/expenses", json={
            "unit_id": unit["id"], "month": MONTH, "category": "society_maintenance",
            "description": "TEST society dues on behalf", "amount": 1500,
            "date": f"{MONTH}-08", "on_behalf_of_building": True,
            "building_property_id": demo_property["id"]}, timeout=30).json()
        created["expenses"].append(e["id"])
        after = admin.get(f"{API}/rentals/rent-roll", params={"month": MONTH}, timeout=30).json()
        tally = {b["building"]: b for b in after["building_tally"]}
        assert tally["Sunrise Residency"]["amount"] == round(base + 1500, 2)
        assert any(i["description"] == "TEST society dues on behalf"
                   for i in tally["Sunrise Residency"]["items"])
        row = _row(after, "TEST_ExpenseUnit")
        assert row["on_behalf_of_building"] == 1500

    def test_maintenance_statement_unaffected_by_rentals(self, admin, demo_property):
        r = admin.get(f"{API}/statement", params={"property_id": demo_property["id"],
                                                  "month": MONTH}, timeout=60)
        assert r.status_code == 200, r.text
        t = r.json()["totals"]
        assert t["total_water_spend"] == 3950
        assert t["avg_cost_per_litre"] == 0.1646
        assert t["recurring_total"] == 6500
        assert t["maintenance_total"] == 8600
        assert t["billable_total"] == 19050
        body = r.text
        assert "TEST society dues on behalf" not in body
        assert "TEST_ExpenseUnit" not in body

    def test_bad_expense_category_rejected(self, admin, unit):
        r = admin.post(f"{API}/rentals/expenses", json={
            "unit_id": unit["id"], "month": MONTH, "category": "bogus",
            "amount": 10, "date": f"{MONTH}-01"}, timeout=30)
        assert r.status_code == 400

    def test_resident_forbidden_on_all_rentals_endpoints(self, resident):
        for path, params in [("units", None), ("collections", {"month": MONTH}),
                             ("expenses", {"month": MONTH}),
                             ("rent-roll", {"month": MONTH}),
                             ("export", {"month": MONTH, "format": "csv"})]:
            r = resident.get(f"{API}/rentals/{path}", params=params, timeout=30)
            assert r.status_code == 403, f"{path} -> {r.status_code}"
        assert resident.post(f"{API}/rentals/units", json={"name": "x"},
                             timeout=30).status_code == 403
        assert resident.post(f"{API}/rentals/demo/seed", timeout=30).status_code == 403

    def test_rentals_require_auth(self):
        r = requests.get(f"{API}/rentals/rent-roll", params={"month": MONTH}, timeout=30)
        assert r.status_code in (401, 403)

    def test_dashboard_has_no_rental_data(self, admin, demo_property):
        r = admin.get(f"{API}/mis", params={"property_id": demo_property["id"],
                                            "month": MONTH}, timeout=60)
        if r.status_code == 404:
            pytest.skip("no /api/mis endpoint")
        assert r.status_code == 200
        assert "TEST_ExpenseUnit" not in r.text and "MG Road Shop" not in r.text


# ------------------------------------------------------------------- exports
class TestRentExports:
    def test_csv_export(self, admin):
        r = admin.get(f"{API}/rentals/export", params={"month": MONTH, "format": "csv"},
                      timeout=60)
        assert r.status_code == 200, r.text
        assert "text/csv" in r.headers.get("content-type", "")
        assert "attachment" in r.headers.get("content-disposition", "")
        body = r.content.decode()
        assert len(r.content) > 200
        assert "SocietyHub Rent Roll" in body
        assert "MG Road Shop" in body
        assert "Paid on behalf of building" in body

    def test_pdf_export(self, admin):
        r = admin.get(f"{API}/rentals/export", params={"month": MONTH, "format": "pdf"},
                      timeout=60)
        assert r.status_code == 200, r.text
        assert r.headers.get("content-type") == "application/pdf"
        assert r.content[:4] == b"%PDF"
        assert len(r.content) > 2000


# ------------------------------------------------------------ annual statement
class TestAnnual:
    def test_annual_totals_and_rows(self, admin, demo_property):
        r = admin.get(f"{API}/annual", params={"property_id": demo_property["id"],
                                               "year": TODAY.year}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["property"]["name"] == "Sunrise Residency"
        assert d["totals"]["months_recorded"] >= 1
        assert d["totals"]["billable_total"] == 19050
        assert d["rows"], "no per-owner rows"
        for row in d["rows"]:
            for k in ["flat_number", "owner_name", "consumption", "water_cost", "recurring",
                      "maintenance", "billable", "contributions", "received",
                      "closing_balance", "months"]:
                assert k in row, k
        assert round(sum(x["billable"] for x in d["rows"]), 2) == 19050

    def test_annual_rows_equal_sum_of_monthly_statements(self, admin, demo_property):
        d = admin.get(f"{API}/annual", params={"property_id": demo_property["id"],
                                               "year": TODAY.year}, timeout=60).json()
        expected = {}
        for m in d["months"]:
            st = admin.get(f"{API}/statement", params={"property_id": demo_property["id"],
                                                       "month": m["month"]}, timeout=60).json()
            for row in st["rows"]:
                agg = expected.setdefault(row["flat_id"], {"billable": 0.0, "received": 0.0,
                                                           "consumption": 0.0})
                agg["billable"] += row["base_cost"]
                agg["received"] += row["received"]
                agg["consumption"] += row["consumption"]
        for row in d["rows"]:
            e = expected[row["flat_id"]]
            assert round(row["billable"], 2) == round(e["billable"], 2), row["flat_number"]
            assert round(row["received"], 2) == round(e["received"], 2), row["flat_number"]
            assert round(row["consumption"], 2) == round(e["consumption"], 2)

    def test_annual_empty_year(self, admin, demo_property):
        d = admin.get(f"{API}/annual", params={"property_id": demo_property["id"],
                                               "year": 2019}, timeout=60).json()
        assert d["months"] == [] and d["rows"] == []
        assert d["totals"]["months_recorded"] == 0

    def test_annual_bad_property_404(self, admin):
        r = admin.get(f"{API}/annual", params={"property_id": "64b7f3c2b1a2c3d4e5f60000",
                                               "year": TODAY.year}, timeout=30)
        assert r.status_code == 404

    def test_annual_csv_export(self, admin, demo_property):
        r = admin.get(f"{API}/annual/export", params={"property_id": demo_property["id"],
                                                      "year": TODAY.year, "format": "csv"},
                      timeout=60)
        assert r.status_code == 200, r.text
        assert "text/csv" in r.headers.get("content-type", "")
        assert "Annual Statement" in r.content.decode()
        assert len(r.content) > 200

    def test_annual_pdf_export(self, admin, demo_property):
        r = admin.get(f"{API}/annual/export", params={"property_id": demo_property["id"],
                                                      "year": TODAY.year, "format": "pdf"},
                      timeout=60)
        assert r.status_code == 200, r.text
        assert r.content[:4] == b"%PDF" and len(r.content) > 2000

    def test_annual_export_resident_forbidden(self, resident, demo_property):
        r = resident.get(f"{API}/annual/export", params={"property_id": demo_property["id"],
                                                         "year": TODAY.year}, timeout=30)
        assert r.status_code == 403

    def test_annual_resident_scoping(self, resident, demo_property):
        """A resident hitting /api/annual should not see every flat's yearly figures."""
        r = resident.get(f"{API}/annual", params={"property_id": demo_property["id"],
                                                  "year": TODAY.year}, timeout=60)
        assert r.status_code in (200, 403), r.text
        if r.status_code == 200:
            flats = [row["flat_number"] for row in r.json()["rows"]]
            assert len(flats) <= 1, f"resident sees all flats in annual statement: {flats}"


# ------------------------------------------------- tanker / charge entry edits
class TestEntryEditing:
    @pytest.fixture(scope="class")
    def scratch(self, admin):
        """Throwaway property so demo-month maintenance totals stay untouched."""
        p = admin.post(f"{API}/properties", json={
            "name": "TEST_EditProp_iter4", "address": "TEST", "recurring_defaults": {}},
            timeout=30)
        assert p.status_code == 200, p.text
        prop = p.json()
        yield prop
        admin.delete(f"{API}/properties/{prop['id']}", timeout=30)

    def test_update_tanker_recomputes(self, admin, scratch):
        pid = scratch["id"]
        t = admin.post(f"{API}/tankers", json={
            "property_id": pid, "month": MONTH, "date": f"{MONTH}-15",
            "supplier": "TEST Vendor", "qty_sump": 5000, "qty_syntex": 0,
            "amount": 900, "tips_amount": 100}, timeout=30)
        assert t.status_code == 200, t.text
        t = t.json()
        assert t["total_cost"] == 1000 and t["cost_per_litre"] == 0.2
        upd = admin.put(f"{API}/tankers/{t['id']}", json={
            "property_id": pid, "month": MONTH, "date": f"{MONTH}-15",
            "supplier": "TEST Vendor 2", "qty_sump": 4000, "qty_syntex": 1000,
            "amount": 1500, "tips_amount": 500}, timeout=30)
        assert upd.status_code == 200, upd.text
        u = upd.json()
        assert u["supplier"] == "TEST Vendor 2"
        assert u["total_qty"] == 5000
        assert u["total_cost"] == 2000
        assert u["cost_per_litre"] == 0.4
        lst = admin.get(f"{API}/tankers", params={"property_id": pid, "month": MONTH},
                        timeout=30).json()
        assert any(x["id"] == t["id"] and x["total_cost"] == 2000 for x in lst)
        assert admin.delete(f"{API}/tankers/{t['id']}", timeout=30).status_code == 200

    def test_update_tanker_404(self, admin, scratch):
        r = admin.put(f"{API}/tankers/64b7f3c2b1a2c3d4e5f60000", json={
            "property_id": scratch["id"], "month": MONTH, "date": f"{MONTH}-01",
            "supplier": "x", "qty_sump": 1, "qty_syntex": 0, "amount": 1}, timeout=30)
        assert r.status_code == 404

    def test_update_charge_preserves_category_and_media(self, admin, scratch):
        pid = scratch["id"]
        c = admin.post(f"{API}/charges", json={
            "property_id": pid, "month": MONTH, "charge_type": "maintenance",
            "description": "TEST repair", "amount": 700, "date": f"{MONTH}-11",
            "media": [{"path": "a.jpg", "category": "in_progress"}]}, timeout=30)
        assert c.status_code == 200, c.text
        c = c.json()
        assert c["category"] == "adhoc"
        upd = admin.put(f"{API}/charges/{c['id']}", json={
            "property_id": pid, "month": MONTH, "charge_type": "maintenance",
            "description": "TEST repair edited", "amount": 950, "date": f"{MONTH}-11",
            "media": [{"path": "a.jpg", "category": "in_progress"},
                      {"path": "b.jpg", "category": "completed"}]}, timeout=30)
        assert upd.status_code == 200, upd.text
        u = upd.json()
        assert u["amount"] == 950 and u["description"] == "TEST repair edited"
        assert u["category"] == "adhoc" and len(u["media"]) == 2
        lst = admin.get(f"{API}/charges", params={"property_id": pid, "month": MONTH},
                        timeout=30).json()
        got = next(x for x in lst if x["id"] == c["id"])
        assert got["amount"] == 950 and len(got["media"]) == 2
        assert admin.delete(f"{API}/charges/{c['id']}", timeout=30).status_code == 200

    def test_update_charge_bad_type_and_404(self, admin, scratch):
        pid = scratch["id"]
        c = admin.post(f"{API}/charges", json={
            "property_id": pid, "month": MONTH, "charge_type": "cleaning",
            "description": "TEST rec", "amount": 100, "date": f"{MONTH}-11"}, timeout=30).json()
        bad = admin.put(f"{API}/charges/{c['id']}", json={
            "property_id": pid, "month": MONTH, "charge_type": "nonsense",
            "amount": 100}, timeout=30)
        assert bad.status_code == 400
        admin.delete(f"{API}/charges/{c['id']}", timeout=30)
        r = admin.put(f"{API}/charges/64b7f3c2b1a2c3d4e5f60000", json={
            "property_id": pid, "month": MONTH, "charge_type": "cleaning",
            "amount": 1}, timeout=30)
        assert r.status_code == 404

    def test_resident_cannot_edit_entries(self, resident, scratch):
        pid = scratch["id"]
        assert resident.put(f"{API}/tankers/64b7f3c2b1a2c3d4e5f60000", json={
            "property_id": pid, "month": MONTH, "date": f"{MONTH}-01", "supplier": "x",
            "qty_sump": 1, "qty_syntex": 0, "amount": 1}, timeout=30).status_code == 403
        assert resident.put(f"{API}/charges/64b7f3c2b1a2c3d4e5f60000", json={
            "property_id": pid, "month": MONTH, "charge_type": "cleaning",
            "amount": 1}, timeout=30).status_code == 403


# -------------------------------------- locked period blocks edits (throwaway)
class TestLockedPeriodBlocksEdits:
    def test_edit_locked_period_returns_423(self, admin):
        pname = "TEST_LockProp_iter4"
        p = admin.post(f"{API}/properties", json={
            "name": pname, "address": "TEST", "recurring_defaults": {}}, timeout=30)
        assert p.status_code == 200, p.text
        pid = p.json()["id"]
        try:
            t = admin.post(f"{API}/tankers", json={
                "property_id": pid, "month": MONTH, "date": f"{MONTH}-10",
                "supplier": "TEST", "qty_sump": 1000, "qty_syntex": 0, "amount": 500},
                timeout=30)
            assert t.status_code == 200, t.text
            tid = t.json()["id"]
            c = admin.post(f"{API}/charges", json={
                "property_id": pid, "month": MONTH, "charge_type": "cleaning",
                "description": "TEST", "amount": 100, "date": f"{MONTH}-10"}, timeout=30)
            assert c.status_code == 200, c.text
            cid = c.json()["id"]

            rst = admin.post(f"{API}/periods/reset",
                             params={"property_id": pid, "month": MONTH}, timeout=60)
            assert rst.status_code == 200, rst.text

            r1 = admin.put(f"{API}/tankers/{tid}", json={
                "property_id": pid, "month": MONTH, "date": f"{MONTH}-10",
                "supplier": "TEST edited", "qty_sump": 2000, "qty_syntex": 0,
                "amount": 900}, timeout=30)
            assert r1.status_code == 423, f"tanker edit on locked period -> {r1.status_code}"
            r2 = admin.put(f"{API}/charges/{cid}", json={
                "property_id": pid, "month": MONTH, "charge_type": "cleaning",
                "description": "TEST edited", "amount": 300, "date": f"{MONTH}-10"}, timeout=30)
            assert r2.status_code == 423, f"charge edit on locked period -> {r2.status_code}"
        finally:
            admin.delete(f"{API}/properties/{pid}", timeout=30)
