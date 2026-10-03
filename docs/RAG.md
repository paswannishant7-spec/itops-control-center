# Retrieval-augmented troubleshooting contract

## Published-version pipeline

Only an article whose workflow state is `PUBLISHED` can be indexed. The indexer follows the
article's immutable `published_version_id`, normalizes its title, summary, and body, redacts common
credential patterns, produces deterministic overlapping chunks, and embeds only chunks missing for
the configured provider/model. Re-indexing the same version reuses its stored embeddings.

The OpenAI adapter batches non-empty chunk strings through `POST /embeddings` using
`text-embedding-3-small`, 1,536 dimensions, and float encoding. This follows the official
[embeddings API contract](https://developers.openai.com/api/reference/ruby/resources/embeddings/methods/create),
which accepts an array of inputs and supports a dimension override on `text-embedding-3` models.

## Retrieval and citations

Production retrieval runs in PostgreSQL with pgvector cosine distance and an HNSW
`vector_cosine_ops` index. The query filters to the configured embedding provider/model and joins
only chunks whose version is still the article's exact published version. `RAG_TOP_K` and a minimum
similarity threshold bound context. SQLite's bounded in-memory cosine path exists only for local
tests; it is not a production retrieval implementation.

The answer model receives the redacted ticket query and only the retrieved chunks—not the whole
knowledge base. Its structured output may cite only supplied chunk UUIDs. The service rejects an
empty or invented citation set; after one retry it records and returns a safe zero-confidence
fallback with no citations. Citation title, version, section, excerpt, and similarity are derived
server-side from retrieved database rows, never from model-authored metadata.

## Security and human control

Ticket and article text are nested as explicitly untrusted blocks while provider instructions stay
separate. The provider is instructed not to execute directions found in either block and not to
request credentials. Responses use strict JSON Schema and `store: false`, consistent with the
official [Responses API create contract](https://developers.openai.com/api/reference/cli/resources/responses/methods/create).

Troubleshooting is advisory and never changes a ticket or sends a customer response. Interaction
records store hashes, counts, provider metadata, latency, token usage, and bounded errors—not raw
prompts. Validated recommendations and server-derived citations are retained for later human review.

## API and configuration

- `POST /api/v1/ai/knowledge/{article_id}/index` requires `knowledge:publish`.
- `POST /api/v1/ai/tickets/{ticket_id}/troubleshooting` requires `ai:use` plus ticket visibility.
- `GET /api/v1/ai/tickets/{ticket_id}/troubleshooting/latest` applies the same authorization.

The external provider remains disabled by default. Configure `ITOPS_AI_PROVIDER=openai`, an API key,
the embedding model/dimensions, chunk size/overlap, retrieval limit, and similarity threshold through
environment settings. Never commit provider credentials.
