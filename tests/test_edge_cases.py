"""Edge case tests for the public preembed primitives."""

from __future__ import annotations

from pathlib import Path

import pytest

from preembed import Pipeline, chunk_text, clean_text, dedupe_chunks, score_chunks
from preembed.pipeline import _metadata_for_retained_chunks
from preembed.types import ChunkMetadata


def test_chunk_text_empty_returns_empty_list():
    assert chunk_text("") == []


def test_dedupe_chunks_empty_returns_empty_list():
    assert dedupe_chunks([]) == []


def test_score_chunks_empty_returns_empty_list():
    assert score_chunks([]) == []


def test_chunk_text_very_long_single_word():
    long_word = "a" * 20_000
    chunks = chunk_text(long_word, chunk_size=64, overlap=8)
    assert chunks
    assert all(isinstance(chunk, str) for chunk in chunks)


def test_dedupe_all_identical_chunks_keeps_one():
    chunks = ["alpha beta gamma"] * 10
    result = dedupe_chunks(chunks, return_stats=True)
    assert len(result.retained_chunks) == 1
    assert result.duplicate_count == 9


def test_chunk_text_token_mode_tokenizer_returns_empty():
    chunks = chunk_text(
        "hello world",
        chunk_size=4,
        overlap=1,
        mode="token",
        tokenizer=lambda value: [],
    )
    assert chunks


def test_chunk_text_token_mode_requires_callable_tokenizer():
    with pytest.raises(TypeError):
        chunk_text(
            "hello", chunk_size=8, overlap=1, mode="token", tokenizer="not-callable"
        )


def test_chunk_text_invalid_overlap_raises():
    with pytest.raises(ValueError):
        chunk_text("hello world", chunk_size=4, overlap=4)


def test_dedupe_chunks_rejects_non_string_items():
    with pytest.raises(TypeError):
        dedupe_chunks(["ok", 42])


def test_dedupe_chunks_rejects_none_item():
    with pytest.raises(TypeError):
        dedupe_chunks(["ok", None])


def test_score_chunks_rejects_non_string_items():
    with pytest.raises(TypeError):
        score_chunks([42])


def test_pipeline_rejects_invalid_path_type():
    with pytest.raises(TypeError):
        Pipeline().run(123)  # type: ignore[arg-type]


def test_clean_text_handles_emoji_and_combining_marks():
    raw = "<p>café 🚀 \u202eRTL\u202c</p>"
    cleaned = clean_text(raw)
    assert "🚀" in cleaned
    assert "café" in cleaned


def test_clean_text_handles_zero_width_characters():
    cleaned = clean_text("hello\u200bworld")
    assert "hello" in cleaned and "world" in cleaned


def test_dedupe_threshold_zero_collapses_overlapping_chunks():
    chunks = ["alpha beta gamma delta", "alpha beta gamma omega"]
    result = dedupe_chunks(chunks, near_duplicate_threshold=0.0, return_stats=True)
    assert len(result.retained_chunks) == 1


def test_dedupe_threshold_one_keeps_distinct():
    chunks = ["alpha beta gamma delta", "alpha beta gamma epsilon"]
    result = dedupe_chunks(chunks, near_duplicate_threshold=1.0, return_stats=True)
    assert len(result.retained_chunks) == 2


def test_dedupe_threshold_out_of_range_raises():
    with pytest.raises(ValueError):
        dedupe_chunks(["a"], near_duplicate_threshold=1.5)


def test_score_chunks_max_penalty_floors_at_zero():
    boilerplate = "home login contact privacy policy terms of service copyright"
    scored = score_chunks([boilerplate, boilerplate])
    assert scored[0].score >= 0.0


def test_metadata_for_retained_chunks_handles_duplicates():
    chunks = ["A", "B", "A", "C"]
    metadata = [
        ChunkMetadata("doc", 0, 0, 1),
        ChunkMetadata("doc", 1, 2, 3),
        ChunkMetadata("doc", 2, 4, 5),
        ChunkMetadata("doc", 3, 6, 7),
    ]
    retained = _metadata_for_retained_chunks(chunks, metadata, ["A", "B", "C"])
    assert [m.chunk_index for m in retained] == [0, 1, 3]


def test_save_report_creates_parent_dirs(tmp_path: Path):
    result = Pipeline().run("hello world " * 20)
    target = tmp_path / "nested" / "deeper" / "report.json"
    result.save_report(str(target))
    assert target.exists()


def test_chunk_text_with_long_token_overlap_still_terminates():
    chunks = chunk_text("word " * 200, chunk_size=10, overlap=9)
    assert chunks
