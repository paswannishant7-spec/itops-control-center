# AI system guide

## Capabilities and boundaries

The AI module provides ticket classification, knowledge-grounded troubleshooting, similar resolved
tickets, response drafts, and summaries. Every capability is advisory: it cannot transition a
ticket, assign work, publish knowledge, send a reply, or run a command. A technician remains the
decision-maker, and approving a draft only places editable text into the reply composer.

The provider boundary is disabled by default. `ITOPS_AI_PROVIDER=openai` enables the external
adapter when `ITOPS_OPENAI_API_KEY` is supplied by the deployment secret manager. The application
uses strict structured output, `store: false`, bounded timeouts/input sizes, and validated enums,
taxonomy, confidence, and citations. Transport, provider, parsing, or validation failures converge
on explicit zero-confidence fallbacks rather than fabricated success.

## Data flow

```text
authorized ticket/knowledge read
  -> bounded field selection
  -> credential-pattern redaction
  -> explicitly untrusted data block
  -> provider request with separate instructions and strict schema
  -> Pydantic/domain validation
  -> content-minimized interaction metadata + validated recommendation
  -> human review
```

Requester identity, email, private attachments, secrets, raw prompts, provider output, and unrelated
records are excluded from interaction logs. Internal notes are excluded from assistant conversation
context. RAG indexes only exact published article versions. Similar-ticket candidate generation and
result disclosure both reapply ticket visibility.

## Grounding and evaluation

Troubleshooting answers may cite only chunk UUIDs supplied by retrieval. Article title, version,
excerpt, and similarity are attached server-side; invented or empty citations cause a safe fallback.
PostgreSQL/pgvector is the production retrieval path. SQLite cosine ranking exists only for tests.

AI feedback records accepted, edited, rejected, or regenerated workflow outcomes. These are
operational review rates, not model-accuracy measurements. Production evaluation should use a
versioned, privacy-reviewed dataset, compare task-specific quality and safety thresholds, segment
results by model/prompt version, and require human sign-off before changing defaults.

## Operations

- Treat model, embedding model, prompt version, confidence thresholds, retrieval size, and similarity
  threshold as controlled configuration.
- Rotate provider credentials without rebuilding images and never expose them to the browser.
- Monitor provider error code, attempts, latency, token counts, fallback rate, citation rejection,
  and human review outcomes without logging ticket content.
- Re-index published knowledge after an embedding-model change; do not mix incompatible vector
  spaces under one provider/model identity.
- Roll back by setting `ITOPS_AI_PROVIDER=disabled`; core service-desk workflows remain available.

Detailed contracts: [classification](AI_CLASSIFICATION.md), [RAG](RAG.md), [similar
tickets](SIMILAR_TICKETS.md), and [technician assistant](AI_TECHNICIAN_ASSISTANT.md).
