# Architecture

## Current system view

```text
Browser --HTTPS/WSS--> TLS edge --> Nginx SPA + same-origin /api proxy --> FastAPI
                                                                       |--> PostgreSQL 17 + pgvector
Endpoint agent --HTTPS-------------------------------------------------|
                                                                       |--> private attachment volume
SLA worker -----------------------------------------------------------> PostgreSQL
Monitoring/alert worker ---------------------------------------------> PostgreSQL
Optional AI provider <---------------- minimized, redacted requests --- FastAPI
Optional ClamAV <---------------------- private INSTREAM scan -------- FastAPI
```

The deployable units are the static React SPA/proxy, FastAPI API, SLA worker, monitoring worker, and
endpoint agent. PostgreSQL is the source of truth and realtime delivery uses a transactional outbox.
The workers share application code and database invariants but run as independent processes. The
reference production topology performs migrations in a one-shot gate before starting API/workers.

The browser never receives provider, database, device-agent, or malware-scanner credentials. The
frontend hides unavailable actions for usability, while the API independently authenticates,
authorizes, scopes, validates, and audits every operation.

## Application boundaries

The static React SPA and FastAPI API use an application factory, central settings, request context middleware, structured logging, controlled errors, explicit CORS, and versioned routes. PostgreSQL-backed services and workers are present in the current implementation; earlier phase-by-phase notes below describe their design history, not unfinished work.

## Dependency direction

```text
frontend feature -> shared frontend API client -> HTTP API
API router -> schema -> service/domain -> repository
core configuration/middleware <- API assembly
```

Route handlers remain thin. Application services own database commits; infrastructure SDK types do not cross into domain interfaces.

## Health semantics

- Liveness confirms the API process can serve requests.
- Readiness performs a bounded database `SELECT 1` and returns `503 not_ready` when PostgreSQL is
  unavailable. Liveness remains independent of database health.

## Error contract

Unhandled failures and validation failures use `application/problem+json`, a stable error code, and the request ID. Raw exceptions and database errors are never returned to clients.

## Logging

Logs are structured and correlated by request ID. Production selects JSON output. Request bodies, authorization headers, cookies, tokens, and secrets are excluded.

## Phase 4 authorization boundary

The access module separates permission catalog, persistent grants, resource-scope policy, service operations, and HTTP dependencies. Authentication resolves the active identity; `require_permission` resolves current database grants. JWT role claims and frontend route hiding are not authorization authorities.

The access-management UI uses real API requests. Changes are committed with bounded-reason audit events. System-role definitions stay migration-controlled; assignment changes are the supported administrative workflow. Record-scope policy is implemented and tested. Phase 5 provides database-derived active team IDs; ticket and asset resources must consume that scope when introduced. See [the matrix and API contracts](RBAC.md).

## Phase 5 directory boundary

The directory module owns departments, locations, teams, membership history, organization-facing user management, and its transactional event stream. Identity remains responsible for credentials and refresh sessions; access remains responsible for system roles and action permissions. A team `MEMBER` or `LEAD` designation is operational metadata and never grants a system permission.

Only active users with an explicit `TECHNICIAN` or `IT_MANAGER` system role can hold an active team membership. Ending a membership preserves history and immediately removes that team from future record scope. Disabling or locking an account ends all active memberships and revokes every refresh session. Directory, access, and identity changes share transaction and lock-order rules so authorization is rechecked immediately before privileged writes.

The frontend directory feature uses the shared bearer-aware API client, runtime response validation, server-side filters, stable pagination, explicit empty/error/success states, and permission-aware controls. UI visibility is convenience only; every operation is independently authorized by the API. See [the directory contract](DIRECTORY.md).

## Phase 6 ticket boundary

The tickets module owns intake, current ticket state, comments, attachment metadata, assignment history, state transitions, and the event timeline. Routers validate and translate HTTP; services own authorization-sensitive business rules and transaction commits; repositories apply scope and filters in SQL. Ticket descriptions and comment bodies do not enter event snapshots.

Visibility is a database predicate, not an in-memory post-filter. An employee sees owned requests. A technician sees directly assigned work, active-team work, and unassigned work whose requester department is covered by an active team. Managers and administrators receive all-ticket access only through `ticket:view_all`. Mutation permissions remain separate from visibility.

Assignment history uses temporal rows and one active interval. Status changes pass through a legal transition graph and every successful change appends an event in the same transaction. The deterministic Phase 6 impact/urgency baseline was replaced by Phase 7's configurable priority policy and SLA instances.

## Phase 7 priority and SLA boundary

Priority selection now reads the persisted nine-cell matrix; missing configuration fails ticket creation instead of silently applying an unapproved default. A ticket receives an SLA instance in its creation transaction. The instance snapshots response/resolution targets and risk threshold from the active priority policy while retaining the referenced business calendar.

Business-time calculation is a pure timezone-aware service over weekly windows, holidays, and persisted pause intervals. Ticket transitions open/close pause intervals and technician first response/resolution milestones update the instance in the same ticket transaction. A separate database-polling worker claims bounded batches with PostgreSQL `SKIP LOCKED`, recomputes clocks from source timestamps, and writes idempotency-keyed risk, breach, escalation, completion, and notification events. This design is safe to retry and does not require Redis before a queued workload exists.

Attachment bytes are behind a storage abstraction and never mounted into the public web server. The first implementation uses private local/volume storage with randomized keys, size limits, extension/MIME agreement, content-signature checks, and an authorized download endpoint. Metadata and event writes are transactional; a failed database write removes the newly stored object. See [the ticket contract](TICKETS.md).

## Phase 8 knowledge boundary

The knowledge module owns categories, article identity/workflow state, immutable content versions, permission-scoped search, and a transactional event stream. Article rows point to the current version and, after publication, the exact released version. Services alone create versions and transitions; repositories enforce visibility and pagination in SQL.

Readers see published content only. Authors additionally see their own drafts and review submissions. Review/publish/archive grants broaden workflow visibility without creating an authorization bypass. Content is returned as inert text; raw article HTML is never executed. Phase 10 derives chunks and embeddings from published versions while preserving the source article/version relationship. See [the knowledge contract](KNOWLEDGE.md).

## Phase 9 AI classification boundary

The AI module separates provider transport, validated schemas, orchestration, persistence, and HTTP routing. Provider-specific request formats never enter ticket services or frontend code. The service reads an already-authorized ticket, minimizes and redacts its fields, supplies only active taxonomy, validates returned IDs/names/enums/bounds, and writes one interaction plus one recommendation transactionally.

Classification is a read/advice path: it cannot update the ticket. Provider and validation failures converge on a persisted safe fallback. The OpenAI adapter uses strict structured output and `store: false`; the default disabled adapter allows deterministic operation without a secret. See [the AI classification contract](AI_CLASSIFICATION.md).

## Phase 10 retrieval-augmented generation

The RAG pipeline indexes only the immutable version selected by a published article. Deterministic,
credential-redacted chunks map one-to-many to provider/model embeddings. PostgreSQL performs bounded
cosine retrieval through pgvector and an HNSW index, with publication and embedding-model filters in
the query. The answer service receives only retrieved chunks, validates cited chunk IDs against that
retrieval set, and derives citation metadata from database rows. See [the RAG contract](RAG.md).

## Phase 11 similar ticket intelligence

The similarity pipeline derives credential-redacted representations from ticket title and
description only, then reuses provider/model vectors while that representation hash remains stable.
Candidate preparation and final vector ranking both apply the existing own/team/all ticket SQL
predicate. Only resolved or closed tickets with recorded resolutions can appear, and the current
ticket is excluded. Resolution and lifecycle metadata are loaded from authorized database rows;
provider output supplies vectors, not diagnoses or resolution text. See [the Similar Tickets
contract](SIMILAR_TICKETS.md).

## Phase 12 AI technician assistant

The assistant adds schema-validated response drafts and ticket summaries to the existing grounded
troubleshooting path. Its context builder includes bounded, redacted public conversation without
identities or internal notes. Interactions and recommendations remain immutable advice records.
Technician review creates a separate one-to-one feedback record; accepting or editing a response
only stages text in the browser's reply composer and cannot post or mutate a ticket. Globally
aggregated feedback metrics require analytics permission and all-ticket scope. See [the assistant and
feedback contract](AI_TECHNICIAN_ASSISTANT.md).

## Phase 13 asset boundary

The assets module owns hardware identity, current custody, assignment intervals, lifecycle state, and
the asset audit stream. Repositories apply own/team/all predicates in SQL: owners see their current
assets, technicians add departments covered by active support teams, and managers/administrators
with `asset:view_all` see the catalog. Services independently require write grants and serialize
custody changes on the asset row.

Ticket relationships cross the boundary only by asset UUID. Ticket create/update asks the asset
service to authorize and validate a non-terminal target, while the database now enforces a
restrictive foreign key. Asset-linked ticket reads independently apply ticket visibility, preventing
asset access from widening ticket disclosure. See [the asset contract](ASSETS.md).

## Phase 14 monitoring boundary

The monitoring module owns device enrollment, per-agent authentication, heartbeats, bounded raw
metrics, credential status, and derived availability state. A separately packaged Python/psutil
agent only gathers privacy-minimized aggregate host data. It uses a stable locally persisted agent ID
and a unique revocable credential; user JWTs and a fleet-wide embedded secret are never used for
device ingestion.

Enrollment and operator reads reuse asset authorization. Agent list and detail queries apply the
asset own/team/all predicate in SQL, while credential issuance and revocation require
`monitoring:manage`. A database-polling monitoring worker uses bounded, lock-safe batches to derive
offline state and prune expired raw telemetry. Phase 15 consumes accepted samples and reconciled
device state through the alerts module. See [the monitoring agent contract](MONITORING_AGENT.md).

## Phase 15 alerts and automation boundary

The alerts module owns threshold policy, alert identity and lifecycle, deterministic automation
rules, execution history, notification preferences, and in-app notifications. Monitoring invokes
the service only after authenticated ingestion or reconciliation; routers never duplicate the
evaluation logic. Alert reads reuse asset own/team/all SQL scope, while acknowledgement, resolution,
suppression, and configuration remain separately permissioned.

Active alerts are unique per policy and device. Repeated matching observations update one alert;
recovery resolves it; later recurrence creates a new alert. Each automation rule executes at most
once per alert. Incident actions reuse ticket assignment, event, priority, and SLA models in the
same transaction, while per-rule savepoints isolate failures. Automation is a fixed action set—not
an LLM or user-supplied program. Notifications are persisted behind an independent service; realtime
WebSocket transport is supplied by Phase 16. See [the alerts and automation
contract](ALERTS_AUTOMATION.md).

## Phase 16 real-time boundary

The real-time module is an authenticated invalidation layer over existing HTTP resources. Domain
events create content-free outbox rows inside their existing transactions. A serialized publisher
assigns sequences only after those rows are committed, avoiding cursor gaps across API and worker
transactions. WebSocket connections poll the shared PostgreSQL feed, so SLA and monitoring worker
changes reach any API replica without process-local coordination.

Delivery repeats live-session validation and applies the ticket, asset, alert, internal-note, and
recipient predicates before emitting each signal. The browser then invalidates the affected TanStack
Query keys and reloads data through the normal API. Connection readiness, reconnection, backlog, and
access-change frames cause broader HTTP resynchronization. See [the real-time
contract](REALTIME.md).

## Phase 17 analytics boundary

The analytics module is a read-only projection over the established ticket and asset access
predicates. It owns formulas, UTC calendar bucketing, ranking, and response shaping but stores no
duplicate operational data. One bounded dashboard read supplies technician team scope and manager
organization scope; Phase 16 signals trigger an authorized HTTP recomputation. See [the formula
contract](ANALYTICS.md).

## Phase 18 audit and security boundary

The audit module normalizes existing append-only domain histories rather than introducing a second
source of truth. It owns cross-domain filtering, pagination, secret-key redaction, and the admin-only
response contract; each domain continues to own creation of its events. Application flush guards and
database triggers enforce immutability independently. HTTP headers, exact CORS validation, identity
throttling, upload scanning, and shared AI untrusted-data instructions remain at their respective
transport boundaries. See [the audit and security contract](AUDIT_SECURITY.md).

## Decisions

- React Router and TanStack Query are configured at the shell boundary for future feature routes and server state.
- The frontend error boundary provides a controlled recovery path.
- Configuration is environment-driven and validated by Pydantic settings.
- `/api/v1` establishes API versioning before domain endpoints exist.
