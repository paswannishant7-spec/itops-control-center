# AI technician assistant and feedback contract

## Assistant outputs

Technicians with `ai:use` and normal visibility of a ticket can request either a response draft or a
ticket summary. Existing knowledge-grounded troubleshooting remains available in the same ticket
workspace. All outputs use strict schemas, configurable confidence bands, and a persisted
interaction/recommendation record. Provider or validation failures produce a clearly labeled,
zero-confidence safe fallback.

The minimized provider input contains bounded, credential-redacted title, description, operational
ticket state, optional resolution, and at most 20 recent public comments. Requester/support labels do
not contain names or IDs. Internal notes, attachments, requester identity, unrelated employee data,
and credentials are excluded. Ticket and conversation blocks are explicitly untrusted and remain
separate from provider instructions.

## Human approval

Every persisted recommendation may receive one immutable review outcome:

- `ACCEPTED` — the technician approved the output as presented.
- `EDITED` — the technician approved an explicitly stored edited version.
- `REJECTED` — the technician declined the output.
- `REGENERATED` — the technician requested a replacement output.

An edited outcome requires edited content; all other outcomes prohibit it. A recommendation cannot
be reviewed twice. Review requires `ai:use`, normal visibility of the source ticket, and an exact
recommendation/ticket relationship. Hidden tickets and mismatched recommendation IDs return no
cross-ticket disclosure.

Approval never posts a reply, changes ticket fields, runs a command, or applies a recommendation.
In the UI, accepting a response draft only fills the editable reply composer. Sending the message is
a separate authenticated technician action.

## Operational metrics

The metrics endpoint reports accepted, edited, rejected, and regenerated counts. Acceptance, edit,
and rejection rates use accepted + edited + rejected as their denominator; regeneration is reported
separately. Empty datasets return zero rates. These are workflow review rates, not scientific AI
accuracy measurements.

Global metrics require `analytics:view` and `ticket:view_all`, limiting access to managers and
administrators under the current role matrix.

## API

- `POST /api/v1/ai/tickets/{ticket_id}/assistant/{task_type}` generates `RESPONSE_DRAFT` or
  `SUMMARIZATION`.
- `GET /api/v1/ai/tickets/{ticket_id}/assistant/{task_type}/latest` returns the latest permitted
  output and its review state.
- `POST /api/v1/ai/tickets/{ticket_id}/recommendations/{recommendation_id}/feedback` records one
  review outcome.
- `GET /api/v1/ai/feedback/metrics` returns globally aggregated operational review rates to callers
  with analytics permission and all-ticket scope.

External AI remains disabled by default. The OpenAI adapter uses strict structured output and
`store: false`, consistent with the official [Responses create
contract](https://developers.openai.com/api/reference/cli/resources/responses/methods/create); no
provider credential belongs in source control.
