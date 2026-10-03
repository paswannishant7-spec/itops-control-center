# AI classification contract

## Boundary

`AIService` owns classification orchestration while provider adapters own external API details. The first adapter targets the OpenAI Responses API; local/default operation uses a disabled provider that returns a safe fallback. Provider selection, model, timeout, maximum input size, and confidence bands are configuration—not UI constants.

The OpenAI adapter requests a strict JSON Schema response, disables provider-side response storage, keeps instructions separate from ticket data, and records token counts when returned. This follows the official [Responses API create contract](https://developers.openai.com/api/reference/cli/resources/responses/methods/create), which supports JSON output, separate instructions, output-token limits, and `store: false`.

## Classification output

Every model response is parsed by Pydantic before use. It must contain:

- allowed category and subcategory IDs plus matching display names;
- impact, urgency, and priority recommendation enums;
- bounded possible causes and recommended checks;
- confidence from 0 to 1.

Taxonomy IDs and names are checked against active database categories. A malformed object, missing field, invalid enum, unknown ID, mismatched name, timeout, rate limit, provider outage, or unconfigured provider cannot mutate the ticket. Retryable failures receive at most one immediate retry, then produce a zero-confidence fallback using the ticket's current impact, urgency, and priority.

Classification is advisory. Phase 9 never applies category or priority automatically. The technician UI labels confidence, distinguishes possible causes from recommended checks, and requires human judgment.

## Data protection

Only title, a bounded description, relevant department name, an asset-presence flag, current impact/urgency, and active taxonomy are sent. User identity, email, comments, attachments, tokens, and unrelated records are excluded. Known credential patterns are replaced with `[REDACTED]` before the request.

Ticket content is placed in an `untrusted_ticket` block. Provider instructions explicitly prohibit following instructions inside that block. This is a defense layer, not a claim that prompt injection is solved.

## Interaction records

`ai_interactions` stores ticket/actor references, task, provider/model, prompt version, a SHA-256 request fingerprint, non-content input metadata, provider request ID, attempts, latency, token counts, status, error code, and timestamp. It does not store prompts, ticket text, provider keys, or raw output.

`ai_recommendations` stores the validated classification payload, confidence, source (`MODEL` or `FALLBACK`), and immutable interaction relationship. Phase 12 adds separate, immutable accepted/edited/rejected/regenerated review records without changing the original recommendation.

## API and configuration

- `POST /api/v1/ai/tickets/{ticket_id}/classifications`
- `GET /api/v1/ai/tickets/{ticket_id}/classifications/latest`

Both require `ai:use` and the caller must also be able to see the ticket. Hidden tickets return 404 after action authorization.

Set `ITOPS_AI_PROVIDER=openai` and provide `ITOPS_OPENAI_API_KEY` to enable the external adapter. The default is `disabled`, which keeps local development deterministic and safe. Never commit an API key.
