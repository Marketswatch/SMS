# SocietyHub — PRD

## Original problem statement
Apartment Water & Maintenance Cost-Split Engine. Admin-driven platform to calculate, split and reconcile
monthly water usage, recurring charges and one-time maintenance across the flats of a building, with a
per-owner statement and a guarded month-end reset. Web admin console + mobile-friendly field entry
(meter readings, tanker purchases, photo/video uploads). No payment gateway in v1 — all payments manual.

## Locked decisions
- Property = building; multi-property supported.
- Split unit = per FLAT (one equal share each); co-owner splits out of scope.
- Every payment records who physically paid (owner/tenant); liability rolls up to the owner.
- Per-charge default payer, overridable on any entry.
- Reserve = purchased − consumed; value split equally; negative reserve (drawdown) allowed and flagged.
- Historical months locked and preserved; carry-overs applied forward.

## User choices (from intake)
- JWT email+password auth, roles: super_admin / admin / owner / resident.
- Object storage uploads: images AND video, camera-capture or file-pick, GPS coordinates attached.
- Fixed monthly recurring defaults auto-populated, per-month override.
- Resident/tenant view-only login included alongside admin/owner.
- MIS export: CSV + PDF + on-screen view.

## Architecture
- Backend: FastAPI (`/app/backend/server.py`), auth helpers (`auth.py`), pure calculation engine
  (`engine.py`), Emergent object storage client (`storage.py`). All routes under `/api`.
- DB: MongoDB collections — users, properties, flats, meters, tanks, periods, tankers, readings,
  charges, payments, files. Periods hold `carry_in` and a locked `snapshot`.
- Frontend: React (CRA + Tailwind + shadcn), contexts for auth and property/period selection,
  pages: Login, Dashboard, Setup, Water, Charges, Reconcile, MIS, MyDues.
- Design: Swiss high-contrast financial console, Cabinet Grotesk + IBM Plex Sans/Mono, tabular numerals,
  red "owes" / green "owed" semantics with icons.

## Implemented (2026-06)
- Phase 1: JWT auth w/ httpOnly cookies + bearer fallback, bcrypt, email-keyed brute-force lockout,
  admin seeding, role gating. Building/flat/owner/tenant/meter/tank CRUD, default-payer config,
  fixed recurring defaults.
- Phase 2: Tanker purchase entry (sump/syntex split, auto total, auto ₹/L, tips + payer, media),
  meter reading entry with opening carry-forward, GPS-tagged image/video upload via object storage.
- Phase 3: Calculation engine — consumption per meter/flat, weighted avg ₹/L, reserve + equal share,
  negative-reserve and meter-rollback flags.
- Phase 4: Recurring + one-time charges with auto-fill defaults, contribution tracking,
  reconciliation per owner (owes/owed), payments received and admin payouts, carry-over.
- Phase 5: MIS on-screen report, CSV + PDF export, guarded month reset with locked history.
- Resident view-only "My Dues" page; role-scoped API (residents see only their own flat/property).

## Backlog
- P0: none known.
- P1: multi-property polish (per-property admin assignment), annual/yearly summary statement,
  edit (not just delete) of tanker/charge entries, resident-visible photo gallery.
- P2: explicit CORS origins, async storage I/O (currently blocking `requests`), split server.py into
  routers, penalty/interest on long-overdue balances, offline-first mobile entry queue.

## Next tasks
1. Yearly summary / annual statement per owner.
2. Inline edit of existing entries.
3. Per-property admin assignment and property-scoped manager logins.

## Credentials
See `/app/memory/test_credentials.md`.
