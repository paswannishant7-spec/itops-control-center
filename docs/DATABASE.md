# Database architecture

## Runtime

PostgreSQL 17 is the system of record. The local and CI image includes pgvector. SQLAlchemy 2 provides typed ORM and Core APIs, Psycopg 3 provides the async PostgreSQL driver, and Alembic owns schema changes.

Step 5/6 subsequently exercised Alembic migrations and application tests against a disposable live PostgreSQL stack, including persistence after Compose restart. The phase-by-phase notes below describe what was known when each revision was introduced; earlier "pending" statements are superseded by that later verification. Detailed constraint inspection, downgrade rehearsal, and concurrent multi-worker behavior are not claimed complete.

The application uses `postgresql+psycopg` URLs. Credentials are represented as Pydantic `SecretStr` values and must not be logged. Connection pools use pre-ping and bounded size, overflow, wait time, and connection timeout.

## Migration policy

- Schema changes are made only through reviewed Alembic revisions.
- CI upgrades an empty PostgreSQL database to `head` and runs `alembic check`.
- Constraint names are deterministic, allowing safe future alterations.
- Migrations should support an expand/migrate/contract deployment sequence.
- Destructive changes require a backup/restore and rollback plan.
- The initial revision enables `pgcrypto` and `vector`; downgrade deliberately leaves shared extensions installed.

Commands:

```bash
cd backend
alembic upgrade head
alembic check
alembic downgrade -1
```

`alembic downgrade -1` validates migration mechanics in disposable environments only. It is not a production rollback strategy.

## Model conventions

- UUID primary-key mixin uses application-generated UUIDs.
- Timestamp mixin uses timezone-aware database timestamps; application services must normalize user input to UTC.
- Table, index, unique, check, foreign-key, and primary-key constraints use deterministic names.
- ORM models do not own transaction commits. Application services will use the shared transaction context.

## Seed architecture

`app.db.seeds.seed_registry()` lists deterministic seeds in foreign-key dependency order. Every seed added by a domain phase must use stable natural identifiers or upserts and remain safe to rerun. Phase 2 intentionally has no business seed data.

Run:

```bash
python -m scripts.seed
```

## Phase 4 access schema

Revision `20260908_0003` adds `roles`, `permissions`, `role_permissions`, `user_roles`, and `role_assignment_events`. The revision freezes the initial four-role/60-permission matrix so future code changes cannot alter historical migration behavior. Assignment and grant tables use composite keys and restrictive foreign keys; assignment history records actor, target, before/after role codes, reason, request ID, and timestamp. JSON is limited to historical snapshots, not live memberships.

Normal runtime does not recreate catalog mappings or elevate existing accounts. See [bootstrap and upgrade](RBAC.md#bootstrap-and-upgrade). Downgrading this revision removes access data and history and is only appropriate for disposable migration verification. The later Step 5/6 PostgreSQL migration run supersedes the original offline-only acceptance boundary; a complete schema comparison is not claimed.

## Phase 5 directory schema

Revision `20260909_0004` creates `departments`, `locations`, `teams`, `team_members`, and append-only application event rows in `directory_events`. It adds nullable employee number, job title, department, and location fields to existing users so populated Phase 4 databases can upgrade without fabricated organization data. Department, location, team, employee-number, and membership access paths have explicit indexes and constraints.

Team membership is an interval, not a replaceable join row: each record has `started_at` and nullable `ended_at`. A PostgreSQL partial unique index permits only one active interval for a user/team pair, while preserving earlier assignments. Services end active intervals instead of deleting them. Department, location, and team records are soft-deactivated; referenced departments or locations cannot be retired while active users or teams still depend on them.

The same revision adds `department:view`, `department:manage`, `location:view`, and `location:manage` plus frozen system-role mappings, bringing the current catalog to 64 permissions. The downgrade removes all Phase 5 data and fields and is appropriate only for disposable migration verification. Step 5/6 exercised the online PostgreSQL upgrade; exhaustive constraint inspection, downgrade rehearsal, and concurrency checks remain unverified.

## Phase 6 ticket schema

Revision `20260909_0005` creates `ticket_categories`, `ticket_subcategories`, `tickets`, `ticket_comments`, `ticket_attachments`, `ticket_events`, and `ticket_assignments`. Ticket rows retain the requester organization snapshot, impact, urgency, calculated priority, controlled status, current assignment, category/asset links, lifecycle timestamps, and resolution fields. Revision `20260912_0012` adds the Phase 13 restrictive asset foreign key.

Comments distinguish public messages from internal notes. Attachment rows store private object keys, original names, inspected MIME type, byte size, and SHA-256 digest—not file bytes. Assignment rows are historical intervals protected by a PostgreSQL partial unique index allowing one active assignment per ticket. Event rows retain bounded before/after operational state, reason, actor, request ID, and timestamp.

The schema indexes status, priority, requester, team, technician, department, location, asset, category, subcategory, and chronological ticket access paths. The downgrade destroys all Phase 6 ticket data and is only suitable for disposable verification. Step 5/6 exercised the online PostgreSQL migration and ticket flows; full schema comparison, partial-index inspection, and concurrency checks are not claimed complete.

## Phase 7 SLA schema

Revision `20260909_0006` creates `priority_matrix`, `business_calendars`, `business_windows`, `business_holidays`, `sla_policies`, `sla_instances`, `sla_pauses`, and `sla_events`. It seeds a complete configurable priority matrix, a UTC 24x7 default calendar, and P1–P4 example policies. Existing tickets are backfilled with policy snapshots during upgrade; future tickets create their instance transactionally.

Partial unique indexes permit one default calendar, one active policy per priority, and one active pause per SLA instance. SLA events use a globally unique idempotency key so repeated worker evaluation cannot duplicate a milestone or outbound-notification intent. Policy targets are snapshotted onto instances; pauses remain historical intervals. The downgrade destroys all Phase 7 SLA configuration and history and is appropriate only for disposable verification.

## Phase 8 knowledge schema

Revision `20260909_0007` creates `knowledge_categories`, `knowledge_articles`, `knowledge_article_versions`, and `knowledge_events`. Normalized unique indexes protect category codes/names and article slugs. Article status/category/owner/author and chronological workflow access paths are indexed.

Version rows are append-only through the application contract and unique on article plus version number. Article current/published pointers reference concrete version rows, while the version retains its source article and author. Publication and lifecycle events are written transactionally. The downgrade destroys knowledge content and history and is suitable only for disposable verification. Phase 10 adds derived chunk/vector tables separately.

## Phase 9 AI classification schema

Revision `20260910_0008` creates `ai_interactions` and `ai_recommendations`. Interactions retain operational metadata, a non-reversible request fingerprint, attempts, timing, token counts, and bounded failure codes without prompts or raw ticket text. Recommendations retain only Pydantic-validated output and confidence.

Both tables use restrictive ticket/user/interaction foreign keys so support history cannot disappear through cascades. A one-to-one interaction/recommendation constraint and ticket chronology indexes support latest-result reads. Status, task, source, output type, confidence, attempts, and latency are database-constrained.

## Readiness

Liveness is independent of PostgreSQL. Readiness performs a bounded `SELECT 1` probe and returns HTTP 503 with `not_ready` when the database is unavailable. The error is not exposed to the client.

## Phase 10 RAG schema

`knowledge_chunks` stores deterministic, content-hashed pieces of an immutable knowledge version,
with unique version ordinals and article/version lookup indexes. `knowledge_embeddings` stores a
provider/model-specific 1,536-dimensional vector per chunk, prevents duplicate embeddings for the
same provider/model, and has a PostgreSQL HNSW cosine index. AI interaction/recommendation task
constraints now include `TROUBLESHOOTING`; validated recommendations retain server-derived citation
payloads while interaction records remain content-minimized.

## Phase 11 similar-ticket schema

Revision `20260910_0010` adds `ticket_embeddings`, one provider/model-specific vector per source
ticket. Each record carries a representation hash and source update timestamp so unchanged vectors
can be reused and stale vectors replaced. The table fixes vectors at 1,536 dimensions, enforces
ticket/provider/model uniqueness, and adds an HNSW cosine index for PostgreSQL ranking. The source
ticket foreign key cascades on ticket deletion; the embedding never substitutes for the ticket's
authorization or resolution record.

## Phase 12 assistant feedback schema

Revision `20260911_0011` extends AI interaction and recommendation type constraints for response
drafts and summaries. `ai_feedback` records one immutable technician decision per recommendation,
including the interaction, ticket, actor, action, output type, confidence snapshot, optional bounded
note, optional edited content, and UTC timestamp. Database checks require edited content only for an
`EDITED` decision. Restrictive foreign keys retain the review trail, while ticket/chronology, actor,
and action indexes support later operational analytics.

## Phase 13 asset schema

Revision `20260912_0012` creates `assets`, `asset_assignments`, and `asset_events`. Normalized unique
indexes protect asset tags and non-null serial numbers. Asset type, lifecycle, health, warranty
interval, and assignment interval constraints reject invalid state. Owner, department, location,
type, status/health, and chronological history access paths are indexed.

Assignments preserve temporal custody and a partial unique index allows only one active interval per
asset. Restrictive user/directory/asset foreign keys preserve history. The revision also converts
`tickets.asset_id` into a restrictive relationship so referenced assets cannot be deleted while
support history exists.

## Phase 14 monitoring schema

Revision `20260913_0013` adds one `device_agents` identity per asset, append-only
`device_heartbeats`, and sampled `device_metrics`. Agent rows contain state, credential/token hashes,
non-secret display prefix, enrollment timestamps, latest activity, and missed-heartbeat count. Raw
credentials and enrollment tokens are never persisted.

Restrictive asset and agent foreign keys preserve inventory relationships. Enumerated status and
credential checks, non-negative counts/counters, valid metric percentages, used/total invariants,
unique credential/token digests, and agent/time indexes protect ingestion and cleanup paths. The
monitoring worker removes expired heartbeat and metric rows according to configured retention. The
downgrade destroys monitoring history and credentials and is suitable only for disposable migration
verification.

## Phase 15 alerts and automation schema

Revision `20260913_0014` adds `alert_policies`, `alerts`, `alert_events`, `automation_rules`,
`automation_executions`, `notification_preferences`, and `notifications`. It also adds the ticket
record type and expands ticket source values so deterministic automation can create first-class
`INCIDENT` records with `AUTOMATION` provenance.

A partial unique index permits one active alert per policy/device, and a rule/alert unique constraint
permits one execution attempt per pair. Notification dedupe prevents repeated delivery for the same
alert and recipient. Restrictive foreign keys preserve policy, asset, agent, rule, team, ticket, and
user relationships. Check constraints enforce enumerated metric/operator/severity/state/action values,
valid thresholds, non-negative observations, and preference bounds. Five conservative default
policies are seeded by migration. The downgrade removes Phase 15 data and reverses the ticket enum
expansion; it is suitable only for disposable migration verification.

## Phase 16 real-time schema

Revision `20260913_0015` creates `realtime_events` and the singleton `realtime_cursor`. Domain
transactions append unpublished, content-free signals. The publisher locks the cursor and assigns
unique contiguous sequence values to committed rows in bounded `SKIP LOCKED` batches. Topic,
sequence, recipient, resource, and creation-time indexes support polling, authorization filtering,
and retention cleanup.

Topic and cursor checks constrain protocol state; the optional recipient has a restrictive user
foreign key. Resource IDs remain intentionally polymorphic and are resolved through the owning
ticket, SLA, alert, or monitoring repository before delivery. The downgrade removes the transient
delivery feed and is suitable only for disposable migration verification.

## Phase 17 analytics reads

Phase 17 adds no tables or denormalized counters. Analytics read indexed source-of-record fields
from tickets, SLA instances, device agents, assets, alerts, and AI feedback within a maximum 365-day
window. Formula definitions, population boundaries, and future aggregation thresholds are recorded
in [the analytics contract](ANALYTICS.md).

## Phase 18 audit immutability

Revision `20260913_0016` creates one PostgreSQL trigger function and attaches `BEFORE UPDATE OR
DELETE` triggers to role assignment, directory, ticket, SLA, knowledge, asset, alert, AI interaction,
and AI feedback histories. Inserts remain transactional with their domain mutations. The application
duplicates this invariant with a SQLAlchemy flush guard so violations fail before SQL is emitted.
The consolidated audit endpoint is a read projection and adds no duplicate event table.

## Production operations

The production migration job is the only deployment component permitted to advance schema and run
idempotent seeds. API and workers wait for it to complete. Before every schema change, verify an
encrypted backup and rehearse the exact migration against a recent restored copy. `alembic check`
must be clean in CI; offline SQL is review evidence, not proof of online lock behavior.

Back up PostgreSQL and the private attachment volume as one recovery unit. Define and monitor RPO,
RTO, backup age, retention, encryption, and off-host replication. Restore drills must verify the
Alembic head, extension availability, constraints/indexes/triggers, representative scoped reads,
attachment digests, and API readiness. Database credentials use a least-privilege runtime role; a
separate controlled migration role is recommended when the platform supports it.

Capacity monitoring includes database/volume disk, connection pool wait/exhaustion, long
transactions, lock waits, query latency, table/index growth, realtime backlog, telemetry retention,
and vector-index size. Scale or introduce derived analytics storage only after measured query plans
justify it.
