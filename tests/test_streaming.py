"""Tests for Pipeline.stream() batched iteration."""

from __future__ import annotations

from pathlib import Path

import pytest

from preembed import Pipeline


def test_stream_yields_all_documents(tmp_path: Path):
    for i in range(7):
        (tmp_path / f"doc{i}.txt").write_text(
            f"Document {i} content " * 30, encoding="utf-8"
        )

    batches = list(
        Pipeline(chunk_size=64, overlap=8).stream(str(tmp_path), batch_size=3)
    )

    assert len(batches) == 3  # 3 + 3 + 1
    total_docs = sum(b.stats.total_documents for b in batches)
    assert total_docs == 7


def test_stream_cross_batch_dedupe(tmp_path: Path):
    content = "Identical content across all files for dedup testing " * 20
    for i in range(4):
        (tmp_path / f"dup{i}.txt").write_text(content, encoding="utf-8")

    batches = list(
        Pipeline(chunk_size=64, overlap=8).stream(str(tmp_path), batch_size=2)
    )

    assert len(batches) >= 1
    first_chunks = batches[0].stats.total_chunks
    assert first_chunks > 0
    total_chunks = sum(b.stats.total_chunks for b in batches)
    assert total_chunks == first_chunks  # second batch fully deduped


def test_stream_cross_batch_normalized_dedupe(tmp_path: Path):
    for i in range(4):
        text = (
            ("Hello  World  Test  Content " * 20)
            if i % 2 == 0
            else ("hello world test content " * 20)
        )
        (tmp_path / f"norm{i}.txt").write_text(text, encoding="utf-8")

    batches = list(
        Pipeline(chunk_size=64, overlap=8).stream(str(tmp_path), batch_size=2)
    )

    first_chunks = batches[0].stats.total_chunks
    total_chunks = sum(b.stats.total_chunks for b in batches)
    assert total_chunks == first_chunks


def test_stream_with_progress(tmp_path: Path):
    for i in range(3):
        (tmp_path / f"doc{i}.txt").write_text(
            f"Content for doc {i} " * 20, encoding="utf-8"
        )

    stages = []
    for _ in Pipeline().stream(
        str(tmp_path), batch_size=2, progress=lambda s, c, t: stages.append(s)
    ):
        pass

    assert "clean" in stages
    assert "dedupe" in stages
    assert "score" in stages


def test_stream_single_batch_matches_run(tmp_path: Path):
    for i in range(3):
        (tmp_path / f"doc{i}.txt").write_text(
            f"Unique content {i} for comparison " * 20, encoding="utf-8"
        )

    pipe = Pipeline(chunk_size=128, overlap=16)
    run_result = pipe.run(str(tmp_path))
    stream_batches = list(pipe.stream(str(tmp_path), batch_size=100))

    assert len(stream_batches) == 1
    assert stream_batches[0].stats.total_chunks == run_result.stats.total_chunks
    assert stream_batches[0].chunks == run_result.chunks


def test_stream_batch_size_validation():
    with pytest.raises(ValueError):
        list(Pipeline().stream("test", batch_size=0))


def test_stream_empty_dir(tmp_path: Path):
    batches = list(Pipeline().stream(str(tmp_path)))
    assert batches == []


def test_stream_nonexistent_path():
    with pytest.raises(FileNotFoundError):
        list(Pipeline().stream("/nonexistent/path/that/does/not/exist"))


def test_stream_single_file(tmp_path: Path):
    f = tmp_path / "single.txt"
    f.write_text("Single file content for streaming " * 20, encoding="utf-8")

    batches = list(Pipeline(chunk_size=64, overlap=8).stream(str(f)))
    assert len(batches) == 1
    assert batches[0].stats.total_documents == 1
    assert batches[0].stats.total_chunks > 0


def test_stream_all_empty_files(tmp_path: Path):
    for i in range(3):
        (tmp_path / f"empty{i}.txt").write_text("", encoding="utf-8")

    batches = list(Pipeline().stream(str(tmp_path), batch_size=2))
    assert batches == []
