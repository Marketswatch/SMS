"""SocietyHub backend regression suite.

Covers: auth (JWT/cookie/lockout), demo seed, CRUD (property/flat/meter/tank),
tankers, readings, charges (+apply-defaults), payments, statement engine math,
flags (meter_rollback / negative_reserve), month reset + lock (423),
MIS export (csv/pdf), uploads, role restrictions.
"""
import os
import re
import io
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
API = BASE_URL + "/api"

CRED_PATH = Path("/app/memory/test_credentials.md")


def _creds():
    content = CRED_PATH.read_text(encoding="utf-8")
    e = re.search(r'(?im)^\s*(?:[-*]\s*)?(?:\*\*)?email(?:\*\*)?\s*:\s*`?([^`\s]+)', content)
    p = re.search(r'(?im)^\s*(?:[-*]\s*)?(?:\*\*)?password(?:\*\*)?\s*:\s*`?([^`\s]+)', content)
    if not e or not p:
        pytest.skip("credentials not parseable")
    return {"email": e.group(1), "password": p.group(1)}


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login failed for {email}: {r.status_code} {r.text[:300]}")
    tok = r.json().get("access_token")
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s, r


@pytest.fixture(scope="session")
def admin():
    c = _creds()
    s, _ = _login(c["email"], c["password"])
    return s


# ------------------------------------------------------------------ auth
class TestAuth:
    def test_root(self):
        r = requests.get(f"{API}/", timeout=30)
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_login_sets_httponly_cookie_and_token(self):
        c = _creds()
        s, r = _login(c["email"], c["password"])
        data = r.json()
        assert data["email"] == c["email"]
        assert data["role"] == "super_admin"
        assert "password_hash" not in data
        assert "_id" not in data
        assert isinstance(data["access_token"], str) and len(data["access_token"]) > 20
        raw = r.headers.get("set-cookie", "")
        assert "access_token=" in raw, raw
        assert "HttpOnly" in raw
        assert "Secure" in raw

    def test_me_with_bearer(self, admin):
        r = admin.get(f"{API}/auth/me", timeout=30)
        assert r.status_code == 200
        assert r.json()["role"] == "super_admin"

    def test_me_without_auth_401(self):
        r = requests.get(f"{API}/auth/me", timeout=30)
        assert r.status_code == 401

    def test_invalid_password_401(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": _creds()["email"], "password": "wrongpass-xyz"}, timeout=30)
        assert r.status_code == 401
        assert "detail" in r.json()

    def test_brute_force_lockout(self):
        email = f"lockout_{uuid.uuid4().hex[:8]}@example.com"
        codes = []
        for _ in range(7):
            r = requests.post(f"{API}/auth/login", json={"email": email, "password": "nope123"}, timeout=30)
            codes.append(r.status_code)
        assert 429 in codes, f"no lockout observed: {codes}"

    def test_cors_credentials_not_wildcard(self):
        """Preflight OPTIONS is answered by the edge proxy in preview, so assert on a
        real request carrying an Origin header (that reaches the app CORS middleware)."""
        r = requests.get(f"{API}/", timeout=30, headers={"Origin": BASE_URL})
        assert r.headers.get("access-control-allow-credentials") == "true", dict(r.headers)
        allow_origin = r.headers.get("access-control-allow-origin")
        assert allow_origin != "*", "wildcard origin with credentials breaks browser cookies"


class TestPasswordHash:
    def test_bcrypt_hash_format(self):
        import asyncio
        from motor.motor_asyncio import AsyncIOMotorClient
        env = dotenv_values("/app/backend/.env")

        async def go():
            cl = AsyncIOMotorClient(env["MONGO_URL"])
            u = await cl[env["DB_NAME"]].users.find_one({"email": _creds()["email"]})
            cl.close()
            return u
        u = asyncio.get_event_loop().run_until_complete(go())
        assert u is not None
        assert u["password_hash"].startswith("$2b$"), u["password_hash"][:10]


# ------------------------------------------------------------------ demo seed
class TestDemoSeed:
    def test_seed_idempotent(self, admin):
        r = admin.post(f"{API}/demo/seed", timeout=60)
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d.get("already") is True, "seed re-ran and duplicated data"

    def test_demo_property_shape(self, admin):
        props = admin.get(f"{API}/properties", timeout=30).json()
        demo = [p for p in props if p["name"] == "Sunrise Residency"]
        assert demo, "demo property missing"
        pid = demo[0]["id"]
        flats = admin.get(f"{API}/flats", params={"property_id": pid}, timeout=30).json()
        meters = admin.get(f"{API}/meters", params={"property_id": pid}, timeout=30).json()
        tanks = admin.get(f"{API}/tanks", params={"property_id": pid}, timeout=30).json()
        assert len(flats) == 4 and len(meters) == 4 and len(tanks) == 2
        assert all("_id" not in x for x in flats + meters + tanks)


# ------------------------------------------------------------------ CRUD + engine on an isolated test property
@pytest.fixture(scope="module")
def prop(admin):
    r = admin.post(f"{API}/properties", json={"name": f"TEST_Tower_{uuid.uuid4().hex[:6]}",
                                              "address": "QA lane"}, timeout=30)
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    yield pid
    admin.delete(f"{API}/properties/{pid}", timeout=30)


@pytest.fixture(scope="module")
def month():
    return "2026-03"


@pytest.fixture(scope="module")
def flats(admin, prop):
    out = []
    for n in ("101", "102"):
        r = admin.post(f"{API}/flats", json={"property_id": prop, "number": n,
                                             "owner_name": f"Owner {n}", "tenant_name": f"Tenant {n}"}, timeout=30)
        assert r.status_code == 200, r.text
        out.append(r.json())
    return out


@pytest.fixture(scope="module")
def meters(admin, prop, flats):
    out = []
    for f in flats:
        r = admin.post(f"{API}/meters", json={"property_id": prop, "flat_id": f["id"],
                                              "label": f"Meter {f['number']}", "opening": 100}, timeout=30)
        assert r.status_code == 200, r.text
        out.append(r.json())
    return out


class TestSetupCRUD:
    def test_property_created_and_listed(self, admin, prop):
        props = admin.get(f"{API}/properties", timeout=30).json()
        me = [p for p in props if p["id"] == prop]
        assert me and me[0]["default_payers"]["cleaning"] == "tenant"

    def test_defaults_update_persists(self, admin, prop):
        payers = {"water": "owner", "cleaning": "owner", "sweeper": "tenant", "security": "owner",
                  "electricity": "tenant", "misc": "owner", "maintenance": "owner", "tips": "tenant"}
        rec = {"security": 5000, "electricity": 1200, "cleaning": 3000, "sweeper": 0}
        r = admin.put(f"{API}/properties/{prop}", json={"name": "TEST_Tower_defaults", "address": "QA lane",
                                                       "default_payers": payers, "recurring_defaults": rec}, timeout=30)
        assert r.status_code == 200
        got = [p for p in admin.get(f"{API}/properties", timeout=30).json() if p["id"] == prop][0]
        assert got["default_payers"]["cleaning"] == "owner"
        assert got["recurring_defaults"]["security"] == 5000

    def test_flat_and_meter_crud(self, admin, prop):
        r = admin.post(f"{API}/flats", json={"property_id": prop, "number": "999",
                                             "owner_name": "Temp Owner", "tenant_name": "Temp Tenant"}, timeout=30)
        assert r.status_code == 200
        fid = r.json()["id"]
        rm = admin.post(f"{API}/meters", json={"property_id": prop, "flat_id": fid,
                                               "label": "Meter 999", "opening": 5}, timeout=30)
        assert rm.status_code == 200
        mid = rm.json()["id"]
        assert any(m["id"] == mid for m in admin.get(f"{API}/meters", params={"property_id": prop}, timeout=30).json())
        assert admin.delete(f"{API}/meters/{mid}", timeout=30).status_code == 200
        assert not any(m["id"] == mid for m in admin.get(f"{API}/meters", params={"property_id": prop}, timeout=30).json())
        assert admin.delete(f"{API}/flats/{fid}", timeout=30).status_code == 200
        assert not any(f["id"] == fid for f in admin.get(f"{API}/flats", params={"property_id": prop}, timeout=30).json())

    def test_tank_crud(self, admin, prop):
        r = admin.post(f"{API}/tanks", json={"property_id": prop, "name": "TEST_Sump",
                                             "tank_type": "sump", "capacity": 10000}, timeout=30)
        assert r.status_code == 200
        tid = r.json()["id"]
        assert admin.delete(f"{API}/tanks/{tid}", timeout=30).status_code == 200
        assert not any(t["id"] == tid for t in admin.get(f"{API}/tanks", params={"property_id": prop}, timeout=30).json())

    def test_invalid_id_400(self, admin):
        assert admin.delete(f"{API}/tanks/not-an-oid", timeout=30).status_code == 400


class TestWaterAndEngine:
    @pytest.fixture(scope="class", autouse=True)
    def seed_defaults(self, admin, prop):
        """Set fixed monthly recurring defaults on this class's property (xdist gives
        each worker its own module-scoped property)."""
        r = admin.put(f"{API}/properties/{prop}", json={
            "name": "TEST_Tower_engine", "address": "QA lane",
            "default_payers": {"water": "owner", "cleaning": "owner", "sweeper": "tenant",
                               "security": "owner", "electricity": "tenant", "misc": "owner",
                               "maintenance": "owner", "tips": "tenant"},
            "recurring_defaults": {"security": 5000, "electricity": 1200, "cleaning": 3000, "sweeper": 0}},
            timeout=30)
        assert r.status_code == 200, r.text

    def test_tanker_autocalc(self, admin, prop, month, flats):
        r = admin.post(f"{API}/tankers", json={"property_id": prop, "month": month, "date": f"{month}-05",
                                               "qty_sump": 6000, "qty_syntex": 2000, "amount": 1600,
                                               "payer_flat_id": flats[0]["id"], "payer_type": "owner",
                                               "tips_amount": 100, "tips_payer_flat_id": flats[1]["id"],
                                               "tips_payer_type": "tenant", "supplier": "QA Water"}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total_qty"] == 8000
        # BUG FIX: lorry(1600) + tips(100) = 1700 -> 1700/8000 = 0.2125
        assert d["total_cost"] == 1700, d
        assert d["cost_per_litre"] == 0.2125, d
        got = admin.get(f"{API}/tankers", params={"property_id": prop, "month": month}, timeout=30).json()
        row = [x for x in got if x["id"] == d["id"]][0]
        assert row["tips_amount"] == 100 and row["tips_payer_flat_id"] == flats[1]["id"]
        assert row["tips_payer_type"] == "tenant"

    def test_readings_prefill_and_save(self, admin, prop, month, meters):
        pre = admin.get(f"{API}/readings", params={"property_id": prop, "month": month}, timeout=30).json()
        assert len(pre) == len(meters)
        assert all(p["opening"] == 100 for p in pre), pre
        assert all(p["closing"] is None for p in pre)
        payload = {"property_id": prop, "month": month, "readings": [
            {"meter_id": meters[0]["id"], "opening": 100, "closing": 2100},
            {"meter_id": meters[1]["id"], "opening": 100, "closing": 1100}]}
        r = admin.put(f"{API}/readings", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        after = {x["meter_id"]: x for x in admin.get(f"{API}/readings",
                 params={"property_id": prop, "month": month}, timeout=30).json()}
        assert after[meters[0]["id"]]["closing"] == 2100
        assert after[meters[1]["id"]]["closing"] == 1100

    def test_charges_and_defaults(self, admin, prop, month, flats):
        r = admin.post(f"{API}/charges/apply-defaults", params={"property_id": prop, "month": month}, timeout=30)
        assert r.status_code == 200, r.text
        created1 = r.json()["created"]
        assert len(created1) == 3, [c["charge_type"] for c in created1]  # sweeper=0 skipped
        r2 = admin.post(f"{API}/charges/apply-defaults", params={"property_id": prop, "month": month}, timeout=30)
        assert r2.json()["created"] == [], "apply-defaults duplicated charges"
        rc = admin.post(f"{API}/charges", json={"property_id": prop, "month": month, "charge_type": "cleaning",
                                                "description": "TEST extra clean", "person_name": "Maid Meena",
                                                "amount": 500, "payer_flat_id": flats[1]["id"],
                                                "payer_type": "tenant", "date": f"{month}-06"}, timeout=30)
        assert rc.status_code == 200
        assert rc.json()["category"] == "recurring"
        assert rc.json()["person_name"] == "Maid Meena"
        rm = admin.post(f"{API}/charges", json={"property_id": prop, "month": month,
                                                "charge_type": "maintenance", "description": "TEST pump fix",
                                                "amount": 2000, "payer_flat_id": None,
                                                "payer_type": "owner", "date": f"{month}-07"}, timeout=30)
        assert rm.status_code == 200 and rm.json()["category"] == "adhoc"
        bad = admin.post(f"{API}/charges", json={"property_id": prop, "month": month,
                                                 "charge_type": "bogus", "amount": 10}, timeout=30)
        assert bad.status_code == 400

    def test_payment_received_and_payout(self, admin, prop, month, flats):
        r = admin.post(f"{API}/payments", json={"property_id": prop, "month": month, "flat_id": flats[0]["id"],
                                                "amount": 1000, "date": f"{month}-21", "payer_type": "tenant",
                                                "direction": "received", "notes": "TEST upi"}, timeout=30)
        assert r.status_code == 200
        r2 = admin.post(f"{API}/payments", json={"property_id": prop, "month": month, "flat_id": flats[1]["id"],
                                                 "amount": 300, "date": f"{month}-22", "payer_type": "owner",
                                                 "direction": "payout", "notes": "TEST refund"}, timeout=30)
        assert r2.status_code == 200

    def test_statement_math(self, admin, prop, month, flats, meters):
        st = admin.get(f"{API}/statement", params={"property_id": prop, "month": month}, timeout=30).json()
        t = st["totals"]
        # purchased 8000 L / (1600 lorry + 100 tips) -> avg 0.2125 ; consumed 2000 + 1000 = 3000
        assert t["total_litres"] == 8000
        assert t["total_water_spend"] == 1700
        assert t["total_tips"] == 100
        assert t["avg_cost_per_litre"] == 0.2125
        assert t["total_consumed"] == 3000
        assert t["reserve_litres"] == 5000
        assert t["reserve_value"] == 1062.5
        assert t["reserve_share"] == 531.25
        # recurring = defaults(5000+1200+3000) + manual 500 = 9700 (tips NOT included) ; /2 = 4850
        assert t["recurring_total"] == 9700, st["recurring_items"]
        assert t["recurring_share"] == 4850
        assert "tips" not in [c["charge_type"] for c in st["recurring_items"]]
        assert t["maintenance_total"] == 2000 and t["maintenance_share"] == 1000
        # no double counting: billed total == water + recurring + maintenance
        assert abs(t["billable_total"] - (t["total_water_spend"] + t["recurring_total"]
                                         + t["maintenance_total"])) < 0.05, t
        rows = {r["flat_number"]: r for r in st["rows"]}
        a, b = rows["101"], rows["102"]
        assert a["consumption"] == 2000 and a["water_own_cost"] == 425
        assert a["water_cost"] == 956.25
        assert a["base_cost"] == round(956.25 + 4850 + 1000, 2)
        # contributions: flat101 fronted tanker 1600 ; flat102 tips 100 + cleaning 500
        assert a["contributions"] == 1600
        assert b["contributions"] == 600
        assert a["received_by_tenant"] == 1000 and a["received_by_owner"] == 0
        assert b["payouts"] == 300
        assert a["net"] == round(a["base_cost"] - 1600 + 0 - 1000 + 0, 2)
        assert b["net"] == round(b["base_cost"] - 600 - 0 + 300, 2)
        assert a["status"] == ("owes" if a["net"] > 0 else "owed")

    def test_meter_rollback_flag(self, admin, prop, month, meters):
        payload = {"property_id": prop, "month": month, "readings": [
            {"meter_id": meters[0]["id"], "opening": 100, "closing": 2100},
            {"meter_id": meters[1]["id"], "opening": 100, "closing": 50}]}
        assert admin.put(f"{API}/readings", json=payload, timeout=30).status_code == 200
        st = admin.get(f"{API}/statement", params={"property_id": prop, "month": month}, timeout=30).json()
        flags = [f["type"] for f in st["flags"]]
        assert "meter_rollback" in flags, st["flags"]
        rolled = [m for m in st["meters"] if m["meter_id"] == meters[1]["id"]][0]
        assert rolled["consumption"] == 0 and rolled["flagged"] is True
        # restore
        payload["readings"][1]["closing"] = 1100
        admin.put(f"{API}/readings", json=payload, timeout=30)

    def test_negative_reserve_flag(self, admin, prop, month, meters):
        payload = {"property_id": prop, "month": month, "readings": [
            {"meter_id": meters[0]["id"], "opening": 100, "closing": 9100},
            {"meter_id": meters[1]["id"], "opening": 100, "closing": 1100}]}
        assert admin.put(f"{API}/readings", json=payload, timeout=30).status_code == 200
        st = admin.get(f"{API}/statement", params={"property_id": prop, "month": month}, timeout=30).json()
        assert "negative_reserve" in [f["type"] for f in st["flags"]], st["flags"]
        assert st["totals"]["reserve_litres"] < 0
        assert st["totals"]["reserve_share"] < 0
        big = [r for r in st["rows"] if r["consumption"] == 9000][0]
        assert big["water_own_cost"] == 1912.5  # still billed at avg cost (incl. tips)
        payload["readings"][0]["closing"] = 2100
        admin.put(f"{API}/readings", json=payload, timeout=30)


# ------------------------------------------------- BUG FIX: tips are part of the lorry (water) cost
class TestTipsInWaterCost:
    """User-reported bug: lorry amount + tips must together form the per-litre cost;
    tips must NOT be split as a separate recurring charge."""

    @pytest.fixture(scope="class")
    def env(self, admin):
        pid = admin.post(f"{API}/properties", json={"name": f"TEST_Tips_{uuid.uuid4().hex[:6]}",
                                                    "address": "QA tips"}, timeout=30).json()["id"]
        month = "2026-04"
        fl = []
        for n in ("A1", "A2"):
            f = admin.post(f"{API}/flats", json={"property_id": pid, "number": n,
                                                 "owner_name": f"O {n}", "tenant_name": f"T {n}"}, timeout=30).json()
            m = admin.post(f"{API}/meters", json={"property_id": pid, "flat_id": f["id"],
                                                  "label": f"M {n}", "opening": 0}, timeout=30).json()
            fl.append((f, m))
        yield {"pid": pid, "month": month, "flats": [x[0] for x in fl], "meters": [x[1] for x in fl]}
        admin.delete(f"{API}/properties/{pid}", timeout=30)

    def test_per_tanker_cost_includes_tips(self, admin, env):
        r = admin.post(f"{API}/tankers", json={"property_id": env["pid"], "month": env["month"],
                                               "date": f"{env['month']}-03", "qty_sump": 6000,
                                               "qty_syntex": 2000, "amount": 1200,
                                               "payer_flat_id": env["flats"][0]["id"], "payer_type": "owner",
                                               "tips_amount": 100,
                                               "tips_payer_flat_id": env["flats"][1]["id"],
                                               "tips_payer_type": "tenant"}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total_qty"] == 8000
        assert d["total_cost"] == 1300, d
        assert d["cost_per_litre"] == 0.1625, d
        # persisted
        row = [x for x in admin.get(f"{API}/tankers", params={"property_id": env["pid"],
                                                              "month": env["month"]}, timeout=30).json()
               if x["id"] == d["id"]][0]
        assert row["total_cost"] == 1300 and row["cost_per_litre"] == 0.1625

    def test_statement_totals_and_no_double_count(self, admin, env):
        # readings so all purchased water is consumed
        admin.put(f"{API}/readings", json={"property_id": env["pid"], "month": env["month"], "readings": [
            {"meter_id": env["meters"][0]["id"], "opening": 0, "closing": 5000},
            {"meter_id": env["meters"][1]["id"], "opening": 0, "closing": 3000}]}, timeout=30)
        # a real recurring charge
        assert admin.post(f"{API}/charges", json={"property_id": env["pid"], "month": env["month"],
                                                  "charge_type": "security", "description": "TEST guard",
                                                  "amount": 2000, "payer_type": "owner",
                                                  "date": f"{env['month']}-04"}, timeout=30).status_code == 200
        st = admin.get(f"{API}/statement", params={"property_id": env["pid"],
                                                   "month": env["month"]}, timeout=30).json()
        t = st["totals"]
        assert t["total_water_spend"] == 1300
        assert t["total_tips"] == 100
        assert t["avg_cost_per_litre"] == 0.1625
        # recurring holds ONLY the security charge — no tips
        assert t["recurring_total"] == 2000, st["recurring_items"]
        assert t["recurring_share"] == 1000
        assert all(c["charge_type"] != "tips" for c in st["recurring_items"])
        # invariant: tips counted exactly once
        assert abs(t["billable_total"] - (1300 + 2000 + t["maintenance_total"])) < 0.05, t
        rows = {r["flat_number"]: r for r in st["rows"]}
        assert rows["A1"]["water_own_cost"] == 812.5
        assert rows["A2"]["water_own_cost"] == 487.5
        # contribution credit for the tip payer unchanged
        assert rows["A2"]["contributions"] == 100, rows["A2"]["contribution_detail"]
        assert any(c["source"] == "tips" and c["amount"] == 100
                   for c in rows["A2"]["contribution_detail"])
        assert rows["A1"]["contributions"] == 1200
        assert rows["A2"]["net"] == round(rows["A2"]["base_cost"] - 100, 2)

    def test_demo_property_expected_figures(self, admin):
        props = admin.get(f"{API}/properties", timeout=30).json()
        demo = [p for p in props if p["name"] == "Sunrise Residency"]
        assert demo, "demo property missing"
        pid = demo[0]["id"]
        month = admin.get(f"{API}/periods", params={"property_id": pid}, timeout=30).json()[0]["month"]
        t = admin.get(f"{API}/statement", params={"property_id": pid, "month": month},
                      timeout=30).json()["totals"]
        assert t["total_water_spend"] == 3950, t
        # 3950 / 24000 = 0.164583, engine reports 4-dp rounded
        assert t["avg_cost_per_litre"] == 0.1646, t
        assert t["recurring_total"] == 6500, t
        assert abs(t["billable_total"] - (t["total_water_spend"] + t["recurring_total"]
                                          + t["maintenance_total"])) < 0.05, t

    def test_csv_labels_mention_tips_in_water(self, admin, env):
        r = admin.get(f"{API}/mis/export", params={"property_id": env["pid"], "month": env["month"],
                                                   "format": "csv"}, timeout=60)
        assert r.status_code == 200
        low = r.text.lower()
        assert "lorry" in low and "tips" in low, r.text[:400]


class TestMISExport:
    def test_csv(self, admin, prop, month):
        r = admin.get(f"{API}/mis/export", params={"property_id": prop, "month": month, "format": "csv"}, timeout=60)
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")
        text = r.text
        assert "Flat" in text and "Net" in text and "TOTAL OWES" in text
        assert len(text.splitlines()) > 8

    def test_pdf(self, admin, prop, month):
        r = admin.get(f"{API}/mis/export", params={"property_id": prop, "month": month, "format": "pdf"}, timeout=90)
        assert r.status_code == 200
        assert r.headers.get("content-type") == "application/pdf"
        assert r.content[:4] == b"%PDF"
        assert len(r.content) > 2000


class TestUploads:
    PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)

    def test_image_upload_and_download(self, admin):
        files = {"file": ("qa.png", io.BytesIO(self.PNG), "image/png")}
        r = admin.post(f"{API}/uploads", files=files, data={"lat": "12.97", "lng": "77.59", "source": "camera"}, timeout=120)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["content_type"] == "image/png" and d["lat"] == "12.97"
        g = admin.get(f"{API}/files/{d['id']}", timeout=60)
        assert g.status_code == 200 and g.content[:4] == b"\x89PNG"

    def test_video_upload_without_gps(self, admin):
        files = {"file": ("qa.mp4", io.BytesIO(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32), "video/mp4")}
        r = admin.post(f"{API}/uploads", files=files, data={"source": "upload"}, timeout=120)
        assert r.status_code == 200, r.text
        assert r.json()["content_type"] == "video/mp4"

    def test_reject_non_media(self, admin):
        files = {"file": ("qa.txt", io.BytesIO(b"hello"), "text/plain")}
        r = admin.post(f"{API}/uploads", files=files, timeout=60)
        assert r.status_code == 400

    def test_file_download_requires_real_auth(self, admin):
        files = {"file": ("qa2.png", io.BytesIO(self.PNG), "image/png")}
        fid = admin.post(f"{API}/uploads", files=files, timeout=120).json()["id"]
        r = requests.get(f"{API}/files/{fid}", params={"auth": "any-garbage"}, timeout=60)
        assert r.status_code == 401, "auth query param accepted without validation"


class TestRoleRestrictions:
    @pytest.fixture(scope="class")
    def resident(self):
        s, _ = _login("tenant1@societyhub.com", "demo123")
        return s

    @pytest.fixture(scope="class")
    def demo_pid(self, admin):
        props = admin.get(f"{API}/properties", timeout=30).json()
        d = [p for p in props if p["name"] == "Sunrise Residency"]
        assert d
        return d[0]["id"]

    def test_resident_statement_scoped(self, resident, demo_pid):
        month = None
        periods = resident.get(f"{API}/periods", params={"property_id": demo_pid}, timeout=30).json()
        month = periods[-1]["month"]
        st = resident.get(f"{API}/statement", params={"property_id": demo_pid, "month": month}, timeout=30).json()
        assert len(st["rows"]) == 1, [r["flat_number"] for r in st["rows"]]
        assert st["rows"][0]["flat_number"] == "101"
        assert st.get("my_flat_id")

    def test_resident_write_forbidden(self, resident, demo_pid):
        month = resident.get(f"{API}/periods", params={"property_id": demo_pid}, timeout=30).json()[-1]["month"]
        r1 = resident.post(f"{API}/tankers", json={"property_id": demo_pid, "month": month, "date": f"{month}-02",
                                                   "qty_sump": 1, "qty_syntex": 1, "amount": 5}, timeout=30)
        r2 = resident.post(f"{API}/charges", json={"property_id": demo_pid, "month": month,
                                                   "charge_type": "misc", "amount": 5}, timeout=30)
        r3 = resident.post(f"{API}/payments", json={"property_id": demo_pid, "month": month,
                                                    "flat_id": "x", "amount": 5, "date": f"{month}-02"}, timeout=30)
        r4 = resident.post(f"{API}/demo/seed", timeout=30)
        r5 = resident.get(f"{API}/users", timeout=30)
        assert [r.status_code for r in (r1, r2, r3, r4, r5)] == [403] * 5

    def test_resident_mis_export_forbidden(self, resident, demo_pid):
        """MIS export is admin-only after iteration_1 fix."""
        month = resident.get(f"{API}/periods", params={"property_id": demo_pid}, timeout=30).json()[-1]["month"]
        r = resident.get(f"{API}/mis/export", params={"property_id": demo_pid, "month": month,
                                                      "format": "csv"}, timeout=60)
        assert r.status_code == 403, r.status_code


# ------------------------------------------------------------------ destructive: month reset (isolated property)
class TestMonthResetIsolated:
    @pytest.fixture(scope="class")
    def setup(self, admin):
        p = admin.post(f"{API}/properties", json={"name": f"TEST_Reset_{uuid.uuid4().hex[:6]}"}, timeout=30).json()
        pid = p["id"]
        month = "2026-05"
        f = admin.post(f"{API}/flats", json={"property_id": pid, "number": "1",
                                             "owner_name": "R Owner"}, timeout=30).json()
        m = admin.post(f"{API}/meters", json={"property_id": pid, "flat_id": f["id"],
                                              "label": "M1", "opening": 10}, timeout=30).json()
        admin.post(f"{API}/tankers", json={"property_id": pid, "month": month, "date": f"{month}-02",
                                           "qty_sump": 1000, "qty_syntex": 0, "amount": 500}, timeout=30)
        admin.put(f"{API}/readings", json={"property_id": pid, "month": month, "readings": [
            {"meter_id": m["id"], "opening": 10, "closing": 510}]}, timeout=30)
        yield {"pid": pid, "month": month, "flat": f, "meter": m}
        admin.delete(f"{API}/properties/{pid}", timeout=30)

    def test_reset_locks_and_carries(self, admin, setup):
        pid, month = setup["pid"], setup["month"]
        before = admin.get(f"{API}/statement", params={"property_id": pid, "month": month}, timeout=30).json()
        net = before["rows"][0]["net"]
        r = admin.post(f"{API}/periods/reset", params={"property_id": pid, "month": month}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["locked_month"] == month and d["new_month"] == "2026-06"
        assert d["carry_in"][setup["flat"]["id"]] == net
        periods = {p["month"]: p for p in admin.get(f"{API}/periods", params={"property_id": pid}, timeout=30).json()}
        assert periods[month]["status"] == "locked"
        assert periods["2026-06"]["status"] == "open"
        nxt = admin.get(f"{API}/readings", params={"property_id": pid, "month": "2026-06"}, timeout=30).json()
        assert nxt[0]["opening"] == 510 and nxt[0]["closing"] is None
        nstmt = admin.get(f"{API}/statement", params={"property_id": pid, "month": "2026-06"}, timeout=30).json()
        assert nstmt["rows"][0]["carry_in"] == net

    def test_locked_writes_return_423(self, admin, setup):
        pid, month = setup["pid"], setup["month"]
        r1 = admin.post(f"{API}/tankers", json={"property_id": pid, "month": month, "date": f"{month}-09",
                                                "qty_sump": 10, "qty_syntex": 0, "amount": 5}, timeout=30)
        r2 = admin.post(f"{API}/charges", json={"property_id": pid, "month": month,
                                                "charge_type": "misc", "amount": 5}, timeout=30)
        r3 = admin.post(f"{API}/payments", json={"property_id": pid, "month": month,
                                                 "flat_id": setup["flat"]["id"], "amount": 5,
                                                 "date": f"{month}-09"}, timeout=30)
        r4 = admin.put(f"{API}/readings", json={"property_id": pid, "month": month, "readings": [
            {"meter_id": setup["meter"]["id"], "opening": 10, "closing": 600}]}, timeout=30)
        r5 = admin.post(f"{API}/periods/reset", params={"property_id": pid, "month": month}, timeout=30)
        assert [x.status_code for x in (r1, r2, r3, r4, r5)] == [423] * 5
