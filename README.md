# preembed

<p align="center">
  <picture>
    <img src="https://raw.githubusercontent.com/AdityaMunot/preembed/main/assets/logo.png" alt="preembed" width="400">
  </picture>
</p>

> Clean, chunk, deduplicate, and score documents before embedding.

**preembed** is a high-performance toolkit that sits between your raw documents and your vector database. It turns messy HTML, markdown, logs, and exports into high-quality, LLM-ready chunks — so your RAG pipeline retrieves better context and hallucinates less.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org)
[![Rust](https://img.shields.io/badge/Rust-Powered-orange.svg)](https://www.rust-lang.org)

## Why

Most RAG pipelines embed documents directly — noise, duplicates, and all. The result: wasted tokens, bloated vector stores, and retrieval that returns boilerplate instead of answers.

preembed fixes the data before it enters the pipeline:

```
raw documents → clean → chunk → dedupe → score → embed
                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                        preembed handles this
```

## Install

```bash
pip install preembed
```

For development (requires Rust toolchain):

```bash
pip install -e ".[dev]"
maturin develop --release
```

## Validate your corpus in 60 seconds

No code required. Point the CLI at a folder of `.md`, `.txt`, `.html`, `.log`, `.json`, or `.csv` files:

```bash
pip install preembed
preembed check path/to/docs --report report.html
```

```
documents:          6
chunks:             6
avg chunk size:     103.2 words
duplicate ratio:    25.00%
low quality:        0 (0.00%, score < 0.5)
top warnings:       low_information_density=2

worst chunks:
  0.63  logs/worker.log#0  [low_information_density]
        2026-11-25T10:00:00Z worker-1 status ok heartbeat ok 2026-11-25T10:01:00Z wor...
  ...

PASS
```

`preembed check` exits `0` when thresholds pass, `1` when they fail, and `2` on bad input, so it works as a CI gate:

```bash
preembed check docs/ --min-score 0.5 --max-low-quality-ratio 0.2 --max-duplicate-ratio 0.1
preembed check docs/ --format json            # machine-readable summary
preembed export docs/ -o chunks.jsonl --min-score 0.5   # streamed, one chunk per line
```

Try it on the bundled messy corpus in [`examples/`](examples/) (duplicates, HTML boilerplate, noisy logs).

## Quickstart

### Pipeline (recommended)

```python
from preembed import Pipeline

result = Pipeline(chunk_size=512, overlap=64).run("path/to/documents/")
result.save_report("report.json")

print(f"{result.stats.total_chunks} chunks, {result.stats.duplicate_ratio:.0%} duplicates removed")
```

### Individual primitives

```python
from preembed import clean_text, chunk_text, dedupe_chunks, score_chunks

text = clean_text("<html><script>tracking()</script><p>Actual content here.</p></html>")
# → "Actual content here."

chunks = chunk_text(text, chunk_size=512, overlap=64)
chunks = dedupe_chunks(chunks)
scored = score_chunks(chunks)
# Each chunk gets a 0-1 quality score + warning labels
```

### Streaming (memory-efficient)

```python
for batch in Pipeline().stream("huge_corpus/", batch_size=50):
    upload_to_vector_db(batch.scored_chunks)
```

Documents are read and processed one batch at a time. Exact and normalized duplicates are removed across batches (near-duplicates within a batch); the cross-batch filter keeps a 16-byte hash per unique chunk, so memory grows with unique chunks, not with document size. A batch whose chunks were all duplicates is still yielded with no chunks, `duplicate_ratio == 1.0`, and the warning `all_chunks_duplicate`.

### Custom scoring

```python
from preembed import register_scorer

@register_scorer("domain_relevance", weight=0.15)
def domain_scorer(chunk: str) -> float:
    return 1.0 if "patient" in chunk.lower() else 0.3
```

Blends with the built-in scoring engine. Errors default to neutral (0.5) — won't crash your pipeline.

## How it works

| Stage | What it does |
|---|---|
| **Clean** | Strip HTML tags plus `script`, `style`, `nav`, `footer`, `noscript`, `template`, and `svg` blocks. Normalize whitespace and unicode. In the pipeline, paragraph and block boundaries are kept for chunking. |
| **Chunk** | Structure-aware splitting on headings, code fences, and paragraphs. Never exceeds `chunk_size` words (or tokens in token mode). Configurable overlap. |
| **Dedupe** | Exact, normalized, and near-duplicate removal via fingerprint similarity. |
| **Score** | Quality score (0–1) based on length, density, structure, duplicates. Warning labels for boilerplate, too-short/long, low-density. |
| **Report** | JSON, Markdown, or HTML diagnostics with per-chunk scores and recommendations. |

## API

```python
# Core primitives
clean_text(text: str, *, preserve_structure=False) -> str
chunk_text(text: str, chunk_size=512, overlap=64, mode="word", tokenizer=None) -> list[str]
dedupe_chunks(chunks, return_stats=False, near_duplicate_threshold=0.9) -> list[str] | DedupeResult
score_chunks(chunks) -> list[Chunk]

# Pipeline
Pipeline(chunk_size=512, overlap=64, dedupe=True, score=True)
Pipeline.run(source, progress=None) -> PipelineResult
Pipeline.stream(source, batch_size=50, progress=None) -> Iterator[PipelineResult]

# Extensibility
register_scorer(name, weight=0.1)(fn)
clear_scorers()
```

### CLI

```text
preembed check SOURCE [--chunk-size N] [--overlap N] [--no-clean] [--no-dedupe]
                      [--min-score F] [--max-low-quality-ratio F] [--max-duplicate-ratio F]
                      [--report PATH] [--format text|json]
preembed export SOURCE -o OUT.jsonl [--chunk-size N] [--overlap N] [--no-clean]
                      [--no-dedupe] [--min-score F]
```

Chunk offsets (`start_offset`/`end_offset`) index into `clean_text(document, preserve_structure=True)`, or the raw document when `clean=False`.

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,lint]"
pytest
cargo test --manifest-path rust/Cargo.toml
ruff check python tests examples && mypy python
```

## License

[MIT](LICENSE)
