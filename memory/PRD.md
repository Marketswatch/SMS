# SocietyHub — PRD

## Problem statement
Admin-driven web + mobile platform to calculate, split and reconcile monthly water usage, recurring
charges and one-time maintenance across building flats, plus a second workspace for personal
Property/Rental management (rent collection, lease tracking, vacancy, payouts to associations).

Two workspaces, switchable from the header:
- **Maintenance Management** — buildings, flats (with floor), owners, tanker purchases, meter
  readings, recurring + ad-hoc charges, per-litre/reserve cost engine, month-end MIS.
- **Property Management** — per-property master (rent, deposit, lease), monthly Bill → Collect →
  Payout flow, deposits ledger, vacancy tracking, rent receipts, reports.

## Stack
React + Tailwind + shadcn/ui · FastAPI + Motor/MongoDB · JWT auth · Emergent object storage.
Key files: `backend/{server.py, engine.py, rentals.py, storage.py}`,
`frontend/src/pages/**`, `pages/rentals/**`, `components/{ReconTable,WaterUsageReport,MediaUpload}.jsx`,
`lib/{api,format,notify,modes}.js`.

## Implemented
- Maintenance: setup, water purchases (tips included in per-litre cost), readings, charges,
  reserve/drawdown, reconciliation, MIS, annual view, bulk WhatsApp/SMS reminders.
- Rentals: property master with lease-end autocalc, monthly bills (rent + maintenance + ad-hoc),
  collections, deposits ledger, building payouts & credits, settlement, vacancy + lost rent,
  rent receipt PDFs, CSV/PDF reports, category master.
- Media: meter / bill / work-in-progress / completion photo & video galleries via object storage.

### June 2026 — session 2
- **Editable bills + carry forward** (rentals): all bill lines editable before saving; previous
  month's unpaid balance auto-carried (advance shown as negative credit), editable/waivable;
  WhatsApp + SMS send buttons per bill. Verified iterations 7–8.
- **Payment modes**: Cash / UPI / Bank Transfer only, Reference no. required for non-cash on
  collections and payouts (POST + PUT), mode + reference shown in history tables.
- **Report formatting** (verified iterations 9–10):
  - S.No first column on every report/reconciliation table (maintenance + rentals).
  - All dates DD-MM-YYYY everywhere — screens, CSV, PDF and receipts (`lib/format.js` `dmy()`,
    `server.py`/`rentals.py` `dmy()`).
  - Water purchases: separate **Lorry paid by** and **Tips paid by** columns + Total Expense /
    Exp-per-head footer.
  - **Floor** per flat (Building Setup, add form + inline editor), shown in all reports.
  - **Water reconciliation report** (Reconcile + MIS, shared `ReconTable.jsx`) with the owner's
    exact columns: S.No · Flat No. · Floor · Owner · Metered cost · Non-metered cost (reserve) ·
    Total water cost · Misc · Total amount · Bal brought forward · Advance paid (fronting) ·
    Amount paid · Balance to pay/receive · Date of payment · Status (Paid / Settled / Partial /
    Pending) — with a TOTAL row, Total Expense, split by no. of houses and Exp per head.
  - **Water usage charges — as per meter readings** report: per-meter S.No, House, Floor, Owner,
    Meter number, Starting/Ending unit, Consumed units, Water charges, Combined per flat, plus the
    legend (total lorries, water received, water cost, cost per litre, metered charges,
    non-metered consumption/cost, per-house share).
  - MIS CSV + PDF exports mirror both reports exactly (PDF visually verified).
- `PaymentIn.direction` / `payer_type` constrained to literals; rental category seeding idempotent.

## Backlog
- P1 Management fee / commission on properties managed for others, with owner payout after fee.
- P1 Property ledger: one property's bills, collections and payouts on a single timeline.
- P2 Deposits: add mode + reference to match the collections policy.
- P2 Sticky left columns on the 15-column reconciliation table (currently horizontal scroll).
- P2 Mobile field refinements (large number pads, camera-first entry); shadcn date pickers.
- P2 Tenant view-only portal; co-owner split handling.
- P2 Split `rentals.py` / `server.py` into modules; batch previous-month queries.
