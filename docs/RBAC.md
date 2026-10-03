# Role-based access control

## Implemented behavior

The four system roles use 64 explicit permissions. Memberships are many-to-many; multiple roles grant the union of their permissions. No role means no domain permissions. ADMIN is an ordinary database mapping, not a bypass.

Alembic revision `20260908_0003` installs the original frozen 60-permission catalog. Revision `20260909_0004` adds explicit department and location read/manage permissions. System-role definitions are version-controlled; mapping changes require a migration. The UI edits assignments only. Capability identifiers do not imply future workflows exist.

The API reads grants from the database for each protected request. Revocation takes effect on the next request, even with an existing token. The frontend updates its displayed grants during session renewal; stale UI cannot authorize an API operation.

## Complete role/permission matrix

| Permission | Employee | Technician | IT manager | Admin |
|---|:---:|:---:|:---:|:---:|
| `ai:configure` | — | — | — | Yes |
| `ai:use` | — | Yes | Yes | Yes |
| `alert:acknowledge` | — | Yes | Yes | Yes |
| `alert:manage` | — | — | — | Yes |
| `alert:resolve` | — | Yes | Yes | Yes |
| `alert:view` | — | Yes | Yes | Yes |
| `analytics:view` | — | Yes | Yes | Yes |
| `asset:create` | — | — | — | Yes |
| `asset:retire` | — | — | — | Yes |
| `asset:update` | — | — | — | Yes |
| `asset:view_all` | — | — | Yes | Yes |
| `asset:view_own` | Yes | Yes | Yes | Yes |
| `asset:view_team` | — | Yes | Yes | Yes |
| `audit:view` | — | — | — | Yes |
| `department:manage` | — | — | — | Yes |
| `department:view` | — | Yes | Yes | Yes |
| `change:approve` | — | — | Yes | Yes |
| `change:create` | — | Yes | Yes | Yes |
| `change:update` | — | Yes | Yes | Yes |
| `change:view` | — | Yes | Yes | Yes |
| `incident:create` | — | Yes | Yes | Yes |
| `incident:resolve` | — | Yes | Yes | Yes |
| `incident:update` | — | Yes | Yes | Yes |
| `incident:view` | — | Yes | Yes | Yes |
| `knowledge:archive` | — | — | Yes | Yes |
| `knowledge:create` | — | Yes | Yes | Yes |
| `knowledge:publish` | — | — | Yes | Yes |
| `knowledge:review` | — | — | Yes | Yes |
| `knowledge:update` | — | Yes | Yes | Yes |
| `knowledge:view` | Yes | Yes | Yes | Yes |
| `location:manage` | — | — | — | Yes |
| `location:view` | — | Yes | Yes | Yes |
| `monitoring:manage` | — | — | — | Yes |
| `monitoring:view` | — | Yes | Yes | Yes |
| `permission:manage` | — | — | — | Yes |
| `permission:view` | — | — | — | Yes |
| `problem:create` | — | Yes | Yes | Yes |
| `problem:resolve` | — | — | Yes | Yes |
| `problem:update` | — | Yes | Yes | Yes |
| `problem:view` | — | Yes | Yes | Yes |
| `role:manage` | — | — | — | Yes |
| `role:view` | — | — | — | Yes |
| `sla:manage` | — | — | — | Yes |
| `sla:view` | — | Yes | Yes | Yes |
| `system:configure` | — | — | — | Yes |
| `team:manage` | — | — | Yes | Yes |
| `team:view` | — | Yes | Yes | Yes |
| `ticket:assign` | — | Yes | Yes | Yes |
| `ticket:close` | — | Yes | Yes | Yes |
| `ticket:comment` | Yes | Yes | Yes | Yes |
| `ticket:create` | Yes | Yes | Yes | Yes |
| `ticket:escalate` | — | Yes | Yes | Yes |
| `ticket:internal_note` | — | Yes | Yes | Yes |
| `ticket:reassign` | — | Yes | Yes | Yes |
| `ticket:reopen` | Yes | Yes | Yes | Yes |
| `ticket:resolve` | — | Yes | Yes | Yes |
| `ticket:update` | — | Yes | Yes | Yes |
| `ticket:view_all` | — | — | Yes | Yes |
| `ticket:view_own` | Yes | Yes | Yes | Yes |
| `ticket:view_team` | — | Yes | Yes | Yes |
| `user:create` | — | — | — | Yes |
| `user:disable` | — | — | — | Yes |
| `user:update` | — | — | — | Yes |
| `user:view` | — | — | — | Yes |

## Record scope

An action permission is necessary but not sufficient to access a ticket or asset. `AccessScope.can_view` implements the reusable own/team/all rule with default denial. Ticket detail, list, comment, attachment, assignment, transition, and timeline operations apply equivalent SQL-backed scope before object disclosure. Employees see only their requests. Technicians see directly assigned tickets, tickets assigned to active teams they belong to, and unassigned requests in departments covered by those teams. IT managers and administrators have the explicit `ticket:view_all` grant. Asset queries apply their corresponding current-owner and active-team-department scope. Ended memberships do not contribute scope.

SLA configuration uses the existing catalog: `sla:view` exposes the matrix, policies, and calendars to technicians, managers, and administrators; `sla:manage` permits configuration writes only to administrators. A visible ticket's SLA clock is part of that ticket record and remains visible to its requester even though employees do not receive global `sla:view` access.

Knowledge visibility is also record-scoped. `knowledge:view` exposes published articles. Technicians with `knowledge:update` additionally see their own unpublished work. Reviewers, publishers, and archivers see every workflow state. Category management requires `knowledge:publish`; draft submission requires ownership; publishing and archiving remain separate grants. See [the knowledge contract](KNOWLEDGE.md).

Ticket classification requires both `ai:use` and normal ticket record visibility. Employees do not receive `ai:use`. Technicians can classify only tickets visible through their own/team scope; managers and administrators retain their explicit all-ticket scope. An AI recommendation grants no write permission and is never applied automatically.
The same `ai:use` plus ticket-visibility boundary applies to troubleshooting, similar tickets, response drafting, summarization, and recommendation feedback. Global AI feedback metrics require both `analytics:view` and `ticket:view_all`, which limits them to managers and administrators under the current role matrix. Review actions never grant ticket mutation authority.

## API

Base: /api/v1/access.

| Endpoint | Required permission |
|---|---|
| GET /me | Authenticated active user |
| GET /roles | role:view |
| GET /permissions | permission:view |
| GET /users/{id}/roles | role:manage |
| PUT /users/{id}/roles | role:manage |

Assignments accept a roles array and required reason. Missing/invalid credentials return 401; insufficient privileges return 403. Unknown IDs return 404 only after authorization. Unknown roles, blank reasons and extra fields return 422. Self-modification returns 409.

Role changes lock catalog rows in deterministic order, recheck the actor, lock the target, replace assignments and write role_assignment_events in one transaction. Audit-write failure rolls back the change. Repeating unchanged desired state is a no-op. Audit rows retain restrictive user foreign keys; no API edits historical events.

An administrator cannot change their own roles or status. Role changes and directory status changes acquire the role catalog in the same deterministic order and recheck the actor before mutation, preventing a concurrent loss of authority from authorizing a stale write. Widening `role:manage` or `user:disable` beyond ADMIN requires revisiting these invariants.

## Bootstrap and upgrade

Fresh installs: apply migrations, configure a valid initial administrator email/password, then run python -m scripts.seed. Identity, ADMIN assignment and bootstrap history are written atomically. Reruns do not restore removed roles.

Existing Phase 3 identities receive no automatic elevation. Configure the account's matching credentials and explicitly run python -m scripts.bootstrap_access once after migration. The command verifies password and active status, refuses if an administrator or assignment history exists, and audits the grant. Remove bootstrap credentials from deployment configuration afterward.

Commands from backend/:

```text
alembic upgrade head
python -m scripts.seed
# Only for an existing Phase 3 identity:
python -m scripts.bootstrap_access
```

The Phase 5 directory lists users and links a selected user directly to the assignment screen.

## Tests and boundaries

SQLAlchemy API tests use isolated SQLite transactions with foreign keys locally. CI sets ITOPS_TEST_DATABASE_URL to a disposable PostgreSQL database initialized by Alembic. Tests use actual authentication dependencies, signed JWTs, repositories and service policies. Frontend HTTP fixtures are isolated test doubles.

Tests cover four roles and no-role accounts against all 64 permissions, record scopes, disabled/anonymous/tampered identities, assignment, immediate revocation, escalation denial, constraints, audit rollback, bootstrap, directory authorization, and real login-to-grants flow.

Shared refresh requests avoid duplicate rotation within one browser tab; timed renewal refreshes access tokens and grants. Cross-tab coordination remains an authentication limitation. Distributed throttling and production settings remain documented in SECURITY.md.

No dependencies were added. References: [SQLAlchemy async sessions](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html) and [FastAPI security dependencies](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/).
## Phase 13 asset scope

Asset visibility consumes the existing catalog grants. Employees receive `asset:view_own`;
technicians add `asset:view_team`; IT managers add `asset:view_all`; administrators hold all asset
grants including create, update, and retire. Team scope is derived from active team memberships and
their active department mapping. Current custody—not historical assignment—controls present access.

## Phase 14 monitoring scope

Monitoring visibility follows the same current asset predicate after the `monitoring:view` action
gate. Technicians can see their own assets plus assets in departments covered by active support
teams; managers and administrators add all-asset scope. Employees do not hold `monitoring:view` and
receive 403 rather than an agent existence signal. `monitoring:manage` is independently required to
issue or rotate enrollment tokens and disable credentials; the frozen role catalog grants it only to
administrators. Device credentials authorize only heartbeat and metric ingestion and cannot access
human-user APIs.

## Phase 15 alert and automation scope

`alert:view` gates the alert stream, then each query applies the existing asset own/team/all SQL
predicate. `alert:acknowledge` and `alert:resolve` permit scoped lifecycle actions for technicians,
managers, and administrators. `alert:manage` is administrator-only and is required for suppression,
threshold policy changes, and deterministic automation-rule changes. Execution history follows the
same permission and asset scope as alerts. Notification inbox and preference endpoints operate only
on the authenticated user's rows. Device credentials cannot read or mutate alerts, rules, tickets,
or notifications.
