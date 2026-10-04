# Deployment and operations

## Supported topology

The production Compose file is a single-host reference, not an availability claim. It runs
PostgreSQL/pgvector, a one-shot migration/base-seed job, the FastAPI service, SLA worker, monitoring
worker, private ClamAV, Nginx-served SPA, and Caddy TLS proxy. Only Caddy publishes host ports
(80 and 443); PostgreSQL, API, workers, ClamAV, and Nginx stay on the Compose network.

## Hosted Portfolio Demo

**This is a portfolio demonstration, not a production deployment.** Use a dedicated VPS and DNS
name containing only fictional data. Allow inbound 80/443 for certificate issuance and HTTPS;
restrict SSH to the operator. **Planning minimum: 2 vCPU, 8 GiB RAM, 30 GiB disk on x86;
recommended initial size: 4 vCPU, 12 GiB RAM, 50 GiB disk.** These are capacity estimates,
not benchmarked application minima: the isolated local rehearsal measured about 1 GiB of steady
ClamAV memory and roughly 0.3 GiB for the other running containers, but did not measure startup
or signature-update peaks, concurrent reviewers, or long-term storage growth. The headroom also
reflects [ClamAV's 3 GiB minimum and 4 GiB preferred host guidance](https://docs.clamav.net/manual/Installing/Docker.html)
while PostgreSQL, API, two workers, Nginx, and Caddy run beside it. Measure peak signature-reload
memory and application use before considering a smaller host. Reserve disk for PostgreSQL,
attachments, image layers, ClamAV signatures, logs, and an off-host backup; no load or recovery
guarantee is implied.

Keep the environment file outside the checkout with restrictive host permissions. Required names
are `ITOPS_API_IMAGE`, `ITOPS_FRONTEND_IMAGE`, `ITOPS_CLAMAV_IMAGE`, `ITOPS_TLS_IMAGE`,
`ITOPS_DEMO_HOST`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `ITOPS_DATABASE_URL`,
`ITOPS_CORS_ORIGINS`, `ITOPS_JWT_SECRET`, and `ITOPS_ATTACHMENT_CLAMAV_HOST`. Set the exact HTTPS
origin in `ITOPS_CORS_ORIGINS`, `ITOPS_ATTACHMENT_CLAMAV_HOST=clamav`,
`ITOPS_ATTACHMENT_SCAN_REQUIRED=true`, `ITOPS_SECURE_COOKIES=true`,
`ITOPS_AI_PROVIDER=disabled`, and `ITOPS_ENVIRONMENT=production`. Do not set an external AI key or
deploy an endpoint agent. `VITE_API_BASE_URL` remains `/api/v1` at frontend build time. Pin all
container images to reviewed versions/digests before deployment. No credential belongs in Git,
container images, or browser assets.

The checked-in release workflow builds the API and frontend Dockerfiles for `linux/amd64` and
publishes to GHCR when explicitly triggered. The example file pins both application images to
registry-reported OCI index digests from release workflow run 37201620316. Copy those exact
`ITOPS_API_IMAGE` and `ITOPS_FRONTEND_IMAGE` references into the restricted deployment environment
file, then validate the resolved Compose configuration. Do not substitute a guessed tag or digest.

Initialize while **ports 80/443 are still blocked** at the VPS firewall and before starting `tls`:

1. Start only `database`; verify its health. Run the one-shot `migrate` service to apply Alembic and
   base seeds. Provide initial-admin variables only for this bootstrap, then remove them.
2. For the fictional directory/workload, deliberately run a **one-time, private** container from
   the API image with `ITOPS_ENVIRONMENT=development` and an operator-supplied
   `ITOPS_ENTERPRISE_SEED_PASSWORD`, executing `python -m scripts.seed` followed by
   `python -m scripts.demo_seed`. Pass the secret through a temporary restricted environment file
   or shell environment, never as a literal command argument. This container starts no web server,
   has no published port, and must run only against this isolated, not-yet-public demo database.
   Remove the seed password immediately afterward. The public API and workers must always start
   in production mode. The seed's development/test guards remain unchanged and cannot run on an
   ordinary production restart. Do not re-run this initialization against a live demo database.

   On the VPS, after placing a restricted environment file outside the checkout, the operator's
   explicit initialization sequence is:

   ```bash
   docker compose --env-file /secure/itops.env -f docker-compose.prod.yml config --quiet
   docker compose --env-file /secure/itops.env -f docker-compose.prod.yml up -d database
   docker compose --env-file /secure/itops.env -f docker-compose.prod.yml run --rm migrate
   # Set ITOPS_ENTERPRISE_SEED_PASSWORD privately in this shell; do not put its value in history.
   docker compose --env-file /secure/itops.env -f docker-compose.prod.yml run --rm --no-deps -e ITOPS_ENVIRONMENT=development -e ITOPS_ENTERPRISE_SEED_PASSWORD migrate sh -c 'python -m scripts.seed && python -m scripts.demo_seed'
   unset ITOPS_ENTERPRISE_SEED_PASSWORD
   ```

   The second container is not a public application process; its environment override exists only
   for this operator-initiated seed, before ingress opens. Verify the output and remove bootstrap
   secrets before starting the public services.
3. Start `clamav`, `api`, `worker`, `monitoring-worker`, and `frontend`; verify internal health and
   scanner readiness. Then start `tls` and permit inbound 80/443 so Caddy can obtain a certificate.
   Caddy redirects HTTP to HTTPS, forwards the original host/protocol, and tunnels WebSockets to
   Nginx, which proxies `/api/` to FastAPI. Verify HTTPS and `/api/v1/health/ready` before issuing
   reviewer credentials. Never accept a login over HTTP.
4. Use the existing audited admin directory workflow to create separate reviewer accounts with
   independently chosen passwords and only the role each reviewer needs. **Never issue the shared
   enterprise-seed password**: it would unlock many fictional users. Keep Admin access operator-only.
   Test Employee, Technician, Manager, and Admin login privately; direct API RBAC denial; ticket
   and attachment workflows (including scanner failure); analytics; audit; and authenticated
   `wss://` reconnect. Give reviewers temporary credentials privately, disable them after use, and
   monitor/reset fictional mutations. This is controlled access, not an anonymous sandbox.

Named volumes retain PostgreSQL, private attachments, ClamAV signatures, and Caddy certificate
state across ordinary container restarts and `docker compose down`/`up` (without `-v`). This is not
a tested backup or restore guarantee. To tear down, close public ingress first, stop the stack,
and remove the dedicated demo volumes only after confirming their exact project name and that their
contents are disposable. Never use `down -v` against a database whose data should be retained.

For higher availability, use managed PostgreSQL, shared private attachment storage, an atomic shared
rate limiter, centralized logs/metrics, and an orchestrator with readiness/liveness probes. Do not
scale the current process-local rate limiter as though it were globally enforcing limits.

## Prerequisites

- Docker Engine with Compose v2 on a supported Linux host.
- A private ClamAV container with current signatures and a public DNS name for Caddy.
- Immutable API/frontend images from the release workflow and reviewed, pinned ClamAV/Caddy images.
- A backup target outside the deployment host.
- A secret manager or host service manager that can render a root-readable environment file outside
  the checkout.

## First deployment

For a **hosted portfolio demo**, use the private initialization order above. Do not use the
single `up -d` command below as the first step before fictional initialization and TLS checks.
The sequence below is a general reference for an already prepared environment.

1. Copy `.env.production.example` outside the repository and replace every placeholder. Use an exact
   HTTPS origin in `ITOPS_CORS_ORIGINS`; wildcards and URL paths are rejected.
2. Keep `ITOPS_API_IMAGE` and `ITOPS_FRONTEND_IMAGE` pinned to reviewed OCI digests.
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

Caddy is the internet-facing TLS layer in the Compose reference. It passes the original `Host` and
`X-Forwarded-Proto=https` to Nginx and supports WebSocket upgrades for `/api/v1/realtime/ws`.
Nginx retains the existing API/WebSocket routing and security headers. Caddy redirects HTTP to
HTTPS. Secure cookies and HSTS remain enabled in production mode. The host operator remains
responsible for DNS, certificate issuance, firewall rules, logs, and abuse controls.

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
