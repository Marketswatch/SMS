"""Iteration 10 — water reconciliation 15-column layout (screen parity in CSV + PDF),
status wording (Settled/Paid/Partial/Pending), Combined column in water usage exports."""
import os
import re
import io
import csv as _csv
import pytest
import requests
from dotenv import dotenv_values

fe = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE}/api"

RECON_HEADERS = ["S.No", "Flat No.", "Floor", "Owner", "Metered cost", "Non-metered cost (reserve)",
                 "Total water cost", "Misc", "Total amount", "Bal brought forward",
                 "Advance paid (fronting)", "Amount paid", "Balance to pay / receive",
                 "Date of payment", "Status"]


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
    assert props, "no maintenance property"
    return props[0]


@pytest.fixture(scope="session")
def month(client, prop):
    r = client.get(f"{API}/periods", params={"property_id": prop["id"]})
    assert r.status_code == 200, r.text
    return r.json()[-1]["month"]


@pytest.fixture(scope="session")
def statement(client, prop, month):
    r = client.get(f"{API}/statement", params={"property_id": prop["id"], "month": month})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="session")
def csv_text(client, prop, month):
    r = client.get(f"{API}/mis/export", params={"property_id": prop["id"], "month": month, "format": "csv"})
    assert r.status_code == 200, r.text
    return r.text


@pytest.fixture(scope="session")
def pdf_bytes(client, prop, month):
    r = client.get(f"{API}/mis/export", params={"property_id": prop["id"], "month": month, "format": "pdf"})
    assert r.status_code == 200, r.text
    return r.content


def _rows(csv_text):
    return list(_csv.reader(io.StringIO(csv_text)))


# --- statement math backing the columns ---
class TestColumnMath:
    def test_row_arithmetic(self, statement):
        rows = statement["rows"]
        assert rows
        t = statement["totals"]
        for r in rows:
            misc = round(r["recurring_share"] + r["maintenance_share"], 2)
            assert abs(r["water_cost"] - (r["water_own_cost"] + r["reserve_share"])) < 0.05, r
            assert abs(r["base_cost"] - (r["water_cost"] + misc)) < 0.05, r
            expected_net = r["base_cost"] + r["carry_in"] - r["contributions"] - r["received"]
            assert abs(r["net"] - expected_net) < 0.05, (r["flat_number"], r["net"], expected_net)
        assert abs(t["reserve_share"] - t["reserve_value"] / (t["flat_count"] or 1)) < 0.05

    def test_metered_cost_matches_consumption_times_rate(self, statement):
        rate = statement["totals"]["avg_cost_per_litre"]
        by_flat = {}
        for m in statement["meters"]:
            by_flat[m["flat_id"]] = by_flat.get(m["flat_id"], 0) + float(m["consumption"] or 0)
        for r in statement["rows"]:
            if r["flat_id"] in by_flat:
                assert abs(r["water_own_cost"] - by_flat[r["flat_id"]] * rate) < 1.0, r["flat_number"]

    def test_totals_line_up_with_column_sums(self, statement):
        rows, t = statement["rows"], statement["totals"]
        assert abs(sum(r["reserve_share"] for r in rows) - t["reserve_value"]) < 0.5
        assert abs(sum(r["water_cost"] for r in rows) - t["total_water_spend"]) < 0.5
        assert abs(sum(r["base_cost"] for r in rows) - t["billable_total"]) < 0.5
        assert abs(sum(r["carry_in"] for r in rows) - t["total_carry_in"]) < 0.5
        assert abs(sum(r["contributions"] for r in rows) - t["total_contributions"]) < 0.5
        assert abs(sum(r["received"] for r in rows) - t["total_received"]) < 0.5
        assert abs(sum(r["water_own_cost"] for r in rows)
                   - (t["total_water_spend"] - t["reserve_value"])) < 1.0


# --- CSV layout parity ---
class TestReconCsv:
    def test_section_title_present(self, csv_text):
        assert "Water reconciliation — owner statement" in csv_text

    def test_exact_15_headers_in_order(self, csv_text):
        rows = _rows(csv_text)
        hdr = [r for r in rows if r and r[0] == "S.No" and r[1] == "Flat No."]
        assert hdr, "reconciliation header row not found"
        assert hdr[0] == RECON_HEADERS, hdr[0]

    def test_data_rows_have_15_cells_and_serials(self, csv_text, statement):
        rows = _rows(csv_text)
        i = [n for n, r in enumerate(rows) if r and r[0] == "S.No" and r[1] == "Flat No."][0]
        data = []
        for r in rows[i + 1:]:
            if not (r and r[0].isdigit()):
                break
            data.append(r)
        assert len(data) == len(statement["rows"]), (len(data), len(statement["rows"]))
        assert [int(r[0]) for r in data] == list(range(1, len(data) + 1))
        for r in data:
            assert len(r) == 15, r

    def test_total_row_and_per_head_line(self, csv_text):
        rows = _rows(csv_text)
        i = [n for n, r in enumerate(rows) if r and r[0] == "S.No" and r[1] == "Flat No."][0]
        tail = rows[i + 1:]
        total = [r for r in tail if len(r) > 3 and r[3] == "TOTAL"]
        assert total, "TOTAL row missing from reconciliation CSV section"
        assert len(total[0]) == 15
        flat = "\n".join(",".join(r) for r in tail).lower()
        assert "total expense" in flat and "split between" in flat and "exp per head" in flat

    def test_total_row_values_match_totals(self, csv_text, statement):
        t = statement["totals"]
        rows = _rows(csv_text)
        total = [r for r in rows if len(r) > 3 and r[3] == "TOTAL"][0]
        assert abs(float(total[5]) - t["reserve_value"]) < 0.5
        assert abs(float(total[6]) - t["total_water_spend"]) < 0.5
        assert abs(float(total[8]) - t["billable_total"]) < 0.5
        assert abs(float(total[11]) - t["total_received"]) < 0.5
        assert abs(float(total[12]) - t["net_position"]) < 0.5

    def test_status_column_wording(self, csv_text, statement):
        rows = _rows(csv_text)
        i = [n for n, r in enumerate(rows) if r and r[0] == "S.No" and r[1] == "Flat No."][0]
        by_flat = {}
        for r in rows[i + 1:]:
            if not (r and r[0].isdigit()):
                break
            by_flat[r[1]] = (r[13], r[14])
        assert by_flat
        for s in statement["rows"]:
            date, label = by_flat[s["flat_number"]]
            if s["payment_status"] == "paid":
                assert label == ("Paid" if s.get("last_paid_on") else "Settled"), (s["flat_number"], label)
            elif s["payment_status"] == "partial":
                assert label == "Partial"
            else:
                assert label == "Pending"
            if s.get("last_paid_on"):
                assert re.match(r"^\d{2}-\d{2}-\d{4}$", date), date

    def test_water_usage_section_has_combined(self, csv_text):
        rows = _rows(csv_text)
        hdr = [r for r in rows if r and r[0] == "S.No" and "Meter number" in r]
        assert hdr, "water usage header missing"
        assert hdr[0][-1] == "Combined (per flat)", hdr[0]

    def test_no_iso_dates(self, csv_text):
        iso = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", csv_text)
        assert not iso, iso[:5]


# --- PDF layout parity ---
class TestReconPdf:
    @pytest.fixture(scope="class")
    def pdf_text(self, pdf_bytes):
        try:
            from pypdf import PdfReader
        except ImportError:
            pytest.skip("pypdf not installed")
        return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf_bytes)).pages)

    def test_is_pdf(self, pdf_bytes):
        assert pdf_bytes[:5] == b"%PDF-"
        assert len(pdf_bytes) > 3000

    def test_both_sections_and_headers(self, pdf_text):
        low = pdf_text.lower().replace("\n", " ")
        for token in ["water reconciliation", "owner statement", "metered cost", "non-metered",
                      "total water", "misc", "bal brought", "advance paid", "amount",
                      "balance to", "date of", "status", "water usage charges", "combined"]:
            assert token in low, f"missing '{token}' in PDF"

    def test_total_row_and_legend(self, pdf_text):
        low = pdf_text.lower()
        assert "total" in low
        for token in ["total lorries", "total water received", "cost per litre",
                      "total water charges", "non-metered cost", "per house share", "exp per head"]:
            assert token in low, f"legend missing '{token}'"

    def test_no_iso_dates(self, pdf_text):
        iso = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", pdf_text)
        assert not iso, iso[:5]
