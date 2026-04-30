"""Property-based tests using Hypothesis."""

from __future__ import annotations

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from preembed import chunk_text, clean_text, dedupe_chunks, score_chunks


# --- clean_text ---


@given(text=st.text(min_size=0, max_size=5000))
@settings(max_examples=200)
def test_clean_text_never_crashes(text: str):
    result = clean_text(text)
    assert isinstance(result, str)


@given(text=st.text(min_size=1, max_size=5000))
@settings(max_examples=200)
def test_clean_text_no_script_tags(text: str):
    result = clean_text(f"<script>{text}</script>")
    assert "<script>" not in result.lower()


# --- chunk_text ---


@given(
    text=st.text(
        min_size=1,
        max_size=3000,
        alphabet=st.characters(whitelist_categories=("L", "N", "Z")),
    ),
    chunk_size=st.integers(min_value=1, max_value=500),
    overlap=st.integers(min_value=0, max_value=499),
)
@settings(max_examples=200)
def test_chunk_size_invariant(text: str, chunk_size: int, overlap: int):
    assume(overlap < chunk_size)
    assume(len(text.split()) > 0)

    chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)

    assert isinstance(chunks, list)
    for chunk in chunks:
        assert isinstance(chunk, str)
        word_count = len(chunk.split())
        assert word_count <= chunk_size, (
            f"chunk has {word_count} words, max {chunk_size}"
        )


@given(
    text=st.text(
        min_size=10,
        max_size=2000,
        alphabet=st.characters(whitelist_categories=("L", "N", "Z")),
    ),
    chunk_size=st.integers(min_value=5, max_value=200),
)
@settings(max_examples=100)
def test_chunk_text_covers_all_words(text: str, chunk_size: int):
    assume(len(text.split()) > 0)
    overlap = min(chunk_size - 1, max(0, chunk_size // 4))

    chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)

    original_words = set(text.split())
    chunk_words = set()
    for chunk in chunks:
        chunk_words.update(chunk.split())

    # Every word in the original should appear in at least one chunk.
    assert original_words <= chunk_words


# --- dedupe_chunks ---


@given(
    chunks=st.lists(st.text(min_size=1, max_size=200), min_size=0, max_size=50),
)
@settings(max_examples=200)
def test_dedupe_never_adds_chunks(chunks: list[str]):
    result = dedupe_chunks(chunks)
    assert len(result) <= len(chunks)


@given(
    chunks=st.lists(st.text(min_size=1, max_size=200), min_size=1, max_size=50),
)
@settings(max_examples=200)
def test_dedupe_retains_are_subset(chunks: list[str]):
    retained = dedupe_chunks(chunks)
    for chunk in retained:
        assert chunk in chunks


# --- score_chunks ---


@given(
    chunks=st.lists(st.text(min_size=1, max_size=500), min_size=1, max_size=30),
)
@settings(max_examples=200)
def test_score_always_in_range(chunks: list[str]):
    scored = score_chunks(chunks)
    assert len(scored) == len(chunks)
    for chunk in scored:
        assert 0.0 <= chunk.score <= 1.0
        assert chunk.tokens >= 0
        assert isinstance(chunk.warnings, list)
