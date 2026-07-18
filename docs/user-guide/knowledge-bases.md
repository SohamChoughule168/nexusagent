# Knowledge bases & RAG

A **knowledge base** is a collection of documents that your agents retrieve from
at answer time. This is retrieval-augmented generation (RAG): the agent answers
from *your* content and cites the source, instead of guessing.

## Lifecycle of a document

1. **Upload** — add a PDF (or text) to a knowledge base. The file is stored and
   a `Document` row is created.
2. **Ingest** — text is extracted (PyMuPDF / pdfminer / PyPDF2, with a
   dependency-free fallback), split into overlapping chunks, and stored as
   `DocumentChunk` rows.
3. **Embed** — each chunk is turned into a dense vector and stored on the chunk.
4. **Retrieve** — at chat time, the query is embedded and the top-k most similar
   chunks are ranked by cosine similarity.
5. **Compose** — retrieved context is layered into the prompt and the agent
   answers, returning citations.

## Creating a knowledge base

In the dashboard, open **Knowledge Bases → New knowledge base**. Give it a name
and (optionally) tweak the chunk size, overlap, and strategy.

## Adding documents

Open a knowledge base and upload PDFs. After upload, run **Ingest** then
**Embed**. The document status moves `uploaded → processed → indexed`. Only
`indexed` documents are retrieved at chat time.

## Embeddings

- **Offline:** a deterministic, hashing-based embedder runs with no API key, so
  the pipeline always works locally.
- **With a key:** set `EMBEDDINGS_PROVIDER=openai` (or `openrouter`) and provide
  `OPENAI_API_KEY` / `OPENROUTER_API_KEY`. The configured `embedding_model`
  (default `text-embedding-3-small`) is used.

## Tips for good retrieval

- Chunk size ~800–1200 tokens with 10–20% overlap works well for most help
  content.
- One knowledge base per distinct domain (e.g. product docs vs. internal policy)
  keeps retrieval focused.
- Keep source files clean — the agent cites whatever text is in the chunk.
