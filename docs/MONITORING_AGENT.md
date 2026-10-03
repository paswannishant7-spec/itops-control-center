# Monitoring agent contract

## Scope and privacy

Phase 14 adds endpoint visibility through a separately installed Python agent. It reports aggregate
CPU, memory, disk, and network counters plus boot time, operating system, hostname, IP addresses,
heartbeat availability, and bounded collection error codes. It does not inspect processes, files,
commands, browser activity, user identities, or content.

The agent is operational telemetry, not a remote administration channel. It accepts no commands and
cannot itself create alerts or incidents. Phase 15 evaluates accepted telemetry and reconciled device
state server-side, deduplicates alerts, and runs only configured deterministic actions. See [the
alerts and automation contract](ALERTS_AUTOMATION.md).

## Enrollment and authentication

An administrator with `monitoring:manage` creates a short-lived, single-use enrollment token for one
active, visible asset. Creating a new enrollment for that asset immediately returns its agent to
`UNREGISTERED`, invalidates any previous device credential, and records a bounded asset event.

The agent exchanges the token once at `/api/v1/monitoring/enroll`. The backend returns a unique
high-entropy credential only in that response, stores only its SHA-256 digest and an eight-character
display prefix, and removes the enrollment token digest. The agent stores the credential in its local
state file using an atomic replacement and owner-only permissions where the operating system supports
them. Remove the enrollment token from the environment after successful enrollment.

Agent ingestion uses `Authorization: Agent <agent_id>.<credential>`. It is intentionally separate
from user bearer authentication. Invalid, revoked, inactive, or disabled credentials receive the same
401 response. There is no shared fleet secret. Disabling an agent clears credential material and
creates an asset event; re-enrollment is required to restore access.

Production agent configuration rejects non-HTTPS API URLs. TLS termination, certificate lifecycle,
and secure provisioning of the one-time token remain deployment responsibilities.

## Status and heartbeat semantics

- `UNREGISTERED`: an enrollment is pending and no active credential exists.
- `OFFLINE`: enrolled but not currently within the configured heartbeat window.
- `ONLINE`: the latest authenticated heartbeat reports availability with no collection failures.
- `DEGRADED`: the latest heartbeat reports unavailable data or bounded collection errors.
- `DISABLED`: an administrator revoked the credential.

A valid heartbeat updates agent and asset `last_seen`, hostname, OS, primary IP, and health. It resets
the missed-heartbeat count. The monitoring worker marks previously online or degraded agents offline
when their last heartbeat is older than `ITOPS_MONITORING_HEARTBEAT_TIMEOUT_SECONDS`; missed count is
derived from the expected interval. Clock-skewed observations outside the accepted window and boot
times later than the observation are rejected.

## Sampling and retention

The API stores at most one accepted metric per agent within
`ITOPS_MONITORING_METRIC_MIN_INTERVAL_SECONDS`; faster valid submissions return `accepted: false`
without another row. The worker deletes metric and heartbeat rows older than
`ITOPS_MONITORING_RETENTION_DAYS`. Agent summary and asset last-known state remain available. The
default policy is a 30-second minimum metric interval, 60-second expected heartbeat, 180-second
offline timeout, 30-day raw telemetry retention, and 60-second reconciliation interval.

Metric and heartbeat tables are indexed by agent and time. This phase uses sampling plus bounded raw
retention rather than permanent high-frequency storage. Long-term rollups can be added only when a
defined analytics requirement needs them.

## API

Human user authentication and asset-derived own/team/all scope apply to fleet reads and management:

- `POST /api/v1/monitoring/enrollments`
- `GET /api/v1/monitoring/agents`
- `GET /api/v1/monitoring/agents/{agent_id}`
- `GET /api/v1/monitoring/agents/{agent_id}/metrics`
- `POST /api/v1/monitoring/agents/{agent_id}/disable`

Device authentication applies only to ingestion:

- `POST /api/v1/monitoring/enroll`
- `POST /api/v1/monitoring/agent/heartbeat`
- `POST /api/v1/monitoring/agent/metrics`

## Running the agent

From `agent/`, install the package in an isolated Python 3.12+ environment. Set
`ITOPS_AGENT_API_URL`, `ITOPS_AGENT_ENROLLMENT_TOKEN`, and optionally `ITOPS_AGENT_STATE_PATH`, then
run `itops-device-agent`. Subsequent runs use the stable ID and credential from the state file.

The process retries transient network/server failures with bounded exponential backoff, avoids
retrying permanent authentication and validation failures, redacts credential-bearing messages, and
handles termination signals for a clean stop. On Windows, production installers should additionally
apply an explicit user-only ACL to the state directory because POSIX mode bits are only best-effort.
