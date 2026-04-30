"""Pipeline orchestration for preembed."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from .text import chunk_text, clean_text, dedupe_chunks, score_chunks
from .types import Chunk, ChunkMetadata, PipelineResult, PipelineStats

ProgressCallback = Callable[[str, int, int], None]  # (stage, current, total)

_MAX_FOLDER_DEPTH = 8
_SUPPORTED_SUFFIXES = frozenset(
    {"", ".txt", ".md", ".markdown", ".html", ".htm", ".log", ".json", ".csv"}
)


@dataclass(slots=True)
class Pipeline:
    """Configure and run the document preparation pipeline."""

    clean: bool = True
    chunk_size: int = 512
    overlap: int = 64
    dedupe: bool = True
    score: bool = True
    report: bool = True

    def run(
        self,
        source: str,
        *,
        progress: ProgressCallback | None = None,
    ) -> PipelineResult:
        """Run the pipeline on raw text, a file path, or a folder path."""
        if not isinstance(source, str):
            raise TypeError("Pipeline.run() expects raw text or a path string.")
        self._validate_config()

        documents = _load_documents(source)
        warnings: list[str] = []
        all_chunks: list[str] = []
        all_metadata: list[ChunkMetadata] = []

        for doc_index, document in enumerate(documents):
            if progress:
                progress("clean", doc_index + 1, len(documents))
            prepared = clean_text(document.text) if self.clean else document.text
            chunks = chunk_text(
                prepared, chunk_size=self.chunk_size, overlap=self.overlap
            )
            all_chunks.extend(chunks)
            all_metadata.extend(_chunk_metadata(document.name, prepared, chunks))

        duplicate_ratio = 0.0
        if self.dedupe:
            if progress:
                progress("dedupe", 0, 1)
            dedupe_result = dedupe_chunks(all_chunks, return_stats=True)
            all_metadata = _metadata_for_retained_chunks(
                all_chunks, all_metadata, dedupe_result.retained_chunks
            )
            all_chunks = dedupe_result.retained_chunks
            duplicate_ratio = dedupe_result.duplicate_ratio

        if progress:
            progress("score", 0, 1)
        scored_chunks = (
            _attach_metadata(score_chunks(all_chunks), all_metadata)
            if self.score
            else []
        )
        low_quality_count = sum(
            1
            for chunk in scored_chunks
            if chunk.score is not None and chunk.score < 0.5
        )
        average_chunk_size = (
            sum(len(chunk.split()) for chunk in all_chunks) / len(all_chunks)
            if all_chunks
            else 0.0
        )

        stats = PipelineStats(
            total_documents=len(documents),
            total_chunks=len(all_chunks),
            average_chunk_size=average_chunk_size,
            duplicate_ratio=duplicate_ratio,
            low_quality_chunk_count=low_quality_count,
        )

        if not all_chunks:
            warnings.append("no_chunks_created")

        return PipelineResult(
            chunks=all_chunks,
            scored_chunks=scored_chunks,
            stats=stats,
            chunk_metadata=all_metadata,
            warnings=warnings,
        )

    def stream(
        self,
        source: str,
        *,
        batch_size: int = 50,
        progress: ProgressCallback | None = None,
    ) -> Iterator[PipelineResult]:
        """Yield PipelineResult per document batch. Memory-efficient for large corpora."""
        if not isinstance(source, str):
            raise TypeError("Pipeline.stream() expects a path string")
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than 0")
        self._validate_config()

        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"source path does not exist: {source}")
        if path.is_file():
            file_list = [path]
        elif path.is_dir():
            file_list = sorted(
                f
                for f in _iter_files(path, max_depth=_MAX_FOLDER_DEPTH)
                if _is_supported_text_file(f)
            )
        else:
            raise ValueError("Pipeline.stream() requires a file or directory path")

        if not file_list:
            return

        total_files = len(file_list)
        seen_raw: set[str] = set()
        seen_norm: set[str] = set()

        for batch_start in range(0, total_files, batch_size):
            batch_files = file_list[batch_start : batch_start + batch_size]
            batch_chunks: list[str] = []
            batch_metadata: list[ChunkMetadata] = []

            for i, file_path in enumerate(batch_files):
                if progress:
                    progress("clean", batch_start + i + 1, total_files)
                doc_name = (
                    file_path.relative_to(path).as_posix()
                    if path.is_dir()
                    else file_path.name
                )
                text = _read_text_file(file_path)
                prepared = clean_text(text) if self.clean else text
                chunks = chunk_text(
                    prepared, chunk_size=self.chunk_size, overlap=self.overlap
                )
                batch_chunks.extend(chunks)
                batch_metadata.extend(_chunk_metadata(doc_name, prepared, chunks))

            # Cross-batch dedupe: filter exact and normalized duplicates from prior batches.
            if self.dedupe and (seen_raw or seen_norm):
                filtered_chunks = []
                filtered_metadata = []
                for chunk, meta in zip(batch_chunks, batch_metadata):
                    raw_h = _content_hash(chunk)
                    norm_h = _normalized_hash(chunk)
                    if raw_h not in seen_raw and norm_h not in seen_norm:
                        filtered_chunks.append(chunk)
                        filtered_metadata.append(meta)
                batch_chunks = filtered_chunks
                batch_metadata = filtered_metadata

            # Record ALL batch chunks before within-batch dedupe so removed duplicates
            # are also tracked for cross-batch filtering in subsequent batches.
            if self.dedupe:
                for chunk in batch_chunks:
                    seen_raw.add(_content_hash(chunk))
                    seen_norm.add(_normalized_hash(chunk))

            # Within-batch dedupe via Rust.
            duplicate_ratio = 0.0
            if self.dedupe and batch_chunks:
                batch_num = batch_start // batch_size + 1
                total_batches = -(-total_files // batch_size)
                if progress:
                    progress("dedupe", batch_num, total_batches)
                dedupe_result = dedupe_chunks(batch_chunks, return_stats=True)
                batch_metadata = _metadata_for_retained_chunks(
                    batch_chunks, batch_metadata, dedupe_result.retained_chunks
                )
                batch_chunks = dedupe_result.retained_chunks
                duplicate_ratio = dedupe_result.duplicate_ratio

            if not batch_chunks:
                continue

            batch_num = batch_start // batch_size + 1
            total_batches = -(-total_files // batch_size)
            if progress:
                progress("score", batch_num, total_batches)
            scored_chunks = (
                _attach_metadata(score_chunks(batch_chunks), batch_metadata)
                if self.score
                else []
            )
            low_quality_count = sum(
                1 for c in scored_chunks if c.score is not None and c.score < 0.5
            )
            average_chunk_size = sum(len(c.split()) for c in batch_chunks) / len(
                batch_chunks
            )

            yield PipelineResult(
                chunks=batch_chunks,
                scored_chunks=scored_chunks,
                stats=PipelineStats(
                    total_documents=len(batch_files),
                    total_chunks=len(batch_chunks),
                    average_chunk_size=average_chunk_size,
                    duplicate_ratio=duplicate_ratio,
                    low_quality_chunk_count=low_quality_count,
                ),
                chunk_metadata=batch_metadata,
                warnings=[],
            )

    def _validate_config(self) -> None:
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be greater than 0")
        if self.overlap < 0:
            raise ValueError("overlap must be greater than or equal to 0")
        if self.overlap >= self.chunk_size:
            raise ValueError("overlap must be smaller than chunk_size")


@dataclass(slots=True)
class _Document:
    name: str
    text: str


def _load_documents(source: str) -> list[_Document]:
    path = Path(source)

    if path.exists() and path.is_file():
        return [_Document(name=path.name, text=_read_text_file(path))]

    if path.exists() and path.is_dir():
        files = sorted(_iter_files(path, max_depth=_MAX_FOLDER_DEPTH))
        return [
            _Document(
                name=file.relative_to(path).as_posix(), text=_read_text_file(file)
            )
            for file in files
            if _is_supported_text_file(file)
        ]

    return [_Document(name="<text>", text=source)]


def _iter_files(root: Path, *, max_depth: int):
    # Bounded BFS that skips hidden files/dirs to avoid scanning caches and dotfolders.
    stack: list[tuple[Path, int]] = [(root, 0)]
    while stack:
        current, depth = stack.pop()
        try:
            entries = list(current.iterdir())
        except (PermissionError, OSError):
            continue
        for entry in entries:
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                if depth < max_depth:
                    stack.append((entry, depth + 1))
            elif entry.is_file():
                yield entry


def _read_text_file(path: Path) -> str:
    # Fall back to lossy UTF-8 decoding so a single non-UTF-8 file does not fail a folder run.
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def _is_supported_text_file(path: Path) -> bool:
    return path.suffix.lower() in _SUPPORTED_SUFFIXES


def _chunk_metadata(
    source_document: str, source_text: str, chunks: list[str]
) -> list[ChunkMetadata]:
    metadata: list[ChunkMetadata] = []
    # Pre-parse source words once instead of per-chunk.
    source_words = list(re.finditer(r"\S+", source_text))
    previous_start = -1

    for chunk_index, chunk in enumerate(chunks):
        start_offset, end_offset = _find_chunk_offsets(
            source_text,
            chunk,
            source_words=source_words,
            minimum_start=previous_start + 1,
        )
        metadata.append(
            ChunkMetadata(
                source_document=source_document,
                chunk_index=chunk_index,
                start_offset=start_offset,
                end_offset=end_offset,
            )
        )
        previous_start = start_offset

    return metadata


def _find_chunk_offsets(
    source_text: str, chunk: str, *, source_words: list, minimum_start: int
) -> tuple[int, int]:
    exact_start = source_text.find(chunk, minimum_start)
    if exact_start >= 0:
        return exact_start, exact_start + len(chunk)

    chunk_words = chunk.split()
    if not chunk_words:
        return minimum_start, minimum_start

    for source_index, source_word in enumerate(source_words):
        if source_word.start() < minimum_start:
            continue
        end_index = source_index + len(chunk_words)
        if end_index > len(source_words):
            break
        candidate = source_words[source_index:end_index]
        if [match.group(0) for match in candidate] == chunk_words:
            return candidate[0].start(), candidate[-1].end()

    # Offset lookup failed; fall back to a zero-width marker at the search cursor.
    fallback = max(0, minimum_start)
    return fallback, fallback


def _metadata_for_retained_chunks(
    chunks: list[str],
    metadata: list[ChunkMetadata],
    retained_chunks: list[str],
) -> list[ChunkMetadata]:
    # Match by first-occurrence index to keep correct metadata when chunks are exact duplicates.
    retained_metadata: list[ChunkMetadata] = []
    cursor = 0
    for retained_chunk in retained_chunks:
        for index in range(cursor, len(chunks)):
            if chunks[index] == retained_chunk:
                retained_metadata.append(metadata[index])
                cursor = index + 1
                break
    return retained_metadata


def _attach_metadata(
    scored_chunks: list[Chunk], metadata: list[ChunkMetadata]
) -> list[Chunk]:
    if len(scored_chunks) != len(metadata):
        raise RuntimeError(
            f"scored chunk count ({len(scored_chunks)}) does not match metadata count ({len(metadata)})"
        )
    for chunk, chunk_metadata in zip(scored_chunks, metadata, strict=True):
        chunk.source_document = chunk_metadata.source_document
        chunk.chunk_index = chunk_metadata.chunk_index
        chunk.start_offset = chunk_metadata.start_offset
        chunk.end_offset = chunk_metadata.end_offset

    return scored_chunks


def _content_hash(text: str) -> str:
    return hashlib.blake2b(text.encode("utf-8"), digest_size=16).hexdigest()


def _normalized_hash(text: str) -> str:
    normalized = " ".join(text.casefold().split())
    return hashlib.blake2b(normalized.encode("utf-8"), digest_size=16).hexdigest()
