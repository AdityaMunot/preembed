# preembed

> Clean, chunk, deduplicate, and score documents before embedding.

**preembed** is a high-performance toolkit that sits between your raw documents and your vector database. It turns messy HTML, markdown, logs, and exports into high-quality, LLM-ready chunks — so your RAG pipeline retrieves better context and hallucinates less.

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
