# Priority and SLA Engine — Phase 7

## Configuration

The nine-cell `priority_matrix` maps `LOW`, `MEDIUM`, and `HIGH` impact/urgency pairs to `LOW`, `MEDIUM`, `HIGH`, or `CRITICAL`. Ticket creation and material impact/urgency edits read this table; missing policy fails closed. Migration defaults reproduce the documented P1–P4 examples but runtime business logic contains no target durations.

Each active SLA policy owns a priority, business calendar, response target, resolution target, and at-risk percentage. Only one active policy may exist per priority. Creating another active policy retires the earlier policy. Existing instance target values remain snapshotted; a ticket priority change applies the current active policy.

Business calendars use IANA timezone names, weekly windows expressed as minutes from the local day's midnight, and whole-day holidays. An end minute above 1440 represents an overnight window. Administrators can manage matrix rules, calendars, and policies at `/administration/sla` or through `/api/v1/sla`; technicians/managers have read-only configuration access.

## SLA clock

Every migrated or newly created ticket has one SLA instance. Response and resolution clocks both begin at ticket creation and accrue only calendar business seconds. The response clock stops at the first public technician response; internal notes do not satisfy the requester response target. Resolution stops at resolution/cancellation/closure. `PENDING_USER` and `PENDING_VENDOR` create pause intervals; leaving either state ends the interval. Reopening clears active SLA completion and resumes resolution timing without deleting history.

The displayed active target is response until first response, then resolution. State is one of `ON_TRACK`, `AT_RISK`, `BREACHED`, `PAUSED`, or `COMPLETED`. The snapshot includes elapsed/remaining seconds, percentage, breach timestamps, escalation time, calendar/timezone, and the worker's last evaluation time. Color is supplementary to state text.

## Worker and idempotency

`python -m scripts.sla_worker` polls bounded active-instance batches at the configured interval. PostgreSQL workers claim rows using `FOR UPDATE SKIP LOCKED`, recalculate from authoritative ticket timestamps and pause history, and persist state. At-risk, breach, resolution escalation, completion, and notification-intent events have deterministic unique keys. A retried cycle therefore updates the same instance without duplicating effects.

Compose runs the worker as a separate service. `ITOPS_SLA_WORKER_INTERVAL_SECONDS` defaults to 60 and `ITOPS_SLA_WORKER_BATCH_SIZE` to 100. SLA escalation is represented by `escalated_at` plus durable `sla.escalated` and notification-intent events; it does not bypass the ticket state machine. Outbound email/chat/in-app transport is intentionally deferred to the notifications/automation phase.

## API

| Method and path | Permission / scope |
|---|---|
| `GET /api/v1/sla/priority-matrix` | `sla:view` |
| `PUT /api/v1/sla/priority-matrix/{impact}/{urgency}` | `sla:manage` |
| `GET/POST /api/v1/sla/calendars` | `sla:view` / `sla:manage` |
| `PUT /api/v1/sla/calendars/{id}` | `sla:manage` |
| `GET/POST /api/v1/sla/policies` | `sla:view` / `sla:manage` |
| `PUT /api/v1/sla/policies/{id}` | `sla:manage` |
| `GET /api/v1/sla/tickets/{ticket_id}` | Existing ticket own/team/all scope |

Ticket list queries additionally accept `sla_state`. The worker is not exposed as an unauthenticated or remotely triggered API.

## Acceptance boundary

Earlier phase-local SQLite calculation tests and offline migration checks were followed by Step 5/6 live PostgreSQL migrations, SLA/ticket journeys, and Docker worker lifecycle checks. Those later runs did not establish exhaustive multi-worker `SKIP LOCKED` contention, timezone coverage, or production-scale behavior; those remain separate acceptance work.
