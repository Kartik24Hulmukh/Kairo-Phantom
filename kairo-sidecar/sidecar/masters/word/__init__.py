"""
sidecar/masters/word/__init__.py
"""

from sidecar.masters.word.context_extractor import (
    WordContextExtractor,
    WordDocumentContext,
    ParagraphInfo,
)
from sidecar.masters.word.writer import WordWriter
from sidecar.masters.word.validator import WordOperationValidator

__all__ = [
    "WordContextExtractor",
    "WordDocumentContext",
    "ParagraphInfo",
    "WordWriter",
    "WordOperationValidator",
]
