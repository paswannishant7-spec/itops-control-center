# Ticket Core — Phase 6

## Scope and lifecycle

Phase 6 implements ticket intake, scoped queues, detail, public conversation, internal notes, protected attachments, current and historical assignment, legal state transitions, resolution, and an event timeline. Phase 7 adds configurable priority/SLA behavior. Phases 9–12 add advisory classification, knowledge-grounded troubleshooting, similar-ticket intelligence, and technician assistance. Phase 13 adds validated asset relationships. Phase 15 adds automated incident records and in-app alert notifications. Problem/change records, tags, watchers, external notification delivery, and realtime delivery remain in their scheduled phases.

Human portal intake creates `record_type=REQUEST` tickets with `source=PORTAL`. Deterministic alert
automation creates `record_type=INCIDENT` tickets with `source=AUTOMATION`; these use the same
assignment, priority, SLA, visibility, workflow, and audit invariants as requests and retain the
originating alert relationship. See [the alerts and automation contract](ALERTS_AUTOMATION.md).

Tickets begin in `NEW`. Impact and urgency accept `LOW`, `MEDIUM`, or `HIGH`; the persisted priority matrix selects `LOW`, `MEDIUM`, `HIGH`, or `CRITICAL`. Ticket creation fails closed if its matrix cell or active SLA policy is absent. See [the SLA contract](SLA.md).

Legal transitions are:

```text
NEW -> OPEN
OPEN -> IN_PROGRESS | CANCELLED
IN_PROGRESS -> PENDING_USER | PENDING_VENDOR | ESCALATED | RESOLVED
PENDING_USER -> IN_PROGRESS
PENDING_VENDOR -> IN_PROGRESS
ESCALATED -> IN_PROGRESS
RESOLVED -> CLOSED | OPEN
CLOSED -> terminal
CANCELLED -> terminal
```

Advancing beyond `NEW` requires an assignment except for cancellation. Resolution requires a summary and code. Reopening clears the active resolution fields, preserves the earlier state in the timeline, and records `reopened_at`. Closed or cancelled tickets cannot be edited, assigned, commented on, or receive attachments.

## Authorization and visibility

Action permission and record visibility are independent requirements:

- `ticket:view_own` exposes tickets where the caller is requester.
- `ticket:view_team` exposes directly assigned tickets, tickets assigned to the caller's active teams, and unassigned tickets in departments covered by those teams.
- `ticket:view_all` exposes all tickets.
- `ticket:update`, `assign`, `reassign`, `escalate`, `resolve`, `close`, and `reopen` control their corresponding mutations.
- `ticket:comment` permits a public reply or attachment on a visible non-terminal ticket.
- `ticket:internal_note` additionally permits internal notes and reveals them in comment queries.

All scope is applied in database queries. Authorization occurs before object-specific disclosure, so inaccessible and absent IDs both produce a 404 after the caller has passed the relevant action gate. A technician without `ticket:view_all` may assign only to one of their active teams. A selected technician must be an active team member with an explicit `TECHNICIAN` or `IT_MANAGER` system role.

## API

Base path: `/api/v1/tickets`.

| Method and path | Purpose |
|---|---|
| `POST /` | Create a request for the authenticated caller (`ticket:create`) |
| `GET /` | Scoped search/filter/pagination |
| `GET /{id}` | Scoped detail |
| `PATCH /{id}` | Update editable ticket data (`ticket:update`) |
| `PUT /{id}/assignment` | Assign/reassign team and optional technician |
| `POST /{id}/transitions` | Apply a legal permission-specific transition |
| `GET/POST /{id}/comments` | Paginated conversation/add message |
| `GET/POST /{id}/attachments` | List/upload private attachments |
| `GET /{id}/attachments/{attachment_id}` | Authorized download |
| `GET /{id}/events` | Paginated chronological timeline |
| `GET /categories` | Active category/subcategory choices |

Ticket list filters include keyword, status, priority, team, technician, department, asset, and timezone-aware created range. Pagination is stable, server-side, and capped at 100 rows. Category administration is deferred; the read endpoint may legitimately return an empty list on a fresh database.

## Attachments

Uploads use the request body as raw bytes with a `filename` query parameter and a declared `Content-Type`, avoiding a multipart parser dependency. Allowed files are PNG, JPEG, GIF, PDF, UTF-8 text, Markdown, CSV, JSON, and logs. The service checks configured size, safe basename, extension/MIME agreement, and content signature or UTF-8 validity. It stores bytes under a randomized private key and records size and SHA-256 metadata.

The default limit is 10 MiB and may be configured from 1 KiB through 25 MiB. `docker compose` mounts `attachment_data` at `/var/lib/itops/attachments`. Direct runs default to `.data/attachments`. The frontend never receives a public file path; download always includes bearer authorization and ticket scope.

This inspection is not antivirus scanning. Production deployment must add malware quarantine/scanning, object-store retention and encryption policy, backup/restore, and orphan reconciliation.

## Events and transactions

Ticket creation, edits, assignment, status changes, comments, and attachments append a ticket event. Events store actor, request ID, bounded operational before/after state, reason, and timestamp. Descriptions and comment bodies are excluded. Assignment changes close the previous interval and create the next interval atomically. A failed event/database write rolls back the business change; failed attachment metadata writes also remove the new storage object.

## UI

`/tickets` provides intake, keyword/status/priority filters, server pagination, and a permission-scoped queue. `/tickets/{id}` provides an information-dense support workstation with request context, requester details, assignment, legal next actions, conversation, private notes, attachments, resolution, timeline, and permission-gated advisory AI panels. The similar-ticket panel shows only authorized resolved history and labels semantic similarity as supporting evidence rather than an exact diagnosis. The assistant panel generates reviewable response drafts and summaries; approving a draft fills the editable reply composer but cannot submit it. Status and priority always include text, not color alone. Every asynchronous region has a loading, empty, error, retry or success state where applicable.

## Acceptance boundary

Local SQLite integration tests, direct service tests, frontend component tests, lint/type/build gates, and offline PostgreSQL migration generation pass. Full acceptance still requires online PostgreSQL migration/schema and concurrency checks, Docker volume persistence, a live employee/technician/admin browser journey, and production attachment security controls.
## Asset relationships

Phase 13 converts `tickets.asset_id` from an indexed placeholder UUID into a restrictive foreign key
to the asset catalog. Ticket create/update validates that the caller can see the selected asset and
that it is not retired or disposed. Unlinking remains permitted on editable tickets. Asset detail
lists only linked tickets that independently pass the caller's existing ticket scope.
