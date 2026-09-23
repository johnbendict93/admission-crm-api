import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.routers import (
    applicants,
    applications,
    auth,
    call_schedules,
    campus_visits,
    counseling_sessions,
    document_types,
    enquiry_monthly_history,
    fee_due_schedule,
    fee_payments,
    followups,
    hostel_allotments,
    leads,
    lookup_values,
    ml_call_sentiment,
    ml_conversion,
    ml_demand_forecast,
    ml_dropout_risk,
    ml_fee_default_risk,
    ml_followup_timing,
    ml_lead_ranking,
    ml_source_roi,
    ml_telecaller_match,
    scholarships,
    settings as settings_router,
    telecallers,
    users,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

openapi_tags = [
    {"name": "Auth", "description": "Login and JWT-based authentication."},
    {"name": "Leads", "description": "Prospective students captured before they apply - the top of the admissions funnel."},
    {"name": "Applicants", "description": "Individuals who have started the application process, with full personal and academic profile data."},
    {"name": "Applications", "description": "A specific programme application tied to an applicant, including seat allotment and review status."},
    {"name": "Fee Payments", "description": "Payments recorded against an applicant's fees."},
    {"name": "Fee Due Schedule", "description": "What an applicant owes, and by when - separate from Fee Payments (what has actually been paid). Feeds roadmap module 18 (Fee Default Risk)."},
    {"name": "Enquiry Monthly History", "description": "Monthly enquiry (lead) counts used as historical training data for demand forecasting (roadmap module 20). Seeded rows are illustrative synthetic history (source=synthetic); combined with live current-year counts derived from leads.created_at for training."},
    {"name": "ML - Demand Forecast", "description": "Predicts the number of enquiries (leads) expected in a given calendar month (roadmap module 20). Read-only; combines seeded synthetic history with real monthly counts derived from leads.created_at; trained offline via ml/train_demand_forecast_model.py, not from live requests."},
    {"name": "ML - Fee Default Risk", "description": "Predicts the probability that a fee_due_schedule row will go unpaid past its due date (roadmap module 18). Read-only; the model is trained offline via ml/train_fee_default_risk_model.py, not from live requests."},
    {"name": "ML - Lead Ranking", "description": "Ranks a telecaller's open leads by predicted conversion probability, best-first (roadmap module 21). Reuses module 13's trained conversion model rather than a separate one."},
    {"name": "Scholarships", "description": "Scholarship applications and awards tied to an applicant."},
    {"name": "Hostel Allotments", "description": "Hostel room assignments tied to an applicant."},
    {"name": "Telecallers", "description": "Staff who place outbound calls to leads."},
    {"name": "Document Types", "description": "Configurable list of document types applicants may be asked to submit."},
    {"name": "Lookup Values", "description": "Configurable dropdown values (grouped by type) used elsewhere in the app."},
    {"name": "Call Schedules", "description": "Scheduled outbound calls to a lead."},
    {"name": "Campus Visits", "description": "Logged campus visits made by a lead."},
    {"name": "Followups", "description": "Logged follow-up calls made to a lead."},
    {"name": "Settings", "description": "Key/value application configuration, grouped by category."},
    {"name": "Counseling Sessions", "description": "Logged counseling sessions between a counselor and an applicant."},
    {"name": "Users", "description": "Staff directory (active users) for pickers such as a counseling session's counselor, plus admin-only user creation. Email and phone are never exposed."},
    {"name": "ML - Call Sentiment", "description": "Predicts the sentiment (positive/neutral/negative) of a followup's free-text notes (roadmap module 19). Read-only; the model is trained offline via ml/train_call_sentiment_model.py, not from live requests."},
    {"name": "ML - Conversion Prediction", "description": "Predicts a lead's probability of eventually enrolling (roadmap module 13). Read-only; the model is trained offline via ml/train_conversion_model.py, not from live requests."},
    {"name": "ML - Source ROI", "description": "Conversion performance by lead source (roadmap module 15). Computed live from the leads table on every request - not a trained model."},
    {"name": "ML - Follow-up Timing", "description": "Ranks candidate calling hours for a lead's assigned telecaller by predicted response quality (roadmap module 14). Read-only; the model is trained offline via ml/train_followup_timing_model.py, not from live requests."},
    {"name": "ML - Dropout Risk", "description": "Predicts the probability that an in-progress application will not end in Admitted (roadmap module 16). Read-only; the model is trained offline via ml/train_dropout_risk_model.py, not from live requests."},
    {"name": "ML - Telecaller Matching", "description": "Ranks active telecallers by a lead's predicted conversion probability if assigned to each one (roadmap module 17). Reuses module 13's trained model rather than a separate one."},
]

# Interactive docs (/docs, /redoc) and the schema (/openapi.json) list every
# endpoint, so they are switched off in production and stay on in development.
# Driven by ENVIRONMENT (set on Render); no hardcoded URLs or flags.
_docs_enabled = settings.ENVIRONMENT != "production"

app = FastAPI(
    title="Admission CRM API",
    version="0.1.0",
    openapi_tags=openapi_tags,
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)

# Origins come from ALLOWED_ORIGINS in .env — add your real Vercel URL there
# once the Next.js frontend is deployed, no code change needed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Log the real error server-side, but never leak internals to the client.
    logger.exception("Unhandled error on %s %s", request.method, request.url)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred. Please try again."},
    )


app.include_router(auth.router)
app.include_router(leads.router)
app.include_router(applicants.router)
app.include_router(applications.router)
app.include_router(fee_payments.router)
app.include_router(fee_due_schedule.router)
app.include_router(enquiry_monthly_history.router)
app.include_router(ml_demand_forecast.router)
app.include_router(scholarships.router)
app.include_router(hostel_allotments.router)
app.include_router(telecallers.router)
app.include_router(document_types.router)
app.include_router(lookup_values.router)
app.include_router(call_schedules.router)
app.include_router(campus_visits.router)
app.include_router(followups.router)
app.include_router(settings_router.router)
app.include_router(counseling_sessions.router)
app.include_router(users.router)
app.include_router(ml_call_sentiment.router)
app.include_router(ml_conversion.router)
app.include_router(ml_source_roi.router)
app.include_router(ml_followup_timing.router)
app.include_router(ml_dropout_risk.router)
app.include_router(ml_fee_default_risk.router)
app.include_router(ml_lead_ranking.router)
app.include_router(ml_telecaller_match.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
