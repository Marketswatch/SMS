"""Iteration 5 backend suite — rent receipts, combined overview, vacancy tracking.

Modules covered:
  * GET /api/rentals/collections/{cid}/receipt  (PDF per kind, 404, 403)
  * GET /api/overview                           (combined maintenance + rentals, cross-checked)
  * GET /api/rentals/rent-roll                  (vacancy: vacant_since/vacant_days/lost_rent, totals)
  * GET /api/rentals/export                     (csv/pdf vacancy summary)
  * light regression: statement isolation, deposits across months, building tally, annual scoping
All records created here are prefixed "QA " and removed in teardown.
"""
import io
import os
import base64
import re
import zlib
from datetime import date, timedelta
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

# STALE (iteration 6): the rentals module was rebuilt — /rentals/collections, /rentals/expenses
# and the old single-amount payment/receipt shape no longer exist. Superseded by
# tests/test_iter6_rentals_rebuild.py. Skipped so it stops polluting the live preview DB.
pytestmark = pytest.mark.skip(reason="rentals module rebuilt in iteration 6; see test_iter6_rentals_rebuild.py")


frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
API = base_url.rstrip("/") + "/api"
CRED_PATH = Path("/app/memory/test_credentials.md")
MONTH = date.today().strftime("%Y-%m")
TODAY = date.today()


# ------------------------------------------------------------------ helpers
def _creds(role_hint):
    content = CRED_PATH.read_text(encoding="utf-8") if CRED_PATH.exists() else ""
    if not content:
        pytest.skip("Missing /app/memory/test_credentials.md")
    emails = re.findall(r"`([^`]+@[^`]+)`", content)
    if role_hint == "admin":
        return "admin@societyhub.com", "admin123"
    return "tenant1@societyhub.com", "demo123"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=40)
    if r.status_code != 200:
        pytest.fail(f"login failed for {email}: {r.status_code} {r.text[:300]}")
    tok = r.json().get("access_token") or r.json().get("token")
    if not tok:
        pytest.fail(f"no token in login response: {r.text[:300]}")
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


def pdf_text(blob: bytes) -> str:
    """Extract visible text from a reportlab PDF (ASCII85 + Flate) without a 3rd-party parser."""
    out = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", blob, re.S):
        raw = m.group(1).strip()
        for decode in (lambda b: base64.a85decode(b, adobe=False), lambda b: b):
            try:
                cand = decode(raw.split(b"~>")[0])
            except Exception:
                continue
            try:
                cand = zlib.decompress(cand)
            except Exception:
                pass
            if b"(" in cand and b"Tj" in cand or b"TJ" in cand:
                raw = cand
                break
        for t in re.findall(rb"\((?:[^()\\]|\\.)*\)", raw):
            out.append(t[1:-1].decode("latin-1", "ignore"))
    return " ".join(out).replace("\\(", "(").replace("\\)", ")")


@pytest.fixture(scope="module")
def admin():
    return _login(*_creds("admin"))


@pytest.fixture(scope="module")
def resident():
    return _login(*_creds("resident"))


@pytest.fixture(scope="module")
def qa_unit(admin):
    """Throwaway occupied rental unit + one of every collection kind."""
    body = {
        "name": "QA Receipt Flat", "kind": "flat", "ownership": "own", "owner_name": "Self",
        "address": "QA Street 1", "rent_amount": 20000, "rent_due_day": 5,
        "deposit_amount": 50000, "tenant_name": "QA Tenant", "tenant_phone": "9000000001",
        "lease_start": f"{MONTH}-01", "lease_end": "2027-12-31", "status": "active",
    }
    r = admin.post(f"{API}/rentals/units", json=body, timeout=40)
    assert r.status_code == 200, r.text
    unit = r.json()
    cols = {}
    specs = [("rent", 12000), ("deposit", 50000), ("deposit_refund", 5000), ("deposit_deduction", 2000)]
    for kind, amt in specs:
        rc = admin.post(f"{API}/rentals/collections", json={
            "unit_id": unit["id"], "month": MONTH, "kind": kind, "amount": amt,
            "date": f"{MONTH}-07", "mode": "upi", "notes": f"QA {kind}"}, timeout=40)
        assert rc.status_code == 200, rc.text
        cols[kind] = rc.json()
    yield {"unit": unit, "cols": cols}
    admin.delete(f"{API}/rentals/units/{unit['id']}", timeout=40)


@pytest.fixture(scope="module")
def qa_vacant_unit(admin):
    since = (TODAY - timedelta(days=100)).isoformat()
    body = {"name": "QA Vacant Shop", "kind": "shop", "ownership": "own", "owner_name": "Self",
            "rent_amount": 30000, "status": "vacant", "vacant_since": since}
    r = admin.post(f"{API}/rentals/units", json=body, timeout=40)
    assert r.status_code == 200, r.text
    unit = r.json()
    yield {"unit": unit, "since": since, "days": 100}
    admin.delete(f"{API}/rentals/units/{unit['id']}", timeout=40)


# =============================================================== receipts
class TestReceipts:
    TITLES = {"rent": "Rent Receipt", "deposit": "Security Deposit Receipt",
              "deposit_refund": "Deposit Refund Voucher", "deposit_deduction": "Deposit Deduction Note"}

    @pytest.mark.parametrize("kind", ["rent", "deposit", "deposit_refund", "deposit_deduction"])
    def test_receipt_pdf_per_kind(self, admin, qa_unit, kind):
        cid = qa_unit["cols"][kind]["id"]
        r = admin.get(f"{API}/rentals/collections/{cid}/receipt", timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert r.content.startswith(b"%PDF"), r.content[:20]
        assert len(r.content) > 800
        assert "application/pdf" in r.headers.get("content-type", "")
        txt = pdf_text(r.content)
        assert self.TITLES[kind] in txt, f"title missing for {kind}: {txt[:400]}"
        assert re.search(r"RCPT-\d{6}-[0-9A-F]{6}", txt), f"receipt no missing: {txt[:400]}"
        for expect in ["QA Receipt Flat", "QA Tenant", MONTH, f"{MONTH}-07", "UPI"]:
            assert expect in txt, f"'{expect}' missing from {kind} receipt: {txt[:600]}"
        amt = qa_unit["cols"][kind]["amount"]
        assert f"{amt:,.2f}" in txt, f"amount {amt} missing: {txt[:600]}"

    def test_rent_receipt_shows_rent_paid_and_balance(self, admin, qa_unit):
        cid = qa_unit["cols"]["rent"]["id"]
        txt = pdf_text(admin.get(f"{API}/rentals/collections/{cid}/receipt", timeout=60).content)
        assert "Monthly rent" in txt and "20,000.00" in txt
        assert "Total paid this month" in txt
        assert "Balance" in txt and "8,000.00" in txt  # 20000 - 12000

    def test_rent_receipt_balance_nil_when_fully_paid(self, admin, qa_unit):
        top = admin.post(f"{API}/rentals/collections", json={
            "unit_id": qa_unit["unit"]["id"], "month": MONTH, "kind": "rent", "amount": 8000,
            "date": f"{MONTH}-09", "mode": "cash", "notes": "QA balance"}, timeout=40)
        assert top.status_code == 200, top.text
        cid2 = top.json()["id"]
        try:
            txt = pdf_text(admin.get(f"{API}/rentals/collections/{cid2}/receipt", timeout=60).content)
            assert "Nil" in txt, txt[:600]
            assert "CASH" in txt
        finally:
            admin.delete(f"{API}/rentals/collections/{cid2}", timeout=40)

    def test_receipt_unknown_id_404(self, admin):
        r = admin.get(f"{API}/rentals/collections/64b7b7b7b7b7b7b7b7b7b7b7/receipt", timeout=40)
        assert r.status_code == 404, f"{r.status_code} {r.text[:200]}"

    def test_receipt_bad_id_400(self, admin):
        r = admin.get(f"{API}/rentals/collections/not-an-id/receipt", timeout=40)
        assert r.status_code == 400, f"{r.status_code} {r.text[:200]}"

    def test_receipt_resident_403(self, resident, qa_unit):
        cid = qa_unit["cols"]["rent"]["id"]
        r = resident.get(f"{API}/rentals/collections/{cid}/receipt", timeout=40)
        assert r.status_code == 403, f"{r.status_code} {r.text[:200]}"


# =============================================================== overview
class TestOverview:
    def test_overview_shape_and_cross_check(self, admin, qa_unit):
        r = admin.get(f"{API}/overview", params={"month": MONTH}, timeout=90)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert '"_id"' not in r.text and "'_id'" not in r.text.replace("property_id", "")
        assert d["month"] == MONTH
        mb = d["maintenance"]["buildings"]
        mt = d["maintenance"]["totals"]
        rt = d["rentals"]["totals"]
        c = d["combined"]

        # maintenance totals == sum of building rows
        assert round(sum(b["billable"] for b in mb), 2) == pytest.approx(mt["billable"], abs=0.02)
        assert round(sum(b["collected"] for b in mb), 2) == pytest.approx(mt["collected"], abs=0.02)
        assert round(sum(b["outstanding"] for b in mb), 2) == pytest.approx(mt["outstanding"], abs=0.02)

        # each building row must match /api/statement
        for b in mb:
            st = admin.get(f"{API}/statement", params={"property_id": b["property_id"], "month": MONTH},
                           timeout=60)
            assert st.status_code == 200, st.text[:200]
            t = st.json()["totals"]
            assert b["billable"] == pytest.approx(t["billable_total"], abs=0.02), b["name"]
            assert b["collected"] == pytest.approx(t["total_received"], abs=0.02), b["name"]
            assert b["outstanding"] == pytest.approx(t["total_owes"], abs=0.02), b["name"]
            assert b["flats"] == t["flat_count"]

        # rentals block must match /api/rentals/rent-roll
        rr = admin.get(f"{API}/rentals/rent-roll", params={"month": MONTH}, timeout=60).json()
        assert rt == rr["totals"]
        assert len(d["rentals"]["rows"]) == len(rr["rows"])
        assert d["rentals"]["building_tally"] == rr["building_tally"]

        # combined math
        assert c["money_in"] == pytest.approx(mt["collected"] + rt["rent_collected"], abs=0.02)
        assert c["money_out"] == pytest.approx(rt["expenses"], abs=0.02)
        assert c["still_to_collect"] == pytest.approx(mt["outstanding"] + rt["pending"], abs=0.02)
        assert c["rent_collected"] == pytest.approx(rt["rent_collected"], abs=0.02)
        assert c["maintenance_collected"] == pytest.approx(mt["collected"], abs=0.02)
        assert c["deposits_held"] == pytest.approx(rt["deposit_held"], abs=0.02)
        assert c["paid_on_behalf_of_buildings"] == pytest.approx(rt["on_behalf_of_building"], abs=0.02)

    @pytest.mark.parametrize("bad", ["2026-13", "202604", "abcd", "2026-1", ""])
    def test_overview_month_validation(self, admin, bad):
        r = admin.get(f"{API}/overview", params={"month": bad}, timeout=60)
        assert r.status_code in (400, 422), f"month='{bad}' -> {r.status_code} {r.text[:200]}"

    def test_overview_missing_month(self, admin):
        r = admin.get(f"{API}/overview", timeout=60)
        assert r.status_code == 422, r.status_code

    def test_overview_resident_403(self, resident):
        r = resident.get(f"{API}/overview", params={"month": MONTH}, timeout=60)
        assert r.status_code == 403, f"{r.status_code} {r.text[:200]}"

    def test_overview_unauthenticated_401(self):
        r = requests.get(f"{API}/overview", params={"month": MONTH}, timeout=60)
        assert r.status_code in (401, 403), r.status_code


# =============================================================== vacancy
class TestVacancy:
    def test_vacant_since_persists(self, admin, qa_vacant_unit):
        uid = qa_vacant_unit["unit"]["id"]
        units = admin.get(f"{API}/rentals/units", timeout=40).json()
        u = next(x for x in units if x["id"] == uid)
        assert u["vacant_since"] == qa_vacant_unit["since"]
        assert u["status"] == "vacant"

    def test_rent_roll_vacancy_metrics(self, admin, qa_vacant_unit):
        uid = qa_vacant_unit["unit"]["id"]
        rr = admin.get(f"{API}/rentals/rent-roll", params={"month": MONTH}, timeout=60).json()
        row = next(r for r in rr["rows"] if r["unit_id"] == uid)
        assert row["status"] == "vacant"
        assert row["rent_due"] == 0, "vacant unit must bill 0 rent"
        assert row["vacant_since"] == qa_vacant_unit["since"]
        assert row["vacant_days"] == qa_vacant_unit["days"]
        assert row["lost_rent"] == pytest.approx(round(30000 * 100 / 30.44, 2), abs=0.05)
        t = rr["totals"]
        assert t["vacant"] >= 1
        assert t["vacant_days"] == sum(r["vacant_days"] for r in rr["rows"])
        assert t["lost_rent"] == pytest.approx(round(sum(r["lost_rent"] for r in rr["rows"]), 2), abs=0.05)

    def test_vacant_without_since_falls_back_to_lease_end(self, admin):
        le = (TODAY - timedelta(days=40)).isoformat()
        r = admin.post(f"{API}/rentals/units", json={
            "name": "QA Vacant No Since", "rent_amount": 10000, "status": "vacant",
            "lease_end": le, "vacant_since": ""}, timeout=40)
        assert r.status_code == 200, r.text
        uid = r.json()["id"]
        try:
            rr = admin.get(f"{API}/rentals/rent-roll", params={"month": MONTH}, timeout=60).json()
            row = next(x for x in rr["rows"] if x["unit_id"] == uid)
            assert row["vacant_since"] == le
            assert row["vacant_days"] == 40
            assert row["lost_rent"] == pytest.approx(round(10000 * 40 / 30.44, 2), abs=0.05)
        finally:
            admin.delete(f"{API}/rentals/units/{uid}", timeout=40)

    def test_vacant_no_since_no_lease_end_zero(self, admin):
        r = admin.post(f"{API}/rentals/units", json={
            "name": "QA Vacant Bare", "rent_amount": 15000, "status": "vacant"}, timeout=40)
        assert r.status_code == 200, r.text
        uid = r.json()["id"]
        try:
            rr = admin.get(f"{API}/rentals/rent-roll", params={"month": MONTH}, timeout=60).json()
            row = next(x for x in rr["rows"] if x["unit_id"] == uid)
            assert row["vacant_since"] == ""
            assert row["vacant_days"] == 0
            assert row["lost_rent"] == 0
        finally:
            admin.delete(f"{API}/rentals/units/{uid}", timeout=40)

    def test_garbage_vacant_since_does_not_500(self, admin):
        r = admin.post(f"{API}/rentals/units", json={
            "name": "QA Vacant Garbage", "rent_amount": 15000, "status": "vacant",
            "vacant_since": "not-a-date"}, timeout=40)
        assert r.status_code == 200, r.text
        uid = r.json()["id"]
        try:
            rr = admin.get(f"{API}/rentals/rent-roll", params={"month": MONTH}, timeout=60)
            assert rr.status_code == 200, f"rent roll 500 on garbage date: {rr.text[:300]}"
            row = next(x for x in rr.json()["rows"] if x["unit_id"] == uid)
            assert row["vacant_days"] == 0 and row["lost_rent"] == 0
            ov = admin.get(f"{API}/overview", params={"month": MONTH}, timeout=90)
            assert ov.status_code == 200, f"overview broke on garbage date: {ov.text[:300]}"
        finally:
            admin.delete(f"{API}/rentals/units/{uid}", timeout=40)

    def test_future_vacant_since_clamped_to_zero(self, admin):
        r = admin.post(f"{API}/rentals/units", json={
            "name": "QA Vacant Future", "rent_amount": 15000, "status": "vacant",
            "vacant_since": (TODAY + timedelta(days=30)).isoformat()}, timeout=40)
        uid = r.json()["id"]
        try:
            rr = admin.get(f"{API}/rentals/rent-roll", params={"month": MONTH}, timeout=60).json()
            row = next(x for x in rr["rows"] if x["unit_id"] == uid)
            assert row["vacant_days"] == 0 and row["lost_rent"] == 0
        finally:
            admin.delete(f"{API}/rentals/units/{uid}", timeout=40)

    def test_export_includes_vacancy_summary(self, admin, qa_vacant_unit):
        csv_r = admin.get(f"{API}/rentals/export", params={"month": MONTH, "format": "csv"}, timeout=60)
        assert csv_r.status_code == 200
        body = csv_r.text
        assert "Vacant units" in body and "Idle days" in body and "Rent forgone to vacancy" in body
        assert "QA Vacant Shop" in body

        pdf_r = admin.get(f"{API}/rentals/export", params={"month": MONTH, "format": "pdf"}, timeout=90)
        assert pdf_r.status_code == 200
        assert pdf_r.content.startswith(b"%PDF")
        txt = pdf_text(pdf_r.content)
        assert "Vacant units" in txt and "Rent forgone" in txt, txt[:500]


# =============================================================== regression
class TestRegression:
    def test_statement_unaffected_by_rentals(self, admin, qa_unit):
        props = admin.get(f"{API}/properties", timeout=40).json()
        assert props, "no buildings"
        pid = props[0]["id"]
        st = admin.get(f"{API}/statement", params={"property_id": pid, "month": MONTH}, timeout=60)
        assert st.status_code == 200
        blob = st.text
        assert "QA Receipt Flat" not in blob and "QA Tenant" not in blob

    def test_deposits_held_across_months(self, admin, qa_unit):
        prev = (date(TODAY.year, TODAY.month, 1) - timedelta(days=1)).strftime("%Y-%m")
        rr = admin.get(f"{API}/rentals/rent-roll", params={"month": prev}, timeout=60).json()
        row = next(r for r in rr["rows"] if r["unit_id"] == qa_unit["unit"]["id"])
        # deposit 50000 in - 5000 refund - 2000 deduction = 43000, visible in any month
        assert row["deposit_held"] == 43000, row
        assert row["rent_collected"] == 0

    def test_rent_roll_status_logic(self, admin, qa_unit):
        rr = admin.get(f"{API}/rentals/rent-roll", params={"month": MONTH}, timeout=60).json()
        for r in rr["rows"]:
            assert r["status"] in ("paid", "pending", "overdue", "vacant")
            if r["status"] == "vacant":
                assert r["rent_due"] == 0
            if r["status"] == "paid":
                assert r["pending"] == 0

    def test_annual_scoped_by_role(self, admin, resident):
        props = admin.get(f"{API}/properties", timeout=40).json()
        pid = props[0]["id"]
        a = admin.get(f"{API}/annual", params={"property_id": pid, "year": TODAY.year}, timeout=60)
        assert a.status_code == 200, a.text[:200]
        assert "rows" in a.json() and "totals" in a.json()
        b = resident.get(f"{API}/annual", params={"property_id": pid, "year": TODAY.year}, timeout=60)
        assert b.status_code in (200, 403), b.status_code
        if b.status_code == 200:
            # resident view must be scoped to at most their own flat
            assert len(b.json()["rows"]) <= len(a.json()["rows"])

    def test_rentals_admin_only(self, resident):
        for path in ["/rentals/units", "/rentals/collections", "/rentals/expenses"]:
            r = resident.get(f"{API}{path}", timeout=40)
            assert r.status_code == 403, f"{path} -> {r.status_code}"
        r = resident.get(f"{API}/rentals/rent-roll", params={"month": MONTH}, timeout=40)
        assert r.status_code == 403
