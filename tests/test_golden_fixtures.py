import json
import re
import statistics
from pathlib import Path

import pytest

from preembed import chunk_text, clean_text, dedupe_chunks, score_chunks


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "benchmarks" / "fixtures"
GOLDEN = FIXTURES / "golden.json"
MANIFEST = FIXTURES / "manifest.json"
HTML_TAG_RE = re.compile(r"</?[A-Za-z][A-Za-z0-9:-]*(?:\s[^<>]*)?>")
ESCAPED_ENTITY_RE = re.compile(r"&(?:amp|lt|gt|quot|apos|#[0-9]+|#x[0-9a-fA-F]+);")
SCRIPT_STYLE_ARTIFACT_RE = re.compile(
    r"console[.]log|<\s*/?\s*(?:script|style)\b|font-family|display\s*:",
    re.IGNORECASE,
)


@pytest.fixture(scope="module")
def golden():
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_golden_covers_manifest_documents(golden):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    expected = set(manifest["documents"])
    actual = set(golden["fixtures"])

    assert actual == expected, (
        "golden fixture coverage must match manifest documents. "
        f"Missing: {sorted(expected - actual)!r}; extra: {sorted(actual - expected)!r}"
    )


@pytest.mark.parametrize(
    "fixture_name", sorted(json.loads(GOLDEN.read_text(encoding="utf-8"))["fixtures"])
)
def test_golden_clean_expectations(golden, fixture_name):
    expectations = golden["fixtures"][fixture_name]["clean"]
    cleaned = _clean_fixture(fixture_name)

    if expectations.get("forbid_html_tags"):
        assert not HTML_TAG_RE.search(cleaned), (
            f"{fixture_name} retained HTML-like tag text: {cleaned!r}"
        )

    if expectations.get("forbid_script_style_text"):
        assert not SCRIPT_STYLE_ARTIFACT_RE.search(cleaned), (
            f"{fixture_name} retained script/style implementation noise: {cleaned!r}"
        )

    if expectations.get("forbid_escaped_entities"):
        assert not ESCAPED_ENTITY_RE.search(cleaned), (
            f"{fixture_name} retained escaped HTML entity: {cleaned!r}"
        )

    for phrase in expectations.get("forbid_phrases", []):
        assert phrase not in cleaned, (
            f"{fixture_name} retained forbidden phrase {phrase!r}: {cleaned!r}"
        )

    for phrase in expectations.get("require_phrases", []):
        assert phrase in cleaned, (
            f"{fixture_name} lost required phrase {phrase!r}: {cleaned!r}"
        )


@pytest.mark.parametrize(
    "fixture_name", sorted(json.loads(GOLDEN.read_text(encoding="utf-8"))["fixtures"])
)
def test_golden_chunk_expectations(golden, fixture_name):
    defaults = golden["defaults"]
    expectations = golden["fixtures"][fixture_name]["chunks"]
    chunks = _chunks_for_fixture(
        fixture_name, defaults["chunk_size"], defaults["overlap"]
    )

    assert len(chunks) >= expectations["min_count"], (
        f"{fixture_name} produced too few chunks: {chunks!r}"
    )

    for phrase in expectations.get("require_any_chunk_phrases", []):
        assert any(phrase in chunk for chunk in chunks), (
            f"{fixture_name} did not keep {phrase!r} in any chunk. Chunks: {chunks!r}"
        )

    for phrase_group in expectations.get("require_same_chunk_phrase_groups", []):
        assert any(
            all(phrase in chunk for phrase in phrase_group) for chunk in chunks
        ), (
            f"{fixture_name} did not keep phrase group in one chunk: {phrase_group!r}. Chunks: {chunks!r}"
        )

    if expectations.get("forbid_unbalanced_code_fences"):
        unbalanced = [chunk for chunk in chunks if chunk.count("```") % 2 != 0]
        assert not unbalanced, (
            f"{fixture_name} split code fences across chunks: {unbalanced!r}"
        )


def test_golden_duplicate_sections_are_deduped(golden):
    fixture_name = "knowledge_base_duplicate.md"
    expectations = golden["fixtures"][fixture_name]["dedupe"]
    chunks = _chunks_for_fixture(
        fixture_name, expectations["chunk_size"], expectations["overlap"]
    )
    result = dedupe_chunks(
        chunks,
        return_stats=True,
        near_duplicate_threshold=expectations["near_duplicate_threshold"],
    )
    retained_ratio = len(result.retained_chunks) / len(chunks)

    assert len(chunks) > len(result.retained_chunks), (
        f"{fixture_name} did not remove any duplicate chunks: {chunks!r}"
    )
    assert retained_ratio <= expectations["max_retained_ratio"], (
        f"{fixture_name} retained too many duplicate chunks: {len(result.retained_chunks)} of {len(chunks)}"
    )

    for phrase in expectations.get("require_retained_phrases", []):
        assert any(phrase in chunk for chunk in result.retained_chunks), (
            f"{fixture_name} did not retain expected phrase {phrase!r}: {result.retained_chunks!r}"
        )

    for phrase in expectations.get("require_removed_phrases", []):
        assert any(phrase in chunk for chunk in result.removed_chunks), (
            f"{fixture_name} did not remove expected duplicate phrase {phrase!r}: {result.removed_chunks!r}"
        )


@pytest.mark.parametrize(
    "fixture_name", sorted(json.loads(GOLDEN.read_text(encoding="utf-8"))["fixtures"])
)
def test_golden_score_expectations(golden, fixture_name):
    defaults = golden["defaults"]
    expectations = golden["fixtures"][fixture_name]["score"]
    chunks = _chunks_for_fixture(
        fixture_name, defaults["chunk_size"], defaults["overlap"]
    )
    scored = score_chunks(dedupe_chunks(chunks))
    scores = [chunk.score or 0.0 for chunk in scored]

    assert scores, f"{fixture_name} produced no scored chunks from chunks: {chunks!r}"

    average_score = statistics.mean(scores)

    assert average_score >= expectations["min_average_score"], (
        f"{fixture_name} average score {average_score:.3f} is below "
        f"{expectations['min_average_score']:.3f}: {[(chunk.text, chunk.score, chunk.warnings) for chunk in scored]!r}"
    )

    for warning in expectations.get("require_any_warning", []):
        assert any(warning in chunk.warnings for chunk in scored), (
            f"{fixture_name} did not produce expected warning {warning!r}: "
            f"{[(chunk.text, chunk.warnings) for chunk in scored]!r}"
        )


def _clean_fixture(fixture_name: str) -> str:
    return clean_text((FIXTURES / fixture_name).read_text(encoding="utf-8"))


def _chunks_for_fixture(fixture_name: str, chunk_size: int, overlap: int) -> list[str]:
    return chunk_text(
        _clean_fixture(fixture_name), chunk_size=chunk_size, overlap=overlap
    )
