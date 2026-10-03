# Alerts, automation, and notifications contract

## Deterministic alert evaluation

Phase 15 evaluates accepted monitoring samples against enabled database policies. Supported metrics
are CPU, memory, and disk percentages, device offline state, and missed-heartbeat count. Policies
configure a name, operator (`GREATER_THAN` or `AT_LEAST`), threshold, severity, and enabled state.
Percentage thresholds are bounded to 0–100, device-offline policies use the boolean threshold 1, and
all payloads reject unknown fields.

The migration seeds five conservative policies: CPU, memory, and disk above 90% are critical; an
offline device is high severity; and three missed heartbeats are critical. Administrators can create
or change policies through the API and UI. Disabling a policy automatically resolves its active
alerts. The engine contains no LLM or free-form executable behavior.

## Alert identity, state, and deduplication

An alert snapshots its policy, source, severity, metric, threshold, latest observed value, affected
agent/asset, trigger time, latest observation, lifecycle actors/timestamps, and optional incident.
The supported states are `TRIGGERED`, `ACKNOWLEDGED`, `SUPPRESSED`, and `RESOLVED`.

A partial unique index permits only one non-resolved alert for a policy/agent pair. Repeated matching
samples update that alert's observed value and timestamp without repeating its automation. When the
condition clears, the engine resolves the alert. A later recurrence creates a new alert and may run
automation again. Technicians can acknowledge and resolve scoped alerts; suppression and policy
management require `alert:manage`.

Alert visibility reuses the asset own/team/all SQL predicate after the `alert:view` gate. A caller
cannot use an alert ID to infer a hidden asset. Every trigger, automatic recovery, lifecycle action,
and policy/rule configuration change creates a bounded alert event without telemetry history,
credentials, or secrets.

## Deterministic automation and incidents

An automation rule matches a minimum alert severity and the `DEVICE_AGENT` source. It can create an
incident, notify a team, or do both; an active assignment team is mandatory. Each rule/alert pair has
one execution record, enforced by a unique index, so an active condition cannot repeatedly create
incidents or notifications.

Automated incidents are ticket records with `record_type=INCIDENT` and `source=AUTOMATION`. They
reference the affected asset, inherit its department/location, are assigned to the configured team,
and initialize the existing priority-matrix and SLA workflow transactionally. The rule creator is
the accountable requester/actor because the current ticket schema requires a human identity; the
ticket and alert retain the exact rule and alert IDs. Failed actions are isolated in a savepoint and
record a bounded `ACTION_FAILED` execution instead of losing the monitoring sample or alert.

## In-app notifications and preferences

Team notification actions target active members only. Each recipient receives at most one
notification per alert. A user's preference independently enables/disables in-app delivery and sets
the minimum alert severity; the default is enabled at `WARNING`. Notification bodies contain only a
condition label and references, not raw device history or credentials. Users can list and mark only
their own notifications as read.

This notification service is independent of the UI and currently handles alert automation. Broader
ticket, SLA, and AI event routing can adopt the same service in later phases. Phase 16 now delivers
content-free notification invalidations over an authenticated WebSocket; notification records still
load through the authorized HTTP endpoint.

## API

- `GET/POST /api/v1/alerts/policies`
- `PATCH /api/v1/alerts/policies/{policy_id}`
- `GET /api/v1/alerts`
- `GET /api/v1/alerts/{alert_id}`
- `POST /api/v1/alerts/{alert_id}/acknowledge`
- `POST /api/v1/alerts/{alert_id}/resolve`
- `POST /api/v1/alerts/{alert_id}/suppress`
- `GET/POST /api/v1/automation/rules`
- `PATCH /api/v1/automation/rules/{rule_id}`
- `GET /api/v1/automation/executions`
- `GET /api/v1/notifications`
- `GET/PUT /api/v1/notifications/preferences/me`
- `POST /api/v1/notifications/{notification_id}/read`
