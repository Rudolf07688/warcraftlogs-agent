# Deployment Notes (design-for-later)

The streaming chat app is built so the same code deploys to Google Cloud Run with
no rework. This captures the plan (clarified 2026-10-01); it is **not** built yet.

## Decisions

- **Google auth = ADC everywhere.** Locally, Docker Compose mounts the host
  `~/.config/gcloud/application_default_credentials.json` into the backend and sets
  `GOOGLE_APPLICATION_CREDENTIALS`. On Cloud Run, the service's **attached service
  account** provides ADC automatically — same code path, no key files.
- **Secrets from Google Secret Manager.** WCL and DB credentials are injected into
  the Cloud Run service as env vars from Secret Manager. Config is env-var based
  (`backend/app/config.py` via `pydantic-settings`), so only the *source* changes
  between local `.env` and production.
- **Database: Cloud SQL for PostgreSQL 17.** Connect via `DATABASE_URL` (Cloud SQL
  connector / unix socket). Local dev uses the docker `db` service. One SQLAlchemy
  async code path regardless.
- **Access control: public + unauthenticated for v1** (accepted risk). Real access
  control (Cloud Run IAM/IAP or app-level auth) is a later improvement.

## To deploy (future work)

1. Build and push the backend image (`backend/Dockerfile`) to Artifact Registry.
2. Provision Cloud SQL (Postgres 17); grant the Cloud Run service account access.
3. Store `WCL_CLIENT_ID`, `WCL_CLIENT_SECRET`, and DB creds in Secret Manager; map
   them to the service as env vars. Set `GOOGLE_GENAI_USE_VERTEXAI=TRUE`,
   `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, and `DATABASE_URL`.
4. Deploy the backend to Cloud Run with its service account; enable the Vertex AI
   and Cloud SQL Admin APIs.
5. Build/deploy the frontend (static build served by a CDN/host or a second Cloud
   Run service) pointed at the backend URL.

## WebSockets on Cloud Run

Supported, but: enable **session affinity**, keep streamed turns well under the
request timeout, and set an adequate timeout. Capture in the deployment work.

## Schema management

v1 creates tables on startup (`Base.metadata.create_all`). Before production,
introduce migrations (e.g. Alembic) instead of create-all.
