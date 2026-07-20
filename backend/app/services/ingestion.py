"""Document ingestion & processing (Milestone 3).

Transforms an uploaded document's raw bytes into searchable text chunks,
reusing the existing ``DocumentChunk`` model and ``DocumentChunkRepository``.

This module ONLY performs text extraction + chunking. It does NOT generate
embeddings or write vectors -- that is the Vector Storage / RAG milestone
(Milestone 7 in the architecture doc). The boundary is deliberate: ingestion
produces ``document_chunks`` rows with ``content`` but no ``embedding_id``,
leaving the chunk ready for a later embedding step to fill in ``embedding_id``.

Reused, never duplicated:
* ``RepositoryFactory`` -> ``documents()`` / ``knowledge_bases()`` / ``document_chunks()``
* ``DocumentChunk`` model (already aligned to the live ``document_chunks`` table)
* ``KnowledgeBase`` chunk config (``chunk_size`` / ``chunk_overlap`` / ``chunk_strategy``)
* tenant isolation + RBAC are enforced by the calling endpoint, not here
"""
import re
import uuid
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.all_models import Document, DocumentChunk, KnowledgeBase
from app.repositories.tenant_repository import RepositoryFactory
from app.services.tenant_context import TenantContext

# Text-like formats are decoded directly (no parser needed).
_TEXT_EXTENSIONS = {
    "txt", "text", "md", "markdown", "csv", "json", "jsonl",
    "html", "htm", "xml", "yml", "yaml", "log",
}
_TEXT_MIME_TYPES = {
    "text/plain", "text/markdown", "text/csv", "text/html",
    "application/json", "application/xml", "text/xml",
}

# Separators tried in order by the recursive character splitter.
_RECURSIVE_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


@dataclass
class ExtractionResult:
    """Outcome of extracting text from a stored document."""

    text: str
    page_count: int
    method: str  # 'text', 'pdf:<lib>', 'pdf-naive', 'empty'


def _decode_text(content: bytes) -> str:
    """Decode raw bytes to text, tolerating non-UTF-8 encodings."""
    if not content:
        return ""
    for encoding in ("utf-8", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    # Last resort: replace invalid bytes so we never hard-fail.
    return content.decode("utf-8", errors="replace")


def _extract_pdf_naive(content: bytes) -> ExtractionResult:
    """Dependency-free best-effort PDF text extraction.

    Scans for ``(...)`` string literals used by PDF text-show operators and
    counts ``/Type /Page`` objects as a page estimate. Accuracy is limited but
    the routine is safe and requires no third-party parser.
    """
    try:
        text_str = content.decode("latin-1")
    except (UnicodeDecodeError, AttributeError):
        text_str = content.decode("utf-8", errors="replace")

    # Unescaped parenthesised strings: ( ... ), handling \\ escapes.
    matches = re.findall(r"\((?:[^()\\]|\\.)*\)", text_str)
    parts: List[str] = []
    for m in matches:
        inner = m[1:-1]
        # Unescape the few PDF string escapes we care about for readability.
        inner = (
            inner.replace("\\n", "\n")
            .replace("\\r", "\n")
            .replace("\\t", " ")
            .replace("\\(", "(")
            .replace("\\)", ")")
            .replace("\\\\", "\\")
        )
        if inner.strip():
            parts.append(inner)
    text = "\n".join(parts)

    page_count = len(re.findall(rb"/Type\s*/Page[^s]", content))
    return ExtractionResult(text=text, page_count=page_count, method="pdf-naive")


def _extract_pdf(content: bytes) -> ExtractionResult:
    """Extract text from a PDF, preferring any installed parser library.

    Tries PyMuPDF, then pdfminer.six, then PyPDF2; if none are installed it
    falls back to the dependency-free naive extractor so ingestion always
    succeeds (yielding potentially empty text rather than raising).
    """
    # 1. PyMuPDF (fitz) -- best text + layout fidelity.
    try:
        import fitz  # type: ignore

        doc = fitz.open(stream=content, filetype="pdf")
        try:
            pages = [page.get_text() for page in doc]
            return ExtractionResult(
                text="\n".join(pages), page_count=len(pages), method="pdf:fitz"
            )
        finally:
            doc.close()
    except ImportError:
        pass

    # 2. pdfminer.six.
    try:
        from pdfminer.high_level import extract_text  # type: ignore

        text = extract_text(__import__("io").BytesIO(content))
        return ExtractionResult(text=text or "", page_count=0, method="pdf:pdfminer")
    except ImportError:
        pass

    # 3. PyPDF2.
    try:
        from PyPDF2 import PdfReader  # type: ignore

        reader = PdfReader(__import__("io").BytesIO(content))
        pages = [p.extract_text() or "" for p in reader.pages]
        return ExtractionResult(
            text="\n".join(pages), page_count=len(pages), method="pdf:pypdf2"
        )
    except ImportError:
        pass

    # 4. Fallback: pure-Python naive scan.
    return _extract_pdf_naive(content)


def extract_text(filename: str, mime_type: str, content: bytes) -> ExtractionResult:
    """Extract human-readable text from a stored document.

    Text-like formats are decoded directly. PDFs use the best available parser
    (or a naive scan). Unknown binaries are decoded as text if they look
    textual, otherwise treated as empty -- ingestion never raises here.
    """
    ext = (filename or "").lower().rsplit(".", 1)[-1] if "." in (filename or "") else ""
    lowered_mime = (mime_type or "").lower()

    if lowered_mime in _TEXT_MIME_TYPES or ext in _TEXT_EXTENSIONS:
        text = _decode_text(content)
        return ExtractionResult(text=text, page_count=0, method="text")

    if lowered_mime == "application/pdf" or ext == "pdf":
        return _extract_pdf(content)

    # Unknown type: try a text decode; if it is mostly binary, treat as empty.
    text = _decode_text(content)
    if text.strip():
        return ExtractionResult(text=text, page_count=0, method="text")
    return ExtractionResult(text="", page_count=0, method="empty")


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def _split_recursive(text: str, separators: List[str]) -> List[str]:
    """Recursively split ``text`` on the first separator present.

    Returns the list of pieces using the most structurally meaningful
    separator available (paragraphs -> lines -> sentences -> words -> chars).
    """
    if not separators:
        return [text]
    sep = separators[0]
    if sep == "":
        # Character-level split (last resort).
        return list(text)
    if sep not in text:
        return _split_recursive(text, separators[1:])
    parts = text.split(sep)
    pieces: List[str] = []
    for i, part in enumerate(parts):
        # Re-attach the separator to every piece except the final one.
        if i < len(parts) - 1:
            part = part + sep
        if part:
            pieces.append(part)
    return pieces


def _merge_with_overlap(
    pieces: List[str], chunk_size: int, overlap: int
) -> List[str]:
    """Merge small pieces into ~``chunk_size`` chunks with ``overlap`` carry-over.

    Oversized individual pieces (longer than ``chunk_size``) are sliced
    directly. The overlap is carried from the tail of the previous chunk into
    the next so context is preserved across boundaries.
    """
    chunks: List[str] = []
    buffer = ""
    for piece in pieces:
        if len(piece) >= chunk_size:
            if buffer:
                chunks.append(buffer)
                buffer = ""
            start = 0
            while start < len(piece):
                end = start + chunk_size
                chunks.append(piece[start:end])
                if end >= len(piece):
                    break
                start = end - overlap
            continue
        if buffer and len(buffer) + len(piece) > chunk_size:
            chunks.append(buffer)
            buffer = buffer[-overlap:] if overlap else ""
        buffer += piece
    if buffer:
        chunks.append(buffer)
    return [c for c in chunks if c.strip()]


def chunk_text(
    text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    strategy: str = "recursive",
) -> List[str]:
    """Split ``text`` into overlapping chunks.

    ``strategy`` is currently ``"recursive"`` (hierarchical separators) or
    ``"fixed"`` (whitespace windows). Both respect ``chunk_size`` and
    ``chunk_overlap``. Returns an empty list for blank input.
    """
    chunk_size = max(1, int(chunk_size))
    chunk_overlap = max(0, min(int(chunk_overlap), chunk_size - 1))
    text = text or ""
    if not text.strip():
        return []

    if strategy == "fixed":
        separators = [" "]
    else:
        separators = _RECURSIVE_SEPARATORS

    pieces = _split_recursive(text, separators)
    return _merge_with_overlap(pieces, chunk_size, chunk_overlap)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def ingest_document(
    db: Session,
    tenant: TenantContext,
    document: Document,
    knowledge_base: KnowledgeBase,
) -> Document:
    """Extract, chunk and persist a document's content (ingestion).

    Reads the raw bytes from ``document.storage_path``, extracts text, splits it
    per the knowledge base's chunk config, (re)creates ``DocumentChunk`` rows,
    and updates the ``Document`` status/chunk_count. Idempotent: re-ingesting
    clears previously created chunks first.

    On an unrecoverable problem (e.g. the stored file is missing) the document
    is marked ``failed`` with an ``error_message`` rather than raising, so the
    API can return the document in a clear terminal state.
    """
    org_id = tenant.organization_id
    repo_factory = RepositoryFactory(db, org_id)
    doc_repo = repo_factory.documents()
    chunk_repo = repo_factory.document_chunks()

    # Read the raw bytes from storage.
    try:
        with open(document.storage_path, "rb") as fh:
            content = fh.read()
    except OSError as exc:
        document.status = "failed"
        document.error_message = f"Stored file unavailable: {exc}"
        document.chunk_count = 0
        return doc_repo.update(document)

    result = extract_text(document.filename, document.mime_type, content)
    chunks = chunk_text(
        result.text,
        knowledge_base.chunk_size or 1000,
        knowledge_base.chunk_overlap or 200,
        knowledge_base.chunk_strategy or "recursive",
    )

    # Idempotent re-ingest: drop any chunks from a previous run.
    existing = chunk_repo.get_by_document(uuid.UUID(str(document.id)))
    for old in existing:
        chunk_repo.delete(old)

    doc_uuid = uuid.UUID(str(document.id))
    kb_uuid = uuid.UUID(str(document.knowledge_base_id))
    org_uuid = uuid.UUID(str(org_id))
    for idx, chunk in enumerate(chunks):
        chunk_obj = DocumentChunk(
            document_id=str(doc_uuid),
            knowledge_base_id=str(kb_uuid),
            organization_id=str(org_uuid),
            chunk_index=idx,
            content=chunk,
            metadata={
                "page_count": result.page_count,
                "method": result.method,
            },
        )
        # ``document_chunks.id`` has no server/default generator, so assign
        # a UUID explicitly (consistent with the other tenant models).
        chunk_obj.id = uuid.uuid4()
        chunk_repo.create(chunk_obj)

    document.status = "processed"
    document.chunk_count = len(chunks)
    # Milestone B: record real indexing progress. Ingestion (extract + chunk)
    # is the first half of the pipeline; embedding is the second. We mark the
    # document 50% once it is chunked and bump it to 100% when embedding
    # completes (see the embed endpoint). ``total_chunks`` seeds the
    # denominator the embed step uses to report per-chunk progress.
    document.total_chunks = len(chunks)
    document.indexing_progress = 50 if len(chunks) else 0
    document.error_message = None
    document.meta = {
        **(document.meta or {}),
        "ingestion": {
            "method": result.method,
            "page_count": result.page_count,
            "chunk_count": len(chunks),
        },
    }
    return doc_repo.update(document)


__all__ = [
    "ExtractionResult",
    "extract_text",
    "chunk_text",
    "ingest_document",
]
