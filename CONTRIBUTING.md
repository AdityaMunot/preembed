# Contributing

## Setup

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m maturin develop --release
```

Rust toolchain (`cargo`, `rustc`) must be on `PATH`. Install via [rustup](https://rustup.rs/) if missing.

## Tests

```bash
.venv/bin/python -m pytest
cargo test --manifest-path rust/Cargo.toml
```

Add or update tests for every behavior change.

## Style

```bash
ruff check python tests benchmarks examples
ruff format python tests benchmarks examples
```

- Public Python API docstrings: one concise line.
- No "what" comments. Keep "why" comments only.
- Type-hint everything in public modules.
- Performance-critical work belongs in Rust; orchestration and validation in Python.

## Pull Requests

- Tests required for every behavior change.
- Do not commit build artifacts (`rust/target/`, `*.so`, wheels).
- Do not commit secrets or local `.env` files.
- Do not push, publish, or create remote resources without explicit maintainer approval.
- Do not bypass safety checks (`--no-verify`, force pushes).

## Scope

`preembed` is a document-preparation toolkit. It is not a full RAG framework. Do not add embedders, retrievers, or vector store integrations.
