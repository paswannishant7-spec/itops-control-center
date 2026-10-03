# Documentation

This directory contains the public technical documentation for ITOps Control Center. Start with the architecture and API guides, then use the domain or operations guide relevant to your task.

## Platform foundations

- [Architecture](ARCHITECTURE.md) — system boundaries, deployment topology, and design decisions.
- [API](API.md) — authentication, errors, resource groups, and realtime protocol.
- [Database](DATABASE.md) — schema, migrations, backup, recovery, and capacity guidance.
- [Role-based access control](RBAC.md) — roles, permissions, record scopes, and bootstrap workflow.
- [Security architecture](SECURITY.md) — identity, sessions, transport, data, and deployment controls.
- [Audit and security hardening](AUDIT_SECURITY.md) — immutable audit data and hardening controls.

## Service management

- [Organization directory](DIRECTORY.md) — users, departments, locations, teams, and memberships.
- [Ticket core](TICKETS.md) — intake, queues, comments, attachments, assignments, and lifecycle.
- [Priority and SLA](SLA.md) — priority policy, calendars, timers, pauses, and escalation.
- [Knowledge base](KNOWLEDGE.md) — authoring, review, publishing, versioning, and visibility.

## AI-assisted support

- [AI system guide](AI.md) — capability boundaries, providers, data flow, and operations.
- [Classification](AI_CLASSIFICATION.md) — category and priority recommendations.
- [Retrieval-augmented troubleshooting](RAG.md) — knowledge retrieval and citations.
- [Similar tickets](SIMILAR_TICKETS.md) — resolved-ticket matching and disclosure controls.
- [Technician assistant](AI_TECHNICIAN_ASSISTANT.md) — drafting, summaries, feedback, and safeguards.

## Assets and operations

- [Asset management](ASSETS.md) — inventory, ownership, lifecycle, and ticket linkage.
- [Monitoring agent](MONITORING_AGENT.md) — enrollment, telemetry, device state, and retention.
- [Alerts and automation](ALERTS_AUTOMATION.md) — policies, deduplication, notifications, and incident creation.
- [Realtime delivery](REALTIME.md) — WebSocket authorization, event delivery, and recovery.
- [Analytics](ANALYTICS.md) — command-center metrics, filters, scopes, and calculation rules.

## Development and delivery

- [Local setup](SETUP.md) — verified Compose startup, configuration, migrations, and development commands.
- [Testing](TESTING.md) — suites, commands, coverage, and acceptance boundaries.
- [Deployment and operations](DEPLOYMENT.md) — production configuration, upgrades, rollback, and incidents.
- [CI/CD](CI_CD.md) — validation gates, image publication, and release promotion.
- [Product demo](DEMO.md) — fictional seed, role walkthrough, reset safety, and live screenshot policy.
