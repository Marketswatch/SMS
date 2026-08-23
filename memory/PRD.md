# SocietyHub — PRD

## Original problem statement
Apartment Water & Maintenance Cost-Split Engine. Admin-driven platform to calculate, split and reconcile
monthly water usage, recurring charges and one-time maintenance across the flats of a building, with a
per-owner statement and a guarded month-end reset. Web admin console + mobile-friendly field entry.
No payment gateway — all payments recorded manually.

Extended (June 2026) with a second workspace: **Property (rental) Management** for units the admin owns
or manages for family/friends — rent, deposits, bills paid, kept strictly separate from the maintenance flow.

## Locked decisions
- Property = building; multi-property supported. Split unit = per FLAT (one equal share each).
- Every payment records who physically paid (owner/tenant); liability rolls up to the owner.
- Reserve = purchased − consumed; negative reserve (drawdown) allowed and flagged.
- **A tanker's cost = lorry amount + tips.** Both form the per-litre price; tips are never split as a recurring charge.
- Historical months locked and preserved; carry-overs applied forward.
- Rentals: rent/deposit money from tenants NEVER mixes with a building's maintenance statement.
  Bills paid on behalf of a building are tagged and tallied separately against that building.
  No commission maths on managed units (deferred).

## User choices (from intake)
- JWT email+password auth; roles super_admin / admin / owner / resident (resident = view-only).
- Object storage uploads: images AND video, camera-capture or gallery, GPS coordinates attached.
- Fixed monthly recurring defaults auto-populated with per-month override.
- MIS export CSV + PDF + on-screen view.
- Meter photos: multiple per meter per month. Work photos: Bill/Invoice, In progress, Completed.
- Owner/tenant reminders: free device-based WhatsApp + SMS (no paid gateway).
- Login shows a workspace chooser: Maintenance Management vs Property Management.

## Architecture
- Backend: FastAPI — `server.py` (auth, setup, water, charges, payments, statement, MIS, annual, reset,
  uploads), `engine.py` (pure calculation engine), `rentals.py` (rental module router), `auth.py`, `storage.py`.
- DB: MongoDB — users, properties, flats, meters, tanks, periods, tankers, readings, charges, payments,
  files, rental_units, rent_collections, rental_expenses.
- Frontend: React + Tailwind + shadcn. Contexts: auth, app (property/period/mode/rentMonth).
  Maintenance pages: Dashboard, Setup, Water, Charges, Reconcile, MIS, Annual, MyDues.
  Rental pages: RentDashboard, Units, Collections, Expenses, RentReport. Plus ModeSelect.
- Design: Swiss high-contrast financial console, Cabinet Grotesk + IBM Plex Sans/Mono, tabular numerals,
  red "owes" / green "owed" semantics paired with icons.

## Implemented
### Iteration 1 (2026-06) — MVP
Auth with bcrypt + JWT cookies, email-keyed brute-force lockout, role gating. Building/flat/owner/tenant/
meter/tank setup, default payers, fixed recurring defaults. Tanker purchases, meter readings with
carry-forward, calculation engine (avg cost, reserve, drawdown + rollback flags), recurring and one-time
charges, reconciliation with carry-over, payments and payouts, MIS CSV+PDF, guarded month reset,
resident My Dues.
### Iteration 2 — tips fix
Tanker cost = lorry + tips everywhere (per-tanker ₹/L, monthly average); tips removed from the recurring
split and rejected as a recurring charge type.
### Iteration 3 — media & references
Required building dropdown on Add Flat + "Building / Flat" labelling; owner/tenant phones with inline edit;
multi-file GPS-tagged photo/video per meter per month; three categorised work-photo sets plus bill photos
on recurring charges; free WhatsApp + SMS dues reminders per owner.
### Iteration 4 — workspaces, rentals, backlog
Mode chooser at login with header switch; full rental module (units own/managed, rent + due day, deposits
with refunds/deductions, lease dates with expiry window alert, bills by category, on-behalf-of-building
tally, rent roll with paid/pending/overdue/vacant status, owner payout report, CSV+PDF export);
work photo gallery dialog; bulk WhatsApp/SMS reminder pass; editing of tanker and charge entries;
annual statement per owner with month-by-month table and CSV+PDF export.

### Iteration 5 — receipts, overview, vacancy
Printable PDF receipts for every rent/deposit/refund/deduction entry (receipt number, property, tenant,
month, mode, amount, and for rent the monthly rent / paid-to-date / balance) plus a WhatsApp share of the
receipt details. Combined Overview screen (`/api/overview`) showing maintenance dues per building and rent
income per property side by side with money in / money out / still to collect, reachable from both
workspaces. Vacancy tracking: `vacant_since` per unit, idle days and rent forgone scoped to the selected
month, vacancy alert + stat + inline per-row figures, a vacancy table in Reports and in the CSV/PDF export.
Units whose lease starts later now report status `upcoming` rather than vacant, and demo seeding refuses to
run once real properties exist.

### Iteration 6 — property module rebuilt (bill → collect → payout)
Rewrote the rental module to the user's spec. Property master now holds rent, monthly maintenance, deposit,
due day and a lease period in months that auto-fills the end date (calendar pick also supported).
Monthly bill per property = rent + maintenance + ad-hoc collectibles (category from a user-extendable
master + note) − amounts the tenant paid on my behalf; sendable by WhatsApp/SMS with a line-by-line
breakdown. Collections are entered per bucket (rent / maintenance / ad-hoc) with a fill-from-outstanding
helper, so each head is accounted separately; receipts print the split. Deposits stay separate.
Payouts to buildings/associations track what I owe per property (maintenance payable defaults to the
figure collected, editable) with credits for bills I or the tenant paid on the building's behalf —
balance = payable − paid − credits. Removed the old Rent & Deposits / Bills Paid screens.

## Backlog
- P1: commission / management fee on managed rental units (explicitly deferred by user);
  tenant-facing rental portal; shadcn date pickers replacing native date inputs.
- P2: async storage I/O (currently blocking `requests`); split server.py into routers;
  short-lived signed file URLs instead of `?auth=` token; penalty/interest on long-overdue owners;
  offline-first mobile entry queue.

## Next tasks
1. Rent receipt PDF per collection.
2. Commission/management fee for managed units.
3. Combined cross-workspace monthly summary (maintenance + rentals side by side).

## Credentials
See `/app/memory/test_credentials.md`.
