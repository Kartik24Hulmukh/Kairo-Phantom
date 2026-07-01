"""
Kairo DocIntel — Ask Your Docs (PDF)

Drop in a PDF → ask a question → get a correct answer with a citation
to the source page. Fully offline.

Pipeline:
  1. Ingest: PDF path → pdfplumber parse → chunk + local-embed → store in local index
  2. Ask: question → retrieve top chunks → answer with citation (page + bbox)
  3. Audit: every answer logged via SignedAuditLog; PromptShield on all inputs

No network calls. No mocks on the advertised path. Typed errors on bad input.
"""

from kairo.docintel.ingest import PdfIngestor, IngestError, IngestResult
from kairo.docintel.retrieval import RetrievalIndex, RetrievalResult
from kairo.docintel.ask import DocIntelSession, AskResult, AskError

__all__ = [
    "PdfIngestor",
    "IngestError",
    "IngestResult",
    "RetrievalIndex",
    "RetrievalResult",
    "DocIntelSession",
    "AskResult",
    "AskError",
]