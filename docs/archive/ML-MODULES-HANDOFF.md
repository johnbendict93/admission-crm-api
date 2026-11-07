# DCE Admission CRM — ML Modules 13-22 Handoff

Paste this whole file as your first message in the new Cowork page so it has full context. Written 22 Sep 2026.

## Standing rules (apply to everything, every session)
- Dev first, no hardcoding, verify live before calling anything done.
- Commit AND push — Claude commits and shows the hash, John pushes himself (his own PowerShell; the device shell has no GitHub credentials).
- Read-only on prod unless John says otherwise.
- Cross-app check before any shared-table change (the old Streamlit app `dce_crm` still reads/writes some of these tables, e.g. `followups`).
- No secrets in chat, never open `.env` files.
- Never touch/scrape real students' personal data — synthetic/fake data only.
- ONE STEP AT A TIME, plain language — John gets confused easily with multi-step technical work.
- Honest over diplomatic assessments; real-world examples over abstract ones.
- Golden Rule: audit the real live schema before writing any model/service code — never guess a column or constraint.

## Environment / access notes
- FastAPI backend repo: `C:\Users\johnb\Downloads\Admission-CRM-API` on John's Windows machine — github.com/johnbendict93/Admission-CRM-API (private). Reach it via the device bridge (`mcp__remote-devices__*` tools); connected folder is `Admission-CRM-API`.
- Next.js frontend: github.com/johnbendict93/Admission-CRM-Frontend (separate repo, not touched by this ML work).
- **Neither the cloud sandbox nor the local `device_bash` shell can reach Supabase** (DNS/proxy blocks confirmed repeatedly). Only John's own conda terminal (`admission-crm-api` env, on his real machine) has network access to it. So: Claude writes/prepares any script that needs to touch Supabase (seed scripts, training scripts, audits), and John runs it himself and pastes back condensed results — don't ask him to paste full raw output, ask for the specific short values needed.
- Deployed API: Render, https://admission-crm-api.onrender.com — manual "Deploy latest commit" required after every push, no auto-deploy.
- DEV vs PROD Supabase projects, switched by the `ENVIRONMENT` setting in `app/core/config.py`.
- Repo convention for a new module: `app/models/<table>.py`, `app/services/<table>_service.py`, `app/routers/<table>.py`, wired into `app/main.py`. See `next-module-brief.md` in the repo root for the full checklist (Golden Rule, DI'd Supabase client, pagination, explicit column lists, version-pinned deps, etc.) — read that file directly rather than re-deriving it.
- Ad hoc audit scripts follow the `check_*.py` naming convention and are gitignored (`.gitignore` line 21: `check_*.py`) — never committed, safe to create freely for read-only DEV audits.

## Business context — why this ML work exists
- Goal: **sell this CRM to colleges and coaching centres**, not just for DCE's internal use.
- John is not currently working at DCE and has no reachable pilot contact right now (a relative who owns a school was considered and ruled out — no trust/understanding there for this kind of product).
- No real usage data exists or is reachable at the moment.
- **Decided:** train and demo the ML modules on realistic synthetic data. When a buyer asks "has anyone used this," answer honestly — "you'd be among our first, here's a free/discounted first-pilot offer" — never deflect or imply real usage that doesn't exist. Don't market specific accuracy numbers from synthetic training as if they reflect real-world performance.
- **Decided delivery model:** sell as web-based software (browser + login, no install). Single-tenant — one private deployment (own Render service + own Supabase project) per customer — rather than building multi-tenant SaaS upfront, since only 1-2 pilot customers are expected initially.
- **Plan:** finish building + demo-harden all ML modules on fake data first, then do cold outreach to small/unfamiliar coaching centres or tuition shops for a free first pilot (warm contacts aren't available).

## The 10-module ML roadmap — current status
MEDIUM complexity:
- **13 Admission Conversion Predictor — DONE.** Logistic regression (scikit-learn Pipeline + ColumnTransformer), joblib-serialized, live API endpoint `GET /ml/leads/{lead_id}/conversion-prediction`. Trained on synthetic leads (n=507). Metrics: n_train=405/n_test=102, accuracy=0.6373, precision=0.2683, recall=0.6111, F1=0.3729, ROC-AUC=0.6151. These numbers are from fake data — don't quote them as real-world performance.
- **14 Optimal Follow-up Time Predictor — not started, ready to build** (Phase 1 below).
- **15 Enquiry Source ROI Analyzer — DONE.** Pure aggregation endpoint (no training/model needed), `GET /ml/source-performance`, live.
- **16 Dropout Risk at Admission Stage — not started, ready to build** (Phase 1 below).
- **17 Telecaller Performance Predictor — not started, ready to build** (Phase 1 below).
- **18 Fee Default Risk Predictor — blocked on a real decision**, see Phase 2 below. Do not start building this until John answers.

HIGH complexity:
- **19 NLP Call Sentiment Analyzer — not started**, needs new design work (Phase 4).
- **20 Time Series Demand Forecaster — not started**, needs new design work (Phase 4).
- **21 Lead Ranking System — not started**, but mostly reuses module 13's existing data/features (Phase 3).
- **22 Anomaly Detection for Fraud Enquiries — not started**, needs new design work (Phase 4).

## Existing fake-data generator
`scripts/seed_dev_fake_leads.py` (repo root). DEV-only, dry-run by default, `--apply` to write, `--delete --apply` to remove. Every fake row is tagged with a `@seed.example.com` email so it's identifiable and safely deletable. Already generates (default 500 leads):
- Realistic `leads` rows: real TN district/town names, the real TNEA cutoff formula (Maths + Physics/2 + Chemistry/2), course-interest mix calibrated to public TNEA 2026 branch shares, source mix, parent occupation, enquiry seasonality, and a logit-based conversion model calibrated to ~24% conversion.
- Matching `applicants` rows for every lead whose `status` becomes `"Enrolled"` — full profile (DOB, address, category, 12th marks, PCM marks, cutoff, etc.)

**Gap:** it does not touch `followups`, `call_schedules`, `applications`, `fee_payments`, or `telecallers`. Those are needed for the remaining modules.

## Schemas already audited (confirmed live via `app/models/*.py`, Sept 2026 — Golden Rule already satisfied here, no need to re-audit from scratch, just read those files if in doubt)
- **followups**: `lead_id` (FK), `called_by` (free text, not a real FK), `call_date`, `call_time` (text type, not native time), `response` (free text), `notes`, `next_followup_date`. This is the table the OLD Streamlit app (`dce_crm`) actively reads/writes today — be careful with cross-app impact. Note: there is ALSO a separate, unrelated legacy table `follow_ups` (with an underscore, has a `due_date` column) that this API does NOT use — ignore it, don't confuse the two.
- **call_schedules**: `lead_id` (FK), `scheduled_by` (free text), `scheduled_time` (timestamptz, must be offset-aware — naive datetimes are rejected with 422), `reminder_sent` (bool), `status` (free text, default `'Pending'`).
- **applications**: `applicant_id` (FK), `application_no`, `academic_year`, `programme` (CHECK: B.E./B.Tech/M.E./M.Tech/MBA/MCA), `department`, `branch`, `preferred_hostel`/`preferred_transport`, `application_stage` (free text, **no CHECK constraint**, default `'Draft'` — currently totally unconstrained, so a stage vocabulary has to be designed, not looked up), `merit_rank`, `allotted_seat_type` (CHECK: Management/Government/NRI/Lateral Entry/Spot), `remarks`, `submitted_at`, `reviewed_by`/`reviewed_at`, `category`.
- **fee_payments**: `applicant_id` (FK), `fee_component`, `amount`, `payment_mode`, `payment_date` (default CURRENT_DATE), `receipt_no`, `academic_year`, `remarks`. **No due_date / expected-fee-schedule / status column anywhere** — it only records payments that actually happened. This is exactly why module 18 is blocked, see Phase 2.
- **telecallers**: `name`, `email`, `phone`, `department`, `active` (bool, default true). No FKs from other tables — `followups.called_by` and `call_schedules.scheduled_by` are free text matched by name string only, not a real foreign key relationship.
- **lookup_values**: `type`, `value`, `sort_order`, `is_active` — generic dropdown-options table, currently EMPTY on dev, nothing enforced through it yet.

## The 4-phase build plan (agreed with John — follow this order)

**Phase 1 — build first, no open decisions.** Extend the fake-data generator to also produce `followups`, `call_schedules`, `application_stage` progression, and a populated `telecallers` table with a deliberate performance skill difference baked in between callers (some convert better than others, so module 17 has signal to learn). This unblocks modules 14, 16, and 17.
  - Implementation note for module 16: today, `applicants`/`applications` rows are only created for leads whose `status` becomes `"Enrolled"` (fully converted). For dropout risk to mean anything, some applicants need to start the process and then stall/withdraw partway through the `application_stage` funnel — so the generator needs to create applicants/applications for a broader population than just fully-enrolled leads, with a defined "dropped out" outcome for some of them.

**Phase 2 — needs ONE decision from John, ask directly, don't guess or silently pick.** Module 18, Fee Default Risk. `fee_payments` has no due-date/expected-payment concept at all. Two real options: (a) a small migration adding due-date tracking so the module stays true to its original "default risk" concept, or (b) redefine module 18's scope to fit the existing schema — e.g. "will this admitted student ever complete their fee payments" instead of "is this payment overdue." Do not build any fee_payments-related code until he answers this.

**Phase 3.** Module 21, Lead Ranking System. Reuses module 13's leads data/features, reframed as a ranking problem — given a telecaller's assigned leads, rank them by likelihood-to-convert so the best ones get called first. Minimal new data-generation work needed.

**Phase 4 — each of these needs new design work, not just more rows in the existing generator:**
- **19 NLP Call Sentiment** — needs a bank of realistic call-note text templates tied to each response category (not one-line placeholder notes), so there's real text for a sentiment model to learn from.
- **20 Time Series Demand Forecaster** — needs multiple years of enquiry history with a trend, not the single year the generator currently spans. Open design question: generate full fake `leads` rows for every past year (bigger dataset, more realistic) or just lighter monthly-aggregate-only history for older years (smaller, faster, less "real" looking) — decide before building.
- **22 Fraud Anomaly Detection** — needs a small percentage of deliberately "bad" leads planted in the data (duplicate phone numbers, bot-like identical timestamps, mismatched district/school/marks combos), with the fraud/not-fraud ground truth tracked OUTSIDE the real schema (a local eval-only file, not a DB column) purely so we can check the model actually catches them.

## Immediate next step when resuming in the new page
Start **Phase 1**: extend `scripts/seed_dev_fake_leads.py` (or a new companion script following the same dry-run/`--apply`/marker-email safety pattern) to generate `followups`, `call_schedules`, `application_stage` progression (with the broadened applicant population described above), and `telecallers` rows. Have John run it in his own conda terminal against DEV — same pattern as before, neither the sandbox nor `device_bash` can reach Supabase. Verify the results live, retrain modules 14/16/17 following the module-13 pattern (shared `ml/features.py`-style train/serve consistency), build their API endpoints (`app/models`, `app/services`, `app/routers`, wire into `app/main.py`), commit with the hash shown, John pushes and redeploys on Render.

In parallel (doesn't block Phase 1), ask John for Phase 2's decision on module 18 (migration vs. redefinition) before writing any fee_payments-related code.
