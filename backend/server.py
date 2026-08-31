import os
import io
import re
import csv
import uuid
import logging
from pathlib import Path
from datetime import datetime, timezone, date
from typing import List, Optional, Dict, Any, Literal

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
from engine import compute_statement, RECURRING_TYPES, ADHOC_TYPES, flat_sort_key
from engine import PAYMENT_STATUS_LABELS as E_LABELS
import rentals
import storage as S
import xlsx as X
import reports as R

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
    valid_month(month)
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
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def valid_month(month: str) -> str:
    if not month or not MONTH_RE.match(month):
        raise HTTPException(status_code=400, detail="Month must be in YYYY-MM format")
    return month


def valid_format(fmt: str, allowed=("csv", "pdf", "xlsx")) -> str:
    if fmt not in allowed:
        raise HTTPException(status_code=400,
                            detail=f"Unsupported format '{fmt}'. Use one of: {', '.join(allowed)}")
    return fmt


def dmy(d) -> str:
    """DD-MM-YYYY for every date shown in an export or receipt."""
    s = str(d or "")[:10]
    parts = s.split("-")
    return f"{parts[2]}-{parts[1]}-{parts[0]}" if len(parts) == 3 else (s or "—")


def mon_label(m: str) -> str:
    parts = str(m or "").split("-")
    if len(parts) < 2:
        return str(m or "")
    names = ["January", "February", "March", "April", "May", "June",
             "July", "August", "September", "October", "November", "December"]
    try:
        return f"{names[int(parts[1]) - 1]} {parts[0]}"
    except (ValueError, IndexError):
        return str(m)


class FlatIn(BaseModel):
    property_id: str
    number: str
    floor: str = ""
    opening_dues: float = 0
    opening_dues_payer: Literal["owner", "tenant"] = "owner"
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
    docs = await db.flats.find(q).to_list(500)
    return [ser(d) for d in sorted(docs, key=flat_sort_key)]


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
    date: str                      # delivery date — drives the reserve inflow and the month
    booking_date: str = ""         # optional; must be on or before the delivery date
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


def tanker_doc(body: "TankerIn") -> dict:
    """Delivery date drives the reserve inflow, so it also decides the month."""
    doc = body.model_dump()
    if doc.get("booking_date") and doc["booking_date"] > doc["date"]:
        raise HTTPException(status_code=400, detail="Delivery date must be on or after the booking date")
    doc["month"] = valid_month(doc["date"][:7])
    doc["total_qty"] = doc["qty_sump"] + doc["qty_syntex"]
    doc["total_cost"] = doc["amount"] + (doc.get("tips_amount") or 0)
    doc["cost_per_litre"] = round(doc["total_cost"] / doc["total_qty"], 4) if doc["total_qty"] else 0
    return doc


@api.post("/tankers")
async def create_tanker(body: TankerIn, user: dict = Depends(admin_user)):
    doc = tanker_doc(body)
    await guard_open(body.property_id, doc["month"])
    await ensure_period(body.property_id, doc["month"])
    doc["created_at"] = datetime.now(timezone.utc)
    doc["created_by"] = user["id"]
    res = await db.tankers.insert_one(doc)
    doc["_id"] = res.inserted_id
    return ser(doc)


@api.get("/tankers")
async def list_tankers(property_id: str, month: str, user: dict = Depends(admin_user)):
    docs = await db.tankers.find({"property_id": property_id, "month": month}).sort("date", 1).to_list(500)
    return [ser(d) for d in docs]


@api.put("/tankers/{tid}")
async def update_tanker(tid: str, body: TankerIn, user: dict = Depends(admin_user)):
    existing = await db.tankers.find_one({"_id": oid(tid)})
    if not existing:
        raise HTTPException(status_code=404, detail="Tanker not found")
    doc = tanker_doc(body)
    await guard_open(existing["property_id"], existing["month"])
    await guard_open(body.property_id, doc["month"])
    await ensure_period(body.property_id, doc["month"])
    doc["updated_at"] = datetime.now(timezone.utc)
    await db.tankers.update_one({"_id": oid(tid)}, {"$set": doc})
    return ser(await db.tankers.find_one({"_id": oid(tid)}))


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


@api.put("/charges/{cid}")
async def update_charge(cid: str, body: ChargeIn, user: dict = Depends(admin_user)):
    existing = await db.charges.find_one({"_id": oid(cid)})
    if not existing:
        raise HTTPException(status_code=404, detail="Charge not found")
    if body.charge_type not in RECURRING_TYPES + ADHOC_TYPES:
        raise HTTPException(status_code=400, detail="Unknown charge type")
    await guard_open(existing["property_id"], existing["month"])
    await guard_open(body.property_id, body.month)
    doc = body.model_dump()
    doc["category"] = "adhoc" if body.charge_type in ADHOC_TYPES else "recurring"
    doc["updated_at"] = datetime.now(timezone.utc)
    await db.charges.update_one({"_id": oid(cid)}, {"$set": doc})
    return ser(await db.charges.find_one({"_id": oid(cid)}))


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
    payer_type: Literal["owner", "tenant"] = "owner"
    direction: Literal["received", "payout"] = "received"
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
async def read_period(property_id: str, month: str) -> dict:
    """Read-only period lookup — never creates a period document."""
    valid_month(month)
    return await db.periods.find_one({"property_id": property_id, "month": month}) or {
        "property_id": property_id, "month": month, "status": "open", "carry_in": {}}


async def build_statement(property_id: str, month: str, ensure: bool = True) -> dict:
    valid_month(month)
    period = await ensure_period(property_id, month) if ensure else await read_period(property_id, month)
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
    stmt = await build_statement(property_id, month, ensure=False)
    if user.get("role") in {"owner", "resident"}:
        flat = await db.flats.find_one({"$or": [{"owner_user_id": user["id"]}, {"tenant_user_id": user["id"]}],
                                        "property_id": property_id})
        fid = str(flat["_id"]) if flat else None
        stmt["rows"] = [r for r in stmt["rows"] if r["flat_id"] == fid]
        stmt["meters"] = [m for m in stmt["meters"] if m.get("flat_id") == fid]
        stmt["my_flat_id"] = fid
    return stmt


@api.get("/annual")
async def annual_statement(property_id: str, year: int, user: dict = Depends(current_user)):
    prop = await db.properties.find_one({"_id": oid(property_id)})
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    my_flat_id = None
    if user.get("role") in {"owner", "resident"}:
        flat = await db.flats.find_one({"property_id": property_id,
                                        "$or": [{"owner_user_id": user["id"]}, {"tenant_user_id": user["id"]}]})
        my_flat_id = str(flat["_id"]) if flat else "none"
    periods = await db.periods.find({"property_id": property_id,
                                    "month": {"$regex": f"^{year}-"}}).sort("month", 1).to_list(24)
    months = []
    per_flat = {}
    for p in periods:
        month = p["month"]
        stmt = p.get("snapshot") if p.get("status") == "locked" and p.get("snapshot") else \
            await build_statement(property_id, month)
        t = stmt["totals"]
        months.append({
            "month": month, "status": p.get("status", "open"),
            "water_spend": t["total_water_spend"], "litres": t["total_litres"],
            "avg_cost_per_litre": t["avg_cost_per_litre"], "consumed": t["total_consumed"],
            "reserve_litres": t["reserve_litres"],
            "recurring_total": t["recurring_total"], "maintenance_total": t["maintenance_total"],
            "billable_total": t["billable_total"], "received": t["total_received"],
            "contributions": t["total_contributions"], "net_position": t["net_position"],
        })
        for r in stmt["rows"]:
            if my_flat_id and r["flat_id"] != my_flat_id:
                continue
            f = per_flat.setdefault(r["flat_id"], {
                "flat_id": r["flat_id"], "flat_number": r["flat_number"], "owner_name": r["owner_name"],
                "consumption": 0.0, "water_cost": 0.0, "recurring": 0.0, "maintenance": 0.0,
                "billable": 0.0, "contributions": 0.0, "received": 0.0, "payouts": 0.0,
                "months": [],
            })
            f["consumption"] += r["consumption"]
            f["water_cost"] += r["water_cost"]
            f["recurring"] += r["recurring_share"]
            f["maintenance"] += r["maintenance_share"]
            f["billable"] += r["base_cost"]
            f["contributions"] += r["contributions"]
            f["received"] += r["received"]
            f["payouts"] += r["payouts"]
            f["months"].append({"month": month, "billable": r["base_cost"], "paid": r["received"],
                                "fronted": r["contributions"], "net": r["net"]})

    rows = []
    for f in per_flat.values():
        closing = f["months"][-1]["net"] if f["months"] else 0
        rows.append({**{k: (round(v, 2) if isinstance(v, float) else v) for k, v in f.items()},
                     "closing_balance": round(closing, 2)})
    rows.sort(key=lambda r: str(r["flat_number"]))

    return {
        "property": {"id": property_id, "name": prop.get("name"), "address": prop.get("address")},
        "year": year, "months": months, "rows": rows,
        "totals": {
            "months_recorded": len(months),
            "water_spend": round(sum(m["water_spend"] for m in months), 2),
            "litres": round(sum(m["litres"] for m in months), 2),
            "recurring_total": round(sum(m["recurring_total"] for m in months), 2),
            "maintenance_total": round(sum(m["maintenance_total"] for m in months), 2),
            "billable_total": round(sum(m["billable_total"] for m in months), 2),
            "received": round(sum(m["received"] for m in months), 2),
            "closing_position": round(sum(r["closing_balance"] for r in rows), 2),
        },
    }


@api.get("/annual/export")
async def annual_export(property_id: str, year: int, format: str = Query("csv"),
                        user: dict = Depends(admin_user)):
    valid_format(format, ("csv", "pdf"))
    data = await annual_statement(property_id, year, user)
    t = data["totals"]
    head = ["S.No", "Flat", "Owner", "Consumption L", "Water cost", "Recurring", "Maintenance",
            "Total billed", "Fronted", "Paid", "Payouts", "Closing balance"]
    counter = {"n": 0}

    def vals(r):
        counter["n"] += 1
        return [counter["n"], r["flat_number"], r["owner_name"], r["consumption"], r["water_cost"], r["recurring"],
                r["maintenance"], r["billable"], r["contributions"], r["received"], r["payouts"],
                r["closing_balance"]]

    if format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([f"SocietyHub Annual Statement — {data['property']['name']} — {year}"])
        w.writerow([])
        w.writerow(["Months recorded", t["months_recorded"], "Water spend", t["water_spend"],
                    "Litres", t["litres"]])
        w.writerow(["Recurring", t["recurring_total"], "Maintenance", t["maintenance_total"],
                    "Total billed", t["billable_total"], "Collected", t["received"]])
        w.writerow([])
        w.writerow(head)
        for r in data["rows"]:
            w.writerow(vals(r))
        w.writerow([])
        w.writerow(["S.No", "Month", "Litres", "Water spend", "Avg /L", "Recurring", "Maintenance", "Billed", "Collected"])
        for i, m in enumerate(data["months"], start=1):
            w.writerow([i, mon_label(m["month"]), m["litres"], m["water_spend"], m["avg_cost_per_litre"],
                        m["recurring_total"], m["maintenance_total"], m["billable_total"], m["received"]])
        out = buf.getvalue().encode("utf-8")
        return StreamingResponse(io.BytesIO(out), media_type="text/csv",
                                 headers={"Content-Disposition": f'attachment; filename="annual-{year}.csv"'})

    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), title=f"Annual {year}")
    styles = getSampleStyleSheet()
    story = [Paragraph(f"Annual Statement — {data['property']['name']} — {year}", styles["Title"]),
             Spacer(1, 10)]
    tbl = Table([head] + [vals(r) for r in data["rows"]], repeatRows=1)
    tbl.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                             ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                             ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                             ("FONTSIZE", (0, 0), (-1, -1), 7),
                             ("ALIGN", (2, 1), (-1, -1), "RIGHT")]))
    story += [tbl, Spacer(1, 16), Paragraph("Month by month", styles["Heading3"])]
    mh = ["S.No", "Month", "Litres", "Water spend", "Avg /L", "Recurring", "Maintenance", "Billed", "Collected"]
    mt = Table([mh] + [[i, mon_label(m["month"]), m["litres"], m["water_spend"], m["avg_cost_per_litre"],
                        m["recurring_total"], m["maintenance_total"], m["billable_total"], m["received"]]
                       for i, m in enumerate(data["months"], start=1)], repeatRows=1)
    mt.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
                            ("FONTSIZE", (0, 0), (-1, -1), 7),
                            ("ALIGN", (1, 1), (-1, -1), "RIGHT")]))
    story += [mt]
    doc.build(story)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="annual-{year}.pdf"'})


@api.get("/overview")
async def combined_overview(month: str, user: dict = Depends(admin_user)):
    """Maintenance dues and rent income for one month, side by side."""
    props = await db.properties.find().sort("created_at", 1).to_list(200)
    buildings, m_tot = [], {"billable": 0.0, "collected": 0.0, "fronted": 0.0, "outstanding": 0.0, "owed": 0.0}
    for p in props:
        pid = str(p["_id"])
        period = await db.periods.find_one({"property_id": pid, "month": month})
        if not period:
            continue
        stmt = period.get("snapshot") if period.get("status") == "locked" and period.get("snapshot") \
            else await build_statement(pid, month, ensure=False)
        t = stmt["totals"]
        buildings.append({
            "property_id": pid, "name": p.get("name"), "status": period.get("status", "open"),
            "flats": t["flat_count"], "billable": t["billable_total"], "collected": t["total_received"],
            "fronted": t["total_contributions"], "outstanding": t["total_owes"], "owed": t["total_owed"],
            "water_spend": t["total_water_spend"], "recurring": t["recurring_total"],
            "maintenance": t["maintenance_total"],
        })
        m_tot["billable"] += t["billable_total"]
        m_tot["collected"] += t["total_received"]
        m_tot["fronted"] += t["total_contributions"]
        m_tot["outstanding"] += t["total_owes"]
        m_tot["owed"] += t["total_owed"]

    rent_router_roll = await rentals.rent_roll_for(db, month)
    r = rent_router_roll["totals"]
    return {
        "month": month,
        "maintenance": {"buildings": buildings, "totals": {k: round(v, 2) for k, v in m_tot.items()}},
        "rentals": {"rows": rent_router_roll["rows"], "totals": r,
                    "building_tally": rent_router_roll["building_tally"]},
        "combined": {
            "money_in": round(m_tot["collected"] + r["rent_collected"], 2),
            "money_out": round(r["expenses"], 2),
            "still_to_collect": round(m_tot["outstanding"] + r["pending"], 2),
            "maintenance_outstanding": round(m_tot["outstanding"], 2),
            "rent_pending": round(r["pending"], 2),
            "rent_collected": r["rent_collected"],
            "maintenance_collected": round(m_tot["collected"], 2),
            "deposits_held": r["deposit_held"],
            "paid_on_behalf_of_buildings": r["on_behalf_of_building"],
            "lost_rent_vacancy": r.get("lost_rent", 0),
        },
    }


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
# ---------------------------------------------------------------- MIS excel pack
def build_mis_workbook(stmt, month, tankers, charges, payments, flat_name,
                       owner_label, pay_label, combined):
    """One workbook, one sheet per report: the full month pack."""
    t = stmt["totals"]
    prop = stmt["property"]["name"]
    period = mon_label(month)
    wb = X.new_book()
    flats_pal = X.Palette(X.OWNER_TINTS)   # one colour per flat, shared by all its meters
    payers = X.Palette(X.PAYER_TINTS)

    # --- 1. Water reconciliation -------------------------------------------------
    ws = X.sheet(wb, "Water Reconciliation")
    row = X.title(ws, 1, f"{prop} — Water Reconciliation", span=16,
                  sub=f"{period} · period {stmt['status']} · all amounts in INR")
    head = ["S.No", "Flat No.", "Floor", "Owner", "Metered", "Non-Metered (in storage)",
            "Total Water cost", "Misc", "Total amount", "Bal brought forward",
            "Advance payment paid by", "Amount paid", "Balance to pay / receive",
            "Date of payment", "Paid by", "Status"]
    data, fills = [], []
    for i, r in enumerate(stmt["rows"], start=1):
        data.append([i, r["flat_number"], r.get("floor", "") or "—", r["owner_name"],
                     r["water_own_cost"], r["reserve_share"], r["water_cost"],
                     round(r["recurring_share"] + r["maintenance_share"], 2), r["base_cost"],
                     r["carry_in"], r["contributions"], r["received"], r["net"],
                     dmy(r.get("last_paid_on")), str(r.get("last_paid_by") or "").title() or "—", pay_label(r)])
        fills.append(flats_pal.fill(r["flat_id"], f"Flat {r['flat_number']}"))
    total = ["", "", "", "TOTAL", round(t["total_water_spend"] - t["reserve_value"], 2), t["reserve_value"],
             t["total_water_spend"], round(t["recurring_total"] + t["maintenance_total"], 2),
             t["billable_total"], t["total_carry_in"], t["total_contributions"], t["total_received"],
             t["net_position"], "", "", ""]
    row = X.group_band(ws, row, [(5, 7, "Water Charges")], len(head))
    row, hdr = X.table(ws, row, head, data, money_cols=range(5, 14), signed_cols=(13,),
                       fills=fills, total_row=total,
                       widths=[6, 10, 10, 30, 13, 15, 13, 12, 13, 14, 17, 13, 15, 14, 9, 11])
    X.freeze(ws, f"E{hdr + 1}")
    row = X.legend(ws, row, [
        ("Total expense for the month", float(t["billable_total"])),
        ("Split between (no. of houses)", t["flat_count"]),
        ("Expense per head", round(t["billable_total"] / (t["flat_count"] or 1), 2)),
        ("Total receivable (owes)", float(t["total_owes"])),
        ("Total payable (owed to owners)", float(t["total_owed"])),
        ("Net position", float(t["net_position"])),
    ], label="Summary")

    # --- 2. Water usage as per meters -------------------------------------------
    ws2 = X.sheet(wb, "Water Usage (Meters)")
    row = X.title(ws2, 1, f"{prop} — Water Usage Charges (as per meter readings)", span=10, sub=period)
    mhead = ["S.No", "House", "Floor", "Owner", "Meter number", "Starting unit", "Ending unit",
             "Consumed units", "Water charges", "Total Amount"]
    mdata, mfills = [], []
    for i, m in enumerate(stmt["meters"], start=1):
        mdata.append([i, m.get("flat_number", ""), m.get("floor", "") or "—", m.get("owner_name", ""),
                      m.get("label", ""), m.get("opening"), m.get("closing"), m.get("consumption"),
                      m.get("charge"), combined.get(m.get("flat_id"), "")])
        mfills.append(flats_pal.fill(m.get("flat_id"), f"Flat {m.get('flat_number')}"))
    mtotal = ["", "", "", "", "TOTAL", "", "", t["total_consumed"], t["metered_charges"], ""]
    row, hdr = X.table(ws2, row, mhead, mdata, money_cols=(9, 10), fills=mfills, total_row=mtotal,
                       widths=[6, 10, 10, 28, 18, 14, 14, 15, 14, 18])
    X.freeze(ws2, f"E{hdr + 1}")
    row = X.legend(ws2, row, [
        ("Total lorries this month", t["tanker_count"]),
        ("Total water received (L)", float(t["total_litres"])),
        ("Total water cost (lorry + tips)", float(t["total_water_spend"])),
        ("Cost per litre of water", float(t["avg_cost_per_litre"])),
        ("Total units consumed (as per meter)", float(t["total_consumed"])),
        ("Total water charges (metered)", float(t["metered_charges"])),
        ("Total non-metered consumption (L)", float(t["reserve_litres"])),
        ("Total non-metered cost", float(t["reserve_value"])),
        (f"Non-metered cost split between {t['flat_count']} houses — per house share", float(t["reserve_share"])),
    ], label="Water legend")

    # --- 3. Tanker purchases -----------------------------------------------------
    ws3 = X.sheet(wb, "Tanker Purchases")
    row = X.title(ws3, 1, f"{prop} — Water Purchases", span=13, sub=period)
    thead = ["S.No", "Booking date", "Delivery date", "Supplier", "Sump (L)", "Syntex (L)", "Total (L)",
             "Lorry amount", "Tips", "Total cost", "Cost / L", "Lorry paid by", "Tips paid by"]
    tdata, tfills = [], []
    tanker_payers = set()
    for i, tk in enumerate(tankers, start=1):
        litres = float(tk.get("qty_sump", 0) or 0) + float(tk.get("qty_syntex", 0) or 0)
        tips = float(tk.get("tips_amount", 0) or 0)
        cost = float(tk.get("amount", 0) or 0) + tips
        payer = flat_name.get(tk.get("payer_flat_id"), "—")
        tips_payer = flat_name.get(tk.get("tips_payer_flat_id") or tk.get("payer_flat_id"), "—") if tips else "—"
        tdata.append([i, dmy(tk.get("booking_date")), dmy(tk.get("date")), tk.get("supplier", ""),
                      float(tk.get("qty_sump", 0) or 0),
                      float(tk.get("qty_syntex", 0) or 0), litres, float(tk.get("amount", 0) or 0), tips, cost,
                      round(cost / litres, 4) if litres else 0,
                      f"{payer} ({tk.get('payer_type', '')})",
                      f"{tips_payer} ({tk.get('tips_payer_type') or tk.get('payer_type', '')})" if tips else "—"])
        tfills.append(payers.fill(tk.get("payer_flat_id"), f"Flat {payer}"))
        tanker_payers.add(tk.get("payer_flat_id"))
    ttotal = ["", "", "", "TOTAL", "", "", float(t["total_litres"]),
              round(t["total_water_spend"] - t["total_tips"], 2), float(t["total_tips"]),
              float(t["total_water_spend"]), float(t["avg_cost_per_litre"]), "", ""]
    row, hdr = X.table(ws3, row, thead, tdata, money_cols=(8, 9, 10, 11), fills=tfills, total_row=ttotal,
                       widths=[6, 13, 13, 20, 11, 11, 11, 13, 10, 12, 10, 22, 22])
    X.freeze(ws3, f"D{hdr + 1}")
    row = X.legend(ws3, row, [
        ("Total expense", float(t["total_water_spend"])),
        ("Split between (no. of houses)", t["flat_count"]),
        ("Expense per head", round(t["total_water_spend"] / (t["flat_count"] or 1), 2)),
    ], label="Summary")

    # --- 4. Charges --------------------------------------------------------------
    ws4 = X.sheet(wb, "Charges")
    row = X.title(ws4, 1, f"{prop} — Recurring & One-time Charges", span=8, sub=period)
    chead = ["S.No", "Bucket", "Type", "Description", "Person", "Amount", "Fronted by", "As", "Date"]
    charge_payers = set()
    for bucket, kinds in (("Recurring", RECURRING_TYPES), ("One-time / repairs", ADHOC_TYPES)):
        subset = [c for c in charges if c.get("charge_type") in kinds]
        row = X.section(ws4, row, f"{bucket} — {len(subset)} entr{'y' if len(subset) == 1 else 'ies'}", span=9)
        cdata, cfills = [], []
        for i, c in enumerate(subset, start=1):
            payer = flat_name.get(c.get("payer_flat_id"), "—")
            cdata.append([i, bucket, c.get("charge_type", ""), c.get("description", ""), c.get("person_name", ""),
                          float(c.get("amount", 0) or 0), payer, c.get("payer_type", ""), dmy(c.get("date"))])
            cfills.append(payers.fill(c.get("payer_flat_id"), f"Flat {payer}"))
            charge_payers.add(c.get("payer_flat_id"))
        subtotal = round(sum(float(c.get("amount", 0) or 0) for c in subset), 2)
        ctotal = ["", "", "TOTAL", "", "", subtotal, "",
                  f"Per head {round(subtotal / (t['flat_count'] or 1), 2)}", ""]
        row, chdr = X.table(ws4, row, chead, cdata, money_cols=(6,), fills=cfills, total_row=ctotal,
                            widths=[6, 18, 16, 30, 18, 12, 14, 10, 12])
        if bucket == "Recurring":
            X.freeze(ws4, f"D{chdr + 1}")

    # --- 5. Ledger ---------------------------------------------------------------
    ws5 = X.sheet(wb, "Ledger")
    row = X.title(ws5, 1, f"{prop} — Payments & Payouts Ledger", span=7, sub=period)
    lhead = ["S.No", "Date", "Flat No.", "Owner", "Direction", "Paid by", "Amount", "Notes"]
    ldata, lfills = [], []
    owner_of = {r["flat_id"]: r["owner_name"] for r in stmt["rows"]}
    for i, p in enumerate(payments, start=1):
        ldata.append([i, dmy(p.get("date")), flat_name.get(p.get("flat_id"), "—"),
                      owner_of.get(p.get("flat_id"), ""),
                      "Received" if p.get("direction") != "payout" else "Payout",
                      str(p.get("payer_type", "")).title(), float(p.get("amount", 0) or 0), p.get("notes", "")])
        lfills.append(flats_pal.fill(p.get("flat_id"), f"Flat {flat_name.get(p.get('flat_id'), '—')}"))
    ltotal = ["", "", "", "TOTAL", "", "", float(t["total_received"]), f"Payouts {t['total_payouts']}"]
    row, hdr = X.table(ws5, row, lhead, ldata, money_cols=(7,), fills=lfills, total_row=ltotal,
                       widths=[6, 12, 10, 26, 12, 12, 13, 34])
    X.freeze(ws5, f"C{hdr + 1}")

    return X.to_bytes(wb)


@api.get("/reports/pack")
async def report_pack(property_id: str, month: str, report: str = Query("all"),
                      format: str = Query("pdf"), user: dict = Depends(admin_user)):
    """Month-end owner pack: colour-coded PDF, WhatsApp image, or a zip of every report."""
    valid_format(format, ("pdf", "png", "zip"))
    wanted = [r.strip() for r in report.split(",") if r.strip()]
    if wanted != ["all"] and any(r not in R.REPORTS for r in wanted):
        raise HTTPException(status_code=400,
                            detail=f"Unknown report. Use 'all' or any of: {', '.join(R.REPORTS)}")
    stmt = await build_statement(property_id, month, ensure=False)
    tankers = [ser(d) for d in await db.tankers.find({"property_id": property_id, "month": month})
               .sort("date", 1).to_list(500)]
    flats = [ser(d) for d in await db.flats.find({"property_id": property_id}).to_list(500)]
    flat_name = {f["id"]: f["number"] for f in flats}
    label = mon_label(month)
    slug = f"{stmt['property']['name'].replace(' ', '-').lower()}-{month}"

    if format == "zip":
        files = []
        for r in (R.REPORTS if wanted == ["all"] else wanted):
            pdf = R.build_pdf(stmt, label, tankers, flat_name, dmy, which=(r,), cover=False).read()
            files.append((f"{r}-{slug}.pdf", pdf))
            files.append((f"{r}-{slug}.png", R.pdf_to_png(pdf).read()))
        combined = R.build_pdf(stmt, label, tankers, flat_name, dmy, which=("all",)).read()
        files.append((f"month-end-pack-{slug}.pdf", combined))
        return StreamingResponse(R.build_zip(files), media_type="application/zip",
                                 headers={"Content-Disposition": f'attachment; filename="societyhub-pack-{slug}.zip"'})

    pdf = R.build_pdf(stmt, label, tankers, flat_name, dmy, which=tuple(wanted)).read()
    name = ("month-end-pack" if wanted == ["all"] else wanted[0]) + f"-{slug}"
    if format == "png":
        return StreamingResponse(R.pdf_to_png(pdf), media_type="image/png",
                                 headers={"Content-Disposition": f'attachment; filename="{name}.png"'})
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})


@api.get("/mis/export")
async def mis_export(property_id: str, month: str, format: str = Query("csv"),
                     user: dict = Depends(admin_user)):
    valid_format(format)
    stmt = await build_statement(property_id, month, ensure=False)
    t = stmt["totals"]

    def owner_label(r):
        return f"{r['owner_name']} ({r['tenant_name']} — tenant)" if r.get("tenant_name") else r["owner_name"]

    def pay_label(r):
        return E_LABELS.get(r.get("payment_status"), "Pending")

    combined = {}
    for m in stmt["meters"]:
        combined[m.get("flat_id")] = round(combined.get(m.get("flat_id"), 0) + float(m.get("charge") or 0), 2)
    if format == "xlsx":
        flats = [ser(d) for d in await db.flats.find({"property_id": property_id}).sort("number", 1).to_list(500)]
        flat_name = {f["id"]: f["number"] for f in flats}
        tankers = [ser(d) for d in await db.tankers.find({"property_id": property_id, "month": month}).sort("date", 1).to_list(500)]
        charges = [ser(d) for d in await db.charges.find({"property_id": property_id, "month": month}).sort("date", 1).to_list(1000)]
        payments = [ser(d) for d in await db.payments.find({"property_id": property_id, "month": month}).sort("date", 1).to_list(1000)]
        book = build_mis_workbook(stmt, month, tankers, charges, payments, flat_name,
                                  owner_label, pay_label, combined)
        name = stmt["property"]["name"].replace(" ", "-").lower()
        return StreamingResponse(book, media_type=X.XLSX_MEDIA,
                                 headers={"Content-Disposition": f'attachment; filename="societyhub-{name}-{month}.xlsx"'})



    if format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([f"SocietyHub MIS — {stmt['property']['name']} — {mon_label(month)}"])
        w.writerow([])
        w.writerow(["Water purchased (L)", t["total_litres"], "Water spend (lorry+tips)", t["total_water_spend"],
                    "Avg cost/L", t["avg_cost_per_litre"], "of which tips", t["total_tips"]])
        w.writerow(["Consumed (L)", t["total_consumed"], "Reserve (L)", t["reserve_litres"],
                    "Reserve value", t["reserve_value"]])
        w.writerow(["Recurring total", t["recurring_total"], "Maintenance total", t["maintenance_total"]])
        w.writerow([])
        w.writerow(["Water reconciliation — owner statement"])
        w.writerow(["", "", "", "", "Water Charges", "Water Charges", "Water Charges", "", "", "", "", "", "", "", "", ""])
        w.writerow(["S.No", "Flat No.", "Floor", "Owner", "Metered", "Non-Metered (in storage)",
                    "Total Water cost", "Misc", "Total amount", "Bal brought forward",
                    "Advance payment paid by", "Amount paid", "Balance to pay / receive",
                    "Date of payment", "Paid by", "Status"])
        for i, r in enumerate(stmt["rows"], start=1):
            w.writerow([i, r["flat_number"], r.get("floor", ""), owner_label(r),
                        r["water_own_cost"], r["reserve_share"], r["water_cost"],
                        round(r["recurring_share"] + r["maintenance_share"], 2), r["base_cost"],
                        r["carry_in"], r["contributions"], r["received"], r["net"],
                        dmy(r.get("last_paid_on")), str(r.get("last_paid_by") or "").title(), pay_label(r)])
        w.writerow(["", "", "", "TOTAL", round(t["total_water_spend"] - t["reserve_value"], 2), t["reserve_value"],
                    t["total_water_spend"], round(t["recurring_total"] + t["maintenance_total"], 2),
                    t["billable_total"], t["total_carry_in"], t["total_contributions"], t["total_received"],
                    t["net_position"], "", "", ""])
        w.writerow([])
        w.writerow(["Total Expense", t["billable_total"], "Split between", t["flat_count"],
                    "Exp per head", round(t["billable_total"] / (t["flat_count"] or 1), 2)])
        w.writerow([])
        w.writerow(["Water usage charges — as per meter readings"])
        w.writerow(["S.No", "House", "Floor", "Owner", "Meter number", "Starting unit", "Ending unit",
                    "Consumed units", "Water charges", "Total Amount"])
        for i, m in enumerate(stmt["meters"], start=1):
            w.writerow([i, m.get("flat_number", ""), m.get("floor", ""), m.get("owner_name", ""), m.get("label", ""),
                        m.get("opening"), m.get("closing"), m.get("consumption"), m.get("charge"),
                        combined.get(m.get("flat_id"), "")])
        w.writerow(["Total lorries this month", t["tanker_count"], "Total water received (L)", t["total_litres"],
                    "Total water cost", t["total_water_spend"], "Cost per litre", t["avg_cost_per_litre"]])
        w.writerow(["Total units consumed (as per meter)", t["total_consumed"], "Total water charges (metered)",
                    t["metered_charges"], "Total non-metered consumption", t["reserve_litres"],
                    "Total non-metered cost", t["reserve_value"], "Per house share", t["reserve_share"]])
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
             Paragraph(f"Period: {mon_label(month)} &nbsp;&nbsp; Status: {stmt['status']}", styles["Normal"]),
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
    story += [st, Spacer(1, 14), Paragraph("Water reconciliation — owner statement", styles["Heading3"])]

    head = ["S.No", "Flat No.", "Floor", "Owner", "Metered", "Non-Metered\n(in storage)",
            "Total Water\ncost", "Misc", "Total\namount", "Bal brought\nforward",
            "Advance payment\npaid by", "Amount\npaid", "Balance to\npay / receive",
            "Date of\npayment", "Paid\nby", "Status"]
    rows = [[None, None, None, None, "Water Charges", "", "", None, None, None, None, None, None, None, None, None],
            head]
    for i, r in enumerate(stmt["rows"], start=1):
        rows.append([i, r["flat_number"], r.get("floor", "") or "—", owner_label(r),
                     r["water_own_cost"], r["reserve_share"], r["water_cost"],
                     round(r["recurring_share"] + r["maintenance_share"], 2), r["base_cost"],
                     r["carry_in"], r["contributions"], r["received"], r["net"],
                     dmy(r.get("last_paid_on")), str(r.get("last_paid_by") or "").title() or "—", pay_label(r)])
    rows.append(["", "", "", "TOTAL", round(t["total_water_spend"] - t["reserve_value"], 2), t["reserve_value"],
                 t["total_water_spend"], round(t["recurring_total"] + t["maintenance_total"], 2),
                 t["billable_total"], t["total_carry_in"], t["total_contributions"], t["total_received"],
                 t["net_position"], "", "", ""])
    tbl = Table(rows, repeatRows=2)
    style = [("GRID", (0, 1), (-1, -1), 0.4, colors.grey),
             ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#0F172A")),
             ("TEXTCOLOR", (0, 1), (-1, 1), colors.white),
             ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E2E8F0")),
             ("SPAN", (4, 0), (6, 0)),
             ("BACKGROUND", (4, 0), (6, 0), colors.HexColor("#2F5597")),
             ("TEXTCOLOR", (4, 0), (6, 0), colors.white),
             ("ALIGN", (4, 0), (6, 0), "CENTER"),
             ("GRID", (4, 0), (6, 0), 0.4, colors.grey),
             ("FONTSIZE", (0, 0), (-1, -1), 7),
             ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("ALIGN", (4, 2), (-3, -1), "RIGHT")]
    for i, r in enumerate(stmt["rows"], start=2):
        if r["net"] > 0:
            style.append(("TEXTCOLOR", (-3, i), (-1, i), colors.HexColor("#DC2626")))
        elif r["net"] < 0:
            style.append(("TEXTCOLOR", (-3, i), (-1, i), colors.HexColor("#16A34A")))
    tbl.setStyle(TableStyle(style))
    story += [tbl, Spacer(1, 8),
              Paragraph(f"Total Expense: {t['billable_total']} &nbsp;|&nbsp; Split between {t['flat_count']} houses "
                        f"&nbsp;|&nbsp; Exp per head: {round(t['billable_total'] / (t['flat_count'] or 1), 2)}",
                        styles["Normal"]),
              Spacer(1, 16), Paragraph("Water usage charges — as per meter readings", styles["Heading3"])]

    whead = ["S.No", "House", "Floor", "Owner", "Meter number", "Starting unit", "Ending unit",
             "Consumed units", "Water charges", "Total\nAmount"]
    wrows = [whead] + [[i, m.get("flat_number", ""), m.get("floor", "") or "—", m.get("owner_name", ""),
                        m.get("label", ""), m.get("opening"), m.get("closing"), m.get("consumption"),
                        m.get("charge"), combined.get(m.get("flat_id"), "")]
                       for i, m in enumerate(stmt["meters"], start=1)]
    wt = Table(wrows, repeatRows=1, hAlign="LEFT")
    wt.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
                            ("FONTSIZE", (0, 0), (-1, -1), 7),
                            ("ALIGN", (5, 1), (-1, -1), "RIGHT")]))
    legend = Table([["Total lorries this month", t["tanker_count"], "Total water received (L)", t["total_litres"]],
                    ["Total water cost (lorry + tips)", t["total_water_spend"], "Cost per litre", t["avg_cost_per_litre"]],
                    ["Total units consumed (as per meter)", t["total_consumed"], "Total water charges (metered)", t["metered_charges"]],
                    ["Total non-metered consumption (L)", t["reserve_litres"], "Total non-metered cost", t["reserve_value"]],
                    [f"Non-metered cost split between {t['flat_count']} houses — per house share", t["reserve_share"], "", ""]],
                   hAlign="LEFT")
    legend.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                                ("FONTSIZE", (0, 0), (-1, -1), 8),
                                ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke)]))
    story += [wt, Spacer(1, 10), legend, Spacer(1, 12),
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
app.include_router(rentals.make_router(db))

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
