import json
import subprocess
import sys
from pathlib import Path

import pytest
from preembed import __version__
from preembed.cli import main

PROSE = (
    "Vector databases store dense embeddings so that semantic search can find "
    "related passages even when the exact keywords differ. Careful chunking keeps "
    "each passage focused on one idea, which improves retrieval precision. Removing "
    "navigation menus, cookie banners, and repeated footers before embedding avoids "
    "wasting index space on text that never answers a question."
)
BOILERPLATE = "Home | About | Contact | Login\nCopyright 2024. All rights reserved."


def _good_corpus(root: Path) -> Path:
    corpus = root / "good"
    corpus.mkdir()
    topics = ["databases", "chunking", "cleaning", "ranking"]
    for i, topic in enumerate(topics):
        text = f"This guide covers {topic} for retrieval systems. {PROSE}"
        (corpus / f"doc{i}.md").write_text(text, encoding="utf-8")
    return corpus


def _duplicate_corpus(root: Path) -> Path:
    corpus = root / "dupes"
    corpus.mkdir()
    for i in range(4):
        (corpus / f"page{i}.txt").write_text(BOILERPLATE, encoding="utf-8")
    return corpus


def test_check_passes_on_clean_corpus(tmp_path, capsys):
    corpus = _good_corpus(tmp_path)

    code = main(["check", str(corpus), "--chunk-size", "64", "--overlap", "8"])

    out = capsys.readouterr().out
    assert code == 0
    assert "PASS" in out
    assert "documents:" in out


def test_check_fails_duplicate_threshold(tmp_path, capsys):
    corpus = _duplicate_corpus(tmp_path)

    code = main(["check", str(corpus), "--max-duplicate-ratio", "0.0"])

    out = capsys.readouterr().out
    assert code == 1
    assert "FAIL" in out
    assert "duplicate ratio" in out


def test_check_fails_when_no_chunks(tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()

    code = main(["check", str(empty)])

    assert code == 1
    assert "no chunks produced" in capsys.readouterr().out


def test_check_missing_path_is_usage_error(tmp_path, capsys):
    code = main(["check", str(tmp_path / "missing")])

    assert code == 2
    assert "does not exist" in capsys.readouterr().err


@pytest.mark.parametrize(
    "extra",
    [
        ["--chunk-size", "10", "--overlap", "10"],
        ["--chunk-size", "0"],
        ["--min-score", "1.5"],
        ["--max-low-quality-ratio", "-0.1"],
    ],
)
def test_check_invalid_args_are_usage_errors(tmp_path, capsys, extra):
    corpus = _good_corpus(tmp_path)

    code = main(["check", str(corpus), *extra])

    assert code == 2
    assert capsys.readouterr().err


def test_check_json_format_is_parseable(tmp_path, capsys):
    corpus = _good_corpus(tmp_path)

    code = main(["check", str(corpus), "--format", "json"])

    summary = json.loads(capsys.readouterr().out)
    assert code == 0
    assert summary["passed"] is True
    assert summary["documents"] == 4
    assert summary["chunks"] > 0
    assert 0.0 <= summary["low_quality_ratio"] <= 1.0
    assert isinstance(summary["worst_chunks"], list)


def test_check_writes_report(tmp_path, capsys):
    corpus = _good_corpus(tmp_path)
    report = tmp_path / "out" / "report.json"

    code = main(["check", str(corpus), "--report", str(report)])

    capsys.readouterr()
    assert code == 0
    assert "stats" in json.loads(report.read_text(encoding="utf-8"))


def test_export_writes_jsonl(tmp_path, capsys):
    corpus = _good_corpus(tmp_path)
    output = tmp_path / "chunks.jsonl"

    code = main(["export", str(corpus), "--output", str(output)])

    lines = output.read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    assert code == 0
    assert records
    expected = {
        "text",
        "score",
        "tokens",
        "warnings",
        "source_document",
        "chunk_index",
        "start_offset",
        "end_offset",
    }
    assert all(set(record) == expected for record in records)
    assert f"wrote {len(records)} chunks" in capsys.readouterr().err


def test_export_min_score_filters_chunks(tmp_path, capsys):
    corpus = _good_corpus(tmp_path)
    (corpus / "nav.txt").write_text(BOILERPLATE, encoding="utf-8")
    all_out = tmp_path / "all.jsonl"
    filtered_out = tmp_path / "filtered.jsonl"

    assert main(["export", str(corpus), "-o", str(all_out), "--no-dedupe"]) == 0
    assert (
        main(
            [
                "export",
                str(corpus),
                "-o",
                str(filtered_out),
                "--no-dedupe",
                "--min-score",
                "0.99",
            ]
        )
        == 0
    )
    capsys.readouterr()

    all_records = [json.loads(line) for line in all_out.read_text().splitlines()]
    kept = [json.loads(line) for line in filtered_out.read_text().splitlines()]
    assert len(kept) < len(all_records)
    assert all(record["score"] >= 0.99 for record in kept)


def test_export_single_file(tmp_path, capsys):
    source = tmp_path / "doc.txt"
    source.write_text(PROSE, encoding="utf-8")
    output = tmp_path / "doc.jsonl"

    code = main(["export", str(source), "--output", str(output)])

    capsys.readouterr()
    records = [json.loads(line) for line in output.read_text().splitlines()]
    assert code == 0
    assert records[0]["source_document"] == "doc.txt"


def test_module_version_subprocess():
    completed = subprocess.run(
        [sys.executable, "-m", "preembed", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert __version__ in completed.stdout
