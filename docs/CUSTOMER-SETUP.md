# New customer setup — one private CRM per college

How to give a new college (or coaching centre) its **own private copy** of the
Admission CRM: its own database, its own API, its own website. Nothing is
shared between customers. Written Nov 2026 from the real code in this repo
and `Admission-CRM-Frontend`.

**Time:** about 1–1.5 hours per customer once you've done it once.
**Cost on free tiers:** ₹0 — but see "Before a paying customer goes live" at
the end; a real customer should be on paid tiers.

Throughout this guide `<college>` means a short lowercase name for the
customer, e.g. `abc-engg`. Use the same name everywhere.

---

## Step 0 — Rehearse once with a fake "test college" (do this before the FIRST real customer)

The dev and prod databases were created *before* the numbered migrations
existed, so a completely fresh database has **never** been built from
`migrations/0001…0020` yet. Before a real customer depends on it, run this
whole guide once with `<college>` = `test-college`, log in, click through
every page, then delete the three test services. Fix anything that breaks
in the migration files (dev first), not by hand-editing the new database.

---

## Step 1 — Create the customer's database (Supabase, ~10 min)

1. supabase.com/dashboard → **New project**.
   - Name: `admission-crm-<college>`
   - Region: **South Asia (Mumbai)** — keeps Indian students' data in India.
   - Database password: generate a strong one and save it in your password
     manager (never in chat, email or this repo).
2. When it's ready, note these four values (Project Settings → API / Connect):
   - **Project URL** (`https://xxxx.supabase.co`)
   - **Secret key** (server key — treat like a password)
   - **Publishable (anon) key**
   - **Direct connection string** (Connect → Connection string → URI, with
     the database password filled in)
3. **Authentication → Sign In / Providers → turn OFF "Allow new users to
   sign up".** Only the college's admin creates staff accounts.

## Step 2 — Build the tables (migrations, ~5 min)

In PowerShell, from the `Admission-CRM-API` folder. The trick: point the
migration runner's "prod" slot at the **customer's** database for this one
window only, using a temporary environment variable (it overrides `.env`,
and disappears when you close the window):

```powershell
cd C:\Users\johnb\Downloads\Admission-CRM-API
$py = "C:\Users\johnb\anaconda3\envs\admission-crm-api\python.exe"
$env:PROD_DATABASE_URL = "<customer direct connection string>"
& $py migrations/run_migrations.py status --env prod
& $py migrations/run_migrations.py apply --env prod
& $py migrations/run_migrations.py verify --env prod
```

(`$py` is the env's own Python. Use it instead of `python` or `conda run`:
plain `python` in PowerShell silently runs the base Anaconda with the wrong
scikit-learn (found 7 Nov 2026), and `conda run` can't answer the "are you
sure?" prompt the runner shows for prod.)

- `status` should list 0001…0020 as **pending** (if it shows anything as
  applied, STOP — you're pointed at the wrong database).
- `apply` builds every table, trigger and security lock-down (0015–0017
  block the public anon key from reading any table).
- `verify` should report no drift.
- **Close this PowerShell window afterwards** so the temporary variable can't
  leak into later commands.

Never paste the connection string into chat or commit it.

## Step 3 — Create the college's first admin (~5 min)

The CRM's own Users page deliberately can't create admins, so the first one
is made here:

1. Supabase → **Authentication → Users → Add user → Create new user**.
   Email = the college admin's real email, a temporary password, tick
   **Auto Confirm User**.
   (A trigger automatically creates their CRM profile with role `counselor`.)
2. Supabase → **SQL Editor** → run (with their email):
   ```sql
   update users set role = 'admin', full_name = '<Their Name>'
   where email = '<their email>';
   select full_name, email, role, is_active from users;
   ```
3. Give them the temporary password **by phone or in person**, and ask them
   to change it after first login.

All other staff (counselors, staff, viewers) the admin creates later from
the CRM's **Users** page.

## Step 4 — Start the customer's API (Render, ~10 min)

render.com → **New → Web Service** → repo `johnbendict93/admission-crm-api`,
branch `main`.

| Setting | Value |
|---|---|
| Name | `admission-crm-api-<college>` |
| Region | Singapore |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Python | picked up from `.python-version` (3.13.9) — don't override |

Environment variables (type them in; **never use "Add from .env"**):

| Key | Value |
|---|---|
| `ENVIRONMENT` | `production` |
| `PROD_SUPABASE_URL` | customer Project URL |
| `PROD_SUPABASE_KEY` | customer **secret** key |
| `PROD_SUPABASE_ANON_KEY` | customer publishable key |
| `COLLEGE_SHORT` | e.g. `ABC` |
| `ALLOWED_ORIGINS` | the customer's website URL from Step 5 (add after Step 5) |

Do **not** add `PROD_DATABASE_URL`, `DEV_*` or `TEST_*` — the running API
never needs them. Leave `DOCS_ENABLED` unset (docs are off in production).

Deploy, wait for "Your service is live", then check in a browser:
- `https://admission-crm-api-<college>.onrender.com/health` → `{"status":"ok"}`
- `…/docs` → `Not Found` (good — hidden in production)

## Step 5 — Start the customer's website (Vercel, ~5 min)

vercel.com → **Add New → Project** → import `Admission-CRM-Frontend` again.

- Project name: `admission-crm-<college>`
- Environment variable: `BACKEND_API_URL` = the Render URL from Step 4
  (no trailing slash). It's the only variable the website needs.
- Deploy.

Then go back to the Render service → Environment → set `ALLOWED_ORIGINS`
to this Vercel URL → save (Render redeploys).

Optional: a custom domain like `crm.abccollege.edu.in` (Vercel → Project →
Domains; the college adds one DNS record).

## Step 6 — Hand-over check (~10 min, do it together with the admin)

Log in as their admin and confirm:
- [ ] Dashboard loads (all zeros is correct for a new college).
- [ ] Settings, Lookup Values, Document Types: fill in the college's own
      values (courses, fee components, required documents).
- [ ] Users → add one counselor → that person can log in.
- [ ] Leads → add one test lead → AI Insights opens → delete the test lead.
- [ ] Telecallers → add their real telecallers.

## Things to tell the customer honestly

- **AI predictions start from sample-data patterns.** The models in
  `ml/artifacts/` were trained on synthetic demo data. They become *their*
  patterns only after retraining on the college's own history (a few
  hundred leads with outcomes). Plan a retrain after the first admission
  season. Every AI popup already says "trained on sample data".
- **Free hosting sleeps.** On free tiers the first page load after ~15 min
  idle takes ~50 s, and a free Supabase project pauses after ~1 week
  unused. Fine for a pilot, not for daily office use.
- **The daily report email** currently runs from the separate Streamlit
  repo's GitHub Action and is wired to one database. It is NOT set up per
  customer yet — offer it later, or move it into this API first.

## Before a paying customer goes live

- Supabase **Pro** (daily backups, no pausing) and Render **Starter** (no
  sleep). Budget roughly ₹3,000–4,000/month per customer at current
  prices — check before quoting.
- A one-page written agreement covering whose data it is, backups, and
  what happens to the data if they stop paying (export + delete).
- Keep a private list per customer (password manager): Supabase project
  name, Render service, Vercel project, admin email. Never in git.

## Removing a customer

Export their data first (Supabase → Table Editor → each table → Export
CSV, or a `pg_dump` with their connection string), hand it over, then
delete the Vercel project, the Render service, and the Supabase project, in
that order.
