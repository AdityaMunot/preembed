"""Python API for preembed."""

__all__ = [
    "Chunk",
    "ChunkMetadata",
    "DedupeResult",
    "Pipeline",
    "PipelineResult",
    "PipelineStats",
    "PreembedError",
    "Scorer",
    "Tokenizer",
    "clean_text",
    "chunk_text",
    "clear_scorers",
    "dedupe_chunks",
    "register_scorer",
    "score_chunks",
]

from .pipeline import Pipeline
from .text import (
    PreembedError,
    chunk_text,
    clean_text,
    clear_scorers,
    dedupe_chunks,
    register_scorer,
    score_chunks,
)
from .types import (
    Chunk,
    ChunkMetadata,
    DedupeResult,
    PipelineResult,
    PipelineStats,
    Scorer,
    Tokenizer,
)

try:
    from importlib.metadata import version as _get_version

    __version__ = _get_version("preembed")
except Exception:
    __version__ = "0.0.0"
