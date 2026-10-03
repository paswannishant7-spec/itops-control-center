# Portfolio and interview brief

This is a public-safe summary of a **local portfolio demonstration**, not an employment claim or a production deployment. [Start with the product README](../README.md) or use the [demo runbook](DEMO.md).

## Resume project entry

**AI-Powered IT Support & Operations Platform** — PostgreSQL-backed, multi-role IT service desk and operations command center.

- Built a React/TypeScript frontend and FastAPI application for employee requests, technician ticket work, manager analytics, and administrator operations.
- Modeled eight ticket states, assignment history, comments/private notes, protected attachments, SLA clocks, knowledge articles, assets, monitoring, alerts, and audit events with SQLAlchemy and Alembic.
- Implemented database-backed authentication with Argon2 password hashes, JWT access tokens, rotating refresh sessions, backend RBAC, and record-level authorization.
- Added authenticated WebSocket change signals, PostgreSQL-backed SLA/monitoring polling workers, and an advisory AI abstraction with explicit disabled-provider fallback.
- Verified the local Docker/PostgreSQL stack during Step 5, including **137/137 PostgreSQL-backed backend tests** and live four-role journeys; documented unresolved production and CI limitations.

The test count is a historical Step 5 result, not a claim of public CI success. Shorten the entry for a one-page resume by retaining the first, third, and fifth bullets.

## LinkedIn project entry

**AI-Powered IT Support & Operations Platform** — a local portfolio project that connects employee support requests with technician queues, SLA tracking, device monitoring, alerts, manager analytics, and auditable administration. I built it with FastAPI, SQLAlchemy, Alembic, PostgreSQL/pgvector, React, TypeScript, and Docker Compose. Security is backend-authoritative: database-backed roles, record-level access, Argon2 password hashing, and rotating sessions. An optional advisory AI layer is separated from core ticket workflows; the local demo uses a labeled fallback rather than claiming live model performance. Portfolio demo status: **ready with limitations**. Add the GitHub URL only after the repository has been published and reviewed.

## Case-study outline

### Problem and solution

A request crosses employee, technician, manager, and admin boundaries. A useful service desk must preserve scope, history, and SLA timing as that request moves. The solution is a modular FastAPI application with a React command center and PostgreSQL as the system of record.

### Architecture and decisions

- **Relational state:** SQLAlchemy models and Alembic migrations encode tickets, assignments, sessions, directory membership, SLA instances, and audit events. PostgreSQL transactions and constraints are used where multiple records must change together.
- **Access control:** the browser adjusts navigation for usability, but FastAPI checks current grants and applies own/team/all record scope in database queries. Assignment and ticket status are separate because routing work does not imply lifecycle progress.
- **Operational delivery:** polling workers claim bounded work from PostgreSQL. Authenticated WebSockets carry scoped invalidation signals; clients fetch current authorized state rather than trusting a pushed record body.
- **AI boundary:** advisory services minimize and validate context and outputs. Provider unavailability has an explicit fallback; it cannot silently mutate a ticket. pgvector supports the optional retrieval path, but external-provider quality was not evaluated in the local demo.
- **Reproducible demo:** Docker Compose starts PostgreSQL, API, frontend, and workers. The fictional seed provides multiple roles and varied tickets, assets, articles, and simulated device signals without representing real infrastructure.

### Security and verification

Argon2 hashes, short-lived JWT access tokens, rotating refresh credentials in HttpOnly cookies, database-backed sessions, backend permission checks, record-scope filters, protected attachments, and append-only audit records address common service-desk trust boundaries. Step 5 exercised real PostgreSQL migrations, 137/137 backend tests, four-role flows, ticket lifecycle, WebSockets, and restart persistence. This is strong local verification, not a penetration-test or production certification.

### Demo and limitations

Show the three [live-demo screenshots](../README.md#product-tour) as an overview → queue → audit narrative, then follow the [2–5 minute flow](../README.md#run-the-local-demo). External AI/RAG provider success, production malware scanning/TLS/backup/failover, formal WCAG and penetration audits, and large-scale load testing remain unverified. Monitoring telemetry is simulated. A local whole-backend Mypy run passed in Step 9, but remote CI has not been observed green. A sensible next step is to close the remaining verification gaps before considering production use.

### What I learned

The main engineering lesson is that access control and operational history must be designed into each workflow, not added only at the UI. Separating advisory AI and realtime signals from authoritative database operations keeps failure modes visible and the core service desk usable.

## Interview talking points

| Question | Concise answer |
| --- | --- |
| How does login work? | FastAPI verifies the database user and Argon2 hash, creates a database-backed session, returns a short-lived access JWT, and sets a rotating refresh credential in an HttpOnly cookie. Disabled or locked users cannot continue. |
| How is an admin endpoint protected? | The API resolves current database grants for the authenticated session. Hiding the link in React is only a usability measure; direct unauthorized requests are denied. |
| How is object-level access protected? | Ticket and asset queries apply own/team/all scope in SQL before returning a record, so changing a URL or ID cannot bypass the server policy. |
| Why PostgreSQL? | The workflows need relational integrity and transactions across tickets, assignments, SLA records, sessions, and audit history. pgvector also supports optional retrieval. |
| Why separate assignment from status? | A technician/team can change without claiming the issue progressed. Separate histories preserve both facts and make legal state transitions explicit. |
| Why WebSockets? | They notify an authorized browser that operational state changed. The browser refetches through scoped HTTP APIs; the socket is not a second source of record detail. |
| Why polling workers rather than Redis/Celery? | The current bounded SLA and monitoring workloads can be claimed from PostgreSQL with idempotent operations. A broker would be considered only if measured throughput or deployment needs justify it. |
| What happens when AI is unavailable? | The advisory path reports fallback/provenance and does not block or autonomously change the ticket. Local demo mode intentionally disables the external provider. |
| Why simulate monitoring? | It makes a repeatable, privacy-safe demo of device/alert flows without implying a real managed fleet. |
| What was actually tested? | Step 5 ran 137/137 backend tests against PostgreSQL plus live role, ticket, WebSocket, and persistence journeys. Step 7 ran frontend lint/type/build/format checks and 32/32 unit tests. No remote CI or production load result is claimed. |
| What would change before production? | Finish CI/Mypy cleanup, verify TLS and secret management, require operational malware scanning, rehearse backup/restore, assess load and failover, and perform formal accessibility/security reviews. |

## Recruiter-facing differentiator

The strongest signal is **end-to-end workflow correctness under role and record scope**: the same ticket appears differently to an employee, technician, manager, and administrator, while assignment, SLA, history, monitoring, and audit remain backed by one transactional data model. The AI layer is presented as an optional, bounded assistant—not a substitute for that engineering.
