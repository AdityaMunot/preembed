# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

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
