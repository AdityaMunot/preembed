"""Shared public types for preembed."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Tokenizer(Protocol):
    """Callable that accepts a string and returns an iterable of tokens."""

    def __call__(self, text: str, /) -> Iterable[object]: ...


@runtime_checkable
class Scorer(Protocol):
    """Callable that accepts a chunk string and returns a score in [0.0, 1.0]."""

    def __call__(self, text: str, /) -> float: ...


@dataclass(slots=True)
class Chunk:
    text: str
    tokens: int | None = None
    score: float | None = None
    warnings: list[str] = field(default_factory=list)
    source_document: str | None = None
    chunk_index: int | None = None
    start_offset: int | None = None
    end_offset: int | None = None


@dataclass(slots=True)
class ChunkMetadata:
    source_document: str
    chunk_index: int
    start_offset: int
    end_offset: int


@dataclass(slots=True)
class PipelineStats:
    total_documents: int = 0
    total_chunks: int = 0
    average_chunk_size: float = 0.0
    duplicate_ratio: float = 0.0
    low_quality_chunk_count: int = 0


@dataclass(slots=True)
class DedupeResult:
    retained_chunks: list[str]
    removed_chunks: list[str]
    duplicate_count: int
    duplicate_ratio: float
    duplicate_groups: list[dict[str, Any]] = field(default_factory=list)
    duplicate_metadata: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class PipelineResult:
    chunks: list[str]
    scored_chunks: list[Chunk]
    stats: PipelineStats
    chunk_metadata: list[ChunkMetadata] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def save_report(self, path: str) -> None:
        from pathlib import Path

        from .report import save_report

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        save_report(self, path)
