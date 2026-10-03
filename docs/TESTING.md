# Testing strategy

## Portfolio acceptance snapshot (Steps 5–6)

The resumed Step 5 run executed 137/137 backend tests against disposable PostgreSQL after real
Compose build/startup and Alembic migration. It also exercised four-role authentication/RBAC,
ticket/comment/attachment flows, monitoring and alerts, WebSocket delivery, and persistence after a
Compose restart. Step 6 exercised the fictional enterprise/demo seed and representative role
journeys. These are historical local observations, not a public CI result. The whole-backend Mypy
check retains seven pre-existing errors in unrelated files; do not interpret the CI configuration
as proof of a green remote run. See the commands below for reruns on a disposable database.

Each phase maintains fast quality gates for both runtimes.

## Frontend

- Oxlint for static lint checks.
- TypeScript project build for strict type checking.
- Vitest, Testing Library, and jsdom for user-observable component behavior.
- Playwright against the production SPA build for desktop and mobile Chromium journeys.
- Vite production build as a deployability check.
- Prettier in check mode for deterministic formatting.

## Backend

- Ruff for imports, correctness, modernization, and style.
- Mypy strict mode for application code.
- Pytest and FastAPI TestClient for HTTP contracts.
- Coverage threshold starts at 90% and must not be weakened to make failures pass.

## Current coverage

The authorization suite covers every catalog permission for all four roles and unassigned accounts, signed-token access tied to live sessions, disabled users, escalation denial, immediate permission and session revocation, audited assignment, rollback, bootstrap, and own/team/all policy.

Phase 5 backend tests cover directory permission and non-disclosure behavior, reference-data lifecycle and conflicts, user creation/search/pagination/profile/status changes, token invalidation, technician eligibility, membership history and scope, role-downgrade guards, constraints, no-op behavior, and transactional audit rollback. Frontend tests cover protected routes, assignment requests, denial feedback, same-tab refresh coalescing, directory loading/errors, user creation, and team membership changes.

Phase 6 backend tests cover intake, priority calculation, employee privacy, team and unassigned visibility, filters, assignment/reassignment history, the complete state graph, resolution/reopen/close behavior, public/internal comments, first response, event history, category validation, attachment content checks, protected download, size limits, and direct service transactions. Frontend tests cover queue rendering and errors, intake submission, ticket workstation rendering, public replies, and requester reopening.

The final Phase 6 local gate ran 64 backend tests with 90.28% application coverage and 15 frontend tests across six files. Ruff, strict Mypy, Prettier, Oxlint, strict TypeScript, the Vite production build, Alembic head inspection, and offline PostgreSQL upgrade SQL generation also passed.

Phase 7 tests cover configurable matrix and policy selection, configuration authorization and validation, weekends, holidays, overnight windows, IANA timezone conversion, pause subtraction and resume, first-response switching, policy changes, SLA record scope, queue filtering, at-risk/breach state, escalation and notification intent, completion, and repeated-worker idempotency. Frontend coverage includes the SLA ticket panel and administrator configuration workspace.

The final Phase 7 local gate ran 69 backend tests with 90.08% application coverage and 16 frontend tests across seven files. Ruff, strict Mypy, Prettier, Oxlint, strict TypeScript, the Vite production build, Alembic head inspection, and offline PostgreSQL upgrade SQL generation passed.

Phase 8 tests cover category management and conflicts, inactive-category rejection, draft privacy, author ownership, immutable version history, tag normalization, legal transitions, separated publish/archive grants, published search, archive removal, traceable publication, and workflow history. Frontend tests cover published search, authoring, detail/version history, review submission, and correlated retry errors.

The final Phase 8 local gate ran 73 backend tests with 90.45% application coverage and 19 frontend tests across eight files. Ruff, strict Mypy, Prettier, Oxlint, strict TypeScript, the Vite production build, Alembic head inspection, and offline PostgreSQL upgrade SQL generation passed.

Phase 9 tests cover structured success, taxonomy validation, malformed/unknown output, credential redaction, advisory non-mutation, role and ticket scope, confidence bands, retry limits, disabled-provider fallback, timeouts, rate limits, outages, provider rejection, Responses API parsing, token metadata, latest-result reads, and privacy-conscious persistence. Frontend coverage verifies contextual generation and presentation of confidence, cause, checks, provenance, and advisory labeling.

The final Phase 9 local gate ran 83 backend tests with 90.62% application coverage and 20 frontend tests across eight files. Ruff, strict Mypy, Prettier, Oxlint, strict TypeScript, the Vite production build, Alembic head inspection, and offline PostgreSQL upgrade SQL generation passed.

Phase 10 adds coverage for deterministic normalization/chunking, secret redaction before embedding,
published-only indexing, embedding reuse, semantic retrieval, real citation provenance, invented-ID
rejection, empty retrieval, provider embedding/answer parsing, prompt-injection boundaries, ticket
scope, and manager-only indexing. Frontend coverage exercises indexed-version status and cited
troubleshooting presentation.

The final Phase 10 local gate ran 88 backend tests with 90.21% application coverage and 21 frontend
tests across eight files. Ruff, strict Mypy, Prettier, Oxlint, strict TypeScript, the Vite production
build, Alembic head inspection, offline PostgreSQL upgrade SQL generation, and OpenAPI smoke
inspection passed.

Phase 11 adds coverage for minimized credential-redacted representations, visible resolved-only
candidate selection, exact own/team/all scope, current-ticket exclusion, embedding creation/reuse
and stale replacement, provider failure rollback, similarity and resolution mapping, and hidden
ticket non-disclosure. Frontend coverage exercises automatic loading, related-ticket navigation,
resolution display, metadata, and the explicit non-diagnostic warning.

The final Phase 11 local gate ran 91 backend tests with 90.29% application coverage and 21 frontend
tests across eight files. Ruff, strict Mypy, Prettier, Oxlint, strict TypeScript, the Vite production
build, Alembic head inspection, offline PostgreSQL upgrade SQL generation, and OpenAPI smoke
inspection passed.

Phase 12 adds coverage for response drafting, summarization, strict assistant schemas, confidence and
fallback handling, public-comment redaction, identity/internal-note exclusion, latest reads, all four
feedback outcomes, edit consistency, duplicate review, ticket scope, operational metrics, and the
non-accuracy label. Frontend coverage verifies review controls and that approval fills—but does not
submit—the reply composer.

The final Phase 12 local gate ran 93 backend tests with 90.35% application coverage and 21 frontend
tests across eight files. Ruff, strict Mypy, Prettier, Oxlint, strict TypeScript, the Vite production
build, Alembic head inspection, offline PostgreSQL upgrade SQL generation, and OpenAPI smoke
inspection passed.

Locally these SQL-backed API tests run in isolated SQLite transactions with foreign keys enabled. CI sets `ITOPS_TEST_DATABASE_URL` to a disposable PostgreSQL database initialized by Alembic. Never point that variable at a production database. Local metadata creation is only a test fixture, not an application migration strategy.

PostgreSQL online migration/schema checks, concurrent role/team/asset/knowledge edits, container startup, private-volume persistence, live malware-scanner integration, and a deployed full-stack browser run still need execution. The repository browser suite deliberately intercepts the API boundary so it remains deterministic; the independently exercised API and PostgreSQL CI suites cover that boundary below the browser.

## Phase 13 coverage

Asset tests cover catalog creation and uniqueness, identifier/date validation, own/team/all
non-disclosure, filters, metadata changes, temporal reassignment, unassignment, retirement,
transactional audit history, terminal-state guards, inactive/missing references, ticket linking, and
the restrictive relationship. Frontend checks cover runtime response parsing, scoped inventory
rendering, registration, and strict build gates. PostgreSQL migration SQL is generated offline;
live PostgreSQL concurrency and schema comparison remain CI/disposable-environment acceptance work.

## Phase 14 coverage

Monitoring tests cover authorization and own/team/all non-disclosure, one-time asset-bound
enrollment, digest-only storage, token replay rejection, unique credential authentication, malformed
and incorrect credentials, disablement and revocation, online/degraded/offline transitions,
timestamp and metric validation, missed-heartbeat calculation, sampling, retention cleanup, asset
health projection, and direct service/repository lifecycles. Agent tests cover privacy-minimized
collection, stable atomic state, HTTPS policy, authenticated requests, retriable error classification,
and secret-safe failures. Frontend coverage exercises scoped fleet rendering, metric presentation,
and one-time enrollment display.

The final Phase 14 local gate ran 99 backend tests with 90.88% application coverage, 23 frontend
tests across ten files, and four standalone agent tests. Ruff, strict Mypy, Prettier, Oxlint, strict
TypeScript, the Vite production build, Alembic head inspection, offline PostgreSQL upgrade SQL
generation, and OpenAPI smoke inspection passed.

## Phase 15 coverage

Alert tests cover policy authorization and validation, asset-scoped disclosure, threshold trigger
and recovery, active-alert deduplication, acknowledgement/resolution/suppression, deterministic
incident creation, team assignment, SLA initialization, one-execution-per-rule behavior, bounded
failure persistence, notification preferences, recipient selection, and notification read ownership.
Monitoring regressions cover metric-driven CPU/memory/disk evaluation plus offline and missed-
heartbeat alerts. Frontend coverage exercises the scoped alert stream, state actions, incident links,
notification inbox, user preferences, and administrator policy/rule configuration.

The final Phase 15 local gate ran 104 backend tests with 91.09% application coverage and 24 frontend
tests across eleven files. The four standalone agent tests remain green. Ruff, strict Mypy,
Prettier, Oxlint, strict TypeScript, the Vite production build, Alembic head inspection, offline
PostgreSQL upgrade SQL generation, and OpenAPI smoke inspection passed.

## Phase 16 coverage

Real-time backend tests cover transaction-bound event capture, rollback, content minimization,
internal-note classification, all six topics, ordered bounded publication, retention, origin checks,
first-frame token authentication, live-session revocation, protocol readiness, recipient isolation,
and topic/resource authorization. Existing ticket, SLA, alert, notification, directory, and
monitoring tests also exercise outbox creation through their normal service transactions.

Frontend tests cover the memory-only authentication frame, token-free URL, protocol validation,
heartbeat response, targeted and debounced query invalidation, duplicate suppression, access-change
session refresh, reconnect state, authorization pause, and connection cleanup.

The final Phase 16 local gate ran 107 backend tests with 90.56% application coverage, 27 frontend
tests across twelve files, and four standalone agent tests. Ruff, strict Mypy, Prettier, Oxlint,
strict TypeScript, the Vite production build, Alembic head inspection, offline PostgreSQL upgrade SQL
generation, and WebSocket route inspection passed.

## Phase 17 coverage

Analytics tests cover team versus organization authorization scope, reporting-window bounds, empty
denominators, MTTR, MTTA, SLA compliance, first-contact proxy, reopen rate, daily/weekly/monthly
volume, workload, recurring category patterns, device health, critical alerts, asset incident
frequency, AI review outcomes, urgent-queue ordering, and endpoint access denial. Frontend coverage
verifies API-derived manager and technician views, performance sample display, real volume charting,
deep links, live scope, AI labeling, and reporting-window reloads.

The final Phase 17 local gate ran 110 backend tests with 90.89% application coverage, 29 frontend
tests across thirteen files, and four standalone agent tests. Ruff, strict Mypy, Prettier, Oxlint,
strict TypeScript, the route-split Vite production build, Alembic head inspection, offline PostgreSQL
upgrade SQL generation, OpenAPI inspection, and WebSocket route inspection passed.

## Phase 18 coverage

Security tests cover all audit-source normalization branches, secret-key redaction, AI content
minimization, exact-action/entity/actor/time filtering, reversed-time rejection, application-level
immutability, production headers, strict CORS configuration, private rate-limit keys, retry timing,
and clean/malicious/unavailable ClamAV responses. Frontend coverage validates the normalized audit
contract. CI additionally executes npm and Python advisory scans; live scanner and PostgreSQL trigger
acceptance remain deployment checks.

## Phase 19 coverage

The comprehensive backend suite inventories every HTTP operation and fails when a non-public route
lacks a human or endpoint-agent identity dependency. Thirteen protected API families are sampled for
a uniform missing-credential `401` problem response. AI coverage verifies that hostile text remains
untrusted input, cannot enter provider instructions, uses the shared prompt-injection policy, disables
provider storage, and requires strict schema output. The existing AI suite continues to exercise
timeouts, transport failures, provider rate limits/outages/rejections, malformed output, empty
retrieval, invalid citations, unsupported tasks, and safe fallbacks. SLA edge coverage now includes
DST spring-forward and fall-back elapsed time, leap-day holidays, reversed ranges, and naive-UTC
normalization.

Playwright runs three real-browser workflows on desktop Chromium and a Pixel 7 viewport: successful
sign-in followed by support-queue navigation and filtering, controlled invalid credentials, and an
authenticated audit view with expandable redacted details. The tests use the built Vite SPA and a
typed, intercepted API boundary; they do not replace a deployed browser/API/PostgreSQL acceptance
run. Vitest explicitly excludes `e2e/**`, keeping the two runners isolated.

The final Phase 19 local gate ran 132 backend tests at 91.00% application coverage, 30 frontend unit
and component tests across 14 files, six Playwright browser cases across two viewports, and four
standalone endpoint-agent tests. Ruff, strict Mypy, Oxlint, Prettier, both TypeScript configurations,
the Vite production build, Alembic head/offline SQL, OpenAPI inspection, and npm/Python advisory
checks passed. CI installs Chromium and runs the browser suite after the production build; its
separate API job uses disposable PostgreSQL.

## Commands

```bash
cd frontend
npm run lint
npm run typecheck
npm run typecheck:e2e
npm test
npm run build
npx playwright install chromium
npm run test:e2e
npm run format:check
```

```bash
cd backend
ruff check app tests
mypy app
pytest
```

```bash
cd agent
ruff check itops_agent tests
mypy itops_agent
pytest
```

Browser failure artifacts are written to `frontend/test-results/` and
`frontend/playwright-report/`; both directories are generated and ignored. CI uses a freshly built
SPA. Locally, `npm run test:e2e` also builds first through its pretest hook.

The optional `npm run screenshots` path exercises schema-valid **mocked fixtures** and writes
to ignored `frontend/test-results/fixture-screenshots/`. It does not refresh public product
screenshots. Public images require a live application, fictional data, and manual privacy review.
The capture suite is skipped during the normal browser gate.

## Phase 20 deployment validation

The frontend suite now also proves that relative and HTTPS API boundaries derive same-origin `ws:`
and secure `wss:` realtime URLs without placing the access token in the URL. The production build is
executed with `VITE_API_BASE_URL=/api/v1` and checked for the absence of the development localhost
origin. Development/production Compose and GitHub workflow files receive syntax and structural
checks; Docker-capable CI performs authoritative Compose rendering and image builds. The current
frontend total is 31 tests across 14 files; backend and agent totals remain 132 and four.

## Phase 21 portfolio validation

The frontend adds a debouncing hook unit test and a deterministic three-view Chromium capture suite.
The product review also verifies route-level chunks, keyboard skip navigation, visible focus, reduced-
motion handling, audit UUID validation, query retry states, filter-aware empty states, and correct
Status/Priority/SLA column mapping. The normal browser gate remains six core cases across desktop and
mobile; portfolio captures run only through `npm run screenshots`.
