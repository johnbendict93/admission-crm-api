# Admission CRM — API (FastAPI + ML)

Backend for an **admissions CRM for engineering colleges and coaching
centres**: it tracks an enquiry from the first phone call to fee payment,
and uses 10 machine-learning models to tell the admissions team *who to
call, when, and by whom*.

**Live demo:** https://admission-crm-demo-tau.vercel.app
(synthetic demo data — read-only login available on request)
**Frontend repo:** https://github.com/johnbendict93/Admission-CRM-Frontend

---

## What it does

| Area | Modules |
|---|---|
| Admissions funnel | Leads, Applicants, Applications, Follow-ups, Call Schedules, Campus Visits, Counseling Sessions |
| Fees & student services | Fee Payments, Fee Due Schedule, Scholarships, Hostel Allotments |
| Team & config | Users (role-based), Telecallers, Settings, Lookup Values, Document Types, Enquiry Monthly History |
| AI / ML (10 models) | see below |

### ML modules

| # | Model | Answers | Approach |
|---|---|---|---|
| 13 | Admission conversion | How likely is this lead to enrol? | Logistic regression with telecaller × course / occupation interaction features (CV ROC-AUC 0.76) |
| 14 | Best time to call | Which hour gets a positive response for *this* family? | Hour × parent-occupation model (CV ROC-AUC 0.81) |
| 16 | Dropout risk | Will an admitted student drop before joining? | Logistic regression (CV ROC-AUC 0.61) |
| 17 | Best telecaller match | Which telecaller should call this lead? | Scores the lead against every telecaller with model 13 |
| 18 | Fee default risk | Will this fee instalment be missed? | Logistic regression (CV ROC-AUC 0.65) |
| 19 | Call sentiment | Was the call positive, neutral or negative? | TF-IDF + logistic regression on call notes |
| 20 | Demand forecast | How many enquiries next month? | Seasonal ridge regression |
| 15 | Enquiry-source ROI | Which channel brings students who actually enrol? | Aggregation over the funnel |
| 21 | Lead ranking | Which open leads should a telecaller call first? | Ranks open leads by model 13 |
| 22 | Fraud / anomaly | Is this enquiry fake or duplicated? | Isolation Forest (caught all 28 planted test anomalies) |

**Honest note on the data:** there is no real customer data yet, so every
model is trained on a **synthetic dataset** (528 leads, ~1,600 call logs)
generated with explainable patterns (TNEA branch shares, seasonal enquiry
peaks, telecaller specialties, family-dependent calling hours). Metrics are
5-fold cross-validated, and every prediction in the UI is labelled
"trained on sample data". The pipelines are built to be retrained on a
college's real history.

---

## Architecture

```
Next.js (Vercel) ──► FastAPI (Render) ──► Supabase Postgres (Mumbai)
                         │
                         └── scikit-learn models (joblib, versioned in git)
```

- **Single-tenant by design:** each college gets its own private API +
  database + website (`docs/CUSTOMER-SETUP.md`).
- **Layered code:** `app/routers` (HTTP) → `app/services` (logic) →
  Supabase client; `app/models` holds Pydantic request/response schemas;
  `ml/` holds feature definitions, pipelines and training scripts.
- **Typed client:** the OpenAPI schema is exported and turned into a typed
  TypeScript client (orval) used by the frontend (`typed-client/`).

## Engineering highlights

- **Auth:** Supabase Auth JWTs verified on every request; roles
  admin / counselor / staff / viewer, viewer is read-only.
- **Database security:** migrations 0015–0017 lock every table away from
  the public anon key; only the server key can read/write.
- **Soft deletes + audit trail** on all core tables (`deleted_at`/`deleted_by`).
- **Versioned SQL migrations** with checksums and drift detection
  (`migrations/run_migrations.py`, see `MIGRATIONS.md`), rollback files
  for risky ones.
- **Tests:** ~300 pytest tests against a dedicated dev database, with an
  autouse fixture that fails any test that leaves rows behind; GitHub
  Actions CI on every push.
- **Separate dev / prod / demo environments**; the public demo runs on the
  dev database with a hard lock so it can never reach production.
- **Timezone-correct** scheduling (`timestamptz`, IST-aware writes).

## Tech stack

Python 3.13 · FastAPI · Pydantic v2 · Supabase (Postgres, Auth) ·
scikit-learn · pandas · psycopg2 · pytest · GitHub Actions · Render

## Run locally

```bash
conda create -n admission-crm-api python=3.13 && conda activate admission-crm-api
pip install -r requirements.txt
cp .env.example .env          # fill in your own Supabase project values
python migrations/run_migrations.py apply --env dev
uvicorn app.main:app --reload # http://127.0.0.1:8000/docs
pytest -q                     # needs TEST_* accounts, see scripts/create_test_users.py
```

## Author

**John Bendict** — systems architect / AI & Data Science educator, Chennai.
Designed the architecture, data model, ML pipelines and deployment; built
with AI-assisted development (Claude).
