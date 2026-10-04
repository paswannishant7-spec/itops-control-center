# Product demo runbook

## Hosted reviewer access

The hosted version is a **controlled portfolio demonstration, not a production service**. A
reviewer receives a separate temporary account and password privately from the operator;
credentials are never published in this repository, embedded in the frontend, or shown in
screenshots. Open only
the operator-provided HTTPS hostname. If the browser cannot establish valid HTTPS, do not sign in.
Use fictional ticket content only; do not upload real personal or company data. Role permissions
still come from the database. Request a role-specific account for Employee, Technician, or Manager
workflows; the operator demonstrates Admin functionality without sharing Admin credentials. The
shared enterprise-seed password is never issued to reviewers. The operator disables
reviewer access and resets fictional changes after a demonstration. The local setup below is for a
disposable developer environment, not instructions to seed a public server.

This runbook supports a repeatable portfolio demonstration of the ITOps Control Center. Use the full-stack path for live mutations and authorization. The checked-in images were captured from the running PostgreSQL-backed fictional demo, not from fixture responses.

## Screenshot provenance

The public screenshots show real application views against the fictional, PostgreSQL-backed Step 6 dataset. Capture new public images only after the stack is healthy and the screen has loaded successfully. Inspect each image for credentials, tokens, private comments, non-fictional personal data, debug UI, and broken states before publishing it. The optional `npm run screenshots` command uses **mocked test fixtures** and writes only under ignored `frontend/test-results/fixture-screenshots/`; its output is not suitable as live product evidence.

## Full-stack setup

1. Copy `.env.example` to `.env` and replace `POSTGRES_PASSWORD`, `ITOPS_JWT_SECRET`, and the initial administrator password. Keep all demo credentials local.
2. To load the optional enterprise demo directory, set `ITOPS_ENTERPRISE_SEED_PASSWORD` to a strong local-only password. Use the same value for `ITOPS_INITIAL_ADMIN_PASSWORD` on a fresh demo database. The seed is blocked outside development and test environments.
3. Start the stack with `docker compose up --build` and wait for the API and frontend health checks. The API container applies migrations and runs the idempotent seeds before serving requests.
4. Open `http://localhost:5173` and sign in as `nishant.paswan@example.com` using the locally configured seed password. Authentication still uses the normal database and Argon2 password-verification path.
5. After seeding, remove `ITOPS_INITIAL_ADMIN_PASSWORD` and `ITOPS_ENTERPRISE_SEED_PASSWORD` from the environment. Rerunning the seed does not reset passwords, statuses, or removed roles on existing accounts.
6. The optional directory seed supplies 35 fictional users across eight departments, six IT teams, and four locations. To add the Step 6 fictional workload to a dedicated development database, run `docker compose exec api python -m scripts.demo_seed` after the stack is healthy. It adds 20 tickets, eight published knowledge articles, 10 assets, three simulated monitoring agents, and operational alerts through the application services. Repeating the command does not duplicate tickets, articles, assets, or agents; it refreshes the fictional telemetry snapshots so device health remains useful for a live demo. The monitoring agents are **fictional demo telemetry**, not production devices; do not run a live agent against them.
7. In **SLA policies**, review the existing business calendar and policy. Ticket SLA values come from the real policy and worker, not fixed dashboard numbers.
8. Open **Tickets** to inspect the populated queue and histories, then create a new high-impact request for the live workflow. Open **Assets**, **Monitoring**, and **Alerts** to show the linked fictional inventory and signals.
9. Do not expose a one-time enrollment token on a recording.

### Safe local reset

Use a dedicated Compose project name for the demo, for example `docker compose -p itops-step6 up -d --build`. The seed refuses non-development/test environments and requires the existing enterprise directory. To reset **only that disposable demo project**, first confirm its name with `docker compose -p itops-step6 ps`, then run `docker compose -p itops-step6 down -v` and start/seed it again. `down -v` permanently removes that project's PostgreSQL and attachment volumes; never run it against an existing project containing data you want to keep. Credentials remain in local environment configuration, never in the seed or this runbook.

If the live environment is not healthy, stop the presentation and use only the reviewed checked-in screenshots. Do not point migrations, tests, or demo setup at a production database.

## Demonstration scenario

### 1. Operational picture — 90 seconds

Open **Command center**. Explain the permission-scoped organization/team view, current risk signals, SLA performance with sample sizes, ticket volume, technician workload, device health, critical alerts, and human-reviewed AI outcomes. Change the reporting window to show that the view is interactive.

### 2. Service desk workflow — 3 minutes

Open **Tickets** and create a request for “Regional VPN access unavailable.” Link the employee asset, set high impact and urgency, then show calculated priority and SLA state. Assign the ticket, add a public response, and move it into progress. Point out that internal notes, attachments, event history, similar resolved tickets, and AI suggestions stay within the same controlled workstation.

### 3. Grounded technician assistance — 90 seconds

Generate troubleshooting guidance on the ticket. Show confidence, cited knowledge chunks, fallback/provenance labels, and the requirement for technician review. Approve a drafted response into the composer, emphasizing that the system never submits it automatically.

### 4. Operations loop — 90 seconds

Open **Assets**, then **Monitoring** and **Alerts**. Trace the ticket back to its asset, explain agent health and telemetry minimization, and show how a threshold alert can create a deduplicated incident with SLA initialization. Mention that WebSocket invalidation keeps visible queues current without putting access tokens in URLs.

### 5. Governance proof — 90 seconds

Open **Audit trail**. Filter by `TICKET` or an entity UUID and inspect a change. Show the actor, reason, request correlation, before/after state, secret redaction, and immutable storage. Close on role-based scope, transactional audit writes, production deployment gates, and the tested failure paths.

## Presenter checklist

- Use a clean browser profile at 1440×1000 or larger and 100% zoom.
- Confirm the admin session, queue data, command-center data, and realtime indicator before sharing the screen.
- Keep a second, lower-privilege user ready to demonstrate permission-aware navigation and data scope.
- Avoid showing `.env`, tokens, enrollment credentials, raw headers, or real personal data.
- Keep the checked-in screenshots open as the offline fallback.
- End by restoring any ticket or alert state changed solely for the demonstration.
