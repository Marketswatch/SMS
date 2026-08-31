# SocietyHub — PRD

## Problem statement
Admin-driven web + mobile platform to calculate, split and reconcile monthly water usage, recurring
charges and one-time maintenance across building flats, plus a second workspace for personal
Property/Rental management (rent collection, lease tracking, vacancy, payouts to associations).

Two workspaces, switchable from the header:
- **Maintenance Management** — buildings, flats (floor + opening dues), owners, tanker purchases
  (booking + delivery dates), meter readings, recurring + ad-hoc charges, per-litre/reserve cost
  engine, month-end MIS and the owner report pack.
- **Property Management** — per-property master (rent, deposit, lease), monthly Bill → Collect →
  Payout flow, deposits ledger, vacancy tracking, rent receipts, reports.

## Stack
React + Tailwind + shadcn/ui · FastAPI + Motor/MongoDB · JWT auth · Emergent object storage ·
openpyxl (Excel) · reportlab (PDF) · pymupdf + Pillow (report images).
Key files: `backend/{server.py, engine.py, rentals.py, xlsx.py, reports.py, storage.py}`,
`frontend/src/pages/**`, `pages/rentals/**`,
`components/{ReconTable,WaterUsageReport,MediaUpload}.jsx`, `lib/{api,format,notify,modes,sort}.js(x)`.

## Implemented (all testing-agent verified, iterations 7–14)
- Maintenance engine: water purchases (tips inside per-litre cost, separate tips payer), readings,
  charges, reserve/drawdown, reconciliation, MIS, annual view, WhatsApp/SMS reminders.
- Rentals: property master with lease-end autocalc, editable bills with carry-forward of unpaid dues
  / advances, collections, deposits, payouts & credits, settlement, vacancy, receipts.
  Payment modes limited to Cash / UPI / Bank Transfer with a mandatory reference for non-cash.
- Media galleries (photo + video) for meters, bills, work in progress and completion.
- **Water reconciliation — owner statement** (shared `ReconTable.jsx`, on Reconciliation + MIS):
  S.No · Flat No. · Floor · Owner · [**Water Charges** group: Metered · Non-Metered (in storage) ·
  Total Water cost] · Misc · Total amount · Bal brought forward · Advance payment paid by ·
  Amount paid · Balance to pay/receive · Date of payment · Paid by · Status.
  Status has four states: **Prepaid · Paid · Pending · Excess Paid Back**
  (`engine.payment_status(net, payout, received)`).
- **Water usage (meters) report**: per-meter rows with a per-flat **Total Amount**.
- Opening / outstanding dues per flat with an Owner/Tenant payable-by dropdown, feeding
  Bal brought forward until the month is closed.
- Tanker **booking vs delivery date** — delivery ≥ booking, and the delivery date drives the reserve
  inflow and the month the purchase is filed under.
- Floor → flat ordering everywhere plus **click-any-heading sorting** (`lib/sort.jsx`).
- **Styled Excel month packs** for both workspaces (5 sheets each) and the **month-end owner pack**
  (`GET /api/reports/pack`): combined PDF with cover, per-report PDFs, WhatsApp PNGs and a zip.
  Each report fits one page; colour coding is **per flat** (a flat and both its meters share one
  tint); no colour-key blocks in the output.
- Every date is DD-MM-YYYY, S.No on every report, Total Expense / split / Exp-per-head footers.
- Hardening: `?format` + month validated (400), read-only endpoints never create period docs,
  literal-constrained payment fields, idempotent category seeding.
- Fixed (iter 14): meter reading inputs wrote by sorted index — now keyed on meter_id.

## Backlog
- P1 Management fee / commission on properties managed for others, with owner payout after fee.
- P1 Property ledger: one property's bills, collections and payouts on a single timeline.
- P2 Sticky left columns / scroll affordance on the 16-column reconciliation table.
- P2 Inline app-styled error for delivery-before-booking (currently the native browser bubble).
- P2 Deposits: add mode + reference like collections.
- P2 Direct /rentals navigation still shows the MAINTENANCE badge and maintenance sidebar.
- P2 Persist selected month / property across reloads; shadcn date pickers.
- P2 Tenant view-only portal; co-owner splits.
- P2 Move `build_mis_workbook` out of `server.py`; delete stale assertions in
  test_iter10/11/12/13 suites that still assert the pre-iteration-14 spec.
