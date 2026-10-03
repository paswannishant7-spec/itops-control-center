# Similar ticket intelligence contract

## Representation and indexing

Opening a ticket workspace requests similar-ticket intelligence. The service builds a normalized,
credential-redacted representation from only the ticket title and description; requester identity,
comments, attachments, and resolution text are excluded. A SHA-256 representation hash allows the
configured provider/model embedding to be reused until those source fields change.

The current ticket and a bounded pool of recent, visible, resolved historical tickets are embedded
in one batch when needed. Embeddings are stored per ticket, provider, and model. A provider failure,
wrong batch size, or unexpected vector dimension rolls back the operation and returns a controlled
503 without fabricated matches.

## Retrieval and authorization

Every candidate and final result is constrained by the existing ticket own/team/all SQL predicate.
Similarity never expands ticket visibility. The current ticket is excluded, and only `RESOLVED` or
`CLOSED` tickets with a recorded resolution are eligible.

PostgreSQL ranks stored 1,536-dimensional vectors by cosine distance through pgvector, applies the
configured similarity threshold and top-k limit, and uses an HNSW `vector_cosine_ops` index. The
bounded in-memory cosine implementation exists only for deterministic SQLite tests.

## Presentation and interpretation

The ticket workspace shows each permitted match's reference, title, similarity score, status,
priority, category, resolution, and resolution/closure date. Resolution and metadata come from the
authorized database row, not from the embedding provider. The interface explicitly states that
semantic similarity is supporting evidence, not an exact diagnosis.

The operation is advisory. It does not change either ticket, copy a resolution, notify a requester,
or trigger an automated action.

## API and configuration

- `POST /api/v1/ai/tickets/{ticket_id}/similar` requires `ai:use` and visibility of the requested
  ticket.
- `ITOPS_SIMILAR_TICKET_CANDIDATE_POOL` bounds newly considered historical tickets.
- `ITOPS_SIMILAR_TICKET_TOP_K` bounds returned matches.
- `ITOPS_SIMILAR_TICKET_MIN_SIMILARITY` sets the cosine similarity floor.

The external provider remains disabled by default. Configure the existing AI provider, API key,
embedding model, and fixed 1,536 dimensions through environment settings. Never commit provider
credentials.
