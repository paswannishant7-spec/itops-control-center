# Knowledge base contract

## Lifecycle and versioning

Articles move through `DRAFT → IN_REVIEW → PUBLISHED → ARCHIVED`. A reviewer may return an in-review article to draft, and an archived article may be restored as a draft. Other transitions fail with HTTP 409.

Creating an article creates immutable version 1. Each draft revision appends a new version; earlier title, summary, content, author, timestamp, and change summary rows are never updated. Publication stores the exact current version ID and publication timestamp on the article, making the released content traceable. Archived restoration clears that publication pointer before further revision.

Content is stored as text and rendered without raw HTML execution. Phase 10 will add derived chunks and embeddings without changing version history.

## Authorization and visibility

- `knowledge:view`: search and read published articles.
- `knowledge:create`: create an owned draft.
- `knowledge:update`: revise and submit an owned draft; reviewers may revise any visible draft.
- `knowledge:review`: see every workflow state, return review items to draft, inspect history, and restore archives.
- `knowledge:publish`: publish reviewed content and manage categories.
- `knowledge:archive`: retire published content.

The repository adds visibility predicates to SQL before counting, sorting, or paginating. Readers only receive `PUBLISHED` rows. Authors additionally receive their own non-published rows. Reviewers/publishers/archivers receive all workflow rows. Unauthorized detail requests return 404, preventing article-existence disclosure.

## Search and API

Base path: `/api/v1/knowledge`.

| Endpoint | Purpose |
|---|---|
| `GET /categories` | List active categories; publishers also see inactive categories |
| `POST /categories` | Create a category |
| `PUT /categories/{id}` | Replace or deactivate a category |
| `GET /articles` | Permission-scoped keyword/filter search with offset/limit pagination |
| `POST /articles` | Create article and version 1 |
| `GET /articles/{id}` | Read the visible current version |
| `POST /articles/{id}/versions` | Append a draft version |
| `GET /articles/{id}/versions` | Read immutable version history |
| `POST /articles/{id}/transitions` | Apply a legal, permission-checked lifecycle transition |
| `GET /articles/{id}/events` | Read reviewer workflow history |

Search accepts `search`, `category_id`, `status`, `offset`, and `limit`. It runs in SQL over slug, current-version title, summary, and content; it does not load the table into application memory.

## Audit and safety

Create, version, review, publish, archive, and restore operations append `knowledge_events` in the same transaction. Events contain bounded operational state, actor, reason, request ID, and timestamp; they exclude article content. Article text is untrusted data and must remain separated from system instructions when Phase 10 retrieval is introduced.
