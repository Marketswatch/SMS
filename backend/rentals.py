"""Property management: monthly bill per property, split collections, and payouts to buildings.

Bill to tenant  = rent + maintenance + ad-hoc collectibles - amounts the tenant paid on my behalf.
Collections are allocated into buckets (rent / maintenance / ad-hoc) so each field is accounted.
Payouts track what I owe each building/association, with credits for bills I paid for them directly.
"""
import io
import csv
import re
import calendar
from datetime import datetime, timezone, date, timedelta
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Request, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from bson import ObjectId

import auth as A
import xlsx as X

UNIT_KINDS = ["flat", "shop", "house", "office", "other"]
OWNERSHIP = ["own", "managed"]
DEPOSIT_KINDS = ["deposit", "deposit_refund", "deposit_deduction"]
DEFAULT_CATEGORIES = ["Maintenance", "Repair", "Water tanker", "Common electricity", "Painting",
                      "Genset charges", "STP charges", "Property tax", "Other"]
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

_statement_builder = None


async def rent_roll_for(db, month: str) -> dict:
    """Back-compat shim used by the combined overview."""
    if _statement_builder is None:
        raise RuntimeError("rentals router not initialised")
    return await _statement_builder(month)


MODE_LABELS = {"cash": "Cash", "upi": "UPI", "bank": "Bank Transfer"}


def dmy(d) -> str:
    """DD-MM-YYYY for every date shown in an export or receipt."""
    s = str(d or "")[:10]
    parts = s.split("-")
    return f"{parts[2]}-{parts[1]}-{parts[0]}" if len(parts) == 3 else (s or "—")


def month_name(m: str) -> str:
    parts = str(m or "").split("-")
    if len(parts) < 2:
        return str(m or "")
    try:
        return f"{calendar.month_name[int(parts[1])]} {parts[0]}"
    except (ValueError, IndexError):
        return str(m)


def r2(x):
    return round(float(x or 0), 2)


def valid_month(month: str) -> str:
    if not month or not MONTH_RE.match(month):
        raise HTTPException(status_code=400, detail="month must be in YYYY-MM format")
    return month


def month_bounds(month: str):
    valid_month(month)
    y, m = (int(v) for v in month.split("-"))
    return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])


def add_months(d: date, months: int) -> date:
    total = d.month - 1 + months
    y, m = d.year + total // 12, total % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


class UnitIn(BaseModel):
    name: str
    kind: str = "flat"
    address: str = ""
    ownership: str = "own"
    owner_name: str = ""
    building_property_id: Optional[str] = None
    building_name: str = ""
    rent_amount: float = 0
    maintenance_amount: float = 0
    deposit_amount: float = 0
    rent_due_day: int = 5
    tenant_name: str = ""
    tenant_phone: str = ""
    lease_start: str = ""
    lease_months: int = 0
    lease_end: str = ""
    vacant_since: str = ""
    status: str = "active"
    notes: str = ""


class BillItem(BaseModel):
    category: str = "Other"
    note: str = ""
    amount: float = 0
    direction: str = "collect"          # collect | tenant_paid
    pay_to_building: bool = False       # counts toward / credits my building payable


class BillIn(BaseModel):
    unit_id: str
    month: str
    rent: float = 0
    maintenance: float = 0
    maintenance_payable: Optional[float] = None   # to the building; defaults to `maintenance`
    carry_forward: float = 0                      # previous month's dues (+) or advance (-)
    items: List[BillItem] = []
    notes: str = ""


class PaymentIn(BaseModel):
    unit_id: str
    month: str
    date: str
    rent_paid: float = 0
    maintenance_paid: float = 0
    adhoc_paid: float = 0
    mode: str = "upi"
    reference: str = ""
    notes: str = ""


class DepositIn(BaseModel):
    unit_id: str
    month: str
    kind: str = "deposit"
    amount: float
    date: str
    mode: str = "bank"
    notes: str = ""


class PayoutIn(BaseModel):
    building_property_id: Optional[str] = None
    building_name: str = ""
    unit_id: Optional[str] = None
    month: str
    amount: float
    date: str
    category: str = "Maintenance"
    note: str = ""
    mode: str = "bank"
    reference: str = ""
    is_credit: bool = False     # a bill I paid for the building -> credited against my payable
    media: List[Dict[str, Any]] = []


class CategoryIn(BaseModel):
    name: str


def require_reference(mode: str, reference: str):
    """Anything other than cash must carry a reference number."""
    if str(mode).lower() != "cash" and not str(reference or "").strip():
        raise HTTPException(status_code=400,
                            detail=f"A reference number is required for {mode or 'non-cash'} payments")


def build_rentals_workbook(data, month, pays, outs, deps, unit_name):
    """Property month pack: one styled sheet per report, tinted per property."""
    t = data["totals"]
    period = month_name(month)
    wb = X.new_book()
    props = X.Palette(X.OWNER_TINTS)

    ws = X.sheet(wb, "Rent Roll")
    row = X.title(ws, 1, "Property Management — Rent Roll", span=17,
                  sub=f"{period} · all amounts in INR")
    head = ["S.No", "Property", "Building", "Tenant", "Rent", "Maintenance", "Ad-hoc to collect",
            "Paid by tenant for me", "Previous dues", "Total to collect", "Rent received",
            "Maintenance received", "Ad-hoc received", "Total received", "Balance", "Status", "Deposit held"]
    rows, fills = [], []
    for i, r in enumerate(data["rows"], start=1):
        rows.append([i, r["name"], r["building"], r["tenant_name"], r["billed_rent"], r["billed_maintenance"],
                     r["adhoc_collect"], r["tenant_paid_on_my_behalf"], r.get("carry_forward", 0),
                     r["total_to_collect"], r["rent_paid"], r["maintenance_paid"], r["adhoc_paid"],
                     r["collected"], r["balance"], str(r["status"]).title(), r["deposit_held"]])
        fills.append(props.fill(r["name"]))
    total = ["", "TOTAL", "", "", "", "", "", "", "", t["total_to_collect"], "", "", "",
             t["collected"], t["balance"], "", t["deposit_held"]]
    row, hdr = X.table(ws, row, head, rows, money_cols=range(5, 16), signed_cols=(15,),
                       fills=fills, total_row=total,
                       widths=[6, 24, 20, 20, 11, 13, 14, 16, 13, 14, 13, 15, 14, 13, 12, 11, 13])
    X.freeze(ws, f"C{hdr + 1}")
    row = X.legend(ws, row, [
        ("Properties", t["unit_count"]), ("Occupied", t["occupied"]), ("Vacant", t["vacant"]),
        ("To collect", float(t["total_to_collect"])), ("Collected", float(t["collected"])),
        ("Balance outstanding", float(t["balance"])), ("Deposits held", float(t["deposit_held"])),
        ("Rent forgone on vacancy", float(t["lost_rent"])),
    ], label="Summary")
    row = X.colour_key(ws, row, props, "Colour key — property")

    ws2 = X.sheet(wb, "Collections")
    row = X.title(ws2, 1, "Collections from tenants", span=9, sub=period)
    chead = ["S.No", "Date", "Property", "Rent", "Maintenance", "Ad-hoc", "Total", "Mode", "Reference", "Notes"]
    crows, cfills = [], []
    for i, p in enumerate(pays, start=1):
        name = unit_name.get(p.get("unit_id"), "—")
        tot = r2(float(p.get("rent_paid", 0) or 0) + float(p.get("maintenance_paid", 0) or 0)
                 + float(p.get("adhoc_paid", 0) or 0))
        crows.append([i, dmy(p.get("date")), name, float(p.get("rent_paid", 0) or 0),
                      float(p.get("maintenance_paid", 0) or 0), float(p.get("adhoc_paid", 0) or 0), tot,
                      MODE_LABELS.get(str(p.get("mode", "")).lower(), p.get("mode", "")),
                      p.get("reference", "") or "—", p.get("notes", "")])
        cfills.append(props.fill(name))
    row, hdr = X.table(ws2, row, chead, crows, money_cols=(4, 5, 6, 7), fills=cfills,
                       total_row=["", "", "TOTAL", "", "", "", float(t["collected"]), "", "", ""],
                       widths=[6, 12, 24, 12, 14, 12, 12, 15, 20, 28])
    X.freeze(ws2, f"D{hdr + 1}")

    ws3 = X.sheet(wb, "Payouts")
    row = X.title(ws3, 1, "Payouts to buildings / associations", span=9, sub=period)
    phead = ["S.No", "Date", "Building", "Property", "Category", "Amount", "Mode", "Reference", "Type", "Note"]
    prows, pfills = [], []
    for i, p in enumerate(outs, start=1):
        name = unit_name.get(p.get("unit_id"), "—")
        prows.append([i, dmy(p.get("date")), p.get("building_name", ""), name, p.get("category", ""),
                      float(p.get("amount", 0) or 0),
                      "—" if p.get("is_credit") else MODE_LABELS.get(str(p.get("mode", "")).lower(), p.get("mode", "")),
                      p.get("reference", "") or "—", "Credit" if p.get("is_credit") else "Paid out",
                      p.get("note", "")])
        pfills.append(props.fill(name))
    ptotal = ["", "", "TOTAL", "", "", float(t["building_paid"]), "", "",
              f"Credits {t['building_credits']}", f"Balance {t['building_balance']}"]
    row, hdr = X.table(ws3, row, phead, prows, money_cols=(6,), fills=pfills, total_row=ptotal,
                       widths=[6, 12, 22, 22, 20, 12, 15, 20, 12, 26])
    X.freeze(ws3, f"D{hdr + 1}")

    ws4 = X.sheet(wb, "Building Settlement")
    row = X.title(ws4, 1, "Owed to buildings / associations", span=6, sub=period)
    bhead = ["S.No", "Building / association", "Payable", "Paid", "Credits", "Balance"]
    brows = [[i, b["building"], b["payable"], b["paid"], b["credits"], b["balance"]]
             for i, b in enumerate(data["buildings"], start=1)]
    btotal = ["", "TOTAL", float(t["building_payable"]), float(t["building_paid"]),
              float(t["building_credits"]), float(t["building_balance"])]
    X.table(ws4, row, bhead, brows, money_cols=(3, 4, 5, 6), signed_cols=(6,), total_row=btotal,
            widths=[6, 30, 14, 14, 14, 14])

    ws5 = X.sheet(wb, "Deposits")
    row = X.title(ws5, 1, "Deposits ledger", span=6, sub=period)
    dhead = ["S.No", "Date", "Property", "Type", "Amount", "Notes"]
    drows, dfills = [], []
    for i, d in enumerate(deps, start=1):
        name = unit_name.get(d.get("unit_id"), "—")
        drows.append([i, dmy(d.get("date")), name, str(d.get("kind", "")).replace("_", " ").title(),
                      float(d.get("amount", 0) or 0), d.get("notes", "")])
        dfills.append(props.fill(name))
    X.table(ws5, row, dhead, drows, money_cols=(5,), fills=dfills,
            total_row=["", "", "TOTAL", "", float(t["deposit_held"]), "held across all properties"],
            widths=[6, 12, 24, 18, 13, 30])

    return X.to_bytes(wb)


def make_router(db):
    router = APIRouter(prefix="/api/rentals")

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

    async def admin_user(request: Request) -> dict:
        user = await A.resolve_user(request, db)
        if user.get("role") not in {"super_admin", "admin"}:
            raise HTTPException(status_code=403, detail="Admin access required")
        return user

    async def require_unit(unit_id: str) -> dict:
        u = await db.rental_units.find_one({"_id": oid(unit_id)})
        if not u:
            raise HTTPException(status_code=404, detail="Property not found")
        return u

    # ------------------------------------------------------- category master
    @router.get("/categories")
    async def list_categories(user: dict = Depends(admin_user)):
        await db.rental_categories.create_index("name", unique=True)
        for n in DEFAULT_CATEGORIES:
            await db.rental_categories.update_one({"name": n},
                                                  {"$setOnInsert": {"name": n, "created_at": datetime.now(timezone.utc)}},
                                                  upsert=True)
        docs = await db.rental_categories.find().sort("name", 1).to_list(300)
        return [ser(d) for d in docs]

    @router.post("/categories")
    async def create_category(body: CategoryIn, user: dict = Depends(admin_user)):
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Category name required")
        existing = await db.rental_categories.find_one({"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}})
        if existing:
            return ser(existing)
        res = await db.rental_categories.insert_one({"name": name, "created_at": datetime.now(timezone.utc)})
        return ser(await db.rental_categories.find_one({"_id": res.inserted_id}))

    @router.delete("/categories/{cid}")
    async def delete_category(cid: str, user: dict = Depends(admin_user)):
        await db.rental_categories.delete_one({"_id": oid(cid)})
        return {"ok": True}

    # ---------------------------------------------------------------- units
    def normalise_unit(doc: dict) -> dict:
        if doc.get("lease_start") and doc.get("lease_months"):
            try:
                start = date.fromisoformat(doc["lease_start"])
                doc["lease_end"] = str(add_months(start, int(doc["lease_months"])) - timedelta(days=1))
            except (ValueError, TypeError):
                pass
        return doc

    @router.post("/units")
    async def create_unit(body: UnitIn, user: dict = Depends(admin_user)):
        if body.kind not in UNIT_KINDS:
            raise HTTPException(status_code=400, detail="Unknown unit type")
        if body.ownership not in OWNERSHIP:
            raise HTTPException(status_code=400, detail="Ownership must be 'own' or 'managed'")
        doc = normalise_unit(body.model_dump())
        doc.update({"created_by": user["id"], "created_at": datetime.now(timezone.utc)})
        res = await db.rental_units.insert_one(doc)
        return ser(await db.rental_units.find_one({"_id": res.inserted_id}))

    @router.get("/units")
    async def list_units(user: dict = Depends(admin_user)):
        docs = await db.rental_units.find().sort("name", 1).to_list(500)
        return [ser(d) for d in docs]

    @router.put("/units/{uid}")
    async def update_unit(uid: str, body: UnitIn, user: dict = Depends(admin_user)):
        await require_unit(uid)
        await db.rental_units.update_one({"_id": oid(uid)}, {"$set": normalise_unit(body.model_dump())})
        return ser(await db.rental_units.find_one({"_id": oid(uid)}))

    @router.delete("/units/{uid}")
    async def delete_unit(uid: str, user: dict = Depends(admin_user)):
        u = await db.rental_units.find_one({"_id": oid(uid)})
        await db.rental_units.delete_one({"_id": oid(uid)})
        for c in ("rental_bills", "rent_payments", "rental_deposits", "rental_payouts"):
            await db[c].delete_many({"unit_id": uid})
        # drop building payouts left without any remaining property for that building
        if u:
            key = u.get("building_property_id")
            name = (u.get("building_name") or "").strip()
            q = {"building_property_id": key} if key else ({"building_name": name} if name else None)
            if q:
                still = await db.rental_units.find_one(q)
                if not still:
                    await db.rental_payouts.delete_many({**q, "unit_id": None})
        return {"ok": True}

    @router.get("/lease-end")
    async def lease_end(start: str, months: str, user: dict = Depends(admin_user)):
        try:
            d = date.fromisoformat(start)
        except ValueError:
            raise HTTPException(status_code=400, detail="start must be YYYY-MM-DD")
        try:
            n = int(months)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="months must be a whole number")
        if n <= 0:
            raise HTTPException(status_code=400, detail="months must be positive")
        return {"lease_end": str(add_months(d, n) - timedelta(days=1))}

    # ---------------------------------------------------------------- bills
    def bill_totals(bill: dict) -> dict:
        items = bill.get("items") or []
        adhoc_collect = sum(float(i.get("amount", 0)) for i in items if i.get("direction") == "collect")
        tenant_paid = sum(float(i.get("amount", 0)) for i in items if i.get("direction") == "tenant_paid")
        rent = float(bill.get("rent", 0) or 0)
        maint = float(bill.get("maintenance", 0) or 0)
        carry = float(bill.get("carry_forward", 0) or 0)
        return {
            "rent": r2(rent), "maintenance": r2(maint), "carry_forward": r2(carry),
            "adhoc_collect": r2(adhoc_collect), "tenant_paid_on_my_behalf": r2(tenant_paid),
            "total_to_collect": r2(rent + maint + adhoc_collect - tenant_paid + carry),
        }

    def prev_month(month: str) -> str:
        y, m = int(month[:4]), int(month[5:7])
        return f"{y - 1:04d}-12" if m == 1 else f"{y:04d}-{m - 1:02d}"

    def existed_in_month(unit: dict, month: str) -> bool:
        """Was this property already on the books in `month`? Avoids inventing dues for new entries."""
        ls = unit.get("lease_start") or ""
        if ls:
            return ls[:7] <= month
        created = unit.get("created_at")
        return bool(created) and str(created)[:7] <= month

    async def prev_outstanding(unit: dict, month: str) -> float:
        """Last month's billed total minus what was collected. + = dues, - = advance."""
        unit_id = str(unit["_id"])
        pm = prev_month(month)
        bill = await db.rental_bills.find_one({"unit_id": unit_id, "month": pm})
        if bill:
            billed = bill_totals(bill)["total_to_collect"]
        elif unit_state(unit, pm) == "active" and existed_in_month(unit, pm):
            # no bill was saved last month — fall back to the property master
            billed = bill_totals({"rent": unit.get("rent_amount", 0),
                                  "maintenance": unit.get("maintenance_amount", 0)})["total_to_collect"]
        else:
            return 0.0
        pays = await db.rent_payments.find({"unit_id": unit_id, "month": pm}).to_list(500)
        got = sum(float(p.get("rent_paid", 0) or 0) + float(p.get("maintenance_paid", 0) or 0)
                  + float(p.get("adhoc_paid", 0) or 0) for p in pays)
        return r2(billed - got)

    async def get_or_draft_bill(unit: dict, month: str, cache: Optional[dict] = None) -> dict:
        uid = str(unit["_id"])
        bill = cache.get(uid) if cache is not None else await db.rental_bills.find_one({"unit_id": uid, "month": month})
        if bill:
            b = ser(bill)
            b["is_draft"] = False
            return b
        return {"id": None, "is_draft": True, "unit_id": uid, "month": month,
                "rent": r2(unit.get("rent_amount", 0)), "maintenance": r2(unit.get("maintenance_amount", 0)),
                "maintenance_payable": None, "carry_forward": await prev_outstanding(unit, month),
                "items": [], "notes": ""}

    @router.get("/bills")
    async def list_bills(month: str, user: dict = Depends(admin_user)):
        valid_month(month)
        units = await db.rental_units.find().sort("name", 1).to_list(500)
        bill_cache = {b["unit_id"]: b for b in
                      await db.rental_bills.find({"month": month}).to_list(2000)}
        out = []
        for u in units:
            bill = await get_or_draft_bill(u, month, bill_cache)
            out.append({**bill, "unit_name": u.get("name"), "tenant_name": u.get("tenant_name", ""),
                        "tenant_phone": u.get("tenant_phone", ""),
                        "building_name": u.get("building_name") or "",
                        "totals": bill_totals(bill)})
        return out

    @router.put("/bills")
    async def upsert_bill(body: BillIn, user: dict = Depends(admin_user)):
        valid_month(body.month)
        await require_unit(body.unit_id)
        doc = body.model_dump()
        doc["updated_at"] = datetime.now(timezone.utc)
        await db.rental_bills.update_one({"unit_id": body.unit_id, "month": body.month},
                                         {"$set": doc}, upsert=True)
        bill = await db.rental_bills.find_one({"unit_id": body.unit_id, "month": body.month})
        b = ser(bill)
        return {**b, "is_draft": False, "totals": bill_totals(b)}

    @router.delete("/bills/{bid}")
    async def delete_bill(bid: str, user: dict = Depends(admin_user)):
        await db.rental_bills.delete_one({"_id": oid(bid)})
        return {"ok": True}

    # ------------------------------------------------------------- payments
    @router.post("/payments")
    async def create_payment(body: PaymentIn, user: dict = Depends(admin_user)):
        valid_month(body.month)
        require_reference(body.mode, body.reference)
        await require_unit(body.unit_id)
        doc = body.model_dump()
        doc["total"] = r2(body.rent_paid + body.maintenance_paid + body.adhoc_paid)
        doc["created_at"] = datetime.now(timezone.utc)
        res = await db.rent_payments.insert_one(doc)
        return ser(await db.rent_payments.find_one({"_id": res.inserted_id}))

    @router.get("/payments")
    async def list_payments(month: Optional[str] = None, unit_id: Optional[str] = None,
                            user: dict = Depends(admin_user)):
        q = {k: v for k, v in (("month", month), ("unit_id", unit_id)) if v}
        docs = await db.rent_payments.find(q).sort("date", 1).to_list(2000)
        return [ser(d) for d in docs]

    @router.put("/payments/{pid}")
    async def update_payment(pid: str, body: PaymentIn, user: dict = Depends(admin_user)):
        valid_month(body.month)
        require_reference(body.mode, body.reference)
        await require_unit(body.unit_id)
        doc = body.model_dump()
        doc["total"] = r2(body.rent_paid + body.maintenance_paid + body.adhoc_paid)
        await db.rent_payments.update_one({"_id": oid(pid)}, {"$set": doc})
        rec = await db.rent_payments.find_one({"_id": oid(pid)})
        if not rec:
            raise HTTPException(status_code=404, detail="Payment not found")
        return ser(rec)

    @router.delete("/payments/{pid}")
    async def delete_payment(pid: str, user: dict = Depends(admin_user)):
        await db.rent_payments.delete_one({"_id": oid(pid)})
        return {"ok": True}

    # -------------------------------------------------------------- deposits
    @router.post("/deposits")
    async def create_deposit(body: DepositIn, user: dict = Depends(admin_user)):
        if body.kind not in DEPOSIT_KINDS:
            raise HTTPException(status_code=400, detail="Unknown deposit entry type")
        valid_month(body.month)
        await require_unit(body.unit_id)
        doc = body.model_dump()
        doc["created_at"] = datetime.now(timezone.utc)
        res = await db.rental_deposits.insert_one(doc)
        return ser(await db.rental_deposits.find_one({"_id": res.inserted_id}))

    @router.get("/deposits")
    async def list_deposits(unit_id: Optional[str] = None, user: dict = Depends(admin_user)):
        q = {"unit_id": unit_id} if unit_id else {}
        docs = await db.rental_deposits.find(q).sort("date", 1).to_list(2000)
        return [ser(d) for d in docs]

    @router.delete("/deposits/{did}")
    async def delete_deposit(did: str, user: dict = Depends(admin_user)):
        await db.rental_deposits.delete_one({"_id": oid(did)})
        return {"ok": True}

    # --------------------------------------------------------------- payouts
    @router.post("/payouts")
    async def create_payout(body: PayoutIn, user: dict = Depends(admin_user)):
        valid_month(body.month)
        if not body.is_credit:
            require_reference(body.mode, body.reference)
        if body.unit_id:
            await require_unit(body.unit_id)
        doc = body.model_dump()
        doc["created_at"] = datetime.now(timezone.utc)
        res = await db.rental_payouts.insert_one(doc)
        return ser(await db.rental_payouts.find_one({"_id": res.inserted_id}))

    @router.get("/payouts")
    async def list_payouts(month: Optional[str] = None, user: dict = Depends(admin_user)):
        q = {"month": month} if month else {}
        docs = await db.rental_payouts.find(q).sort("date", 1).to_list(2000)
        return [ser(d) for d in docs]

    @router.put("/payouts/{pid}")
    async def update_payout(pid: str, body: PayoutIn, user: dict = Depends(admin_user)):
        valid_month(body.month)
        if not body.is_credit:
            require_reference(body.mode, body.reference)
        if body.unit_id:
            await require_unit(body.unit_id)
        await db.rental_payouts.update_one({"_id": oid(pid)}, {"$set": body.model_dump()})
        rec = await db.rental_payouts.find_one({"_id": oid(pid)})
        if not rec:
            raise HTTPException(status_code=404, detail="Payout not found")
        return ser(rec)

    @router.delete("/payouts/{pid}")
    async def delete_payout(pid: str, user: dict = Depends(admin_user)):
        await db.rental_payouts.delete_one({"_id": oid(pid)})
        return {"ok": True}

    # ------------------------------------------------------------- statement
    def unit_state(u: dict, month: str) -> str:
        first, last = month_bounds(month)
        ls, le = u.get("lease_start") or "", u.get("lease_end") or ""
        if ls and ls > str(last):
            return "upcoming"
        if u.get("status") != "active":
            return "vacant"
        if le and le < str(first):
            return "ended"
        return "active"

    async def build_statement(month: str) -> dict:
        valid_month(month)
        units = await db.rental_units.find().sort("name", 1).to_list(500)
        payments = await db.rent_payments.find({"month": month}).to_list(2000)
        deposits = await db.rental_deposits.find().to_list(3000)
        payouts = await db.rental_payouts.find({"month": month}).to_list(2000)
        bill_cache = {b["unit_id"]: b for b in
                      await db.rental_bills.find({"month": month}).to_list(2000)}
        props = {str(p["_id"]): p.get("name") for p in await db.properties.find().to_list(200)}
        today = date.today().isoformat()
        first, last = month_bounds(month)

        rows, buildings = [], {}
        for u in units:
            uid = str(u["_id"])
            state = unit_state(u, month)
            bill = await get_or_draft_bill(u, month)
            bt = bill_totals(bill)
            if state != "active":
                bt = {**bt, "rent": 0.0, "maintenance": 0.0, "adhoc_collect": 0.0,
                      "tenant_paid_on_my_behalf": 0.0, "total_to_collect": bt["carry_forward"]}

            paid = [p for p in payments if p["unit_id"] == uid]
            rent_paid = sum(float(p.get("rent_paid", 0)) for p in paid)
            maint_paid = sum(float(p.get("maintenance_paid", 0)) for p in paid)
            adhoc_paid = sum(float(p.get("adhoc_paid", 0)) for p in paid)
            collected = rent_paid + maint_paid + adhoc_paid
            balance = bt["total_to_collect"] - collected

            dep_in = sum(float(d["amount"]) for d in deposits if d["unit_id"] == uid and d["kind"] == "deposit")
            dep_out = sum(float(d["amount"]) for d in deposits
                          if d["unit_id"] == uid and d["kind"] in ("deposit_refund", "deposit_deduction"))

            due_day = int(u.get("rent_due_day", 5) or 5)
            due_date = f"{month}-{min(max(due_day, 1), 28):02d}"
            status = ("upcoming" if state == "upcoming" else
                      "vacant" if state in ("vacant", "ended") else
                      "paid" if balance <= 0.005 else
                      "overdue" if due_date < today else "pending")

            vacant_since = u.get("vacant_since") or ""
            vacant_days, lost_rent = 0, 0.0
            if status == "vacant" and vacant_since:
                try:
                    end_ref = min(today, str(last))
                    vacant_days = max((date.fromisoformat(end_ref) - date.fromisoformat(vacant_since)).days, 0)
                    lost_rent = r2(float(u.get("rent_amount", 0) or 0) * vacant_days / 30.44)
                except ValueError:
                    vacant_days, lost_rent = 0, 0.0

            items = bill.get("items") or []
            maint_payable = bill.get("maintenance_payable")
            maint_payable = bt["maintenance"] if maint_payable in (None, "") else r2(maint_payable)
            adhoc_payable = sum(float(i.get("amount", 0)) for i in items
                                if i.get("direction") == "collect" and i.get("pay_to_building"))
            tenant_credit = sum(float(i.get("amount", 0)) for i in items
                                if i.get("direction") == "tenant_paid" and i.get("pay_to_building"))
            if state != "active":
                maint_payable, adhoc_payable, tenant_credit = 0.0, 0.0, 0.0

            bkey = u.get("building_property_id") or (u.get("building_name") or "").strip() or "unassigned"
            bname = props.get(u.get("building_property_id") or "", "") or u.get("building_name") or "Unassigned"
            b = buildings.setdefault(bkey, {"key": bkey, "building": bname, "payable": 0.0,
                                            "paid": 0.0, "credits": 0.0, "units": [], "entries": []})
            b["payable"] = r2(b["payable"] + maint_payable + adhoc_payable)
            b["credits"] = r2(b["credits"] + tenant_credit)
            if tenant_credit:
                b["entries"].append({"kind": "tenant_credit", "label": f"{u.get('name')} — tenant paid on my behalf",
                                     "amount": r2(tenant_credit), "date": ""})
            b["units"].append({"unit_id": uid, "name": u.get("name"),
                               "maintenance_payable": r2(maint_payable), "adhoc_payable": r2(adhoc_payable)})

            rows.append({
                "unit_id": uid, "name": u.get("name"), "kind": u.get("kind"),
                "ownership": u.get("ownership"), "owner_name": u.get("owner_name") or "",
                "building": bname, "building_key": bkey,
                "tenant_name": u.get("tenant_name") or "", "tenant_phone": u.get("tenant_phone") or "",
                "rent_amount": r2(u.get("rent_amount", 0)),
                "billed_rent": bt["rent"], "billed_maintenance": bt["maintenance"],
                "carry_forward": bt["carry_forward"],
                "adhoc_collect": bt["adhoc_collect"], "tenant_paid_on_my_behalf": bt["tenant_paid_on_my_behalf"],
                "total_to_collect": bt["total_to_collect"], "items": items,
                "rent_paid": r2(rent_paid), "maintenance_paid": r2(maint_paid), "adhoc_paid": r2(adhoc_paid),
                "collected": r2(collected), "balance": r2(balance),
                "rent_outstanding": r2(max(bt["rent"] - rent_paid, 0)),
                "maintenance_outstanding": r2(max(bt["maintenance"] - maint_paid, 0)),
                "adhoc_outstanding": r2(bt["adhoc_collect"] + bt["carry_forward"]
                                        - bt["tenant_paid_on_my_behalf"] - adhoc_paid),
                "deposit_held": r2(dep_in - dep_out), "deposit_expected": r2(u.get("deposit_amount", 0)),
                "maintenance_payable_to_building": r2(maint_payable),
                "adhoc_payable_to_building": r2(adhoc_payable),
                "building_credit_by_tenant": r2(tenant_credit),
                "bill_exists": not bill.get("is_draft"), "due_date": due_date, "status": status,
                "lease_start": u.get("lease_start") or "", "lease_end": u.get("lease_end") or "",
                "lease_months": u.get("lease_months") or 0,
                "vacant_since": vacant_since, "vacant_days": vacant_days, "lost_rent": lost_rent,
                # legacy keys kept so the combined overview keeps working
                "rent_due": bt["total_to_collect"], "rent_collected": r2(collected),
                "pending": r2(max(balance, 0)), "advance": r2(max(-balance, 0)),
                "expenses": 0.0, "on_behalf_of_building": r2(tenant_credit),
                "net_to_owner": r2(collected),
            })

        for p in payouts:
            bkey = p.get("building_property_id") or (p.get("building_name") or "").strip() or "unassigned"
            bname = props.get(p.get("building_property_id") or "", "") or p.get("building_name") or "Unassigned"
            b = buildings.setdefault(bkey, {"key": bkey, "building": bname, "payable": 0.0,
                                            "paid": 0.0, "credits": 0.0, "units": [], "entries": []})
            amt = r2(p.get("amount", 0))
            if p.get("is_credit"):
                b["credits"] = r2(b["credits"] + amt)
            else:
                b["paid"] = r2(b["paid"] + amt)
            b["entries"].append({"kind": "credit" if p.get("is_credit") else "payout",
                                 "label": f"{p.get('category', '')}{(' — ' + p['note']) if p.get('note') else ''}",
                                 "amount": amt, "date": p.get("date", "")})

        for b in buildings.values():
            b["balance"] = r2(b["payable"] - b["paid"] - b["credits"])

        active = [r for r in rows if r["status"] not in ("vacant", "upcoming")]
        totals = {
            "unit_count": len(rows),
            "occupied": len(active),
            "vacant": sum(1 for r in rows if r["status"] == "vacant"),
            "upcoming": sum(1 for r in rows if r["status"] == "upcoming"),
            "billed_rent": r2(sum(r["billed_rent"] for r in rows)),
            "billed_maintenance": r2(sum(r["billed_maintenance"] for r in rows)),
            "adhoc_collect": r2(sum(r["adhoc_collect"] for r in rows)),
            "carry_forward": r2(sum(r["carry_forward"] for r in rows)),
            "tenant_paid_on_my_behalf": r2(sum(r["tenant_paid_on_my_behalf"] for r in rows)),
            "total_to_collect": r2(sum(r["total_to_collect"] for r in rows)),
            "rent_paid": r2(sum(r["rent_paid"] for r in rows)),
            "maintenance_paid": r2(sum(r["maintenance_paid"] for r in rows)),
            "adhoc_paid": r2(sum(r["adhoc_paid"] for r in rows)),
            "collected": r2(sum(r["collected"] for r in rows)),
            "balance": r2(sum(r["balance"] for r in rows)),
            "overdue": r2(sum(r["balance"] for r in rows if r["status"] == "overdue")),
            "deposit_held": r2(sum(r["deposit_held"] for r in rows)),
            "building_payable": r2(sum(b["payable"] for b in buildings.values())),
            "building_paid": r2(sum(b["paid"] for b in buildings.values())),
            "building_credits": r2(sum(b["credits"] for b in buildings.values())),
            "building_balance": r2(sum(b["balance"] for b in buildings.values())),
            "vacant_days": sum(r["vacant_days"] for r in rows),
            "lost_rent": r2(sum(r["lost_rent"] for r in rows)),
            "bills_missing": sum(1 for r in rows if not r["bill_exists"] and r["status"] not in ("vacant", "upcoming")),
            # legacy keys for the combined overview
            "rent_due": r2(sum(r["total_to_collect"] for r in rows)),
            "rent_collected": r2(sum(r["collected"] for r in rows)),
            "pending": r2(sum(max(r["balance"], 0) for r in rows)),
            "expenses": r2(sum(b["paid"] for b in buildings.values())),
            "on_behalf_of_building": r2(sum(b["credits"] for b in buildings.values())),
            "net_to_owner": r2(sum(r["collected"] for r in rows)),
        }
        return {"month": month, "rows": rows, "totals": totals,
                "buildings": list(buildings.values()),
                "building_tally": [{"building": b["building"], "amount": b["credits"],
                                    "items": [{"description": e["label"], "category": e["kind"],
                                               "amount": e["amount"], "date": e["date"]}
                                              for e in b["entries"] if e["kind"] != "payout"]}
                                   for b in buildings.values() if b["credits"]]}

    @router.get("/statement")
    async def statement(month: str, user: dict = Depends(admin_user)):
        return await build_statement(month)

    @router.get("/rent-roll")
    async def rent_roll(month: str, user: dict = Depends(admin_user)):
        return await build_statement(month)

    global _statement_builder
    _statement_builder = build_statement

    # ---------------------------------------------------------------- export
    @router.get("/export")
    async def export_statement(month: str, format: str = Query("csv"), user: dict = Depends(admin_user)):
        if format not in ("csv", "pdf", "xlsx"):
            raise HTTPException(status_code=400,
                                detail=f"Unsupported format '{format}'. Use one of: csv, pdf, xlsx")
        data = await build_statement(month)
        t = data["totals"]
        head = ["S.No", "Property", "Building", "Tenant", "Rent", "Maintenance", "Ad-hoc to collect",
                "Paid by tenant for me", "Previous dues", "Total to collect", "Rent received", "Maintenance received",
                "Ad-hoc received", "Total received", "Balance", "Status", "Deposit held"]
        counter = {"n": 0}

        def vals(r):
            counter["n"] += 1
            return [counter["n"], r["name"], r["building"], r["tenant_name"], r["billed_rent"], r["billed_maintenance"],
                    r["adhoc_collect"], r["tenant_paid_on_my_behalf"], r.get("carry_forward", 0),
                    r["total_to_collect"], r["rent_paid"],
                    r["maintenance_paid"], r["adhoc_paid"], r["collected"], r["balance"], r["status"],
                    r["deposit_held"]]

        bhead = ["S.No", "Building", "Payable", "Paid", "Credits", "Balance"]
        bcounter = {"n": 0}

        def bvals(b):
            bcounter["n"] += 1
            return [bcounter["n"], b["building"], b["payable"], b["paid"], b["credits"], b["balance"]]

        if format == "xlsx":
            first, last = month_bounds(month)
            pays = [ser(d) for d in await db.rent_payments.find({"month": month}).sort("date", 1).to_list(1000)]
            outs = [ser(d) for d in await db.rental_payouts.find({"month": month}).sort("date", 1).to_list(1000)]
            deps = [ser(d) for d in await db.rental_deposits.find(
                {"date": {"$gte": first.isoformat(), "$lte": last.isoformat()}}).sort("date", 1).to_list(500)]
            unit_name = {u["id"]: u["name"] for u in [ser(d) for d in await db.rental_units.find().to_list(500)]}
            book = build_rentals_workbook(data, month, pays, outs, deps, unit_name)
            return StreamingResponse(book, media_type=X.XLSX_MEDIA,
                                     headers={"Content-Disposition": f'attachment; filename="societyhub-properties-{month}.xlsx"'})

        if format == "csv":
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow([f"SocietyHub Property Statement — {month_name(month)}"])
            w.writerow([])
            w.writerow(["Properties", t["unit_count"], "Occupied", t["occupied"], "Vacant", t["vacant"]])
            w.writerow(["To collect", t["total_to_collect"], "Collected", t["collected"], "Balance", t["balance"]])
            w.writerow(["Owed to buildings", t["building_payable"], "Paid", t["building_paid"],
                        "Credits", t["building_credits"], "Balance", t["building_balance"]])
            w.writerow([])
            w.writerow(head)
            for r in data["rows"]:
                w.writerow(vals(r))
            w.writerow([])
            w.writerow(bhead)
            for b in data["buildings"]:
                w.writerow(bvals(b))
            out = buf.getvalue().encode("utf-8")
            return StreamingResponse(io.BytesIO(out), media_type="text/csv",
                                     headers={"Content-Disposition": f'attachment; filename="properties-{month}.csv"'})

        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=landscape(A4), title=f"Properties {month}")
        styles = getSampleStyleSheet()
        story = [Paragraph("SocietyHub — Property Statement", styles["Title"]),
                 Paragraph(f"Period: {month_name(month)}", styles["Normal"]), Spacer(1, 10)]
        summary = [["To collect", t["total_to_collect"], "Collected", t["collected"], "Balance", t["balance"]],
                   ["Owed to buildings", t["building_payable"], "Paid", t["building_paid"],
                    "Credits", t["building_credits"]],
                   ["Deposits held", t["deposit_held"], "Vacant", t["vacant"], "Rent forgone", t["lost_rent"]]]
        st = Table(summary, hAlign="LEFT")
        st.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 8)]))
        story += [st, Spacer(1, 14)]
        tbl = Table([head] + [vals(r) for r in data["rows"]], repeatRows=1)
        tbl.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                                 ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                                 ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                                 ("FONTSIZE", (0, 0), (-1, -1), 7),
                                 ("ALIGN", (3, 1), (-1, -1), "RIGHT")]))
        story += [tbl, Spacer(1, 16), Paragraph("Owed to buildings / associations", styles["Heading3"])]
        bt = Table([bhead] + [bvals(b) for b in data["buildings"]], repeatRows=1, hAlign="LEFT")
        bt.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
                                ("FONTSIZE", (0, 0), (-1, -1), 7),
                                ("ALIGN", (1, 1), (-1, -1), "RIGHT")]))
        story += [bt]
        doc.build(story)
        buf.seek(0)
        return StreamingResponse(buf, media_type="application/pdf",
                                 headers={"Content-Disposition": f'attachment; filename="properties-{month}.pdf"'})

    # --------------------------------------------------------------- receipt
    @router.get("/payments/{pid}/receipt")
    async def payment_receipt(pid: str, user: dict = Depends(admin_user)):
        pay = await db.rent_payments.find_one({"_id": oid(pid)})
        if not pay:
            raise HTTPException(status_code=404, detail="Payment not found")
        unit = await require_unit(pay["unit_id"])
        receipt_no = f"RCPT-{pay['month'].replace('-', '')}-{str(pay['_id'])[-6:].upper()}"

        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, title=receipt_no)
        styles = getSampleStyleSheet()
        rows = [["Property", unit.get("name", "")],
                ["Tenant", unit.get("tenant_name", "") or "—"],
                ["For the month of", month_name(pay["month"])],
                ["Date received", dmy(pay.get("date"))],
                ["Mode", MODE_LABELS.get(str(pay.get("mode", "")).lower(), str(pay.get("mode", "")).upper())],
                ["Reference", pay.get("reference") or "—"],
                ["Rent", f"Rs. {r2(pay.get('rent_paid')):,.2f}"],
                ["Maintenance", f"Rs. {r2(pay.get('maintenance_paid')):,.2f}"],
                ["Ad-hoc", f"Rs. {r2(pay.get('adhoc_paid')):,.2f}"],
                ["Total received", f"Rs. {r2(pay.get('total')):,.2f}"]]
        if pay.get("notes"):
            rows.append(["Notes", pay["notes"]])
        tbl = Table(rows, colWidths=[150, 320], hAlign="LEFT")
        tbl.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                                 ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F1F5F9")),
                                 ("FONTSIZE", (0, 0), (-1, -1), 9),
                                 ("TOPPADDING", (0, 0), (-1, -1), 7),
                                 ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
        story = [Paragraph("Payment Receipt", styles["Title"]),
                 Paragraph(f"Receipt no. {receipt_no}", styles["Normal"]), Spacer(1, 16), tbl,
                 Spacer(1, 26), Paragraph("This is a computer-generated receipt.", styles["Normal"]),
                 Spacer(1, 34), Paragraph("_______________________<br/>Authorised signature", styles["Normal"])]
        doc.build(story)
        buf.seek(0)
        return StreamingResponse(buf, media_type="application/pdf",
                                 headers={"Content-Disposition": f'attachment; filename="{receipt_no}.pdf"'})

    return router
