"""Property (rental) management module — units, rent/deposit collection, expenses, rent roll.

Kept fully separate from the maintenance cost-split flow: money collected from tenants here
never mixes with the building's maintenance statement. Expenses an admin pays on behalf of a
building are tagged so they can be tallied against that building separately.
"""
import io
import csv
import re
from datetime import datetime, timezone, date
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Request, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from bson import ObjectId

import auth as A

UNIT_KINDS = ["flat", "shop", "house", "office", "other"]
OWNERSHIP = ["own", "managed"]
EXPENSE_CATEGORIES = ["tax", "repair", "society_maintenance", "utility", "other"]
COLLECTION_KINDS = ["rent", "deposit", "deposit_refund", "deposit_deduction"]


def r2(x):
    return round(float(x or 0), 2)


MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

_build_rent_roll = None


async def rent_roll_for(db, month: str) -> dict:
    """Reuse the rent-roll builder from outside the router (combined overview)."""
    if _build_rent_roll is None:
        raise RuntimeError("rentals router not initialised")
    return await _build_rent_roll(month)


def valid_month(month: str) -> str:
    if not month or not MONTH_RE.match(month):
        raise HTTPException(status_code=400, detail="month must be in YYYY-MM format")
    return month


def month_bounds(month: str):
    valid_month(month)
    y, m = (int(v) for v in month.split("-"))
    start = date(y, m, 1)
    end = date(y + (m == 12), (m % 12) + 1, 1)
    return start, end


class UnitIn(BaseModel):
    name: str
    kind: str = "flat"
    address: str = ""
    ownership: str = "own"
    owner_name: str = ""
    building_property_id: Optional[str] = None
    flat_id: Optional[str] = None
    rent_amount: float = 0
    rent_due_day: int = 5
    deposit_amount: float = 0
    tenant_name: str = ""
    tenant_phone: str = ""
    lease_start: str = ""
    lease_end: str = ""
    vacant_since: str = ""
    status: str = "active"
    notes: str = ""


class CollectionIn(BaseModel):
    unit_id: str
    month: str
    kind: str = "rent"
    amount: float
    date: str
    mode: str = "upi"
    notes: str = ""


class ExpenseIn(BaseModel):
    unit_id: str
    month: str
    category: str = "repair"
    description: str = ""
    amount: float
    date: str
    on_behalf_of_building: bool = False
    building_property_id: Optional[str] = None
    media: List[Dict[str, Any]] = []


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

    # ------------------------------------------------------------------ units
    @router.post("/units")
    async def create_unit(body: UnitIn, user: dict = Depends(admin_user)):
        if body.kind not in UNIT_KINDS:
            raise HTTPException(status_code=400, detail="Unknown unit type")
        if body.ownership not in OWNERSHIP:
            raise HTTPException(status_code=400, detail="Ownership must be 'own' or 'managed'")
        doc = body.model_dump()
        doc.update({"created_by": user["id"], "created_at": datetime.now(timezone.utc)})
        res = await db.rental_units.insert_one(doc)
        doc["_id"] = res.inserted_id
        return ser(doc)

    @router.get("/units")
    async def list_units(user: dict = Depends(admin_user)):
        docs = await db.rental_units.find().sort("name", 1).to_list(500)
        return [ser(d) for d in docs]

    @router.put("/units/{uid}")
    async def update_unit(uid: str, body: UnitIn, user: dict = Depends(admin_user)):
        await db.rental_units.update_one({"_id": oid(uid)}, {"$set": body.model_dump()})
        doc = await db.rental_units.find_one({"_id": oid(uid)})
        if not doc:
            raise HTTPException(status_code=404, detail="Unit not found")
        return ser(doc)

    @router.delete("/units/{uid}")
    async def delete_unit(uid: str, user: dict = Depends(admin_user)):
        await db.rental_units.delete_one({"_id": oid(uid)})
        await db.rent_collections.delete_many({"unit_id": uid})
        await db.rental_expenses.delete_many({"unit_id": uid})
        return {"ok": True}

    async def require_unit(unit_id: str):
        if not await db.rental_units.find_one({"_id": oid(unit_id)}):
            raise HTTPException(status_code=404, detail="Property not found")

    # ------------------------------------------------------------ collections
    @router.post("/collections")
    async def create_collection(body: CollectionIn, user: dict = Depends(admin_user)):
        if body.kind not in COLLECTION_KINDS:
            raise HTTPException(status_code=400, detail="Unknown collection type")
        valid_month(body.month)
        await require_unit(body.unit_id)
        doc = body.model_dump()
        doc["created_at"] = datetime.now(timezone.utc)
        res = await db.rent_collections.insert_one(doc)
        doc["_id"] = res.inserted_id
        return ser(doc)

    @router.get("/collections")
    async def list_collections(month: Optional[str] = None, unit_id: Optional[str] = None,
                               user: dict = Depends(admin_user)):
        q = {}
        if month:
            q["month"] = month
        if unit_id:
            q["unit_id"] = unit_id
        docs = await db.rent_collections.find(q).sort("date", 1).to_list(2000)
        return [ser(d) for d in docs]

    @router.put("/collections/{cid}")
    async def update_collection(cid: str, body: CollectionIn, user: dict = Depends(admin_user)):
        valid_month(body.month)
        await require_unit(body.unit_id)
        await db.rent_collections.update_one({"_id": oid(cid)}, {"$set": body.model_dump()})
        doc = await db.rent_collections.find_one({"_id": oid(cid)})
        if not doc:
            raise HTTPException(status_code=404, detail="Entry not found")
        return ser(doc)

    @router.delete("/collections/{cid}")
    async def delete_collection(cid: str, user: dict = Depends(admin_user)):
        await db.rent_collections.delete_one({"_id": oid(cid)})
        return {"ok": True}

    # --------------------------------------------------------------- expenses
    @router.post("/expenses")
    async def create_expense(body: ExpenseIn, user: dict = Depends(admin_user)):
        if body.category not in EXPENSE_CATEGORIES:
            raise HTTPException(status_code=400, detail="Unknown expense category")
        valid_month(body.month)
        await require_unit(body.unit_id)
        doc = body.model_dump()
        doc["created_at"] = datetime.now(timezone.utc)
        res = await db.rental_expenses.insert_one(doc)
        doc["_id"] = res.inserted_id
        return ser(doc)

    @router.get("/expenses")
    async def list_expenses(month: Optional[str] = None, unit_id: Optional[str] = None,
                            user: dict = Depends(admin_user)):
        q = {}
        if month:
            q["month"] = month
        if unit_id:
            q["unit_id"] = unit_id
        docs = await db.rental_expenses.find(q).sort("date", 1).to_list(2000)
        return [ser(d) for d in docs]

    @router.put("/expenses/{eid}")
    async def update_expense(eid: str, body: ExpenseIn, user: dict = Depends(admin_user)):
        valid_month(body.month)
        await require_unit(body.unit_id)
        await db.rental_expenses.update_one({"_id": oid(eid)}, {"$set": body.model_dump()})
        doc = await db.rental_expenses.find_one({"_id": oid(eid)})
        if not doc:
            raise HTTPException(status_code=404, detail="Expense not found")
        return ser(doc)

    @router.delete("/expenses/{eid}")
    async def delete_expense(eid: str, user: dict = Depends(admin_user)):
        await db.rental_expenses.delete_one({"_id": oid(eid)})
        return {"ok": True}

    # --------------------------------------------------------------- rent roll
    def lease_active(u: dict, month: str) -> bool:
        return unit_state(u, month) == "active"

    def unit_state(u: dict, month: str) -> str:
        """active | upcoming (lease starts later) | ended | vacant"""
        _, nxt = month_bounds(month)
        last_day = str(date.fromordinal(nxt.toordinal() - 1))
        first_day = str(month_bounds(month)[0])
        ls, le = u.get("lease_start") or "", u.get("lease_end") or ""
        if ls and ls > last_day:
            return "upcoming"
        if u.get("status") != "active":
            return "vacant"
        if le and le < first_day:
            return "ended"
        return "active"

    async def build_rent_roll(month: str) -> dict:
        valid_month(month)
        units = await db.rental_units.find().sort("name", 1).to_list(500)
        cols = await db.rent_collections.find({"month": month}).to_list(2000)
        exps = await db.rental_expenses.find({"month": month}).to_list(2000)
        all_cols = await db.rent_collections.find().to_list(5000)
        props = {str(p["_id"]): p.get("name") for p in await db.properties.find().to_list(200)}
        today = date.today().isoformat()

        rows = []
        for u in units:
            uid = str(u["_id"])
            umonth = [c for c in cols if c["unit_id"] == uid]
            uexp = [e for e in exps if e["unit_id"] == uid]
            rent_collected = sum(float(c["amount"]) for c in umonth if c["kind"] == "rent")
            deposit_in = sum(float(c["amount"]) for c in all_cols
                             if c["unit_id"] == uid and c["kind"] == "deposit")
            deposit_out = sum(float(c["amount"]) for c in all_cols
                              if c["unit_id"] == uid and c["kind"] in ("deposit_refund", "deposit_deduction"))
            active = lease_active(u, month)
            state = unit_state(u, month)
            rent_amount = float(u.get("rent_amount", 0) or 0)
            rent_due = rent_amount if active else 0.0
            pending = rent_due - rent_collected
            due_day = int(u.get("rent_due_day", 5) or 5)
            due_date = f"{month}-{min(max(due_day, 1), 28):02d}"
            status = ("upcoming" if state == "upcoming" else
                      "vacant" if state in ("vacant", "ended") else
                      "paid" if pending <= 0 else
                      "overdue" if due_date < today else "pending")
            expense_total = sum(float(e["amount"]) for e in uexp)
            on_behalf = sum(float(e["amount"]) for e in uexp if e.get("on_behalf_of_building"))
            lease_end = u.get("lease_end") or ""
            _, nxt = month_bounds(month)
            window_end = str(date(nxt.year + (nxt.month == 12), (nxt.month % 12) + 1, 1))
            expiring = bool(lease_end) and today <= lease_end < window_end

            vacant_since = u.get("vacant_since") or (lease_end if status == "vacant" else "")
            vacant_days, lost_rent = 0, 0.0
            if status == "vacant" and vacant_since:
                # Scope the idle window to the selected month so past months don't show today's figure.
                month_last = str(date.fromordinal(nxt.toordinal() - 1))
                end_ref = min(today, month_last)
                try:
                    vacant_days = max((date.fromisoformat(end_ref) - date.fromisoformat(vacant_since)).days, 0)
                    lost_rent = r2(rent_amount * vacant_days / 30.44)
                except ValueError:
                    vacant_days, lost_rent = 0, 0.0

            rows.append({
                "unit_id": uid, "name": u.get("name"), "kind": u.get("kind"),
                "ownership": u.get("ownership"), "owner_name": u.get("owner_name") or "",
                "building": props.get(u.get("building_property_id") or "", ""),
                "tenant_name": u.get("tenant_name") or "", "tenant_phone": u.get("tenant_phone") or "",
                "rent_amount": r2(rent_amount),
                "rent_due": r2(rent_due), "rent_collected": r2(rent_collected),
                "pending": r2(max(pending, 0)), "advance": r2(max(-pending, 0)),
                "due_date": due_date, "status": status,
                "deposit_held": r2(deposit_in - deposit_out),
                "deposit_expected": r2(u.get("deposit_amount", 0)),
                "expenses": r2(expense_total), "on_behalf_of_building": r2(on_behalf),
                "net_to_owner": r2(rent_collected - expense_total),
                "lease_start": u.get("lease_start") or "", "lease_end": lease_end,
                "lease_expiring_soon": expiring,
                "vacant_since": vacant_since, "vacant_days": vacant_days, "lost_rent": lost_rent,
            })

        building_tally = {}
        for e in exps:
            if not e.get("on_behalf_of_building"):
                continue
            key = e.get("building_property_id") or "unassigned"
            b = building_tally.setdefault(key, {"building": props.get(key, "Unassigned"), "amount": 0.0, "items": []})
            b["amount"] = r2(b["amount"] + float(e["amount"]))
            b["items"].append({"description": e.get("description"), "category": e.get("category"),
                               "amount": r2(e["amount"]), "date": e.get("date")})

        totals = {
            "unit_count": len(rows),
            "occupied": sum(1 for r in rows if r["status"] not in ("vacant", "upcoming")),
            "vacant": sum(1 for r in rows if r["status"] == "vacant"),
            "upcoming": sum(1 for r in rows if r["status"] == "upcoming"),
            "rent_due": r2(sum(r["rent_due"] for r in rows)),
            "rent_collected": r2(sum(r["rent_collected"] for r in rows)),
            "pending": r2(sum(r["pending"] for r in rows)),
            "overdue": r2(sum(r["pending"] for r in rows if r["status"] == "overdue")),
            "deposit_held": r2(sum(r["deposit_held"] for r in rows)),
            "expenses": r2(sum(r["expenses"] for r in rows)),
            "on_behalf_of_building": r2(sum(r["on_behalf_of_building"] for r in rows)),
            "net_to_owner": r2(sum(r["net_to_owner"] for r in rows)),
            "owned_units": sum(1 for r in rows if r["ownership"] == "own"),
            "managed_units": sum(1 for r in rows if r["ownership"] == "managed"),
            "vacant_days": sum(r["vacant_days"] for r in rows),
            "lost_rent": r2(sum(r["lost_rent"] for r in rows)),
        }
        return {"month": month, "rows": rows, "totals": totals,
                "building_tally": list(building_tally.values())}

    @router.get("/rent-roll")
    async def rent_roll(month: str, user: dict = Depends(admin_user)):
        return await build_rent_roll(month)

    global _build_rent_roll
    _build_rent_roll = build_rent_roll

    @router.get("/export")
    async def export_rent_roll(month: str, format: str = Query("csv"), user: dict = Depends(admin_user)):
        data = await build_rent_roll(month)
        t = data["totals"]
        head = ["Unit", "Type", "Building", "Ownership", "Owner", "Tenant", "Rent due", "Collected",
                "Pending", "Status", "Deposit held", "Expenses", "Of which on behalf of building",
                "Net to owner", "Lease end"]

        def row_vals(r):
            return [r["name"], r["kind"], r["building"], r["ownership"], r["owner_name"], r["tenant_name"],
                    r["rent_due"], r["rent_collected"], r["pending"], r["status"], r["deposit_held"],
                    r["expenses"], r["on_behalf_of_building"], r["net_to_owner"], r["lease_end"]]

        if format == "csv":
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow([f"SocietyHub Rent Roll — {month}"])
            w.writerow([])
            w.writerow(["Units", t["unit_count"], "Occupied", t["occupied"], "Vacant", t["vacant"]])
            w.writerow(["Rent due", t["rent_due"], "Collected", t["rent_collected"],
                        "Pending", t["pending"], "Overdue", t["overdue"]])
            w.writerow(["Deposits held", t["deposit_held"], "Expenses", t["expenses"],
                        "On behalf of buildings", t["on_behalf_of_building"], "Net to owners", t["net_to_owner"]])
            w.writerow(["Vacant units", t["vacant"], "Idle days", t["vacant_days"],
                        "Rent forgone to vacancy", t["lost_rent"]])
            w.writerow([])
            w.writerow(head)
            for r in data["rows"]:
                w.writerow(row_vals(r))
            if data["building_tally"]:
                w.writerow([])
                w.writerow(["Paid on behalf of building", "Amount"])
                for b in data["building_tally"]:
                    w.writerow([b["building"], b["amount"]])
            out = buf.getvalue().encode("utf-8")
            return StreamingResponse(io.BytesIO(out), media_type="text/csv",
                                     headers={"Content-Disposition": f'attachment; filename="rent-roll-{month}.csv"'})

        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=landscape(A4), title=f"Rent roll {month}")
        styles = getSampleStyleSheet()
        story = [Paragraph("SocietyHub — Rent Roll & Owner Payout", styles["Title"]),
                 Paragraph(f"Period: {month}", styles["Normal"]), Spacer(1, 10)]
        summary = [["Units", t["unit_count"], "Occupied", t["occupied"], "Vacant", t["vacant"]],
                   ["Rent due", t["rent_due"], "Collected", t["rent_collected"], "Pending", t["pending"]],
                   ["Deposits held", t["deposit_held"], "Expenses", t["expenses"], "Net to owners", t["net_to_owner"]],
                   ["Vacant units", t["vacant"], "Idle days", t["vacant_days"], "Rent forgone", t["lost_rent"]]]
        st = Table(summary, hAlign="LEFT")
        st.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                                ("FONTSIZE", (0, 0), (-1, -1), 8)]))
        story += [st, Spacer(1, 14)]
        rows = [head] + [row_vals(r) for r in data["rows"]]
        tbl = Table(rows, repeatRows=1)
        style = [("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                 ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                 ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                 ("FONTSIZE", (0, 0), (-1, -1), 7),
                 ("ALIGN", (6, 1), (-1, -1), "RIGHT")]
        for i, r in enumerate(data["rows"], start=1):
            if r["status"] == "overdue":
                style.append(("TEXTCOLOR", (9, i), (9, i), colors.HexColor("#DC2626")))
            elif r["status"] == "paid":
                style.append(("TEXTCOLOR", (9, i), (9, i), colors.HexColor("#16A34A")))
        tbl.setStyle(TableStyle(style))
        story += [tbl]
        if data["building_tally"]:
            story += [Spacer(1, 14), Paragraph("Paid on behalf of buildings (tally separately)", styles["Heading3"])]
            bt = Table([["Building", "Amount"]] + [[b["building"], b["amount"]] for b in data["building_tally"]],
                       hAlign="LEFT")
            bt.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 8)]))
            story += [bt]
        doc.build(story)
        buf.seek(0)
        return StreamingResponse(buf, media_type="application/pdf",
                                 headers={"Content-Disposition": f'attachment; filename="rent-roll-{month}.pdf"'})

    @router.get("/collections/{cid}/receipt")
    async def collection_receipt(cid: str, user: dict = Depends(admin_user)):
        col = await db.rent_collections.find_one({"_id": oid(cid)})
        if not col:
            raise HTTPException(status_code=404, detail="Entry not found")
        unit = await db.rental_units.find_one({"_id": oid(col["unit_id"])})
        if not unit:
            raise HTTPException(status_code=404, detail="Property not found")
        receipt_no = f"RCPT-{col['month'].replace('-', '')}-{str(col['_id'])[-6:].upper()}"

        cols = await db.rent_collections.find({"unit_id": col["unit_id"], "month": col["month"],
                                               "kind": "rent"}).to_list(500)
        paid_this_month = r2(sum(float(c["amount"]) for c in cols))
        rent = float(unit.get("rent_amount", 0) or 0)
        balance = r2(rent - paid_this_month) if col["kind"] == "rent" else 0.0

        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

        labels = {"rent": "Rent Receipt", "deposit": "Security Deposit Receipt",
                  "deposit_refund": "Deposit Refund Voucher", "deposit_deduction": "Deposit Deduction Note"}
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, title=receipt_no)
        styles = getSampleStyleSheet()
        story = [Paragraph(labels.get(col["kind"], "Receipt"), styles["Title"]),
                 Paragraph(f"Receipt no. {receipt_no}", styles["Normal"]), Spacer(1, 16)]
        detail = [["Property", unit.get("name", "")],
                  ["Address", unit.get("address", "") or "—"],
                  ["Tenant", unit.get("tenant_name", "") or "—"],
                  ["Received by", "Self (owner)" if unit.get("ownership") == "own"
                   else f"{user.get('name')} on behalf of {unit.get('owner_name') or 'owner'}"],
                  ["For the month of", col["month"]],
                  ["Date received", col.get("date", "")],
                  ["Payment mode", str(col.get("mode", "")).upper()],
                  ["Amount", f"Rs. {r2(col['amount']):,.2f}"]]
        if col["kind"] == "rent":
            detail += [["Monthly rent", f"Rs. {rent:,.2f}"],
                       ["Total paid this month", f"Rs. {paid_this_month:,.2f}"],
                       ["Balance", "Nil" if balance <= 0 else f"Rs. {balance:,.2f}"]]
        if col.get("notes"):
            detail.append(["Notes", col["notes"]])
        tbl = Table(detail, colWidths=[150, 320], hAlign="LEFT")
        tbl.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                                 ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F1F5F9")),
                                 ("FONTSIZE", (0, 0), (-1, -1), 9),
                                 ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                 ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                                 ("TOPPADDING", (0, 0), (-1, -1), 7)]))
        story += [tbl, Spacer(1, 26),
                  Paragraph("This is a computer-generated receipt for the amount stated above.", styles["Normal"]),
                  Spacer(1, 34), Paragraph("_______________________<br/>Authorised signature", styles["Normal"])]
        doc.build(story)
        buf.seek(0)
        return StreamingResponse(buf, media_type="application/pdf",
                                 headers={"Content-Disposition": f'attachment; filename="{receipt_no}.pdf"'})

    @router.post("/demo/seed")
    async def seed_rentals(user: dict = Depends(admin_user)):
        if await db.rental_units.find_one({}):
            return {"ok": True, "already": True,
                    "note": "Sample data skipped — real properties already exist."}
        prop = await db.properties.find_one({"name": "Sunrise Residency"})
        pid = str(prop["_id"]) if prop else None
        month = date.today().strftime("%Y-%m")
        specs = [
            {"name": "Sunrise 101 (own)", "kind": "flat", "ownership": "own", "owner_name": "Self",
             "building_property_id": pid, "rent_amount": 18000, "deposit_amount": 100000,
             "tenant_name": "Arjun Rao", "tenant_phone": "9876511101", "rent_due_day": 5,
             "lease_start": "2026-01-01", "lease_end": "2026-12-31"},
            {"name": "MG Road Shop", "kind": "shop", "ownership": "own", "owner_name": "Self",
             "address": "MG Road, Bengaluru", "rent_amount": 42000, "deposit_amount": 250000,
             "tenant_name": "Cafe Verde", "tenant_phone": "9876511102", "rent_due_day": 1,
             "lease_start": "2025-06-01", "lease_end": "2027-05-31"},
            {"name": "Whitefield House", "kind": "house", "ownership": "managed",
             "owner_name": "Suresh Iyer (friend)", "address": "Whitefield, Bengaluru",
             "rent_amount": 26000, "deposit_amount": 150000, "tenant_name": "Neha Gupta",
             "tenant_phone": "9876511103", "rent_due_day": 10,
             "lease_start": "2026-03-01", "lease_end": "2026-09-30"},
        ]
        ids = []
        for s in specs:
            doc = UnitIn(**s).model_dump()
            doc.update({"created_by": user["id"], "created_at": datetime.now(timezone.utc)})
            res = await db.rental_units.insert_one(doc)
            ids.append(str(res.inserted_id))

        await db.rent_collections.insert_many([
            {"unit_id": ids[0], "month": month, "kind": "rent", "amount": 18000,
             "date": f"{month}-04", "mode": "upi", "notes": "", "created_at": datetime.now(timezone.utc)},
            {"unit_id": ids[0], "month": month, "kind": "deposit", "amount": 100000,
             "date": "2026-01-01", "mode": "bank", "notes": "Lease start", "created_at": datetime.now(timezone.utc)},
            {"unit_id": ids[1], "month": month, "kind": "rent", "amount": 20000,
             "date": f"{month}-02", "mode": "bank", "notes": "Part payment", "created_at": datetime.now(timezone.utc)},
            {"unit_id": ids[2], "month": month, "kind": "deposit", "amount": 150000,
             "date": "2026-03-01", "mode": "bank", "notes": "", "created_at": datetime.now(timezone.utc)},
        ])
        await db.rental_expenses.insert_many([
            {"unit_id": ids[0], "month": month, "category": "society_maintenance",
             "description": "Sunrise maintenance paid for flat 101", "amount": 4614.38,
             "date": f"{month}-06", "on_behalf_of_building": True, "building_property_id": pid,
             "media": [], "created_at": datetime.now(timezone.utc)},
            {"unit_id": ids[1], "month": month, "category": "repair",
             "description": "Shutter repair", "amount": 3200, "date": f"{month}-09",
             "on_behalf_of_building": False, "building_property_id": None, "media": [],
             "created_at": datetime.now(timezone.utc)},
            {"unit_id": ids[2], "month": month, "category": "tax",
             "description": "Property tax instalment", "amount": 7800, "date": f"{month}-12",
             "on_behalf_of_building": False, "building_property_id": None, "media": [],
             "created_at": datetime.now(timezone.utc)},
        ])
        return {"ok": True, "unit_ids": ids}

    return router
