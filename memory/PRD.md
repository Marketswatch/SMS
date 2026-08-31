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

## Implemented
- Maintenance engine: water purchases (tips inside per-litre cost, separate tips payer), readings,
  charges, reserve/drawdown, reconciliation, MIS, annual view, bulk WhatsApp/SMS reminders.
- Rentals: property master with lease-end autocalc, editable bills with carry-forward, collections,
  deposits, building payouts & credits, settlement, vacancy, receipts.
- Media galleries (photos + video) for meters, bills, work in progress and completion.

### June 2026 — session 2 (iterations 7–13, all testing-agent verified)
- Rentals: editable bills, carry-forward of unpaid dues / advances, Cash-UPI-Bank modes with
  mandatory reference for non-cash (POST + PUT).
- Reports: S.No everywhere · all dates DD-MM-YYYY (screens, CSV, Excel, PDF, receipts) ·
  Floor per flat · Lorry-paid-by vs Tips-paid-by · Total Expense / split / Exp-per-head footers.
- **Water reconciliation report** (shared `ReconTable.jsx`, on Reconciliation + MIS) with the owner's
  columns: S.No · Flat No. · Floor · Owner · Metered cost · Non-metered cost (reserve) · Total water
  cost · Misc · Total amount · Bal brought forward · Advance payment paid by · Amount paid ·
  Balance to pay/receive · Date of payment · Paid by · Status.
- **Water usage (meters) report** with combined per flat and the full water legend.
- **Styled Excel month packs** for both workspaces (5 sheets each), navy headers, currency formats,
  TOTAL rows, frozen panes, per-owner / per-meter / per-payer colour coding with colour keys,
  names written verbatim.
- **Booking vs delivery date** on tankers — delivery must be ≥ booking and drives the reserve inflow
  and the month the purchase is filed under.
- **Opening / outstanding dues per flat** with an Owner/Tenant payable-by dropdown; flows into
  Bal brought forward until the month is closed, then normal carry-forward takes over.
- **Floor → flat ordering** across all reports, plus **click-any-heading sorting** (`lib/sort.jsx`)
  on reconciliation, meters, tankers, readings, charges and the rentals rent roll.
- **Month-end owner pack** (`GET /api/reports/pack`, `reports.py`): combined colour-coded PDF with
  cover page, per-report PDFs, WhatsApp PNG images and a zip of everything, covering water usage by
  meter, water purchases, recurring entries and the reconciliation statement — plus a
  "Share on WhatsApp" action on the MIS page.
- Hardening: `?format` and month validated (400), read-only endpoints never create period docs,
  literal-constrained payment fields, idempotent category seeding.

## Backlog
- P1 Management fee / commission on properties managed for others, with owner payout after fee.
- P1 Property ledger: one property's bills, collections and payouts on a single timeline.
- P2 Sticky left columns + scroll affordance on the wide reconciliation table.
- P2 Inline app-styled error for delivery-before-booking (currently the native browser bubble).
- P2 Deposits: add mode + reference like collections.
- P2 Persist selected month / property across reloads; shadcn date pickers.
- P2 Tenant view-only portal; co-owner splits.
- P2 Move `build_mis_workbook` out of `server.py`; refresh legacy data-dependent tests.
