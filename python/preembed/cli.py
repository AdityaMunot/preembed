"""Command-line interface for validating and exporting corpora with preembed."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from . import __version__
from .pipeline import Pipeline
from .types import Chunk, PipelineResult

EXIT_OK = 0
EXIT_THRESHOLD = 1
EXIT_USAGE = 2

_WORST_CHUNK_COUNT = 5
_PREVIEW_CHARS = 80
_TOP_WARNING_COUNT = 5


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected an integer, got {value!r}")
    if number <= 0:
        raise argparse.ArgumentTypeError(f"must be greater than 0, got {number}")
    return number


def _non_negative_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected an integer, got {value!r}")
    if number < 0:
        raise argparse.ArgumentTypeError(f"must be >= 0, got {number}")
    return number


def _unit_float(value: str) -> float:
    try:
        number = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected a number, got {value!r}")
    if not 0.0 <= number <= 1.0:
        raise argparse.ArgumentTypeError(f"must be between 0 and 1, got {number}")
    return number


def _add_pipeline_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "source", metavar="SOURCE", help="path to a file or folder to process"
    )
    parser.add_argument(
        "--chunk-size",
        type=_positive_int,
        metavar="N",
        default=512,
        help="maximum words per chunk (default: 512)",
    )
    parser.add_argument(
        "--overlap",
        type=_non_negative_int,
        metavar="N",
        default=64,
        help="words of overlap between chunks; must be < chunk size (default: 64)",
    )
    parser.add_argument("--no-clean", action="store_true", help="skip text cleaning")
    parser.add_argument(
        "--no-dedupe", action="store_true", help="skip duplicate removal"
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for the preembed CLI."""
    parser = argparse.ArgumentParser(
        prog="preembed",
        description="Clean, chunk, dedupe, and score documents before embedding.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    subparsers.required = True

    check = subparsers.add_parser(
        "check",
        help="validate corpus quality against thresholds",
        description=(
            "Run the pipeline on SOURCE and report corpus quality. Exits 0 when "
            "all thresholds pass, 1 when any fails, 2 on usage or input errors."
        ),
    )
    _add_pipeline_args(check)
    check.add_argument(
        "--min-score",
        type=_unit_float,
        metavar="F",
        default=0.5,
        help="chunks scoring below this are low quality (default: 0.5)",
    )
    check.add_argument(
        "--max-low-quality-ratio",
        type=_unit_float,
        metavar="F",
        default=0.25,
        help="fail if the low-quality chunk ratio exceeds this (default: 0.25)",
    )
    check.add_argument(
        "--max-duplicate-ratio",
        type=_unit_float,
        metavar="F",
        default=None,
        help="fail if the duplicate ratio exceeds this (default: unset)",
    )
    check.add_argument(
        "--report",
        metavar="PATH",
        default=None,
        help="also write a full report (.json, .md, or .html)",
    )
    check.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="summary output format (default: text)",
    )

    export = subparsers.add_parser(
        "export",
        help="write processed chunks to JSONL",
        description="Stream SOURCE through the pipeline and write chunks as JSONL.",
    )
    _add_pipeline_args(export)
    export.add_argument(
        "--output",
        "-o",
        metavar="PATH",
        required=True,
        help="destination .jsonl file",
    )
    export.add_argument(
        "--min-score",
        type=_unit_float,
        metavar="F",
        default=None,
        help="drop chunks scoring below this (default: keep all)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the preembed CLI and return a process exit code."""
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else EXIT_USAGE

    if args.overlap >= args.chunk_size:
        return _usage_error(
            f"--overlap ({args.overlap}) must be smaller than "
            f"--chunk-size ({args.chunk_size})"
        )

    source = Path(args.source)
    if not source.exists():
        return _usage_error(
            f"source path does not exist: {args.source} "
            "(preembed CLI accepts a file or folder path, not raw text)"
        )
    if not (source.is_file() or source.is_dir()):
        return _usage_error(f"source must be a file or folder: {args.source}")

    pipeline = Pipeline(
        clean=not args.no_clean,
        chunk_size=args.chunk_size,
        overlap=args.overlap,
        dedupe=not args.no_dedupe,
        score=True,
    )
    try:
        if args.command == "check":
            return _run_check(args, pipeline)
        return _run_export(args, pipeline)
    except (OSError, ValueError) as exc:
        return _usage_error(str(exc))


def _usage_error(message: str) -> int:
    print(f"preembed: error: {message}", file=sys.stderr)
    return EXIT_USAGE


def _run_check(args: argparse.Namespace, pipeline: Pipeline) -> int:
    result = pipeline.run(str(args.source))
    summary = _summarize(result, min_score=args.min_score)
    summary["source"] = str(args.source)
    failures = _threshold_failures(
        summary,
        max_low_quality_ratio=args.max_low_quality_ratio,
        max_duplicate_ratio=args.max_duplicate_ratio,
    )
    summary["thresholds"] = {
        "min_score": args.min_score,
        "max_low_quality_ratio": args.max_low_quality_ratio,
        "max_duplicate_ratio": args.max_duplicate_ratio,
    }
    summary["passed"] = not failures
    summary["failures"] = failures

    if args.report:
        result.save_report(args.report)
        summary["report"] = args.report

    if args.format == "json":
        print(json.dumps(summary, indent=2))
    else:
        _print_text_summary(summary)
    return EXIT_THRESHOLD if failures else EXIT_OK


def _summarize(result: PipelineResult, *, min_score: float) -> dict[str, Any]:
    stats = result.stats
    chunks = result.scored_chunks
    low_quality = sum(
        1 for chunk in chunks if chunk.score is not None and chunk.score < min_score
    )
    low_quality_ratio = low_quality / len(chunks) if chunks else 0.0
    warning_counts = Counter(w for chunk in chunks for w in chunk.warnings)
    worst = sorted(
        chunks,
        key=lambda c: (
            c.score if c.score is not None else 1.0,
            c.source_document or "",
            c.chunk_index if c.chunk_index is not None else 0,
        ),
    )[:_WORST_CHUNK_COUNT]
    return {
        "source": None,
        "documents": stats.total_documents,
        "chunks": stats.total_chunks,
        "average_chunk_size": round(stats.average_chunk_size, 2),
        "duplicate_ratio": round(stats.duplicate_ratio, 4),
        "low_quality_count": low_quality,
        "low_quality_ratio": round(low_quality_ratio, 4),
        "warning_counts": dict(warning_counts.most_common(_TOP_WARNING_COUNT)),
        "pipeline_warnings": list(result.warnings),
        "worst_chunks": [_chunk_summary(chunk) for chunk in worst],
    }


def _chunk_summary(chunk: Chunk) -> dict[str, Any]:
    return {
        "source_document": chunk.source_document,
        "chunk_index": chunk.chunk_index,
        "score": None if chunk.score is None else round(chunk.score, 4),
        "warnings": list(chunk.warnings),
        "preview": _preview(chunk.text),
    }


def _preview(text: str) -> str:
    flat = " ".join(text.split())
    if len(flat) <= _PREVIEW_CHARS:
        return flat
    return flat[: _PREVIEW_CHARS - 3].rstrip() + "..."


def _threshold_failures(
    summary: dict[str, Any],
    *,
    max_low_quality_ratio: float,
    max_duplicate_ratio: float | None,
) -> list[str]:
    if summary["chunks"] == 0:
        return ["no chunks produced"]
    failures: list[str] = []
    if summary["low_quality_ratio"] > max_low_quality_ratio:
        failures.append(
            f"low-quality ratio {summary['low_quality_ratio']:.2%} exceeds "
            f"--max-low-quality-ratio {max_low_quality_ratio:.2%}"
        )
    if (
        max_duplicate_ratio is not None
        and summary["duplicate_ratio"] > max_duplicate_ratio
    ):
        failures.append(
            f"duplicate ratio {summary['duplicate_ratio']:.2%} exceeds "
            f"--max-duplicate-ratio {max_duplicate_ratio:.2%}"
        )
    return failures


def _print_text_summary(summary: dict[str, Any]) -> None:
    lines = [
        f"documents:          {summary['documents']}",
        f"chunks:             {summary['chunks']}",
        f"avg chunk size:     {summary['average_chunk_size']:.1f} words",
        f"duplicate ratio:    {summary['duplicate_ratio']:.2%}",
        (
            f"low quality:        {summary['low_quality_count']} "
            f"({summary['low_quality_ratio']:.2%}, score < "
            f"{summary['thresholds']['min_score']})"
        ),
    ]
    if summary["warning_counts"]:
        top = ", ".join(f"{k}={v}" for k, v in summary["warning_counts"].items())
        lines.append(f"top warnings:       {top}")
    if summary["worst_chunks"]:
        lines.append("")
        lines.append("worst chunks:")
        for chunk in summary["worst_chunks"]:
            score = "n/a" if chunk["score"] is None else f"{chunk['score']:.2f}"
            warnings = ",".join(chunk["warnings"]) or "-"
            lines.append(
                f"  {score}  {chunk['source_document']}#{chunk['chunk_index']}"
                f"  [{warnings}]"
            )
            lines.append(f"        {chunk['preview']}")
    if summary.get("report"):
        lines.append("")
        lines.append(f"report written to {summary['report']}")
    lines.append("")
    if summary["failures"]:
        lines.append("FAIL")
        lines.extend(f"  - {failure}" for failure in summary["failures"])
    else:
        lines.append("PASS")
    print("\n".join(lines))


def _run_export(args: argparse.Namespace, pipeline: Pipeline) -> int:
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with output.open("w", encoding="utf-8") as handle:
        for batch in pipeline.stream(str(args.source), batch_size=50):
            for chunk in batch.scored_chunks:
                if (
                    args.min_score is not None
                    and chunk.score is not None
                    and chunk.score < args.min_score
                ):
                    continue
                handle.write(json.dumps(_chunk_record(chunk), ensure_ascii=False))
                handle.write("\n")
                written += 1
    print(f"wrote {written} chunks to {output}", file=sys.stderr)
    return EXIT_OK


def _chunk_record(chunk: Chunk) -> dict[str, Any]:
    return {
        "text": chunk.text,
        "score": chunk.score,
        "tokens": chunk.tokens,
        "warnings": list(chunk.warnings),
        "source_document": chunk.source_document,
        "chunk_index": chunk.chunk_index,
        "start_offset": chunk.start_offset,
        "end_offset": chunk.end_offset,
    }
