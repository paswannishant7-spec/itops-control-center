# Audit and security hardening

## Consolidated audit trail

`GET /api/v1/audit/events` requires the live, database-derived `audit:view` grant. It merges role
assignment, directory, ticket, SLA, knowledge, asset, alert, and AI review events into one newest-
first contract. Administrators can filter by source, exact normalized action, entity UUID, actor
UUID, and inclusive timestamps, with a maximum page size of 100 and a bounded offset of 10,000.

Every result identifies its source, action, entity, actor when applicable, reason, request ID when
available, before/after state, and timestamp. Automated SLA events are explicitly system-authored.
AI review events expose only output type and confidence; feedback and edited response text are not
returned. A recursive final-output guard replaces values whose keys indicate passwords, tokens,
secrets, authorization, cookies, or API keys.

Audit ORM objects are append-only. A synchronous SQLAlchemy `before_flush` guard rejects updates
and deletes in every API/worker process. Migration `20260913_0016` adds PostgreSQL `BEFORE UPDATE OR
DELETE` triggers for the same role, directory, ticket, SLA, knowledge, asset, alert, AI interaction,
and AI feedback records. Direct database clients therefore cannot bypass the application guard.
Downgrading removes the triggers and should occur only in a controlled maintenance window.

## HTTP and browser boundary

API responses carry `nosniff`, frame denial, no-referrer, restrictive permissions policy, and an
API-oriented content security policy. `/api/*` responses are marked `no-store`; production responses
also carry one-year HSTS with subdomains. The static frontend server applies a SPA-specific CSP and
the corresponding browser headers. Its checked-in `connect-src` permits only same-origin and the
local API/WebSocket endpoints; a split-origin production deployment must replace those two local
origins with its exact HTTPS/WSS API origins. TLS must terminate before either service in production.

CORS accepts exact HTTP(S) origins only. Credentials, paths, query strings, fragments, wildcards,
and normalized duplicates are rejected at startup. Credentials remain enabled because refresh
tokens use an HttpOnly, SameSite=Strict, path-scoped cookie.

## Authentication throttling

Login and refresh endpoints use separate bounded sliding-window limiters. Keys combine source IP
with a SHA-256 digest of the normalized email or refresh token, keeping credentials out of limiter
keys. Rejections return `429` and `Retry-After`. The limiter is process-local; deployments with more
than one API replica must replace it with a shared, atomic limiter at the edge or in Redis.

## Upload controls

Existing byte, extension/MIME, signature, UTF-8, NUL-byte, randomized-key, path-containment, and
record-authorization checks run before storage. When `ITOPS_ATTACHMENT_CLAMAV_HOST` is configured,
the validated bytes are sent over ClamAV's bounded INSTREAM protocol before any write. Malware is a
controlled `422`; scanner transport or protocol failure is a fail-closed `503`.

Set `ITOPS_ATTACHMENT_SCAN_REQUIRED=true` with a reachable private scanner in production. Settings
validation prevents required scanning without a host. ClamAV connectivity must remain on a trusted
network and its signature updates, capacity, monitoring, and quarantine policy are deployment
responsibilities.

## AI boundary and prompt injection

Every generative/classification request has a shared high-priority policy: all `untrusted_*` fields
are inert data, embedded role/override instructions are ignored, hidden context and secrets are not
revealed, actions are neither executed nor claimed, and only the strict requested JSON schema may be
returned. User/ticket/knowledge content remains JSON-separated from provider instructions.

This is defense in depth with existing credential redaction, data minimization, bounded retrieval,
taxonomy/citation allowlists, schema validation, external storage disabled, content-free interaction
logs, and human review. Prompt injection cannot be treated as perfectly detectable; no AI output is
authorized to mutate operational records automatically.

## Supply-chain checks

CI runs `npm audit --omit=dev --audit-level=high` and pinned `pip-audit` after clean dependency
installation. Dependabot checks npm, pip, Docker, and GitHub Actions weekly. These checks detect
disclosed package advisories; they do not replace lockfile review, image scanning, provenance,
secret scanning, or deployment vulnerability management.
