# Analytics and command center

Phase 17 adds a single permission-scoped operational contract at
`GET /api/v1/analytics/dashboard?window_days=30`. The accepted reporting window is 7–365 days.
The browser presents the response as the technician operations view for team scope and the IT
command center for organization scope. Numbers are calculated from live records; there are no
sample or fallback values.

## Authorization and scope

The endpoint requires `analytics:view` and then reuses both existing access predicates:

- ticket metrics use `ticket:view_own`, `ticket:view_team`, and `ticket:view_all`;
- device and alert metrics use `asset:view_own`, `asset:view_team`, and `asset:view_all`;
- AI feedback is joined back to a ticket and follows the same ticket predicate.

An IT manager or administrator with both all-record permissions receives `ORGANIZATION` scope. A
technician receives `TEAM` scope containing their requests, direct assignments, active team queues,
team-department tickets, and team-department assets. The API never computes a global result and
filters it afterward.

## Exact formulas

Each window contains the requested number of UTC calendar days, beginning at 00:00 UTC on its first
day and ending at response generation. All durations are calendar minutes and are rounded to one
decimal. Percentages are rounded to one decimal and include the denominator as `sample_size`. When
the denominator is zero, the API returns `null`, not a fabricated zero or 100 percent.

| Metric | Formula |
| --- | --- |
| Open tickets | Visible tickets currently in `NEW`, `OPEN`, `IN_PROGRESS`, `PENDING_USER`, `PENDING_VENDOR`, or `ESCALATED`. |
| Assigned to me | Open tickets whose current technician is the caller. |
| Unassigned | Open tickets without a current technician. |
| Active incidents | Open tickets with record type `INCIDENT`. |
| Critical incidents | Active incidents with priority `CRITICAL`. |
| SLA at risk / breached | Open tickets whose current SLA state is `AT_RISK` / `BREACHED`. |
| Online / offline devices | Visible enrolled device agents whose current state is exactly `ONLINE` / `OFFLINE`. |
| Unhealthy devices | Visible agents currently `OFFLINE` or `DEGRADED`. |
| Critical alerts | Visible, unsuppressed alerts in `TRIGGERED` or `ACKNOWLEDGED` with severity `CRITICAL`. |
| MTTR | Mean of `resolved_at - created_at` for tickets resolved inside the reporting window. Invalid negative intervals are excluded. |
| MTTA | Mean of `first_response_at - created_at` for tickets first responded to inside the reporting window. In this product, the first public technician response is the acknowledgement timestamp. |
| SLA compliance | Completed resolution SLAs inside the window without `resolution_breached_at` and whose elapsed resolution seconds do not exceed the stored target, divided by completed resolution SLAs. |
| First-contact resolution proxy | Tickets resolved inside the window with no recorded reopen timestamp, divided by tickets resolved inside the window. This is explicitly a proxy because contact-session data is not captured. |
| Reopen rate | Tickets resolved inside the window with a recorded reopen timestamp, divided by tickets resolved inside the window. |
| Ticket volume | Visible tickets created and resolved in the window, bucketed independently by UTC day, ISO week starting Monday, and calendar month. Empty buckets are returned as zeroes. |
| Technician workload | Current open assignments plus resolutions inside the window, grouped by the ticket's current assigned technician. |
| Asset incident frequency | Incident tickets created inside the window, grouped by linked asset. |
| Recurring issues | Category/subcategory combinations occurring at least twice among tickets created inside the window. |
| AI assistance | Accepted, edited, and rejected feedback divided by those three reviewed outcomes. Regeneration is reported separately and excluded from the review-rate denominator. These are operational review rates, not model accuracy. |

Ticket demand is also grouped by category, department, and priority for the same created-in-window
population. Results are ranked and bounded for a readable command-center payload.

## Real-time behavior

The existing WebSocket continues to carry only content-free invalidation signals. Ticket, SLA,
alert, and device signals invalidate the active `analytics-dashboard` query; the browser then
reloads the authorized HTTP aggregate. Disconnect recovery uses the Phase 16 HTTP fallback.

## Performance and retention

The query reads only current open records or records with creation, response, or resolution activity
inside a maximum 365-day window. Current source indexes cover ticket status/creation, SLA state,
device state, alert state/severity, and AI-feedback ticket/time lookup. This first implementation
calculates portable calendar buckets in the service so local SQLite tests and PostgreSQL agree.

At larger production volumes, scheduled aggregate tables and a short-lived, scope-keyed cache may
be introduced after measurement. Any cache key must include the caller's effective record scope and
window, and ticket/SLA/alert/device/access events must invalidate it. No security-sensitive global
cache is used in Phase 17.

## Known interpretation limits

- Workload credits a resolution to the ticket's current technician; historical assignee-at-resolution
  reporting needs a dedicated assignment fact model.
- Recurring issues are category/subcategory patterns because problem-management records are not yet
  implemented.
- MTTA uses first technician response as acknowledgement; no separate acknowledgement field exists.
- First-contact resolution is labeled as a proxy rather than presented as a formal contact-center KPI.
