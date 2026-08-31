"""Iteration 9 — report formatting: S.No, DD-MM-YYYY dates, Floor field, tips payer, water usage report."""
import os
import re
import io
import pytest
import requests
from dotenv import dotenv_values

fe = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE}/api"
DMY = re.compile(r"^\d{2}-\d{2}-\d{4}$")


@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "admin@societyhub.com", "password": "admin123"})
    assert r.status_code == 200, r.text
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="session")
def prop(client):
    r = client.get(f"{API}/properties")
    assert r.status_code == 200, r.text
    props = [p for p in r.json() if p.get("kind", "maintenance") != "rental"]
    assert props, "no maintenance property found"
    return props[0]


@pytest.fixture(scope="session")
def month(client, prop):
    r = client.get(f"{API}/periods", params={"property_id": prop["id"]})
    assert r.status_code == 200, r.text
    per = r.json()
    # frontend defaults to the newest period; use it because it carries the live data
    return (per[-1]["month"] if isinstance(per, list) and per else None)


@pytest.fixture(scope="session")
def statement(client, prop, month):
    r = client.get(f"{API}/statement", params={"property_id": prop["id"], "month": month})
    assert r.status_code == 200, r.text
    return r.json()


# --- Flats: floor field ---
class TestFlatFloor:
    def test_flat_floor_persists(self, client, prop):
        r = client.get(f"{API}/flats", params={"property_id": prop["id"]})
        assert r.status_code == 200
        flats = r.json()
        assert flats, "no flats"
        # pre-existing seeded flats may not carry the key until first edit
        assert all(isinstance(f.get("floor", ""), str) for f in flats)
        f = flats[0]
        body = {k: f.get(k) for k in ["property_id", "number", "owner_name", "owner_user_id",
                                      "owner_phone", "tenant_name", "tenant_user_id", "tenant_phone"]}
        body = {k: (v if v is not None else "") if k != "owner_user_id" and k != "tenant_user_id" else v
                for k, v in body.items()}
        original = f.get("floor", "")
        body["floor"] = "Second"
        up = client.put(f"{API}/flats/{f['id']}", json=body)
        assert up.status_code == 200, up.text
        assert up.json()["floor"] == "Second"
        again = client.get(f"{API}/flats", params={"property_id": prop["id"]})
        got = [x for x in again.json() if x["id"] == f["id"]][0]
        assert got["floor"] == "Second"
        # restore
        body["floor"] = original
        client.put(f"{API}/flats/{f['id']}", json=body)

    def test_create_flat_with_floor(self, client, prop):
        r = client.post(f"{API}/flats", json={"property_id": prop["id"], "number": "TEST_901",
                                              "floor": "Fourth", "owner_name": "TEST_Owner"})
        assert r.status_code in (200, 201), r.text
        fid = r.json()["id"]
        assert r.json()["floor"] == "Fourth"
        assert "_id" not in r.json()
        d = client.delete(f"{API}/flats/{fid}")
        assert d.status_code == 200


# --- Statement / engine fields feeding the reports ---
class TestStatementFields:
    def test_rows_carry_floor_status_paydate(self, statement):
        rows = statement["rows"]
        assert rows
        for r in rows:
            assert "floor" in r
            assert r["payment_status"] in ("paid", "partial", "pending"), r["payment_status"]
            assert "last_paid_on" in r

    def test_meters_carry_flat_floor_owner_charge(self, statement):
        meters = statement["meters"]
        assert meters, "no meters in statement"
        for m in meters:
            for k in ["flat_number", "floor", "owner_name", "charge", "opening", "closing",
                      "consumption", "label", "flat_id"]:
                assert k in m, f"meter row missing {k}"

    def test_totals_have_tanker_count_and_metered_charges(self, statement):
        t = statement["totals"]
        for k in ["tanker_count", "metered_charges", "total_consumed", "reserve_litres",
                  "reserve_value", "reserve_share", "flat_count", "avg_cost_per_litre",
                  "total_litres", "total_water_spend"]:
            assert k in t, f"totals missing {k}"
        assert isinstance(t["tanker_count"], int)

    def test_metered_charges_matches_meter_sum(self, statement):
        s = round(sum(float(m["charge"]) for m in statement["meters"]), 1)
        assert abs(s - float(statement["totals"]["metered_charges"])) < 1.0, (
            s, statement["totals"]["metered_charges"])


# --- Tankers: tips payer can differ from lorry payer ---
class TestTankerTipsPayer:
    def test_create_tanker_with_different_tips_payer(self, client, prop, month):
        flats = client.get(f"{API}/flats", params={"property_id": prop["id"]}).json()
        assert len(flats) >= 2
        a, b = flats[0]["id"], flats[1]["id"]
        payload = {"property_id": prop["id"], "month": month, "date": f"{month}-15",
                   "qty_sump": 5000, "qty_syntex": 0, "amount": 1200,
                   "payer_flat_id": a, "payer_type": "owner",
                   "tips_amount": 150, "tips_payer_flat_id": b, "tips_payer_type": "tenant",
                   "supplier": "TEST_Supplier"}
        r = client.post(f"{API}/tankers", json=payload)
        assert r.status_code in (200, 201), r.text
        doc = r.json()
        tid = doc["id"]
        try:
            assert doc["payer_flat_id"] == a
            assert doc["tips_payer_flat_id"] == b
            assert doc["total_cost"] == 1350
            lst = client.get(f"{API}/tankers", params={"property_id": prop["id"], "month": month}).json()
            got = [t for t in lst if t["id"] == tid]
            assert got, "tanker not persisted"
            assert got[0]["tips_payer_flat_id"] == b

            # contributions: lorry to A, tips to B
            st = client.get(f"{API}/statement", params={"property_id": prop["id"], "month": month}).json()
            ra = [x for x in st["rows"] if x["flat_id"] == a][0]
            rb = [x for x in st["rows"] if x["flat_id"] == b][0]
            assert any(d["source"] == "tanker" and d["amount"] == 1200 for d in ra["contribution_detail"])
            assert any(d["source"] == "tips" and d["amount"] == 150 for d in rb["contribution_detail"])
        finally:
            client.delete(f"{API}/tankers/{tid}")


# --- MIS export CSV ---
class TestMisCsv:
    @pytest.fixture(scope="class")
    def csv_text(self, client, prop, month):
        r = client.get(f"{API}/mis/export", params={"property_id": prop["id"], "month": month, "format": "csv"})
        assert r.status_code == 200, r.text
        return r.text

    def test_owner_table_headers(self, csv_text):
        assert "S.No,Flat No.,Floor,Owner" in csv_text.replace('"', ''), csv_text[:800]

    def test_has_payment_status_and_date_cols(self, csv_text):
        head = [l for l in csv_text.splitlines() if l.startswith("S.No,Flat No.")][0]
        assert "Status" in head and "Date of payment" in head, head

    def test_water_usage_section_present(self, csv_text):
        low = csv_text.lower()
        assert "water usage charges" in low, "water usage section missing from CSV"
        assert "Meter number" in csv_text
        assert "Starting unit" in csv_text and "Ending unit" in csv_text
        assert "cost per litre" in low

    def test_total_expense_per_head(self, csv_text):
        low = csv_text.lower()
        assert "total expense" in low, "Total Expense line missing"
        assert "per head" in low, "Exp per head line missing"

    def test_all_dates_are_dmy(self, csv_text):
        iso = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", csv_text)
        assert not iso, f"ISO dates leaked into CSV: {iso[:5]}"

    def test_serials_sequential(self, csv_text):
        lines = csv_text.splitlines()
        i = [n for n, l in enumerate(lines) if l.startswith("S.No,Flat No.")][0]
        serial = []
        for l in lines[i + 1:]:
            first = l.split(",")[0]
            if not first.isdigit():
                break
            serial.append(int(first))
        assert serial == list(range(1, len(serial) + 1)), serial


class TestMisPdf:
    def test_pdf_downloads(self, client, prop, month):
        r = client.get(f"{API}/mis/export", params={"property_id": prop["id"], "month": month, "format": "pdf"})
        assert r.status_code == 200, r.text
        assert r.content[:5] == b"%PDF-", r.content[:20]
        assert len(r.content) > 3000

    def test_pdf_text_has_sections(self, client, prop, month):
        r = client.get(f"{API}/mis/export", params={"property_id": prop["id"], "month": month, "format": "pdf"})
        try:
            from pypdf import PdfReader
        except ImportError:
            pytest.skip("pypdf not installed")
        txt = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(r.content)).pages)
        low = txt.lower()
        assert "s.no" in low
        assert "floor" in low
        assert "water usage charges" in low
        assert "cost per litre" in low
        assert "per head" in low
        iso = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", txt)
        assert not iso, f"ISO dates in PDF: {iso[:5]}"


class TestAnnualExport:
    def test_annual_csv_has_serial(self, client, prop, month):
        r = client.get(f"{API}/annual/export", params={"property_id": prop["id"], "year": int(month[:4]), "format": "csv"})
        assert r.status_code == 200, r.text
        assert "S.No" in r.text
        iso = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", r.text)
        assert not iso, f"ISO dates in annual CSV: {iso[:5]}"

    def test_annual_pdf(self, client, prop, month):
        r = client.get(f"{API}/annual/export", params={"property_id": prop["id"], "year": int(month[:4]), "format": "pdf"})
        assert r.status_code == 200
        assert r.content[:5] == b"%PDF-"


# --- Rentals exports ---
class TestRentalsExports:
    @pytest.fixture(scope="class")
    def rmonth(self, client):
        u = client.get(f"{API}/rentals/units")
        assert u.status_code == 200, u.text[:300]
        assert u.json(), "no rental units"
        import datetime as _dt
        return _dt.date.today().strftime("%Y-%m")

    def test_rentals_report_csv_serial(self, client, rmonth):
        r = client.get(f"{API}/rentals/export", params={"month": rmonth, "format": "csv"})
        assert r.status_code == 200, r.text[:400]
        assert "S.No" in r.text, r.text[:400]
        assert "Previous dues" in r.text
        iso = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", r.text)
        assert not iso, f"ISO dates in rentals CSV: {iso[:5]}"

    def test_rentals_report_pdf(self, client, rmonth):
        r = client.get(f"{API}/rentals/export", params={"month": rmonth, "format": "pdf"})
        assert r.status_code == 200, r.text[:300]
        assert r.content[:5] == b"%PDF-"

    def test_receipt_pdf_dmy_and_mode(self, client):
        pays = client.get(f"{API}/rentals/payments")
        assert pays.status_code == 200, pays.text[:300]
        items = pays.json()
        if not items:
            pytest.skip("no rental payments to build a receipt")
        pid = items[0]["id"]
        r = client.get(f"{API}/rentals/payments/{pid}/receipt")
        assert r.status_code == 200, r.text[:300]
        assert r.content[:5] == b"%PDF-"
        try:
            from pypdf import PdfReader
        except ImportError:
            pytest.skip("pypdf not installed")
        txt = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(r.content)).pages)
        low = txt.lower()
        assert "reference" in low, "Reference row missing on receipt"
        assert re.search(r"\d{2}-\d{2}-\d{4}", txt), "no DD-MM-YYYY date on receipt"
        iso = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", txt)
        assert not iso, f"ISO dates on receipt: {iso[:5]}"
        assert re.search(r"cash|upi|bank transfer|cheque", low), "no readable mode on receipt"
