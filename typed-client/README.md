# Typed API client (generated)

Generates TypeScript types + React Query hooks from the live
Admission-CRM-API OpenAPI schema, so the future Next.js frontend is built
against real backend contracts instead of hand-typed guesses.

## 1. Export the live schema (run from the API repo root, in the
   `admission-crm-api` conda env - needs the app's real dependencies):

    python -c "import json; from app.main import app; json.dump(app.openapi(), open('openapi.json', 'w'), indent=2)"

## 2. Generate the client (from this `typed-client/` folder):

    npm install
    npm run generate

Output lands in `src/generated/` - `endpoints.ts` (React Query hooks, one
group per router tag) and `models/` (request/response types matching the
Pydantic schemas exactly). Regenerate whenever the backend schema changes -
never hand-edit anything under `src/generated/`.
