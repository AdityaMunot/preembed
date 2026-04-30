"""Report generation helpers for preembed."""

from __future__ import annotations

import json
from dataclasses import asdict
from html import escape
from pathlib import Path

_FORMAT_HANDLERS = {}


def _register(suffixes: set[str]):
    def decorator(fn):
        for s in suffixes:
            _FORMAT_HANDLERS[s] = fn
        return fn

    return decorator


def save_report(result, path: str) -> None:
    suffix = Path(path).suffix.lower() or ".json"
    handler = _FORMAT_HANDLERS.get(suffix)
    if handler is None:
        raise ValueError(f"Unsupported report format: {suffix}")
    handler(result, path)


# --- Shared helpers ---


def _report_data(result) -> dict:
    return {
        "stats": asdict(result.stats),
        "warnings": result.warnings,
        "recommendations": _recommendations(result),
        "chunks": _serialized_chunks(result),
    }


def _recommendations(result) -> list[str]:
    recs: list[str] = []

    if result.stats.duplicate_ratio > 0.1:
        recs.append("Review duplicate-heavy sources before embedding.")
    if result.stats.low_quality_chunk_count:
        recs.append(
            "Inspect low-scoring chunks and tune cleaning or chunk size settings."
        )
    if result.stats.average_chunk_size < 80 and result.stats.total_chunks:
        recs.append("Consider increasing chunk_size to reduce very small chunks.")

    chunk_warnings = {w for c in result.scored_chunks for w in c.warnings}
    if "boilerplate" in chunk_warnings:
        recs.append("Add source-specific boilerplate removal rules.")
    if "too_long" in chunk_warnings:
        recs.append(
            "Reduce chunk_size or improve structural splitting for long chunks."
        )

    return recs


def _serialized_chunks(result) -> list[dict]:
    if result.scored_chunks:
        return [asdict(chunk) for chunk in result.scored_chunks]

    metadata_list = list(result.chunk_metadata)
    if metadata_list and len(metadata_list) != len(result.chunks):
        raise RuntimeError(
            f"chunk metadata count ({len(metadata_list)}) does not match chunk count ({len(result.chunks)})"
        )
    return [
        {
            "text": chunk,
            "tokens": len(chunk.split()),
            "score": None,
            "warnings": [],
            "source_document": metadata_list[i].source_document
            if i < len(metadata_list)
            else None,
            "chunk_index": metadata_list[i].chunk_index
            if i < len(metadata_list)
            else None,
            "start_offset": metadata_list[i].start_offset
            if i < len(metadata_list)
            else None,
            "end_offset": metadata_list[i].end_offset
            if i < len(metadata_list)
            else None,
        }
        for i, chunk in enumerate(result.chunks)
    ]


def _chunk_summary(chunk: dict) -> str:
    warnings = ", ".join(chunk["warnings"]) if chunk["warnings"] else "none"
    return (
        f"Score: {chunk['score']}  Tokens: {chunk['tokens']}  Warnings: {warnings}  "
        f"Source: {chunk['source_document']}  Index: {chunk['chunk_index']}  "
        f"Offsets: {chunk['start_offset']}..{chunk['end_offset']}"
    )


# --- Format handlers ---


@_register({"", ".json"})
def _save_json(result, path: str) -> None:
    Path(path).write_text(json.dumps(_report_data(result), indent=2), encoding="utf-8")


@_register({".md", ".markdown"})
def _save_markdown(result, path: str) -> None:
    data = _report_data(result)
    s = data["stats"]
    lines = [
        "# preembed Diagnostics Report",
        "",
        "## Stats",
        "",
        f"- Total documents: {s['total_documents']}",
        f"- Total chunks: {s['total_chunks']}",
        f"- Average chunk size: {s['average_chunk_size']:.2f}",
        f"- Duplicate ratio: {s['duplicate_ratio']:.2%}",
        f"- Low-quality chunks: {s['low_quality_chunk_count']}",
        "",
        "## Warnings",
        "",
    ]
    lines.extend([f"- {w}" for w in data["warnings"]] or ["- None"])
    lines.extend(["", "## Recommendations", ""])
    lines.extend(
        [f"- {r}" for r in data["recommendations"]]
        or ["- No immediate fixes recommended."]
    )
    lines.extend(["", "## Chunks", ""])

    for i, chunk in enumerate(data["chunks"], start=1):
        lines.extend(
            [
                f"### Chunk {i}",
                "",
                f"- {_chunk_summary(chunk)}",
                "",
                "```text",
                chunk["text"],
                "```",
                "",
            ]
        )

    Path(path).write_text("\n".join(lines), encoding="utf-8")


@_register({".html", ".htm"})
def _save_html(result, path: str) -> None:
    data = _report_data(result)
    s = data["stats"]
    warning_items = (
        "".join(f"<li>{escape(w)}</li>" for w in data["warnings"]) or "<li>None</li>"
    )
    rec_items = (
        "".join(f"<li>{escape(r)}</li>" for r in data["recommendations"])
        or "<li>No immediate fixes recommended.</li>"
    )
    chunk_items = "\n".join(
        f"<section><h3>Chunk {i}</h3><p>{escape(_chunk_summary(c))}</p><pre>{escape(c['text'])}</pre></section>"
        for i, c in enumerate(data["chunks"], start=1)
    )

    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>preembed Diagnostics Report</title>
  <style>
    body {{ font-family: system-ui, sans-serif; line-height: 1.5; margin: 2rem; max-width: 960px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 0.5rem; text-align: left; }}
    pre {{ background: #f6f8fa; padding: 1rem; overflow-x: auto; }}
  </style>
</head>
<body>
  <h1>preembed Diagnostics Report</h1>
  <h2>Stats</h2>
  <table>
    <tr><th>Total documents</th><td>{s["total_documents"]}</td></tr>
    <tr><th>Total chunks</th><td>{s["total_chunks"]}</td></tr>
    <tr><th>Average chunk size</th><td>{s["average_chunk_size"]:.2f}</td></tr>
    <tr><th>Duplicate ratio</th><td>{s["duplicate_ratio"]:.2%}</td></tr>
    <tr><th>Low-quality chunks</th><td>{s["low_quality_chunk_count"]}</td></tr>
  </table>
  <h2>Warnings</h2>
  <ul>{warning_items}</ul>
  <h2>Recommendations</h2>
  <ul>{rec_items}</ul>
  <h2>Chunks</h2>
  {chunk_items}
</body>
</html>
"""

    Path(path).write_text(document, encoding="utf-8")
