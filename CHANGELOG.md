# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

### Added
- `preembed` CLI: `preembed check` validates a corpus against score/duplicate thresholds with CI-friendly exit codes (0 pass, 1 threshold failure, 2 bad input), text or JSON output, and optional reports; `preembed export` streams chunks to JSONL. Also available as `python -m preembed`.
- `clean_text(..., preserve_structure=True)` keeps line and paragraph boundaries (HTML block tags become paragraph breaks).
- `examples/` sample corpus and quickstart script, exercised by the CI wheel smoke test.
- Type stub for the native `preembed_core` module.

### Changed
- `Pipeline` cleans with `preserve_structure=True`, so structure-aware chunking now sees headings, paragraphs, and code fences. Chunk boundaries can differ from 0.1.1, and offsets index into the structure-preserving cleaned text.
- HTML cleaning also drops `nav`, `footer`, `noscript`, `template`, and `svg` blocks. Self-closing and unclosed layout tags no longer hide following content.
- `Pipeline.stream()` `duplicate_ratio` now includes cross-batch removals, and batches whose chunks were all duplicates are yielded (empty, with warning `all_chunks_duplicate`) so document counts add up.
- CI: ruff pinned to 0.15.12, mypy is now a required check, examples are linted.

### Fixed
- `chunk_text` could exceed `chunk_size` when overlap carried into the next paragraph; overlap is now trimmed to fit.
- Token-mode chunking could exceed `chunk_size` when a single word was longer than the token budget; such words are now split.

## [0.1.1] - 2026-04-29

### Fixed
- sdist now includes LICENSE file.
- Structured error types (`PreembedError`) with context from native extension.
- Rust FFI validates chunk_size, overlap, and dedupe threshold before processing.

### Added
- `PreembedError` exception for native extension errors.
- Linux ARM (aarch64) wheel builds.
- macOS Intel (x86_64) wheel builds.
- CI smoke test: builds wheel, installs, verifies quickstart.
- Automated PyPI publishing via Trusted Publishing.

## [0.1.0] - 2026-04-29

### Added
- `clean_text`, `chunk_text`, `dedupe_chunks`, `score_chunks` — Rust-backed primitives.
- `Pipeline` orchestrator with `run()` and `stream()` (batched iteration with cross-batch dedupe).
- `progress` callback on `Pipeline.run()` and `Pipeline.stream()`.
- `register_scorer` / `clear_scorers` — pluggable custom scoring.
- `Tokenizer` and `Scorer` runtime-checkable protocols.
- `__version__` from `importlib.metadata`.
- JSON, Markdown, and HTML diagnostics reports.
- Token-mode chunking with pluggable tokenizer.
- Benchmark harness + real-world corpus (16 sources, 4.4 MB).
- Criterion microbenchmarks for Rust primitives.
- Proptest fuzz tests for Rust core.
- Hypothesis property tests for Python API.
- CI: lint, format, mypy, coverage, security audit, benchmark smoke, weekly wheels.
