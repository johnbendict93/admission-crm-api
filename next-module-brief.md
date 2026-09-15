# Admission CRM API — Next Module Build Brief

## Context
- Project root: `C:\Users\johnb\Downloads\Admission-CRM-API`
- Stack: FastAPI + Supabase (South Asia Mumbai region), conda env `admission-crm-api`
- Reference pattern (proven, standardized — copy this structure exactly):
  `app/models/leads.py`, `app/services/leads_service.py`, `app/routers/leads.py`,
  `app/core/config.py`, `app/core/database.py`
- Supabase tables available (from Table Editor): `applicants`, `applications`,
  `call_schedules`, `campus_visits`, `counseling_sessions`, `document_types`,
  `fee_payments`, `follow_ups`, `followups`, `hostel_allotments`, `leads` (done),
  `lookup_values`, `scholarships`, `settings`, `telecallers`, `users`

## Target module for this task
**Applicants** (table: `applicants`) — adjust this section if you want a different
module; everything else in this brief still applies.

---

## GOLDEN RULE — mandatory, every module, no exceptions
1. **Zero hardcoding.** No literal table names, URLs, allowed-origins, or config
   values anywhere in code. Everything flows through `app/core/config.py`'s
   `Settings` class, reading from `.env`.
2. **100% dynamic, optimized, lightweight, standardized.**
3. **Audit before writing.** Before creating any Pydantic model or service
   function for a table, open Supabase Table Editor and read the table's REAL
   columns first. Never guess a schema. (This caused a real bug on the Leads
   module — a guessed `notes` column that didn't exist — do not repeat it.)
4. **Verify before delivery.** Test every endpoint (GET list, GET by id, POST at
   minimum) against the live Supabase table before calling the module done.
   Never hand off code that needs rework.

## Industrial-standard checklist — mandatory, every module
- [ ] Dependency-injected Supabase client via `Depends(get_supabase_client)`
      from `app/core/database.py` — never a module-level global client.
- [ ] Explicit `select()` column list — never `select("*")`.
- [ ] Pagination on all list endpoints (`limit`, `offset` query params, sane
      default, capped max — see `leads.py` router for the pattern).
- [ ] Real error handling: catch `postgrest.exceptions.APIError`, raise
      `HTTPException` with a clear message — never let a raw unhandled 500
      reach the client.
- [ ] CORS stays as explicit `allow_methods` / `allow_headers` in `main.py` —
      never `"*"`.
- [ ] Any new dependency goes into `requirements.txt` version-pinned (`==`) to
      what's actually installed (`pip freeze` to check) — never unpinned.
- [ ] New table name added to `app/core/config.py`'s `Settings` (same pattern
      as `LEADS_TABLE`) and to `.env` / `.env.example` — never a hardcoded
      string in the service file.

## Explicitly deferred — do not build yet
- Automated test suite (pytest) — deferred until 2–3 more modules exist.
- ML modules (items 13–22 in the roadmap) — later phase, not now.

---

## Task: build the Applicants module end-to-end

Follow the exact file structure of the Leads module:

1. **Audit first.** Open Supabase Table Editor → `applicants` table → record
   every real column name and type.
2. **`app/models/applicants.py`** — Pydantic schema matching the real table
   exactly (`ApplicantBase`, `ApplicantCreate`, `ApplicantResponse`, same shape
   as `leads.py`).
3. **`app/services/applicants_service.py`** — Supabase query logic: DI client
   parameter, explicit column list, `get_all_applicants` (paginated),
   `get_applicant_by_id`, `create_applicant`, proper `APIError` handling.
4. **`app/routers/applicants.py`** — `GET /applicants` (paginated),
   `GET /applicants/{id}`, `POST /applicants`, using `Depends` throughout,
   translating `APIError` into `HTTPException(400, ...)`.
5. **Wire it up:** register the new router in `app/main.py`
   (`app.include_router(applicants.router)`).
6. **Config:** add `APPLICANTS_TABLE: str = "applicants"` to `Settings` in
   `app/core/config.py`, and `APPLICANTS_TABLE=applicants` to `.env` and
   `.env.example`.
7. **Test:** start the server
   (`uvicorn app.main:app --reload`, in the `admission-crm-api` conda env)
   and confirm GET and POST work against the real live table — not mocked
   data.
8. **Report back:** what was built, what was tested (with actual responses,
   not just "it works"), and explicit confirmation that every item in the
   Golden Rule and the industrial-standard checklist above was followed —
   flag anything that wasn't, and why.
