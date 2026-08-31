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
React + Tailwind + shadcn/ui · FastAPI + Motor/MongoDB · JWT auth · Emergent object storage ·
openpyxl for Excel · reportlab for PDF.
Key files: `backend/{server.py, engine.py, rentals.py, xlsx.py, storage.py}`,
`frontend/src/pages/**`, `pages/rentals/**`,
`components/{ReconTable,WaterUsageReport,MediaUpload}.jsx`, `lib/{api,format,notify,modes}.js`.

## Implemented
- Maintenance: setup, water purchases (tips in per-litre cost, separate tips payer), readings,
  charges, reserve/drawdown, reconciliation, MIS, annual view, bulk WhatsApp/SMS reminders.
- Rentals: property master with lease-end autocalc, editable monthly bills with carry-forward,
  collections, deposits ledger, building payouts & credits, settlement, vacancy + lost rent,
  rent receipt PDFs, category master.
- Media: meter / bill / work-in-progress / completion photo & video galleries via object storage.

### June 2026 — session 2
- **Editable bills + carry forward** (rentals), previous month's unpaid balance auto-carried,
  advances as negative credit, editable/waivable; WhatsApp + SMS per bill. (iter 7–8)
- **Payment modes** Cash / UPI / Bank Transfer only, Reference required for non-cash on POST+PUT
  for collections and payouts; mode + reference in history tables.
- **Report formatting** (iter 9–10): S.No on every report table; all dates DD-MM-YYYY everywhere
  (screens, CSV, PDF, receipts); Floor per flat; Lorry paid by vs Tips paid by columns;
  Total Expense / split by houses / Exp per head footers.
- **Water reconciliation report** (shared `ReconTable.jsx`, used by Reconciliation + MIS) with the
  owner's exact 15 columns: S.No · Flat No. · Floor · Owner · Metered cost · Non-metered cost
  (reserve) · Total water cost · Misc · Total amount · Bal brought forward · Advance paid
  (fronting) · Amount paid · Balance to pay/receive · Date of payment · Status.
- **Water usage (meters) report**: per-meter rows + combined per flat + lorry/cost-per-litre/
  non-metered legend.
- **Styled Excel month packs** (iter 11–12), one workbook per workspace:
  - Maintenance: Water Reconciliation · Water Usage (Meters) · Tanker Purchases · Charges · Ledger.
  - Property: Rent Roll · Collections · Payouts · Building Settlement · Deposits.
  - Navy header bands, bold white headers, borders, currency formats, shaded TOTAL rows, frozen
    panes, summary/legend blocks, red/green balance highlighting.
  - Colour coding: unique generated tint per owner, per meter (keyed on meter id) and per fronting
    flat / per property, with a per-sheet "Colour key" block. 30 hues, no overlap between palettes.
  - Owner names, meter numbers and property names written verbatim.
  - Excel button on MIS Report and Property Reports (`export-xlsx-btn`, `rent-export-xlsx-btn`).
- Hardening: `?format` validated (400 on unknown), month validated YYYY-MM, read-only statement /
  export / overview no longer create period documents, `PaymentIn.direction` + `payer_type`
  constrained to literals, rental category seeding idempotent.
- Verified by testing agent: iterations 7–12 (iter 12 = 48/48 new + 72/72 regression).

## Backlog
- P1 Management fee / commission on properties managed for others, with owner payout after fee.
- P1 Property ledger: one property's bills, collections and payouts on a single timeline.
- P2 Sticky/frozen left columns + scroll affordance on the 15-column reconciliation table.
- P2 Deposits: add mode + reference to match the collections policy.
- P2 Persist selected month / property across reloads (currently AppContext state only).
- P2 shadcn date pickers instead of native date/month inputs.
- P2 Tenant view-only portal; co-owner split handling.
- P2 Move `build_mis_workbook` out of `server.py` (now ~1350 lines) into a reports module.
- P2 Refresh legacy data-dependent tests (backend_test.py, test_media_notify.py) that hard-code
  older Sunrise figures.
