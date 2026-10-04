# Security architecture

## Authentication

- Passwords are hashed with Argon2id through `argon2-cffi`; plaintext passwords are never stored or logged.
- Login payloads with an empty identifier/password, malformed email, missing fields, or extra fields return `422` before authentication. A well-formed unknown account or wrong password returns the same generic `401`. Neither failure creates a session; successful credentials return `200` and the database-backed user identity.
- Passwords are limited to 12–128 characters and require upper/lowercase letters, a digit, and a symbol for locally managed accounts.
- Access tokens are HS256 JWTs with issuer, audience, subject, session ID, unique ID, issued-at, expiry, and token-type claims. They expire after 10 minutes by default.
- Access tokens remain in frontend memory. They are not written to local or session storage.
- Refresh tokens are 384-bit opaque random values. Only SHA-256 digests are stored in PostgreSQL.
- Refresh tokens rotate on every use. Reusing a rotated token revokes every active session in its token family.
- The refresh token is sent in an HttpOnly, SameSite=Strict cookie restricted to the authentication API path. Production must enable `Secure` cookies.
- Every bearer request verifies that the JWT session ID still identifies an active, unrevoked, unexpired refresh session. Logout, refresh-token rotation, replay-family revocation, and administrative account suspension therefore invalidate the corresponding access token immediately.

## Account state and disclosure

Only `ACTIVE` users may authenticate or refresh. Missing users, wrong passwords, and disabled/locked accounts receive the same login response. Password verification performs a dummy Argon2 check for unknown users to reduce timing disclosure.

Login and refresh are independently throttled by source address plus a digest of the normalized
credential identifier. Rejections include `Retry-After`. The in-process implementation is suitable
for one API replica; horizontal deployments require a shared atomic limiter.

## Bootstrap identity

The seed command creates a fresh identity, ADMIN assignment, and bootstrap audit event atomically from environment values. It does not restore roles to existing users. Existing Phase 3 accounts require the explicit credential-verifying `scripts.bootstrap_access` upgrade command. See [RBAC bootstrap instructions](RBAC.md#bootstrap-and-upgrade). Remove bootstrap credentials after use; no demo password is committed.

## Password reset architecture

The schema stores only hashed, expiring, single-use password-reset tokens. Request/confirm delivery endpoints are deferred until a notification transport and abuse policy are selected. Their future design must use generic request responses, short expiries, family/session revocation after reset, and audit events.

## Known boundaries

- Protected requests check both current session state and current database grants. Role assignments and Phase 5 directory mutations require bounded reasons where appropriate and a transactional audit event. Self role/status modification is prohibited. See [RBAC](RBAC.md) and [the directory contract](DIRECTORY.md).
- Only active explicitly assigned technicians or IT managers can join active teams. Disabling or locking an account ends active memberships and revokes every refresh session in the same transaction. Reactivating the account does not revive memberships or old tokens.
- Directory and other domain event payloads contain bounded operational state rather than request bodies. Phase 18 enforces append-only records in both SQLAlchemy and PostgreSQL and supplies the permission-protected consolidated viewer described in [the audit hardening contract](AUDIT_SECURITY.md).
- Ticket authorization combines explicit action grants with SQL-level own/team/all visibility. Unauthorized callers receive no object-existence signal. Internal comments are excluded from requester responses even when public comments share the same ticket.
- Attachment uploads are bounded before buffering completes, require an allowed extension/MIME pair, and undergo PDF/image signature or UTF-8 text inspection. Storage keys are randomized and path-contained; bytes are served only through an authenticated, ticket-scoped endpoint. Configured ClamAV scanning occurs before storage and fails closed; production must require it.
- Ticket event state excludes descriptions and comment bodies. Attachment events contain only identifiers, MIME type, and size. Local/Compose attachment storage is private but does not yet provide object-store retention policies, malware quarantine, encryption-key management, or disaster-recovery replication.
- SLA administration is protected by explicit `sla:view`/`sla:manage` grants. Ticket SLA disclosure reuses ticket record scope, so employees cannot probe another request through the SLA endpoint. Worker events use deterministic idempotency keys, carry bounded timing metadata, and contain no comments, descriptions, credentials, or uploaded data.
- Knowledge search applies publication/ownership/reviewer scope in SQL, and hidden detail requests return 404. Versions are append-only through the service contract, publication records an exact version pointer, and workflow events omit article content. The UI renders content as text rather than executable HTML. Retrieved knowledge is treated as untrusted data and remains separate from system instructions.
- AI classification sends a minimized, size-bounded, credential-redacted ticket block without requester identity, comments, attachments, or unrelated records. Ticket content is explicitly untrusted and remains separate from provider instructions. Outputs are schema- and taxonomy-validated, never applied automatically, and fall back to current ticket values at zero confidence. Interaction logs retain hashes/metadata rather than prompts, raw output, ticket content, or API keys. External response storage is disabled by the OpenAI adapter.
- RAG indexes only exact published versions, redacts common credential patterns before embedding/storage, and retrieves a bounded top-k set rather than loading the knowledge base into a prompt. Ticket and retrieved content remain untrusted blocks. Model citation UUIDs must belong to the retrieval set; titles, versions, excerpts, and scores are attached server-side. Empty retrieval and invalid citations return a no-citation fallback, and troubleshooting never mutates a ticket.
- Similar-ticket representations contain only normalized, credential-redacted title and description text; they exclude requester identity, comments, attachments, and resolution text. Candidate generation and final ranking both reuse ticket own/team/all SQL scope, hidden source tickets return 404, and only visible resolved or closed tickets can disclose their server-sourced resolutions. A provider failure returns no fabricated matches, and semantic similarity is never presented as an exact diagnosis.
- Assistant drafting and summarization use bounded, credential-redacted ticket fields and recent public comments without names or IDs; internal notes and attachments are excluded. Ticket content remains an untrusted provider block. Reviews require `ai:use`, exact ticket visibility, and a matching recommendation; one immutable decision prevents quiet relabeling. Approval only stages editable text and never sends a reply or changes a ticket. Global review metrics require analytics permission plus all-ticket scope and are explicitly not labeled AI accuracy.
- Asset authorization uses SQL-level own/team/all predicates derived from current custody and active support-team departments. Hidden records return 404, write grants remain separate, and every mutation requires a bounded reason plus transactional event. Assignment history is append-preserving, terminal assets reject new changes or ticket links, and linked-ticket reads reapply ticket scope rather than inheriting asset visibility.
- Role changes serialize through PostgreSQL row locks. The Phase 5/6 disposable-PostgreSQL runs verified the supported authentication and RBAC flows; exhaustive concurrency and penetration testing are not claimed.
- Refresh requests are coalesced within one browser tab. Cross-tab refresh-token rotation coordination remains unimplemented.
- HS256 is appropriate for the current single issuer/verifier service. A separate identity service or third-party issuer would justify asymmetric signing/OIDC.
- TLS termination, secret-manager integration, shared multi-replica rate limiting, image scanning, and centralized security telemetry remain deployment responsibilities.

## Phase 18 audit and hardening controls

Phase 18 adds the administrator audit view, two-layer audit immutability, exact-origin startup
validation, browser/API security headers, refresh throttling, optional fail-closed ClamAV INSTREAM
inspection, CI dependency audits, weekly dependency updates, and a shared prompt-injection policy.
See [the complete contract](AUDIT_SECURITY.md).

## Phase 14 device identity and telemetry

Device identity is separate from human identity. Administrators mint a short-lived, one-time token
for a specific active asset; its exchange produces a random per-installation credential that is
returned once. The backend stores SHA-256 digests of high-entropy random material, compares them in
constant time, and never stores a reusable plaintext token or universal fleet secret. Rotation
invalidates the previous credential, and disablement revokes and clears it.

Agent endpoints use an explicit `Agent` authorization scheme and return a uniform 401 for missing,
invalid, revoked, or disabled credentials. Operator endpoints continue to use live-session JWTs,
permission checks, and SQL-enforced asset scope. Enrollment and disablement are recorded in the asset
event stream without secret values.

Payload schemas reject unknown fields, invalid bounds, malformed IP addresses, excessive lists,
impossible memory/disk totals, stale/future timestamps, and invalid boot times. Collection is limited
to aggregate operational telemetry; logs exclude authorization data and only expose bounded safe
error categories. HTTPS is mandatory for non-local agent configuration. Deployment must protect the
agent state path with an OS account boundary and, on Windows, an explicit user-only ACL.

## Phase 15 alert and automation controls

Alert reads inherit asset SQL scope and return no hidden-device existence signal. Policies and rules
accept schema-validated fixed fields; there is no script body, provider prompt, or LLM-generated
action. An active-alert unique index, a rule/alert execution key, and per-recipient notification
dedupe make retries safe. Incident creation, team assignment, ticket history, SLA initialization,
alert linkage, execution status, and notification writes are transactional; a per-rule savepoint
records bounded failures without discarding the monitoring observation.

Alert events and notifications contain operational identifiers and bounded summaries, not raw
telemetry history, credentials, secrets, comments, or attachments. Users can access only their own
notification preferences and inbox. Phase 15 persists in-app delivery only; Phase 16 adds the
authenticated delivery signal described below. External transports remain later work.

## Phase 16 WebSocket controls

The WebSocket accepts credentials only in a bounded first message, keeping bearer tokens out of
URLs, proxy access logs, subprotocol negotiation, and persistent browser storage. It rejects missing
or unapproved origins, validates the JWT and live refresh session, and rechecks account status and
database grants for every delivery batch and idle heartbeat. Logout, refresh-family revocation,
expiry, and account disablement therefore end delivery.

Outbox rows and frames contain only topic, sequence, and optional resource/recipient identifiers.
Ticket internal-note signals require the internal-note grant; ticket/SLA, alert, and device signals
reuse their existing SQL record predicates; notifications require an exact recipient. Invisible
events advance the server cursor without producing a frame. Access changes trigger permission and
query resynchronization. Backlog gaps trigger HTTP resync rather than replaying data outside current
scope. See [the real-time contract](REALTIME.md).

## Phase 17 analytics controls

Analytics require `analytics:view` and apply the same database-derived ticket and asset predicates
before aggregation. AI outcomes are joined to visible tickets. Team users therefore do not receive
organization totals, hidden entity labels, or counts that could disclose out-of-scope activity.
Empty denominators are explicit nulls rather than misleading performance claims. Formula and scope
details are in [the analytics contract](ANALYTICS.md).

## Production security gate

Before production, terminate TLS at a maintained edge, use exact HTTPS CORS origins and secure
cookies, inject independent database/JWT/provider secrets from a secret manager, require a private
ClamAV service, restrict database and attachment access, and centralize secret-safe logs and alerts.
Pin immutable images, verify SBOM/provenance and vulnerability policy, protect release environments,
test backup restoration, and document credential rotation and incident ownership.

The same-origin frontend proxy removes localhost from the production API boundary and CSP. The
reference production Compose file binds only the frontend to loopback; operators must not expose
PostgreSQL, the API container, workers, ClamAV, or attachment storage directly. See [deployment](DEPLOYMENT.md)
and [CI/CD](CI_CD.md).
