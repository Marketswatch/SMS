"""Iteration 3 tests: building reference on flats, meter reading media, charge media
categories, owner phones in statement, and confirmation that no SMS gateway exists."""
import io
import os
import re

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000a49444154"
    "789c6360000002000154a24f6b0000000049454e44ae426082"
)


@pytest.fixture(scope="session")
def creds():
    txt = open("/app/memory/test_credentials.md").read()
    e = re.search(r"(?im)^\s*[-*]?\s*email:\s*`?([^`\s]+)", txt)
    p = re.search(r"(?im)^\s*[-*]?\s*password:\s*`?([^`\s]+)", txt)
    if not e or not p:
        pytest.skip("credentials missing")
    return {"email": e.group(1), "password": p.group(1)}


@pytest.fixture(scope="session")
def client(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login failed {r.status_code} {r.text[:300]}")
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="session")
def demo(client):
    r = client.get(f"{API}/properties", timeout=30)
    assert r.status_code == 200, r.text
    props = r.json()
    p = next((x for x in props if x["name"] == "Sunrise Residency"), None)
    assert p, "demo property missing"
    m = client.get(f"{API}/periods", params={"property_id": p["id"]}, timeout=30).json()
    month = [x for x in m if x.get("status") == "open"][0]["month"] if m else None
    return {"pid": p["id"], "month": month}


@pytest.fixture(scope="session")
def upload_ids(client):
    ids = []
    yield ids


def do_upload(client, name="TEST_shot.png", source="upload"):
    files = {"file": (name, io.BytesIO(PNG), "image/png")}
    r = client.post(f"{API}/uploads", files=files, data={"source": source}, timeout=60)
    assert r.status_code == 200, f"upload failed {r.status_code} {r.text[:300]}"
    d = r.json()
    assert d["id"] and d["content_type"] == "image/png"
    assert d["source"] == source
    return d


# ---------------------------------------------------------------- uploads + files
class TestUploads:
    def test_upload_without_gps(self, client):
        d = do_upload(client)
        assert d.get("lat") in (None, "")

    def test_download_requires_auth(self, client):
        d = do_upload(client)
        anon = requests.get(f"{API}/files/{d['id']}", timeout=30)
        assert anon.status_code == 401
        ok = requests.get(f"{API}/files/{d['id']}", params={"auth": client.headers["Authorization"].split()[1]}, timeout=30)
        assert ok.status_code == 200
        assert ok.headers["content-type"].startswith("image/")

    def test_reject_non_media(self, client):
        files = {"file": ("TEST_x.txt", io.BytesIO(b"hello"), "text/plain")}
        r = client.post(f"{API}/uploads", files=files, data={"source": "upload"}, timeout=30)
        assert r.status_code == 400


# ---------------------------------------------------------------- flats / building ref
class TestFlatBuilding:
    def test_create_flat_under_chosen_building(self, client, demo):
        prop = client.post(f"{API}/properties", json={
            "name": "TEST_Building_A", "address": "TEST addr",
            "recurring_defaults": {}, "default_payers": {}}, timeout=30)
        assert prop.status_code == 200, prop.text
        pid2 = prop.json()["id"]
        try:
            r = client.post(f"{API}/flats", json={
                "property_id": pid2, "number": "TEST_9A", "owner_name": "TEST Owner",
                "owner_phone": "9876500999", "tenant_name": "TEST Tenant",
                "tenant_phone": "9876500888"}, timeout=30)
            assert r.status_code == 200, r.text
            flat = r.json()
            assert flat["property_id"] == pid2
            assert flat["owner_phone"] == "9876500999"
            assert flat["tenant_phone"] == "9876500888"
            assert "_id" not in flat

            # visible under new building
            l2 = client.get(f"{API}/flats", params={"property_id": pid2}, timeout=30).json()
            assert [f["number"] for f in l2] == ["TEST_9A"]
            # not under demo building
            l1 = client.get(f"{API}/flats", params={"property_id": demo["pid"]}, timeout=30).json()
            assert "TEST_9A" not in [f["number"] for f in l1]

            # inline phone edit persists
            up = client.put(f"{API}/flats/{flat['id']}", json={
                "property_id": pid2, "number": "TEST_9A", "owner_name": "TEST Owner",
                "owner_phone": "9000011111", "tenant_name": "TEST Tenant",
                "tenant_phone": "9876500888"}, timeout=30)
            assert up.status_code == 200, up.text
            assert up.json()["owner_phone"] == "9000011111"
            got = client.get(f"{API}/flats", params={"property_id": pid2}, timeout=30).json()[0]
            assert got["owner_phone"] == "9000011111"

            client.delete(f"{API}/flats/{flat['id']}", timeout=30)
            assert client.get(f"{API}/flats", params={"property_id": pid2}, timeout=30).json() == []
        finally:
            client.delete(f"{API}/properties/{pid2}", timeout=30)

    def test_demo_flats_have_owner_phones(self, client, demo):
        flats = client.get(f"{API}/flats", params={"property_id": demo["pid"]}, timeout=30).json()
        nums = sorted(f["number"] for f in flats)
        assert nums == ["101", "102", "201", "202"], nums
        for f in flats:
            assert f.get("owner_phone"), f"flat {f['number']} has no owner_phone"


# ---------------------------------------------------------------- reading media
class TestReadingMedia:
    def test_media_attaches_to_correct_meter_only(self, client, demo):
        pid, month = demo["pid"], demo["month"]
        rows = client.get(f"{API}/readings", params={"property_id": pid, "month": month}, timeout=30).json()
        assert len(rows) >= 2
        orig = {r["meter_id"]: r for r in rows}
        target = rows[0]
        other = rows[1]
        m1 = do_upload(client, "TEST_m1.png", "camera")
        m2 = do_upload(client, "TEST_m2.png", "upload")

        payload = {"property_id": pid, "month": month, "readings": [
            {"meter_id": r["meter_id"], "opening": r["opening"], "closing": r["closing"],
             "media": [m1, m2] if r["meter_id"] == target["meter_id"] else (r.get("media") or [])}
            for r in rows]}
        res = client.put(f"{API}/readings", json=payload, timeout=30)
        assert res.status_code == 200, res.text

        after = {r["meter_id"]: r for r in client.get(
            f"{API}/readings", params={"property_id": pid, "month": month}, timeout=30).json()}
        assert len(after[target["meter_id"]]["media"]) == 2
        assert {m["id"] for m in after[target["meter_id"]]["media"]} == {m1["id"], m2["id"]}
        assert after[other["meter_id"]]["media"] == (orig[other["meter_id"]].get("media") or [])
        # readings numbers unchanged
        assert after[target["meter_id"]]["closing"] == target["closing"]

        # remove one -> persists removal
        payload["readings"] = [
            {"meter_id": r["meter_id"], "opening": r["opening"], "closing": r["closing"],
             "media": [m1] if r["meter_id"] == target["meter_id"] else (r.get("media") or [])}
            for r in rows]
        assert client.put(f"{API}/readings", json=payload, timeout=30).status_code == 200
        after2 = {r["meter_id"]: r for r in client.get(
            f"{API}/readings", params={"property_id": pid, "month": month}, timeout=30).json()}
        assert [m["id"] for m in after2[target["meter_id"]]["media"]] == [m1["id"]]

        # cleanup: restore original media
        payload["readings"] = [
            {"meter_id": r["meter_id"], "opening": r["opening"], "closing": r["closing"],
             "media": orig[r["meter_id"]].get("media") or []} for r in rows]
        assert client.put(f"{API}/readings", json=payload, timeout=30).status_code == 200


# ---------------------------------------------------------------- charge media categories
class TestChargeMedia:
    def test_adhoc_three_categories(self, client, demo):
        pid, month = demo["pid"], demo["month"]
        bill = {**do_upload(client, "TEST_bill.png"), "category": "bill"}
        prog = {**do_upload(client, "TEST_prog.png"), "category": "in_progress"}
        done = {**do_upload(client, "TEST_done.png"), "category": "completed"}
        r = client.post(f"{API}/charges", json={
            "property_id": pid, "month": month, "charge_type": "maintenance",
            "description": "TEST_repair media", "amount": 100, "payer_type": "owner",
            "media": [bill, prog, done]}, timeout=30)
        assert r.status_code == 200, r.text
        cid = r.json()["id"]
        try:
            got = [c for c in client.get(f"{API}/charges", params={"property_id": pid, "month": month},
                                         timeout=30).json() if c["id"] == cid][0]
            cats = sorted(m["category"] for m in got["media"])
            assert cats == ["bill", "completed", "in_progress"], cats
            assert got["category"] == "adhoc"
        finally:
            client.delete(f"{API}/charges/{cid}", timeout=30)

    def test_recurring_bill_media(self, client, demo):
        pid, month = demo["pid"], demo["month"]
        bill = {**do_upload(client, "TEST_rec_bill.png"), "category": "bill"}
        r = client.post(f"{API}/charges", json={
            "property_id": pid, "month": month, "charge_type": "electricity",
            "description": "TEST_recurring media", "amount": 10, "payer_type": "owner",
            "media": [bill]}, timeout=30)
        assert r.status_code == 200, r.text
        cid = r.json()["id"]
        try:
            got = [c for c in client.get(f"{API}/charges", params={"property_id": pid, "month": month},
                                         timeout=30).json() if c["id"] == cid][0]
            assert got["category"] == "recurring"
            assert [m["id"] for m in got["media"]] == [bill["id"]]
            assert got["media"][0]["category"] == "bill"
        finally:
            client.delete(f"{API}/charges/{cid}", timeout=30)

    def test_tips_rejected_as_charge(self, client, demo):
        r = client.post(f"{API}/charges", json={
            "property_id": demo["pid"], "month": demo["month"], "charge_type": "tips",
            "amount": 50}, timeout=30)
        assert r.status_code == 400


# ---------------------------------------------------------------- statement / notify data
class TestStatementNotify:
    def test_rows_expose_phones_and_math(self, client, demo):
        s = client.get(f"{API}/statement", params={"property_id": demo["pid"], "month": demo["month"]},
                       timeout=60)
        assert s.status_code == 200, s.text
        d = s.json()
        t = d["totals"]
        assert t["total_water_spend"] == 3950
        assert round(t["avg_cost_per_litre"], 4) == 0.1646
        assert t["recurring_total"] == 6500
        assert t["maintenance_total"] == 8600
        assert t["billable_total"] == 19050
        assert d["property"]["name"] == "Sunrise Residency"
        for r in d["rows"]:
            assert "owner_phone" in r and "tenant_phone" in r
            assert r["owner_phone"], f"row {r['flat_number']} missing owner_phone"

    def test_no_sms_gateway_endpoints(self, client):
        for url in (f"{BASE_URL}/api/openapi.json", f"{BASE_URL}/openapi.json"):
            spec = requests.get(url, timeout=30)
            if spec.status_code == 200 and "application/json" in spec.headers.get("content-type", ""):
                paths = list(spec.json().get("paths", {}).keys())
                bad = [x for x in paths if any(k in x.lower() for k in ("sms", "twilio", "whatsapp", "notify"))]
                assert not bad, f"unexpected messaging endpoints: {bad}"
                break
        src = open("/app/backend/server.py").read().lower()
        for k in ("twilio", "msg91", "gupshup", "sms_api"):
            assert k not in src, f"paid gateway reference found: {k}"
