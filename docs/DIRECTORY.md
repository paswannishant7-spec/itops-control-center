# Organization directory — Phase 5

## Scope

Phase 5 provides organization reference data, administrative user lifecycle management, technician teams, and historical membership. Its own boundary stops before ticket creation or assignment; the Phase 6 ticket module now consumes active team scope.

Departments and locations have stable UUIDs, names, optional descriptions, active state, and timestamps. Teams have a name, optional description, department and location, active state, and timestamps. Users add an optional unique employee number, job title, department, and location to the Phase 3 identity record.

Records are retired rather than hard-deleted. A department or location cannot be deactivated while an active user or active team references it. Deactivating a team ends every active membership. Historical memberships and directory events remain available to the service layer.

## User lifecycle

Administrators can create a user with an initial system role and password, update organization/profile fields, search and filter the directory, and change account state among `ACTIVE`, `DISABLED`, and `LOCKED`. Status changes require a reason and cannot target the acting administrator.

Disabling or locking a user atomically ends active team memberships, revokes all refresh sessions, and records an event. Bearer authentication checks the backing session on every request, so already-issued access tokens stop working immediately. Reactivating an account does not restore old sessions or team memberships.

Only active departments and locations may be assigned to active users. Search is bounded and case-insensitive; results have stable ordering, a maximum page size of 100, and optional status, department, location, and system-role filters.

## Teams and technician assignment

System roles and team roles are intentionally separate:

- `TECHNICIAN` and `IT_MANAGER` are system roles that establish technician eligibility.
- `MEMBER` and `LEAD` are team-level designations and grant no system permission.

Only an active user with an explicit `TECHNICIAN` or `IT_MANAGER` assignment may join an active team. `ADMIN` alone is not technician eligibility. Removing the last qualifying system role is rejected while any active team membership remains. Membership removal ends the current interval rather than deleting it; inactive intervals never contribute to future team scope.

## API

Base path: `/api/v1/directory`.

| Resource and operation | Endpoint | Required permission |
|---|---|---|
| List/create departments | `GET/POST /departments` | `department:view` / `department:manage` |
| Update or deactivate department | `PATCH /departments/{id}` | `department:manage` |
| List/create locations | `GET/POST /locations` | `location:view` / `location:manage` |
| Update or deactivate location | `PATCH /locations/{id}` | `location:manage` |
| List/create users | `GET/POST /users` | `user:view` / `user:create` and `role:manage` |
| Read/update user | `GET/PATCH /users/{id}` | `user:view` / `user:update` |
| Change user status | `PUT /users/{id}/status` | `user:disable` |
| List/create teams | `GET/POST /teams` | `team:view` / `team:manage` |
| Read/update/deactivate team | `GET/PATCH /teams/{id}` | `team:view` / `team:manage` |
| Find eligible technicians | `GET /teams/{id}/eligible-technicians` | `team:manage` |
| Add/update membership | `PUT /teams/{id}/members/{user_id}` | `team:manage` |
| End membership | `DELETE /teams/{id}/members/{user_id}` | `team:manage` |

The eligible-technician response is intentionally minimal and team-scoped; it does not act as a general user-directory bypass. Authentication and permission checks happen before object lookup, so unauthorized callers cannot use ID differences to enumerate records. Controlled conflicts return 409, schema/domain validation returns 422, and error responses include a request ID.

## Audit and transactions

Every Phase 5 write records a `directory_events` row in the same transaction as its state change. User creation also records the initial system-role assignment in `role_assignment_events`. Events include actor, entity, action, bounded before/after state, reason where applicable, request ID, and timestamp. They exclude plaintext passwords, password hashes, tokens, cookies, authorization headers, and request bodies. An audit-write failure rolls back the business change.

Privileged directory writes and role changes lock the system-role catalog in a consistent order, then recheck the actor before changing a target. This is designed to serialize concurrent authority changes on PostgreSQL; SQLite unit tests cannot validate row-lock behavior.

## UI

The `/directory` route is available to accounts with `team:view`. Its user, team, department, and location areas independently reveal only the controls supported by current permissions. The user table offers server-side search, filters, pagination, create/edit/status workflows, and a link to role management. Team detail supports create/edit/deactivate, eligible-technician search, and member/lead assignment. All panels include loading, empty, retryable-error, validation, conflict, and success states.

Frontend permission gates are usability controls, never authorization boundaries. API responses are runtime-validated and failed requests surface their correlation ID.

## Acceptance boundary

Local lint, type, unit/API, coverage, build, and offline Alembic SQL checks are the Phase 5 development gate. Online PostgreSQL migration and lock behavior, Docker Compose startup, and live-browser acceptance remain required before production acceptance. Ticket assignment was delivered in Phase 6; database-enforced event immutability, global audit search, and cross-tab refresh coordination remain deferred to their scheduled phases.
