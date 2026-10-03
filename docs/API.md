# API guide

## Discovery and versioning

The HTTP API is rooted at `/api/v1`. A running API publishes interactive OpenAPI at `/docs`, ReDoc
at `/redoc`, and the machine-readable document at `/openapi.json`. The current schema contains 83
paths and 105 HTTP operations. Additive fields and endpoints remain within `v1`; breaking request,
response, authorization, or semantic changes require a new versioned boundary.

The production frontend uses the same public origin and sends `/api/v1/**` through its Nginx proxy.
Direct development defaults to `http://localhost:8000/api/v1`.

## Authentication

- Human sessions start with `POST /api/v1/auth/login`. The access token is sent as
  `Authorization: Bearer <token>` and is held in browser memory.
- The rotating refresh token is an `HttpOnly` cookie. `POST /auth/refresh` rotates it and
  `POST /auth/logout` revokes the session family.
- Authorization reads live database permissions and active record scope; JWT role claims and hidden
  UI controls are not authorities.
- Endpoint agents authenticate only to ingestion routes with
  `Authorization: Agent <agent-id>.<credential>`. Human and agent credentials are not interchangeable.

All non-public HTTP operations require a human or agent identity dependency. Public operations are
liveness, readiness, login, refresh, logout, and one-time agent enrollment. Missing human
credentials return `401`, `WWW-Authenticate: Bearer`, and a problem response.

## Errors, tracing, and retries

Errors use `application/problem+json`:

```json
{
  "type": "urn:itops:error:validation_failed",
  "title": "Request validation failed",
  "status": 422,
  "code": "validation_failed",
  "request_id": "2f35d413-9ea4-4f5b-b3cc-b327df734667",
  "details": []
}
```

Supply `X-Request-ID` to correlate one request or use the generated response header. Do not retry
validation, authorization, or conflict failures. Retry `429` after `Retry-After` and retry transient
`5xx`/network failures with bounded exponential backoff. Mutation clients must not blindly replay a
request unless the operation documents an idempotency boundary.

List endpoints use explicit `limit`/`offset` pagination and return an item collection plus total,
limit, and offset where applicable. Filtering and record scope execute in SQL before pagination.

## Resource groups

| Prefix                                     | Responsibility                                                            |
| ------------------------------------------ | ------------------------------------------------------------------------- |
| `/health`                                  | Process liveness and database-backed readiness                            |
| `/auth`, `/access`                         | Session lifecycle, current grants, roles, and assignments                 |
| `/directory`                               | Users, departments, locations, teams, and memberships                     |
| `/tickets`, `/sla`                         | Service desk lifecycle, comments, attachments, events, and service levels |
| `/knowledge`, `/ai`                        | Knowledge workflow, indexing, grounded assistance, reviews, and metrics   |
| `/assets`, `/monitoring`                   | Inventory, custody, device enrollment, heartbeat, and metrics             |
| `/alerts`, `/automation`, `/notifications` | Detection, incident automation, and in-app delivery                       |
| `/analytics`, `/audit`                     | Scope-aware reporting and consolidated immutable history                  |

The OpenAPI document is the field-level source of truth. The domain documents in this directory
explain state transitions, scope, invariants, and failure semantics that a schema alone cannot show.

## Realtime protocol

`/api/v1/realtime/ws` is a WebSocket and is intentionally absent from OpenAPI. The browser opens the
socket without a token in its URL, then sends a bounded first frame:

```json
{ "type": "authenticate", "access_token": "<memory-only token>" }
```

The server replies with `ready`, then content-free `invalidate`, `resync`, and `ping` frames. Clients
answer `ping` with `pong` and reload affected HTTP resources after invalidation. Authorization and
session state are rechecked during delivery. See [the realtime contract](REALTIME.md).

## Change checklist

For every API change, update the Pydantic schema, route/service/repository tests, authorization and
non-disclosure tests, generated OpenAPI expectations, the relevant domain document, and this index
when a resource group or protocol changes. Never document a frontend-only permission as security.
