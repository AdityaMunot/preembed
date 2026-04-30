"""Public text preparation functions."""

from __future__ import annotations

import html
import unicodedata
from collections.abc import Iterable

from . import preembed_core as _core
from .types import Chunk, DedupeResult, Tokenizer


class PreembedError(RuntimeError):
    """Raised when the native extension encounters an unexpected error."""


def _native_call(fn, *args, context: str = ""):
    try:
        return fn(*args)
    except Exception as e:
        raise PreembedError(f"{context}: {e}") from e

# --- Custom scorer registry ---

_custom_scorers: list[tuple[str, float, object]] = []  # (name, weight, fn)


def register_scorer(name: str, *, weight: float = 0.1):
    """Decorator to register a custom scoring function.

    The function must accept a chunk string and return a float in [0.0, 1.0].
    The weight determines how much this scorer contributes to the final blended score.
    Rust-computed base score is weighted at (1 - sum_of_custom_weights).
    """
    if not 0 < weight <= 1:
        raise ValueError("weight must be between 0 (exclusive) and 1 (inclusive)")

    def decorator(fn):
        if not callable(fn):
            raise TypeError("scorer must be callable")
        _custom_scorers.append((name, weight, fn))
        return fn

    return decorator


def clear_scorers() -> None:
    """Remove all registered custom scorers."""
    _custom_scorers.clear()


def clean_text(text: str) -> str:
    """Clean raw text or simple HTML into normalized text."""
    if not isinstance(text, str):
        raise TypeError("clean_text() expects a string.")

    normalized = unicodedata.normalize("NFKC", text)
    return _native_call(_core.clean_text, _unescape_if_needed(normalized), context="clean_text")


def _unescape_if_needed(text: str) -> str:
    return html.unescape(text) if "&" in text else text


def chunk_text(
    text: str,
    chunk_size: int = 512,
    overlap: int = 64,
    preserve_headings: bool = True,
    *,
    mode: str = "word",
    tokenizer: Tokenizer | None = None,
):
    """Split text into LLM-ready chunks."""
    _validate_chunk_config(text, chunk_size, overlap)
    if mode not in {"word", "token"}:
        raise ValueError("mode must be 'word' or 'token'.")
    if mode == "token" and not callable(tokenizer):
        raise TypeError("token mode requires a callable tokenizer.")

    if mode == "token":
        return _chunk_text_by_tokens(
            text, chunk_size, overlap, preserve_headings, tokenizer
        )

    return _native_call(_core.chunk_text, text, chunk_size, overlap, preserve_headings, context="chunk_text")


def _validate_chunk_config(text: str, chunk_size: int, overlap: int) -> None:
    if not isinstance(text, str):
        raise TypeError("chunk_text() expects a string.")
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0.")
    if overlap < 0:
        raise ValueError("overlap must be greater than or equal to 0.")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size.")


# --- Token-mode chunking (Python, uses caller's tokenizer) ---


def _split_structural_units(text: str, preserve_headings: bool) -> list[str]:
    units: list[str] = []
    current: list[str] = []
    in_code_block = False

    for line in text.splitlines():
        stripped = line.strip()

        if stripped.startswith("```"):
            current.append(line)
            in_code_block = not in_code_block
            if not in_code_block:
                units.append("\n".join(current).strip())
                current = []
            continue

        if in_code_block:
            current.append(line)
            continue

        if not stripped:
            if current:
                units.append("\n".join(current).strip())
                current = []
            continue

        if preserve_headings and stripped.startswith("#"):
            if current:
                units.append("\n".join(current).strip())
            current = [line]
            continue

        current.append(line)

    if current:
        units.append("\n".join(current).strip())

    return units


def _chunk_text_by_tokens(
    text: str,
    chunk_size: int,
    overlap: int,
    preserve_headings: bool,
    tokenizer: Tokenizer,
) -> list[str]:
    units = _split_structural_units(text, preserve_headings=preserve_headings)
    chunks: list[str] = []
    current_words: list[str] = []

    for unit in units:
        unit_words = unit.split()
        if not unit_words:
            continue

        if _token_count_words(unit_words, tokenizer) > chunk_size:
            _flush_words(chunks, current_words)
            current_words = []
            chunks.extend(
                _split_words_by_token_count(unit_words, chunk_size, overlap, tokenizer)
            )
            continue

        if (
            current_words
            and _token_count_words(current_words + unit_words, tokenizer) > chunk_size
        ):
            previous = current_words[:]
            _flush_words(chunks, current_words)
            current_words = _token_overlap_words(previous, overlap, tokenizer)
            while (
                current_words
                and _token_count_words(current_words + unit_words, tokenizer)
                > chunk_size
            ):
                current_words.pop(0)

        current_words.extend(unit_words)

    _flush_words(chunks, current_words)
    return chunks


def _split_words_by_token_count(
    words: list[str],
    chunk_size: int,
    overlap: int,
    tokenizer: Tokenizer,
) -> list[str]:
    chunks: list[str] = []
    current_words: list[str] = []

    for word in words:
        if not current_words:
            current_words = [word]
            continue

        if _token_count_words(current_words + [word], tokenizer) <= chunk_size:
            current_words.append(word)
            continue

        previous = current_words[:]
        _flush_words(chunks, current_words)
        current_words = _token_overlap_words(previous, overlap, tokenizer)
        while (
            current_words
            and _token_count_words(current_words + [word], tokenizer) > chunk_size
        ):
            current_words.pop(0)
        current_words.append(word)

    _flush_words(chunks, current_words)
    return chunks


def _token_overlap_words(
    words: list[str],
    overlap: int,
    tokenizer: Tokenizer,
) -> list[str]:
    if overlap == 0:
        return []

    for start in range(len(words)):
        suffix = words[start:]
        if _token_count_words(suffix, tokenizer) <= overlap:
            return suffix

    return []


def _token_count_words(words: list[str], tokenizer: Tokenizer) -> int:
    return _token_count(" ".join(words), tokenizer)


def _token_count(text: str, tokenizer: Tokenizer) -> int:
    try:
        return len(list(tokenizer(text)))
    except TypeError as error:
        raise TypeError("tokenizer must return an iterable of tokens.") from error


def _flush_words(chunks: list[str], words: list[str]) -> None:
    if words:
        chunks.append(" ".join(words))


# --- Dedupe ---


def dedupe_chunks(
    chunks,
    *,
    return_stats: bool = False,
    near_duplicate_threshold: float = 0.9,
    exact: bool = True,
    normalized: bool = True,
    near_duplicates: bool = True,
):
    """Remove duplicate and near-duplicate chunks."""
    chunk_texts = _validate_chunk_iterable(chunks, "dedupe_chunks")
    if not 0 <= near_duplicate_threshold <= 1:
        raise ValueError("near_duplicate_threshold must be between 0 and 1.")
    for name, value in {
        "exact": exact,
        "normalized": normalized,
        "near_duplicates": near_duplicates,
    }.items():
        if not isinstance(value, bool):
            raise TypeError(f"{name} must be a boolean.")

    result = _native_call(
        _core.dedupe_chunks,
        chunk_texts, near_duplicate_threshold, exact, normalized, near_duplicates,
        context="dedupe_chunks",
    )

    if not return_stats:
        return result["retained_chunks"]

    return DedupeResult(
        retained_chunks=result["retained_chunks"],
        removed_chunks=result["removed_chunks"],
        duplicate_count=result["duplicate_count"],
        duplicate_ratio=result["duplicate_ratio"],
        duplicate_groups=result.get("duplicate_groups", []),
        duplicate_metadata=result.get("duplicate_metadata", []),
    )


def _validate_chunk_iterable(chunks, function_name: str) -> list[str]:
    if isinstance(chunks, str) or not isinstance(chunks, Iterable):
        raise TypeError(f"{function_name}() expects an iterable of chunk strings.")

    chunk_texts = list(chunks)
    for chunk in chunk_texts:
        if not isinstance(chunk, str):
            raise TypeError(f"{function_name}() expects chunk strings.")

    return chunk_texts


# --- Score ---


def score_chunks(chunks):
    """Score chunk quality and attach warning labels."""
    chunk_texts = _validate_chunk_iterable(chunks, "score_chunks")

    scored = [
        Chunk(
            text=item["text"],
            tokens=item["tokens"],
            score=item["score"],
            warnings=item["warnings"],
        )
        for item in _native_call(_core.score_chunks, chunk_texts, context="score_chunks")
    ]

    if not _custom_scorers:
        return scored

    # Blend custom scorers with the Rust base score.
    total_custom_weight = sum(w for _, w, _ in _custom_scorers)
    if total_custom_weight > 1:
        total_custom_weight = 1.0
    base_weight = max(0.0, 1.0 - total_custom_weight)

    for chunk in scored:
        custom_total = 0.0
        for scorer_name, weight, fn in _custom_scorers:
            try:
                value = float(fn(chunk.text))
                value = max(0.0, min(1.0, value))
            except Exception:
                value = 0.5  # neutral on error
            custom_total += weight * value
        blended = base_weight * (chunk.score or 0.0) + custom_total
        chunk.score = round(max(0.0, min(1.0, blended)), 3)

    return scored
