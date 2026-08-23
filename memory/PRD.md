# SocietyHub — PRD

## Problem statement
Admin-driven web + mobile platform to calculate, split and reconcile monthly water usage, recurring
charges and one-time maintenance across building flats, plus a second workspace for personal
Property/Rental management (rent collection, lease tracking, vacancy, payouts to associations).

Two workspaces, switchable from the header:
- **Maintenance Management** — buildings, flats, owners, tanker purchases, meter readings,
  recurring + ad-hoc charges, per-litre/reserve cost engine, month-end MIS with carry-forward.
- **Property Management** — per-property master (rent, deposit, lease), monthly Bill → Collect →
  Payout flow, deposits ledger, vacancy tracking, rent receipts, reports.

## Stack
React + Tailwind + shadcn/ui · FastAPI + Motor/MongoDB · JWT auth · Emergent object storage for photos.

Key files: `backend/server.py`, `engine.py` (maintenance), `rentals.py` (property),
`storage.py`; `frontend/src/pages/**`, `pages/rentals/**`, `lib/{api,format,notify,modes}.js`.

## Implemented
- Maintenance: setup, water purchases (incl. tips in per-litre logic), readings, charges,
  reserves/drawdowns, reconciliation, MIS, annual view, bulk WhatsApp/SMS reminders.
- Rentals: property master with lease-end autocalc, monthly bills (rent + maintenance + ad-hoc in /
  tenant-paid out), segregated collections, deposits ledger, building payouts & credits, settlement
  view, vacancy + lost-rent, rent receipt PDFs, CSV/report export, category master.
- Media: meter / bill / work-in-progress / completion photo galleries via object storage.

### 2026-06 (this session)
- **Editable bills**: rent, maintenance, payable-to-building and ad-hoc items all editable inline
  before saving; live total shown. WhatsApp + SMS send buttons on each bill card.
- **Carry forward**: next month's bill draft auto-fills `carry_forward` = last month's billed total −
  collected (positive = dues, negative = advance credit). Falls back to the property master when no
  bill was saved last month, guarded by lease/created-at so new properties don't get bogus dues.
  Editable / waivable before saving; appears in the WhatsApp/SMS bill text.
- **Payment modes**: restricted to Cash / UPI / Bank Transfer everywhere (`lib/modes.js`);
  Reference / UPI txn no. required for all non-cash collections and payouts (enforced on POST and
  PUT); mode + reference shown in the collections and payouts history tables.
- Category master seeding made idempotent.
- Verified by testing agent: iterations 7 and 8.

## Backlog
- P1 Management fee / commission cut on properties managed for others, with owner payout after commission.
- P1 Property ledger: single unified timeline of bills, collections and payouts per property.
- P2 Deposits: add mode + reference to match the collections policy.
- P2 Video upload support alongside photos for meters / work.
- P2 Mobile field refinements (large number pads, camera-first entry).
- P2 Tenant view-only portal; co-owner split handling.
- P2 Split `rentals.py` (~750 lines) into modules; batch previous-month queries in `prev_outstanding`.
