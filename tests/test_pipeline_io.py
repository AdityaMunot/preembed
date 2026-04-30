"""Pipeline I/O tests: encoding, traversal, and offset edge cases."""

from __future__ import annotations

from pathlib import Path


from preembed import Pipeline, score_chunks


def test_pipeline_handles_non_utf8_file(tmp_path: Path):
    bad = tmp_path / "latin1.txt"
    bad.write_bytes("café résumé".encode("latin-1"))

    result = Pipeline().run(str(tmp_path))

    assert result.stats.total_documents >= 1


def test_pipeline_skips_hidden_files(tmp_path: Path):
    (tmp_path / "visible.txt").write_text(
        "visible document content " * 50, encoding="utf-8"
    )
    (tmp_path / ".hidden.txt").write_text("hidden content", encoding="utf-8")

    result = Pipeline().run(str(tmp_path))

    sources = {meta.source_document for meta in result.chunk_metadata}
    assert "visible.txt" in sources
    assert ".hidden.txt" not in sources


def test_pipeline_bounds_recursion_depth(tmp_path: Path):
    deep = tmp_path
    for index in range(15):
        deep = deep / f"level{index}"
        deep.mkdir()
    (deep / "deep.txt").write_text("ignored deep content", encoding="utf-8")
    (tmp_path / "shallow.txt").write_text("shallow content " * 20, encoding="utf-8")

    result = Pipeline().run(str(tmp_path))

    sources = {meta.source_document for meta in result.chunk_metadata}
    assert any(name.startswith("shallow") for name in sources)


def test_pipeline_offsets_after_aggressive_cleaning(tmp_path: Path):
    raw = (
        "<html><body>"
        + ("<script>noise</script>" * 50)
        + "Real content here. " * 30
        + "</body></html>"
    )
    file = tmp_path / "noisy.html"
    file.write_text(raw, encoding="utf-8")

    result = Pipeline().run(str(file))

    assert result.chunks
    for meta in result.chunk_metadata:
        assert meta.start_offset >= 0
        assert meta.end_offset >= meta.start_offset


def test_pipeline_handles_empty_file(tmp_path: Path):
    empty = tmp_path / "empty.txt"
    empty.write_text("", encoding="utf-8")
    result = Pipeline().run(str(empty))
    assert result.stats.total_chunks == 0


def test_pipeline_handles_broken_symlink(tmp_path: Path):
    link = tmp_path / "broken.txt"
    link.symlink_to(tmp_path / "nonexistent.txt")
    (tmp_path / "real.txt").write_text("real content " * 30, encoding="utf-8")

    result = Pipeline().run(str(tmp_path))

    sources = {m.source_document for m in result.chunk_metadata}
    assert "real.txt" in sources
    assert "broken.txt" not in sources


def test_report_json_with_special_chars(tmp_path: Path):
    src = tmp_path / "input.txt"
    src.write_text(
        'Special chars: <script>alert("xss")</script> & "quotes" apostrophe ' * 20,
        encoding="utf-8",
    )
    result = Pipeline().run(str(src))
    target = tmp_path / "report.json"
    result.save_report(str(target))
    assert target.exists()
    import json

    data = json.loads(target.read_text(encoding="utf-8"))
    assert "chunks" in data


def test_report_markdown_with_special_chars(tmp_path: Path):
    src = tmp_path / "input.md"
    src.write_text(
        "## Heading\n\n" + ("Content with `code` and *markdown* " * 30),
        encoding="utf-8",
    )
    result = Pipeline().run(str(src))
    target = tmp_path / "report.md"
    result.save_report(str(target))
    assert target.exists()
    text = target.read_text(encoding="utf-8")
    assert "# preembed Diagnostics Report" in text


def test_report_html_with_special_chars(tmp_path: Path):
    src = tmp_path / "input.html"
    src.write_text(
        "<p>HTML &amp; entities &lt;tag&gt;</p> " * 30,
        encoding="utf-8",
    )
    result = Pipeline().run(str(src))
    target = tmp_path / "report.html"
    result.save_report(str(target))
    assert target.exists()
    text = target.read_text(encoding="utf-8")
    assert "<!doctype html>" in text


def test_report_without_scoring(tmp_path: Path):
    src = tmp_path / "input.txt"
    src.write_text("hello world " * 50, encoding="utf-8")
    result = Pipeline(score=False).run(str(src))
    target = tmp_path / "report.json"
    result.save_report(str(target))
    assert target.exists()
    import json

    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["chunks"][0]["score"] is None


def test_mixed_language_scoring():

    chunks = [
        "这是中文文本的一个测试 " * 20,
        "Ceci est un test en français avec des accents " * 10,
        "Dies ist ein deutscher Textblock für Qualitätstests " * 10,
    ]
    scored = score_chunks(chunks)
    assert len(scored) == 3
    for chunk in scored:
        assert 0.0 <= chunk.score <= 1.0
