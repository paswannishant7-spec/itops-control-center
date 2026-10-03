# Real-time delivery contract

## Purpose and boundary

Phase 16 uses WebSockets for operational changes where delay affects an active support view: ticket
assignment, conversation and status; SLA warnings and breaches; alerts; in-app notifications; and
device status. The socket sends invalidation signals rather than complete records. After a signal,
the browser reloads current data through the existing authorized HTTP API. This keeps one source of
truth for serialization and record authorization and prevents comments, internal notes, telemetry,
notification text, or credentials from entering the event stream.

## Durable publication

Ticket, SLA, alert, notification, device, and access changes create a `realtime_events` row through
a SQLAlchemy session listener. The signal is written in the same transaction as the domain change,
so rollback removes both. Signals contain only a topic, optional resource/recipient UUIDs, an
internal-content flag, and a timestamp.

New rows begin unpublished. A publisher locks the singleton `realtime_cursor`, selects only committed
unpublished rows with `FOR UPDATE SKIP LOCKED`, and assigns a gap-free sequence. This two-stage
outbox avoids cursor gaps when overlapping transactions commit in a different order. Each API
replica can safely publish and poll the same PostgreSQL tables; no connection-local broadcast state
or new message-broker dependency is required. Published rows are retained for 24 hours by default.

## Connection and authentication

The endpoint is `WS /api/v1/realtime/ws`. Browsers cannot attach the normal bearer header, so the
client sends exactly one authentication frame immediately after connection:

```json
{"type":"authenticate","access_token":"<in-memory access token>"}
```

The token never appears in the URL, subprotocol, persistent browser storage, server log, or event
row. The server requires an exact allowed `Origin`, validates the signed token, checks the live
refresh session and active account, and reloads current database grants before each event batch and
during idle heartbeats. Token expiry, logout, replay-family revocation, or account disablement closes
the socket with code `4401`; an unapproved origin closes with `4403`.

## Authorization and privacy

Every signal is filtered before delivery:

- Ticket and SLA resources reuse the ticket own/team/all SQL predicate.
- Internal-note signals additionally require `ticket:internal_note`.
- Alert and device resources reuse their asset-backed own/team/all predicates after their action
  permission gate.
- Notifications are delivered only to their stored recipient.
- Role and directory changes emit a resync signal so affected clients reload permissions and scoped
  queries immediately.

Hidden resources produce no frame and no existence signal. The sequence cursor still advances, so
the client cannot infer how many invisible records matched another user's scope.

## Protocol

After authentication the server sends:

```json
{"type":"ready","protocol":1,"cursor":42,"topics":["tickets","sla"],"heartbeat_seconds":20}
```

Change frames are deliberately small:

```json
{"type":"invalidate","sequence":43,"topic":"tickets","resource_id":"<ticket UUID>"}
```

`resync` instructs the browser to invalidate all active queries after a retention gap, excessive
backlog, or access change. The server sends `ping`; the browser answers `pong`. Malformed client
frames close with `1008`, and a database or temporary delivery failure closes with `1013`.

## Browser recovery

The React provider owns one socket for the current in-memory access token. It validates incoming
frames, ignores duplicates, debounces topic-specific TanStack Query invalidations, and clears cached
data when user identity changes. Token renewal reconnects with the new token. Transport failures use
bounded exponential reconnect delay and a 30-second HTTP refresh fallback. A visible status chip
shows connected, reconnecting, or paused state. Successful connection and reconnection trigger an
HTTP resync, which covers changes committed while the browser was offline.

Reverse proxies must forward WebSocket upgrade and connection headers, preserve the request
`Origin`, and use an idle timeout longer than two heartbeat periods. TLS deployments use `wss:`; the
frontend derives the scheme and path from `VITE_API_BASE_URL`.
