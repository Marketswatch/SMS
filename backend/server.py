import os
import io
import csv
import uuid
import logging
from pathlib import Path
from datetime import datetime, timezone, date
from typing import List, Optional, Dict, Any

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field
from bson import ObjectId

import auth as A
from engine import compute_statement, RECURRING_TYPES, ADHOC_TYPES
import storage as S

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("societyhub")

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="SocietyHub API")
api = APIRouter(prefix="/api")

WRITE_ROLES = {"super_admin", "admin"}


def oid(v: str) -> ObjectId:
    try:
        return ObjectId(v)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")


def ser(doc: dict) -> dict:
    d = dict(doc)
    d["id"] = str(d.pop("_id"))
    for k, v in list(d.items()):
        if isinstance(v, ObjectId):
            d[k] = str(v)
        elif isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


async def current_user(request: Request) -> dict:
    return await A.resolve_user(request, db)


async def admin_user(request: Request) -> dict:
    user = await A.resolve_user(request, db)
    if user.get("role") not in WRITE_ROLES:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ---------------------------------------------------------------- auth models
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str
    role: str = "resident"


class LoginIn(BaseModel):
    email: EmailStr
    password: str


@api.get("/")
async def root():
    return {"service": "SocietyHub", "status": "ok"}


@api.post("/auth/register")
async def register(body: RegisterIn, response: Response):
    email = body.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    role = body.role if body.role in {"super_admin", "admin", "owner", "resident"} else "resident"
    doc = {"email": email, "password_hash": A.hash_password(body.password), "name": body.name,
           "role": role, "created_at": datetime.now(timezone.utc)}
    res = await db.users.insert_one(doc)
    uid = str(res.inserted_id)
    A.set_auth_cookies(response, A.create_access_token(uid, email), A.create_refresh_token(uid))
    doc["_id"] = res.inserted_id
    return A.clean_user(doc)


@api.post("/auth/login")
async def login(body: LoginIn, request: Request, response: Response):
    email = body.email.lower()
    ident = email
    await A.check_lockout(db, ident)
    user = await db.users.find_one({"email": email})
    if not user or not A.verify_password(body.password, user["password_hash"]):
        await A.record_failure(db, ident)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    await A.clear_failures(db, ident)
    uid = str(user["_id"])
    access = A.create_access_token(uid, email)
    A.set_auth_cookies(response, access, A.create_refresh_token(uid))
    out = A.clean_user(user)
    out["access_token"] = access
    return out


@api.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"ok": True}


@api.get("/auth/me")
async def me(user: dict = Depends(current_user)):
    return user


@api.get("/users")
async def list_users(user: dict = Depends(admin_user)):
    docs = await db.users.find({}, {"password_hash": 0}).to_list(500)
    return [ser(d) for d in docs]


# ---------------------------------------------------------------- properties
DEFAULT_PAYERS = {"water": "tenant", "cleaning": "tenant", "sweeper": "tenant",
                  "security": "tenant", "electricity": "tenant", "misc": "owner",
                  "maintenance": "owner", "tips": "tenant"}

DEFAULT_RECURRING = {"security": 0, "electricity": 0, "cleaning": 0, "sweeper": 0}


class PropertyIn(BaseModel):
    name: str
    address: str = ""
    default_payers: Optional[Dict[str, str]] = None
    recurring_defaults: Optional[Dict[str, float]] = None


def current_month() -> str:
    return date.today().strftime("%Y-%m")


def next_month(month: str) -> str:
    y, m = (int(x) for x in month.split("-"))
    m += 1
    if m > 12:
        m = 1
        y += 1
    return f"{y:04d}-{m:02d}"


async def ensure_period(property_id: str, month: str) -> dict:
    p = await db.periods.find_one({"property_id": property_id, "month": month})
    if p:
        return p
    doc = {"property_id": property_id, "month": month, "status": "open",
           "carry_in": {}, "created_at": datetime.now(timezone.utc)}
    res = await db.periods.insert_one(doc)
    doc["_id"] = res.inserted_id
    return doc


@api.post("/properties")
async def create_property(body: PropertyIn, user: dict = Depends(admin_user)):
    doc = {"name": body.name, "address": body.address,
           "default_payers": body.default_payers or DEFAULT_PAYERS,
           "recurring_defaults": body.recurring_defaults or DEFAULT_RECURRING,
           "created_by": user["id"], "created_at": datetime.now(timezone.utc)}
    res = await db.properties.insert_one(doc)
    await ensure_period(str(res.inserted_id), current_month())
    doc["_id"] = res.inserted_id
    return ser(doc)


@api.get("/properties")
async def list_properties(user: dict = Depends(current_user)):
    docs = await db.properties.find().sort("created_at", 1).to_list(200)
    out = [ser(d) for d in docs]
    if user.get("role") in {"owner", "resident"}:
        mine = await db.flats.find(
            {"$or": [{"owner_user_id": user["id"]}, {"tenant_user_id": user["id"]}]}).to_list(100)
        allowed = {f["property_id"] for f in mine}
        out = [p for p in out if p["id"] in allowed]
    return out


@api.put("/properties/{pid}")
async def update_property(pid: str, body: PropertyIn, user: dict = Depends(admin_user)):
    upd = {"name": body.name, "address": body.address}
    if body.default_payers is not None:
        upd["default_payers"] = body.default_payers
    if body.recurring_defaults is not None:
        upd["recurring_defaults"] = body.recurring_defaults
    await db.properties.update_one({"_id": oid(pid)}, {"$set": upd})
    doc = await db.properties.find_one({"_id": oid(pid)})
    if not doc:
        raise HTTPException(status_code=404, detail="Property not found")
    return ser(doc)


@api.delete("/properties/{pid}")
async def delete_property(pid: str, user: dict = Depends(admin_user)):
    await db.properties.delete_one({"_id": oid(pid)})
    for c in ("flats", "meters", "tanks", "periods", "tankers", "readings", "charges", "payments"):
        await db[c].delete_many({"property_id": pid})
    return {"ok": True}


# ---------------------------------------------------------------- flats
class FlatIn(BaseModel):
    property_id: str
    number: str
    owner_name: str
    owner_user_id: Optional[str] = None
    owner_phone: str = ""
    tenant_name: str = ""
    tenant_user_id: Optional[str] = None
    tenant_phone: str = ""


@api.post("/flats")
async def create_flat(body: FlatIn, user: dict = Depends(admin_user)):
    doc = body.model_dump()
    doc["created_at"] = datetime.now(timezone.utc)
    res = await db.flats.insert_one(doc)
    doc["_id"] = res.inserted_id
    return ser(doc)


@api.get("/flats")
async def list_flats(property_id: str, user: dict = Depends(current_user)):
    q = {"property_id": property_id}
    if user.get("role") in {"owner", "resident"}:
        q["$or"] = [{"owner_user_id": user["id"]}, {"tenant_user_id": user["id"]}]
    docs = await db.flats.find(q).sort("number", 1).to_list(500)
    return [ser(d) for d in docs]


@api.put("/flats/{fid}")
async def update_flat(fid: str, body: FlatIn, user: dict = Depends(admin_user)):
    await db.flats.update_one({"_id": oid(fid)}, {"$set": body.model_dump()})
    doc = await db.flats.find_one({"_id": oid(fid)})
    if not doc:
        raise HTTPException(status_code=404, detail="Flat not found")
    return ser(doc)


@api.delete("/flats/{fid}")
async def delete_flat(fid: str, user: dict = Depends(admin_user)):
    await db.flats.delete_one({"_id": oid(fid)})
    await db.meters.delete_many({"flat_id": fid})
    return {"ok": True}


# ---------------------------------------------------------------- meters
class MeterIn(BaseModel):
    property_id: str
    flat_id: str
    label: str
    opening: float = 0


@api.post("/meters")
async def create_meter(body: MeterIn, user: dict = Depends(admin_user)):
    doc = body.model_dump()
    doc["created_at"] = datetime.now(timezone.utc)
    res = await db.meters.insert_one(doc)
    doc["_id"] = res.inserted_id
    return ser(doc)


@api.get("/meters")
async def list_meters(property_id: str, user: dict = Depends(admin_user)):
    docs = await db.meters.find({"property_id": property_id}).to_list(500)
    return [ser(d) for d in docs]


@api.delete("/meters/{mid}")
async def delete_meter(mid: str, user: dict = Depends(admin_user)):
    await db.meters.delete_one({"_id": oid(mid)})
    await db.readings.delete_many({"meter_id": mid})
    return {"ok": True}


# ---------------------------------------------------------------- tanks
class TankIn(BaseModel):
    property_id: str
    name: str
    tank_type: str = "sump"
    capacity: float = 0


@api.post("/tanks")
async def create_tank(body: TankIn, user: dict = Depends(admin_user)):
    doc = body.model_dump()
    doc["created_at"] = datetime.now(timezone.utc)
    res = await db.tanks.insert_one(doc)
    doc["_id"] = res.inserted_id
    return ser(doc)


@api.get("/tanks")
async def list_tanks(property_id: str, user: dict = Depends(current_user)):
    docs = await db.tanks.find({"property_id": property_id}).to_list(200)
    return [ser(d) for d in docs]


@api.delete("/tanks/{tid}")
async def delete_tank(tid: str, user: dict = Depends(admin_user)):
    await db.tanks.delete_one({"_id": oid(tid)})
    return {"ok": True}


# ---------------------------------------------------------------- periods
@api.get("/periods")
async def list_periods(property_id: str, user: dict = Depends(current_user)):
    docs = await db.periods.find({"property_id": property_id}).sort("month", 1).to_list(300)
    if not docs:
        docs = [await ensure_period(property_id, current_month())]
    return [ser(d) for d in docs]


async def get_period(property_id: str, month: str) -> dict:
    p = await ensure_period(property_id, month)
    return p


async def guard_open(property_id: str, month: str):
    p = await db.periods.find_one({"property_id": property_id, "month": month})
    if p and p.get("status") == "locked":
        raise HTTPException(status_code=423, detail=f"Period {month} is locked. Historical data cannot be edited.")


# ---------------------------------------------------------------- tankers
class TankerIn(BaseModel):
    property_id: str
    month: str
    date: str
    qty_sump: float = 0
    qty_syntex: float = 0
    amount: float = 0
    payer_flat_id: Optional[str] = None
    payer_type: str = "owner"
    tips_amount: float = 0
    tips_payer_flat_id: Optional[str] = None
    tips_payer_type: str = "owner"
    supplier: str = ""
    notes: str = ""
    media: List[Dict[str, Any]] = []


@api.post("/tankers")
async def create_tanker(body: TankerIn, user: dict = Depends(admin_user)):
    await guard_open(body.property_id, body.month)
    await ensure_period(body.property_id, body.month)
    doc = body.model_dump()
    doc["total_qty"] = doc["qty_sump"] + doc["qty_syntex"]
    doc["total_cost"] = doc["amount"] + (doc.get("tips_amount") or 0)
    doc["cost_per_litre"] = round(doc["total_cost"] / doc["total_qty"], 4) if doc["total_qty"] else 0
    doc["created_at"] = datetime.now(timezone.utc)
    doc["created_by"] = user["id"]
    res = await db.tankers.insert_one(doc)
    doc["_id"] = res.inserted_id
    return ser(doc)


@api.get("/tankers")
async def list_tankers(property_id: str, month: str, user: dict = Depends(admin_user)):
    docs = await db.tankers.find({"property_id": property_id, "month": month}).sort("date", 1).to_list(500)
    return [ser(d) for d in docs]


@api.delete("/tankers/{tid}")
async def delete_tanker(tid: str, user: dict = Depends(admin_user)):
    doc = await db.tankers.find_one({"_id": oid(tid)})
    if doc:
        await guard_open(doc["property_id"], doc["month"])
    await db.tankers.delete_one({"_id": oid(tid)})
    return {"ok": True}


# ---------------------------------------------------------------- readings
class ReadingIn(BaseModel):
    meter_id: str
    opening: float
    closing: Optional[float] = None
    media: List[Dict[str, Any]] = []


class ReadingsBulk(BaseModel):
    property_id: str
    month: str
    readings: List[ReadingIn]


@api.get("/readings")
async def list_readings(property_id: str, month: str, user: dict = Depends(current_user)):
    meters = await db.meters.find({"property_id": property_id}).to_list(500)
    existing = {r["meter_id"]: r for r in
                await db.readings.find({"property_id": property_id, "month": month}).to_list(1000)}
    out = []
    for m in meters:
        mid = str(m["_id"])
        r = existing.get(mid)
        out.append({
            "meter_id": mid, "label": m.get("label"), "flat_id": m.get("flat_id"),
            "opening": float(r["opening"]) if r else float(m.get("opening", 0) or 0),
            "closing": (float(r["closing"]) if r and r.get("closing") is not None else None),
            "media": (r.get("media") or []) if r else [],
        })
    return out


@api.put("/readings")
async def save_readings(body: ReadingsBulk, user: dict = Depends(admin_user)):
    await guard_open(body.property_id, body.month)
    await ensure_period(body.property_id, body.month)
    for r in body.readings:
        await db.readings.update_one(
            {"property_id": body.property_id, "month": body.month, "meter_id": r.meter_id},
            {"$set": {"opening": r.opening, "closing": r.closing, "media": r.media,
                      "updated_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
    return await list_readings(body.property_id, body.month, user)


# ---------------------------------------------------------------- charges
class ChargeIn(BaseModel):
    property_id: str
    month: str
    charge_type: str
    description: str = ""
    person_name: str = ""
    amount: float
    payer_flat_id: Optional[str] = None
    payer_type: str = "owner"
    date: str = ""
    media: List[Dict[str, Any]] = []


@api.post("/charges")
async def create_charge(body: ChargeIn, user: dict = Depends(admin_user)):
    if body.charge_type not in RECURRING_TYPES + ADHOC_TYPES:
        raise HTTPException(status_code=400, detail="Unknown charge type")
    await guard_open(body.property_id, body.month)
    await ensure_period(body.property_id, body.month)
    doc = body.model_dump()
    doc["category"] = "adhoc" if body.charge_type in ADHOC_TYPES else "recurring"
    doc["created_at"] = datetime.now(timezone.utc)
    res = await db.charges.insert_one(doc)
    doc["_id"] = res.inserted_id
    return ser(doc)


@api.get("/charges")
async def list_charges(property_id: str, month: str, user: dict = Depends(admin_user)):
    docs = await db.charges.find({"property_id": property_id, "month": month}).to_list(1000)
    return [ser(d) for d in docs]


@api.delete("/charges/{cid}")
async def delete_charge(cid: str, user: dict = Depends(admin_user)):
    doc = await db.charges.find_one({"_id": oid(cid)})
    if doc:
        await guard_open(doc["property_id"], doc["month"])
    await db.charges.delete_one({"_id": oid(cid)})
    return {"ok": True}


@api.post("/charges/apply-defaults")
async def apply_recurring_defaults(property_id: str, month: str, user: dict = Depends(admin_user)):
    await guard_open(property_id, month)
    prop = await db.properties.find_one({"_id": oid(property_id)})
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    defaults = prop.get("recurring_defaults") or {}
    payers = prop.get("default_payers") or DEFAULT_PAYERS
    created = []
    for ctype, amount in defaults.items():
        if not amount or float(amount) <= 0:
            continue
        exists = await db.charges.find_one({"property_id": property_id, "month": month, "charge_type": ctype})
        if exists:
            continue
        doc = {"property_id": property_id, "month": month, "charge_type": ctype,
               "description": f"{ctype.title()} (monthly default)", "person_name": "",
               "amount": float(amount), "payer_flat_id": None,
               "payer_type": payers.get(ctype, "owner"), "date": f"{month}-01",
               "media": [], "category": "recurring", "created_at": datetime.now(timezone.utc)}
        res = await db.charges.insert_one(doc)
        doc["_id"] = res.inserted_id
        created.append(ser(doc))
    return {"created": created}


# ---------------------------------------------------------------- payments
class PaymentIn(BaseModel):
    property_id: str
    month: str
    flat_id: str
    amount: float
    date: str
    payer_type: str = "owner"
    direction: str = "received"
    notes: str = ""


@api.post("/payments")
async def create_payment(body: PaymentIn, user: dict = Depends(admin_user)):
    await guard_open(body.property_id, body.month)
    await ensure_period(body.property_id, body.month)
    doc = body.model_dump()
    doc["created_at"] = datetime.now(timezone.utc)
    res = await db.payments.insert_one(doc)
    doc["_id"] = res.inserted_id
    return ser(doc)


@api.get("/payments")
async def list_payments(property_id: str, month: str, user: dict = Depends(admin_user)):
    docs = await db.payments.find({"property_id": property_id, "month": month}).sort("date", 1).to_list(1000)
    return [ser(d) for d in docs]


@api.delete("/payments/{pid}")
async def delete_payment(pid: str, user: dict = Depends(admin_user)):
    doc = await db.payments.find_one({"_id": oid(pid)})
    if doc:
        await guard_open(doc["property_id"], doc["month"])
    await db.payments.delete_one({"_id": oid(pid)})
    return {"ok": True}


# ---------------------------------------------------------------- statement
async def build_statement(property_id: str, month: str) -> dict:
    period = await ensure_period(property_id, month)
    prop = await db.properties.find_one({"_id": oid(property_id)})
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    flats = [ser(d) for d in await db.flats.find({"property_id": property_id}).sort("number", 1).to_list(500)]
    meters = [ser(d) for d in await db.meters.find({"property_id": property_id}).to_list(500)]
    readings = await db.readings.find({"property_id": property_id, "month": month}).to_list(1000)
    readings = [{"meter_id": r["meter_id"], "opening": r.get("opening", 0), "closing": r.get("closing")} for r in readings]
    tankers = [ser(d) for d in await db.tankers.find({"property_id": property_id, "month": month}).to_list(500)]
    charges = [ser(d) for d in await db.charges.find({"property_id": property_id, "month": month}).to_list(1000)]
    payments = [ser(d) for d in await db.payments.find({"property_id": property_id, "month": month}).to_list(1000)]
    stmt = compute_statement(flats, meters, readings, tankers, charges, payments, period.get("carry_in", {}))
    stmt["property"] = {"id": property_id, "name": prop.get("name"), "address": prop.get("address")}
    stmt["month"] = month
    stmt["status"] = period.get("status", "open")
    return stmt


@api.get("/statement")
async def statement(property_id: str, month: str, user: dict = Depends(current_user)):
    stmt = await build_statement(property_id, month)
    if user.get("role") in {"owner", "resident"}:
        flat = await db.flats.find_one({"$or": [{"owner_user_id": user["id"]}, {"tenant_user_id": user["id"]}],
                                        "property_id": property_id})
        fid = str(flat["_id"]) if flat else None
        stmt["rows"] = [r for r in stmt["rows"] if r["flat_id"] == fid]
        stmt["meters"] = [m for m in stmt["meters"] if m.get("flat_id") == fid]
        stmt["my_flat_id"] = fid
    return stmt


# ---------------------------------------------------------------- month reset
@api.post("/periods/reset")
async def reset_month(property_id: str, month: str, user: dict = Depends(admin_user)):
    period = await ensure_period(property_id, month)
    if period.get("status") == "locked":
        raise HTTPException(status_code=423, detail="Period already locked")
    stmt = await build_statement(property_id, month)
    nxt = next_month(month)
    carry = {r["flat_id"]: r["net"] for r in stmt["rows"]}

    await db.periods.update_one({"_id": period["_id"]},
                                {"$set": {"status": "locked", "locked_at": datetime.now(timezone.utc),
                                          "snapshot": stmt}})
    nxt_period = await ensure_period(property_id, nxt)
    await db.periods.update_one({"_id": nxt_period["_id"]}, {"$set": {"carry_in": carry, "status": "open"}})

    # carry closing readings to next month's opening
    for m in stmt["meters"]:
        opening = m["closing"] if m["closing"] is not None else m["opening"]
        await db.readings.update_one(
            {"property_id": property_id, "month": nxt, "meter_id": m["meter_id"]},
            {"$set": {"opening": opening, "closing": None, "updated_at": datetime.now(timezone.utc)}},
            upsert=True)
        await db.meters.update_one({"_id": oid(m["meter_id"])}, {"$set": {"opening": opening}})

    return {"ok": True, "locked_month": month, "new_month": nxt, "carry_in": carry}


# ---------------------------------------------------------------- MIS export
@api.get("/mis/export")
async def mis_export(property_id: str, month: str, format: str = Query("csv"),
                     user: dict = Depends(admin_user)):
    stmt = await build_statement(property_id, month)
    t = stmt["totals"]
    if format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([f"SocietyHub MIS — {stmt['property']['name']} — {month}"])
        w.writerow([])
        w.writerow(["Water purchased (L)", t["total_litres"], "Water spend (lorry+tips)", t["total_water_spend"],
                    "Avg cost/L", t["avg_cost_per_litre"], "of which tips", t["total_tips"]])
        w.writerow(["Consumed (L)", t["total_consumed"], "Reserve (L)", t["reserve_litres"],
                    "Reserve value", t["reserve_value"]])
        w.writerow(["Recurring total", t["recurring_total"], "Maintenance total", t["maintenance_total"]])
        w.writerow([])
        w.writerow(["Flat", "Owner", "Tenant", "Consumption L", "Water cost", "Reserve share",
                    "Recurring share", "Maintenance share", "Base cost", "Contributions",
                    "Carry-in", "Paid by tenant", "Paid by owner", "Payouts", "Net", "Status"])
        for r in stmt["rows"]:
            w.writerow([r["flat_number"], r["owner_name"], r["tenant_name"], r["consumption"],
                        r["water_own_cost"], r["reserve_share"], r["recurring_share"],
                        r["maintenance_share"], r["base_cost"], r["contributions"], r["carry_in"],
                        r["received_by_tenant"], r["received_by_owner"], r["payouts"], r["net"], r["status"]])
        w.writerow([])
        w.writerow(["TOTAL OWES", t["total_owes"], "TOTAL OWED", t["total_owed"], "NET", t["net_position"]])
        data = buf.getvalue().encode("utf-8")
        return StreamingResponse(io.BytesIO(data), media_type="text/csv",
                                 headers={"Content-Disposition": f'attachment; filename="mis-{month}.csv"'})

    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=landscape(A4), title=f"MIS {month}")
    styles = getSampleStyleSheet()
    story = [Paragraph(f"SocietyHub MIS — {stmt['property']['name']}", styles["Title"]),
             Paragraph(f"Period: {month} &nbsp;&nbsp; Status: {stmt['status']}", styles["Normal"]),
             Spacer(1, 10)]
    summary = [["Water purchased (L)", t["total_litres"], "Water spend (lorry + tips)", t["total_water_spend"],
                "Avg cost / L", t["avg_cost_per_litre"]],
               ["Consumed (L)", t["total_consumed"], "Reserve (L)", t["reserve_litres"],
                "Reserve value", t["reserve_value"]],
               ["Recurring total", t["recurring_total"], "Maintenance total", t["maintenance_total"],
                "Billable total", t["billable_total"]]]
    st = Table(summary, hAlign="LEFT")
    st.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                            ("FONTSIZE", (0, 0), (-1, -1), 8),
                            ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke)]))
    story += [st, Spacer(1, 14)]

    head = ["Flat", "Owner", "Tenant", "Cons L", "Water", "Reserve", "Recurring",
            "Maint.", "Base", "Contrib.", "Carry", "Tenant paid", "Owner paid", "Payout", "Net", "Status"]
    rows = [head]
    for r in stmt["rows"]:
        rows.append([r["flat_number"], r["owner_name"], r["tenant_name"], r["consumption"],
                     r["water_own_cost"], r["reserve_share"], r["recurring_share"], r["maintenance_share"],
                     r["base_cost"], r["contributions"], r["carry_in"], r["received_by_tenant"],
                     r["received_by_owner"], r["payouts"], r["net"], r["status"].upper()])
    tbl = Table(rows, repeatRows=1)
    style = [("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
             ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
             ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
             ("FONTSIZE", (0, 0), (-1, -1), 7),
             ("ALIGN", (3, 1), (-1, -1), "RIGHT")]
    for i, r in enumerate(stmt["rows"], start=1):
        if r["net"] > 0:
            style.append(("TEXTCOLOR", (-2, i), (-1, i), colors.HexColor("#DC2626")))
        elif r["net"] < 0:
            style.append(("TEXTCOLOR", (-2, i), (-1, i), colors.HexColor("#16A34A")))
    tbl.setStyle(TableStyle(style))
    story += [tbl, Spacer(1, 12),
              Paragraph(f"Total receivable (owes): {t['total_owes']} &nbsp;|&nbsp; Total payable (owed): {t['total_owed']} &nbsp;|&nbsp; Net: {t['net_position']}", styles["Normal"])]
    doc.build(story)
    out.seek(0)
    return StreamingResponse(out, media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="mis-{month}.pdf"'})


# ---------------------------------------------------------------- uploads
MAX_UPLOAD = 40 * 1024 * 1024


@api.post("/uploads")
async def upload_file(file: UploadFile = File(...), lat: Optional[str] = Form(None),
                      lng: Optional[str] = Form(None), source: str = Form("upload"),
                      user: dict = Depends(admin_user)):
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="File too large (max 40MB)")
    ctype = file.content_type or "application/octet-stream"
    if not (ctype.startswith("image/") or ctype.startswith("video/")):
        raise HTTPException(status_code=400, detail="Only images and videos allowed")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "bin"
    path = f"{S.APP_NAME}/uploads/{user['id']}/{uuid.uuid4()}.{ext}"
    try:
        result = S.put_object(path, data, ctype)
    except Exception as e:
        logger.error(f"upload failed: {e}")
        raise HTTPException(status_code=502, detail="Storage upload failed")
    doc = {"storage_path": result["path"], "original_filename": file.filename,
           "content_type": ctype, "size": result.get("size", len(data)),
           "lat": lat, "lng": lng, "source": source, "is_deleted": False,
           "uploaded_by": user["id"], "created_at": datetime.now(timezone.utc)}
    res = await db.files.insert_one(doc)
    return {"id": str(res.inserted_id), "storage_path": result["path"], "content_type": ctype,
            "original_filename": file.filename, "lat": lat, "lng": lng, "source": source}


@api.get("/files/{file_id}")
async def download_file(file_id: str, request: Request, auth: Optional[str] = Query(None)):
    token = A.extract_token(request) or auth
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    await A.verify_access_token(token, db)
    rec = await db.files.find_one({"_id": oid(file_id), "is_deleted": False})
    if not rec:
        raise HTTPException(status_code=404, detail="File not found")
    data, ctype = S.get_object(rec["storage_path"])
    return Response(content=data, media_type=rec.get("content_type", ctype))


# ---------------------------------------------------------------- demo seed
@api.post("/demo/seed")
async def demo_seed(user: dict = Depends(admin_user)):
    existing = await db.properties.find_one({"name": "Sunrise Residency"})
    if existing:
        return {"ok": True, "property_id": str(existing["_id"]), "already": True}

    async def mkuser(email, name, role):
        u = await db.users.find_one({"email": email})
        if u:
            return str(u["_id"])
        res = await db.users.insert_one({"email": email, "password_hash": A.hash_password("demo123"),
                                         "name": name, "role": role,
                                         "created_at": datetime.now(timezone.utc)})
        return str(res.inserted_id)

    await mkuser("manager@societyhub.com", "Society Manager", "admin")
    owner_id = await mkuser("owner1@societyhub.com", "Ramesh Kumar", "owner")
    tenant_id = await mkuser("tenant1@societyhub.com", "Arjun Rao", "resident")

    prop = {"name": "Sunrise Residency", "address": "12th Cross, Indiranagar, Bengaluru",
            "default_payers": DEFAULT_PAYERS,
            "recurring_defaults": {"security": 6000, "electricity": 3500, "cleaning": 4000, "sweeper": 2500},
            "created_by": user["id"], "created_at": datetime.now(timezone.utc)}
    pres = await db.properties.insert_one(prop)
    pid = str(pres.inserted_id)
    month = current_month()
    await ensure_period(pid, month)

    flats_spec = [("101", "Ramesh Kumar", "Arjun Rao", owner_id, tenant_id, "9876500101"),
                  ("102", "Sunita Desai", "", None, None, "9876500102"),
                  ("201", "Vikram Nair", "Priya Menon", None, None, "9876500201"),
                  ("202", "Anil Joshi", "", None, None, "9876500202")]
    flat_ids = []
    for num, owner, tenant, ouid, tuid, phone in flats_spec:
        r = await db.flats.insert_one({"property_id": pid, "number": num, "owner_name": owner,
                                       "owner_user_id": ouid, "owner_phone": phone,
                                       "tenant_name": tenant, "tenant_user_id": tuid, "tenant_phone": "",
                                       "created_at": datetime.now(timezone.utc)})
        fid = str(r.inserted_id)
        flat_ids.append(fid)
        await db.meters.insert_one({"property_id": pid, "flat_id": fid, "label": f"Meter {num}",
                                    "opening": 1000, "created_at": datetime.now(timezone.utc)})

    await db.tanks.insert_one({"property_id": pid, "name": "Main Sump", "tank_type": "sump",
                               "capacity": 20000, "created_at": datetime.now(timezone.utc)})
    await db.tanks.insert_one({"property_id": pid, "name": "Roof Syntex", "tank_type": "syntex",
                               "capacity": 5000, "created_at": datetime.now(timezone.utc)})

    for i, (d, sump, syn, amt, payer) in enumerate([
            (f"{month}-03", 6000, 2000, 1200, flat_ids[0]),
            (f"{month}-11", 6000, 2000, 1250, flat_ids[1]),
            (f"{month}-19", 6000, 2000, 1200, flat_ids[0])]):
        await db.tankers.insert_one({"property_id": pid, "month": month, "date": d,
                                     "qty_sump": sump, "qty_syntex": syn, "total_qty": sump + syn,
                                     "amount": amt, "cost_per_litre": round((amt + 100) / (sump + syn), 4),
                                     "total_cost": amt + 100,
                                     "payer_flat_id": payer, "payer_type": "owner",
                                     "tips_amount": 100, "tips_payer_flat_id": payer,
                                     "tips_payer_type": "tenant", "supplier": "Krishna Water Supply",
                                     "notes": "", "media": [], "created_at": datetime.now(timezone.utc)})

    meters = await db.meters.find({"property_id": pid}).to_list(50)
    for i, m in enumerate(meters):
        await db.readings.insert_one({"property_id": pid, "month": month, "meter_id": str(m["_id"]),
                                      "opening": 1000, "closing": 1000 + 4500 + i * 600,
                                      "updated_at": datetime.now(timezone.utc)})

    await db.charges.insert_one({"property_id": pid, "month": month, "charge_type": "cleaning",
                                 "description": "Monthly cleaning", "person_name": "Lakshmi",
                                 "amount": 4000, "payer_flat_id": flat_ids[2], "payer_type": "tenant",
                                 "date": f"{month}-05", "media": [], "category": "recurring",
                                 "created_at": datetime.now(timezone.utc)})
    await db.charges.insert_one({"property_id": pid, "month": month, "charge_type": "sweeper",
                                 "description": "Sweeping", "person_name": "Ganesh", "amount": 2500,
                                 "payer_flat_id": flat_ids[3], "payer_type": "owner",
                                 "date": f"{month}-05", "media": [], "category": "recurring",
                                 "created_at": datetime.now(timezone.utc)})
    await db.charges.insert_one({"property_id": pid, "month": month, "charge_type": "maintenance",
                                 "description": "Overhead tank motor replacement", "person_name": "",
                                 "amount": 8600, "payer_flat_id": flat_ids[0], "payer_type": "owner",
                                 "date": f"{month}-14", "media": [], "category": "adhoc",
                                 "created_at": datetime.now(timezone.utc)})
    await db.payments.insert_one({"property_id": pid, "month": month, "flat_id": flat_ids[1],
                                 "amount": 2000, "date": f"{month}-20", "payer_type": "tenant",
                                  "direction": "received", "notes": "UPI",
                                  "created_at": datetime.now(timezone.utc)})
    return {"ok": True, "property_id": pid}


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await A.seed_admin(db)
    await db.users.create_index("email", unique=True)
    await db.login_attempts.create_index("identifier")
    await db.flats.create_index([("property_id", 1)])
    await db.readings.create_index([("property_id", 1), ("month", 1), ("meter_id", 1)])
    await db.periods.create_index([("property_id", 1), ("month", 1)], unique=True)
    try:
        S.init_storage()
        logger.info("storage ready")
    except Exception as e:
        logger.error(f"storage init failed: {e}")


@app.on_event("shutdown")
async def shutdown():
    client.close()
