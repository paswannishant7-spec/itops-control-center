# Asset management contract

## Scope

Phase 13 introduces a controlled catalog for laptops, desktops, monitors, printers, servers, network devices, and mobile devices. An asset records its tag, serial number, hostname, type, vendor/model, operating system, network identifiers, current owner and organization, purchase/warranty dates, lifecycle status, last-seen timestamp, and health state.

Phase 13 introduced the inventory boundary. Phase 14 now allows an administrator to bind one secured
agent identity to an active asset. Authenticated heartbeats project last-seen, hostname, OS, primary
IP, and health onto that asset; telemetry history and credentials remain owned by the monitoring
module. See [the monitoring contract](MONITORING_AGENT.md).

## Authorization

Visibility is enforced in SQL. `asset:view_own` exposes assets whose current owner is the caller. `asset:view_team` adds assets in departments covered by the caller's active support teams. `asset:view_all` exposes the full inventory. A hidden identifier and a missing identifier both return 404 after the action permission gate.

Creation, metadata updates, custody changes, and retirement use separate permissions. The current role catalog grants write operations only to administrators; the UI is never the authorization authority. Ticket linking requires the actor to see the asset, and terminal assets cannot receive new links.

## Custody and history

The asset row stores current owner, department, and location for efficient scoped access. Every non-empty custody change closes the previous temporal assignment and creates one new active assignment in the same transaction. A partial unique index permits one active assignment per asset. Clearing or retirement closes the active interval and removes current custody.

Every create, update, assignment, unassignment, and retirement appends a bounded event with actor, reason, request ID, timestamp, and operational before/after state. Events exclude secrets and ticket content.

## Lifecycle and relationships

Active operational states are `ACTIVE`, `IN_REPAIR`, and `LOST`; terminal states are `RETIRED` and `DISPOSED`. Retirement clears custody and blocks metadata/custody changes. Ticket `asset_id` now has a restrictive foreign key to the asset catalog. Asset detail returns only linked tickets independently visible through the caller's ticket scope.

## API

- `GET/POST /api/v1/assets`
- `GET/PATCH /api/v1/assets/{asset_id}`
- `POST /api/v1/assets/{asset_id}/assignments`
- `POST /api/v1/assets/{asset_id}/retire`
- `GET /api/v1/assets/{asset_id}/history`
- `GET /api/v1/assets/{asset_id}/tickets`

List operations support search, type, lifecycle, health, owner, department, and location filters with stable pagination.
