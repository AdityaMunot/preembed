import json
import re

import pytest

from preembed import Pipeline, chunk_text, clean_text, dedupe_chunks, score_chunks


def test_pipeline_placeholder_exists():
    pipe = Pipeline()

    result = pipe.run("Hello world. Hello world.")

    assert result.stats.total_documents == 1
    assert result.stats.total_chunks == 1
    assert result.chunks == ["Hello world. Hello world."]


def test_clean_text_normalizes_whitespace():
    assert clean_text("hello\n\n  world") == "hello world"


def test_clean_text_strips_simple_html():
    assert clean_text("<h1>Hello</h1><p>world</p>") == "Hello world"


def test_clean_text_unescapes_html_entities():
    assert clean_text("<p>Tom &amp; Jerry</p>") == "Tom & Jerry"


def test_clean_text_removes_script_and_style_blocks():
    source = "<style>.x{}</style><p>Hello</p><script>alert(1)</script>"

    assert clean_text(source) == "Hello"


def test_clean_text_normalizes_unicode():
    assert clean_text("ＡＢＣ") == "ABC"


def test_clean_text_preserves_markdown_markers_as_text():
    assert clean_text("# Heading\n\n- item") == "# Heading - item"


def test_clean_text_requires_string():
    with pytest.raises(TypeError):
        clean_text(None)


def test_chunk_text_splits_by_word_count():
    chunks = chunk_text("one two three four five", chunk_size=2, overlap=0)

    assert chunks == [
        "one two",
        "three four",
        "five",
    ]
    assert all(isinstance(chunk, str) for chunk in chunks)


def test_chunk_text_supports_overlap():
    assert chunk_text("one two three four five", chunk_size=3, overlap=1) == [
        "one two three",
        "three four five",
    ]


def test_chunk_text_word_mode_is_default_behavior():
    text = "one two three four five"

    assert chunk_text(text, chunk_size=3, overlap=1) == chunk_text(
        text,
        chunk_size=3,
        overlap=1,
        mode="word",
    )


def test_chunk_text_preserves_fourth_positional_argument():
    source = "# Heading\n\nbody text"

    assert chunk_text(source, 10, 0, False) == ["# Heading body text"]


def test_chunk_text_token_mode_uses_tokenizer_budget():
    chunks = chunk_text(
        "alpha, beta gamma.",
        chunk_size=3,
        overlap=0,
        mode="token",
        tokenizer=_punctuation_tokenizer,
    )

    assert chunks == ["alpha, beta", "gamma."]
    assert all(len(_punctuation_tokenizer(chunk)) <= 3 for chunk in chunks)


def test_chunk_text_token_mode_supports_token_overlap():
    chunks = chunk_text(
        "alpha, beta gamma.",
        chunk_size=3,
        overlap=1,
        mode="token",
        tokenizer=_punctuation_tokenizer,
    )

    assert chunks == ["alpha, beta", "beta gamma."]
    assert all(len(_punctuation_tokenizer(chunk)) <= 3 for chunk in chunks)


def test_chunk_text_token_mode_requires_tokenizer():
    with pytest.raises(TypeError):
        chunk_text("hello world", mode="token")


def test_chunk_text_preserves_code_block_as_unit_when_possible():
    source = "Intro\n\n```python\nprint('hello')\n```\n\nOutro"

    assert chunk_text(source, chunk_size=10, overlap=0) == [
        "Intro ```python print('hello') ``` Outro",
    ]


def test_chunk_text_validates_config():
    with pytest.raises(ValueError):
        chunk_text("hello", chunk_size=2, overlap=2)

    with pytest.raises(ValueError):
        chunk_text("hello", mode="byte")


def _punctuation_tokenizer(text: str) -> list[str]:
    return re.findall(r"\w+|[^\w\s]", text)


def test_dedupe_chunks_removes_exact_duplicates():
    assert dedupe_chunks(["a", "b", "a"]) == ["a", "b"]


def test_dedupe_chunks_removes_normalized_duplicates():
    assert dedupe_chunks(["Hello   world", "hello world"]) == ["Hello   world"]


def test_dedupe_chunks_removes_near_duplicates():
    chunks = [
        "alpha beta gamma delta epsilon zeta eta",
        "alpha beta gamma delta epsilon zeta theta",
    ]

    assert dedupe_chunks(chunks, near_duplicate_threshold=0.6) == [chunks[0]]


def test_dedupe_chunks_can_return_stats():
    result = dedupe_chunks(["a", "a", "b"], return_stats=True)

    assert result.retained_chunks == ["a", "b"]
    assert result.removed_chunks == ["a"]
    assert result.duplicate_count == 1
    assert result.duplicate_ratio == pytest.approx(1 / 3)
    assert result.duplicate_groups == [
        {
            "retained_index": 0,
            "retained_chunk": "a",
            "duplicates": [
                {
                    "index": 1,
                    "chunk": "a",
                    "retained_index": 0,
                    "retained_chunk": "a",
                    "kind": "exact",
                    "similarity": 1.0,
                }
            ],
        }
    ]
    assert result.duplicate_metadata[0]["kind"] == "exact"


def test_dedupe_chunks_can_disable_exact_matching():
    assert dedupe_chunks(
        ["same", "same"], exact=False, normalized=False, near_duplicates=False
    ) == [
        "same",
        "same",
    ]


def test_dedupe_chunks_can_disable_normalized_matching():
    assert dedupe_chunks(
        ["Hello   world", "hello world"],
        exact=True,
        normalized=False,
        near_duplicates=False,
    ) == [
        "Hello   world",
        "hello world",
    ]


def test_dedupe_chunks_threshold_controls_near_duplicates():
    chunks = [
        "alpha beta gamma delta epsilon zeta eta",
        "alpha beta gamma delta epsilon zeta theta",
    ]

    assert dedupe_chunks(
        chunks, exact=False, normalized=False, near_duplicate_threshold=0.6
    ) == [chunks[0]]
    assert (
        dedupe_chunks(
            chunks, exact=False, normalized=False, near_duplicate_threshold=0.9
        )
        == chunks
    )


def test_dedupe_chunks_requires_iterable_of_strings():
    with pytest.raises(TypeError):
        dedupe_chunks("not a chunk list")

    with pytest.raises(TypeError):
        dedupe_chunks(["ok", None])


def test_dedupe_chunks_validates_near_duplicate_threshold():
    with pytest.raises(ValueError):
        dedupe_chunks(["ok"], near_duplicate_threshold=1.5)


def test_score_chunks_returns_chunk_scores():
    scored = score_chunks(
        ["This is a useful chunk with several distinct words for testing quality."]
    )

    assert scored[0].text.startswith("This is")
    assert scored[0].tokens == 12
    assert 0 <= scored[0].score <= 1


def test_score_chunks_warns_for_duplicates_and_boilerplate():
    scored = score_chunks(
        [
            "Home Login About Contact Privacy Policy",
            "Home Login About Contact Privacy Policy",
        ]
    )

    assert "duplicate_likelihood" in scored[0].warnings
    assert "boilerplate" in scored[0].warnings


def test_score_chunks_penalizes_low_information_text():
    scored = score_chunks(
        [
            "status status status status status status status status status status "
            "status status status status status status status status status status"
        ]
    )

    assert scored[0].score < 0.4
    assert "low_information_density" in scored[0].warnings


def test_score_chunks_penalizes_duplicate_chunks():
    chunks = [
        "This chunk explains account recovery tokens, audit log retention, administrator approval workflows, requester verification steps, and escalation handling.",
        "This chunk explains account recovery tokens, audit log retention, administrator approval workflows, requester verification steps, and escalation handling.",
    ]

    scored = score_chunks(chunks)

    assert scored[0].score < 0.6
    assert "duplicate_likelihood" in scored[0].warnings


def test_score_chunks_preserves_code_structure_credit():
    scored = score_chunks(
        [
            "```python\n"
            "def normalize(items):\n"
            "    cleaned = []\n"
            "    for item in items:\n"
            "        if item:\n"
            "            cleaned.append(item.strip().lower())\n"
            "    return cleaned\n"
            "```\n"
            "The helper normalizes identifiers before duplicate comparison."
        ]
    )

    assert scored[0].score >= 0.6


def test_score_chunks_requires_iterable_of_strings():
    with pytest.raises(TypeError):
        score_chunks("not a chunk list")

    with pytest.raises(TypeError):
        score_chunks(["ok", None])


def test_pipeline_runs_on_file(tmp_path):
    source = tmp_path / "doc.md"
    source.write_text("# Title\n\nHello world", encoding="utf-8")

    result = Pipeline(chunk_size=10, overlap=0).run(str(source))

    assert result.stats.total_documents == 1
    assert result.chunks == ["# Title Hello world"]
    assert result.chunk_metadata[0].source_document == "doc.md"
    assert result.chunk_metadata[0].chunk_index == 0
    assert result.chunk_metadata[0].start_offset == 0
    assert result.chunk_metadata[0].end_offset == len(
        clean_text(source.read_text(encoding="utf-8"))
    )


def test_pipeline_runs_on_folder(tmp_path):
    (tmp_path / "a.md").write_text("Alpha", encoding="utf-8")
    (tmp_path / "b.txt").write_text("Beta", encoding="utf-8")

    result = Pipeline(chunk_size=10, overlap=0).run(str(tmp_path))

    assert result.stats.total_documents == 2
    assert result.stats.total_chunks == 2
    assert result.chunks == ["Alpha", "Beta"]
    assert [metadata.source_document for metadata in result.chunk_metadata] == [
        "a.md",
        "b.txt",
    ]
    assert [metadata.start_offset for metadata in result.chunk_metadata] == [0, 0]
    assert [metadata.end_offset for metadata in result.chunk_metadata] == [5, 4]


def test_pipeline_offsets_reference_cleaned_text():
    source = "<h1>Title</h1><p>Alpha &amp; Beta</p>"
    cleaned = clean_text(source)

    result = Pipeline(chunk_size=10, overlap=0).run(source)

    assert result.chunks == [cleaned]
    assert result.chunk_metadata[0].source_document == "<text>"
    assert result.chunk_metadata[0].start_offset == 0
    assert result.chunk_metadata[0].end_offset == len(cleaned)
    assert result.scored_chunks[0].start_offset == 0
    assert result.scored_chunks[0].end_offset == len(cleaned)


def test_pipeline_offsets_reference_raw_text_when_cleaning_disabled():
    source = "one two\nthree four five"

    result = Pipeline(
        clean=False, chunk_size=3, overlap=1, dedupe=False, score=False
    ).run(source)

    assert result.chunks == ["one two three", "three four five"]
    for chunk, metadata in zip(result.chunks, result.chunk_metadata, strict=True):
        assert (
            source[metadata.start_offset : metadata.end_offset].split() == chunk.split()
        )


def test_pipeline_ignores_unsupported_folder_files(tmp_path):
    (tmp_path / "a.md").write_text("Alpha", encoding="utf-8")
    (tmp_path / "image.png").write_bytes(b"\x89PNG")

    result = Pipeline(chunk_size=10, overlap=0).run(str(tmp_path))

    assert result.stats.total_documents == 1
    assert result.chunks == ["Alpha"]


def test_pipeline_rejects_invalid_config():
    with pytest.raises(ValueError):
        Pipeline(chunk_size=10, overlap=10).run("hello")


def test_pipeline_saves_json_report(tmp_path):
    report_path = tmp_path / "report.json"
    result = Pipeline(chunk_size=10, overlap=0).run("Hello world")

    result.save_report(str(report_path))

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["stats"]["total_documents"] == 1
    assert payload["recommendations"]
    assert payload["chunks"][0]["text"] == "Hello world"
    assert payload["chunks"][0]["source_document"] == "<text>"
    assert payload["chunks"][0]["start_offset"] == 0
    assert payload["chunks"][0]["end_offset"] == len("Hello world")


def test_pipeline_rejects_unsupported_report_format(tmp_path):
    report_path = tmp_path / "report.xml"
    result = Pipeline(chunk_size=10, overlap=0).run("Hello world")

    with pytest.raises(ValueError):
        result.save_report(str(report_path))


def test_pipeline_report_includes_chunks_when_scoring_disabled(tmp_path):
    report_path = tmp_path / "report.json"
    result = Pipeline(chunk_size=10, overlap=0, score=False).run("Hello world")

    result.save_report(str(report_path))

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["chunks"][0]["text"] == "Hello world"
    assert payload["chunks"][0]["score"] is None
    assert payload["chunks"][0]["source_document"] == "<text>"
    assert payload["chunks"][0]["start_offset"] == 0
    assert payload["chunks"][0]["end_offset"] == len("Hello world")


def test_pipeline_saves_markdown_report(tmp_path):
    report_path = tmp_path / "report.md"
    result = Pipeline(chunk_size=10, overlap=0).run(
        "Home Login About Contact Privacy Policy"
    )

    result.save_report(str(report_path))

    content = report_path.read_text(encoding="utf-8")
    assert "# preembed Diagnostics Report" in content
    assert "Recommendations" in content


def test_pipeline_saves_html_report(tmp_path):
    report_path = tmp_path / "report.html"
    result = Pipeline(chunk_size=10, overlap=0).run("Hello <world>")

    result.save_report(str(report_path))

    content = report_path.read_text(encoding="utf-8")
    assert "<!doctype html>" in content
    assert "preembed Diagnostics Report" in content
    assert "Offsets:" in content
    assert "&lt;world&gt;" not in content
