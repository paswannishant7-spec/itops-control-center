# Deployment and operations

## Supported topology

The production Compose file is a single-host reference, not an availability claim. It runs
PostgreSQL/pgvector, a one-shot migration/seed job, the FastAPI service, SLA worker, monitoring
worker, and Nginx-served SPA. Only the frontend binds to the host, on `127.0.0.1:8080` by default.
Place a managed TLS reverse proxy or load balancer in front of it.

For higher availability, use managed PostgreSQL, shared private attachment storage, an atomic shared
rate limiter, centralized logs/metrics, and an orchestrator with readiness/liveness probes. Do not
scale the current process-local rate limiter as though it were globally enforcing limits.

## Prerequisites

- Docker Engine with Compose v2 on a supported Linux host.
- A private DNS-reachable ClamAV service with current signatures.
- TLS termination and a public DNS name.
- Two immutable images produced by the release workflow.
- A backup target outside the deployment host.
- A secret manager or host service manager that can render a root-readable environment file outside
  the checkout.

## First deployment

1. Copy `.env.production.example` outside the repository and replace every placeholder. Use an exact
   HTTPS origin in `ITOPS_CORS_ORIGINS`; wildcards and URL paths are rejected.
2. Pin `ITOPS_API_IMAGE` and `ITOPS_FRONTEND_IMAGE` to a release tag or, preferably, an OCI digest.
3. Set an independently generated database password and JWT secret. URL-encode reserved database
   password characters in `ITOPS_DATABASE_URL`.
4. Set the three initial-administrator variables for the first run only.
5. Validate and pull before changing the running stack:

   ```bash
   docker compose --env-file /secure/itops.env -f docker-compose.prod.yml config --quiet
   docker compose --env-file /secure/itops.env -f docker-compose.prod.yml pull
   ```

6. Take or verify a database backup, then start the migration job and services:

   ```bash
   docker compose --env-file /secure/itops.env -f docker-compose.prod.yml up -d
   docker compose --env-file /secure/itops.env -f docker-compose.prod.yml ps
   ```

7. Confirm `/healthz`, `/api/v1/health/live`, `/api/v1/health/ready`, sign-in, an authorized API
   read, WebSocket readiness, worker logs, attachment scanning, and one backup/restore rehearsal.
8. Remove the initial-administrator password, email, and name from the environment source and rerun
   Compose. Manage later role changes through the audited access workflow.

The migration service applies Alembic to `head` and runs idempotent seeds before API/workers start.
It must complete successfully. Never run two independent schema versions against one database.

## TLS proxy requirements

Forward the original `Host`, client IP chain, and `X-Forwarded-Proto=https`; support WebSocket
upgrade for `/api/v1/realtime/ws`; allow the configured attachment size; set request/time limits;
and preserve response security headers. Redirect HTTP to HTTPS. The application enables secure
cookies and HSTS in production, but the internet-facing TLS layer remains responsible for valid
certificates, modern protocols, access logs, and denial-of-service controls.

The frontend container calls the API at same-origin `/api/v1` and proxies WebSockets internally.
No production image requires a browser-visible API hostname or localhost CSP exception.

## Upgrade and rollback

1. Review migration and application release notes; test the exact image digests against a restored
   production backup.
2. Back up PostgreSQL and the attachment volume. Record current image digests and Alembic revision.
3. Update image references and run `pull`, then `up -d`. Compose gates API/workers on migration
   success and gates the frontend on API health.
4. Run the smoke checks above and inspect error rate, latency, worker progress, database saturation,
   WebSocket reconnects, AI fallback rate, and scanner failures.

Application rollback means restoring the previous immutable images only when the database schema is
backward compatible. Do not run `alembic downgrade` as an incident reflex. For an incompatible or
destructive migration, stop writes and restore the verified pre-deploy database and attachment
backup according to the release-specific plan.

## Backup and restore

- Take encrypted PostgreSQL logical or physical backups on a defined schedule with point-in-time
  recovery appropriate to the service objective.
- Back up `attachment_data` consistently with the database; attachment rows and objects form one
  logical record.
- Keep copies off-host, restrict restore privileges, monitor backup age/failure, and test restores.
- A restore drill is complete only after Alembic revision, row counts, sign-in, scoped ticket reads,
  attachment digest/download, and readiness checks pass.

## Runtime monitoring and incidents

Alert on readiness failure, restart loops, migration failure, worker lag, database pool exhaustion,
disk/volume pressure, stale backups, ClamAV failure/signature age, authentication throttling spikes,
unexpected `5xx`, WebSocket reconnect rate, and provider fallback/error rate. Correlate API logs with
`X-Request-ID`; logs must remain free of bodies, cookies, authorization headers, and secrets.

During an incident, preserve evidence, identify the affected release and migration, disable the AI
provider or external ingress independently where useful, rotate exposed credentials, and prefer
bounded service degradation over bypassing authorization, malware scanning, or audit controls.

## Endpoint agent deployment

Install the agent under a dedicated OS account. Restrict its state file to that account, use the
HTTPS public API URL, supply the enrollment token only for first start, then remove it. Revocation or
rotation happens from the monitoring UI; never reuse one credential across devices. See
[`agent/README.md`](../agent/README.md) and [`agent/.env.example`](../agent/.env.example).
