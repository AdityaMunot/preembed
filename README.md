# preembed

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
                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
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

## Quickstart

### Pipeline (recommended)

```python
from preembed import Pipeline

result = Pipeline(chunk_size=512, overlap=64).run("docs/")
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

Cross-batch deduplication included. Processes one batch at a time — constant memory regardless of corpus size.

### Custom scoring

```python
from preembed import register_scorer

@register_scorer("domain_relevance", weight=0.15)
def domain_scorer(chunk: str) -> float:
    return 1.0 if "patient" in chunk.lower() else 0.3
```

Blends with the built-in scoring engine. Errors default to neutral (0.5) — won't crash your pipeline.

## Performance

Benchmarked on a 15 MB real-world corpus (Wikipedia, RFCs, Gutenberg, GitHub, MDN, Hacker News):

| Operation | preembed | BeautifulSoup | LangChain | LlamaIndex |
|---|---:|---:|---:|---:|
| **Cleaning** | 110 ms | 1,643 ms | — | — |
| **Chunking** | 31 ms | — | 1,467 ms | 1,465 ms |
| **Full pipeline** | 543 ms | — | — | — |

Cleaning is native-compiled. Deduplication uses an inverted fingerprint index — O(1) for exact/normalized matches.

<details>
<summary>More benchmark comparisons</summary>

| Chunker | Time | Chunks | Quality |
|---|---:|---:|---:|
| preembed | 31 ms | 8,136 | 1.000 |
| Chonkie | 103 ms | 8,994 | 0.975 |
| semantic-text-splitter | 211 ms | 8,710 | 0.956 |
| semchunk | 214 ms | 8,396 | 0.967 |
| LangChain Recursive | 1,467 ms | 16,889 | 0.672 |
| LlamaIndex Sentence | 1,465 ms | 16,889 | 0.672 |

Quality scores are heuristic signals (length, density, structure, duplicates), not human relevance judgments. See [docs/BENCHMARKS.md](docs/BENCHMARKS.md) for methodology and caveats.

</details>

## How it works

| Stage | What it does |
|---|---|
| **Clean** | Strip HTML, scripts, styles. Normalize whitespace and unicode. |
| **Chunk** | Structure-aware splitting. Preserves headings, code blocks, paragraphs. Configurable size + overlap. |
| **Dedupe** | Exact, normalized, and near-duplicate removal via fingerprint similarity. |
| **Score** | Quality score (0–1) based on length, density, structure, duplicates. Warning labels for boilerplate, too-short/long, low-density. |
| **Report** | JSON, Markdown, or HTML diagnostics with per-chunk scores and recommendations. |

## API

```python
# Core primitives
clean_text(text: str) -> str
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

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## License

[MIT](LICENSE)
