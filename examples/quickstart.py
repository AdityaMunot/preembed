"""Run preembed on the bundled sample corpus and print what it found."""

from __future__ import annotations

import sys
from pathlib import Path

from preembed import Pipeline

CORPUS = Path(__file__).parent / "sample_corpus"


def main(source: str = str(CORPUS)) -> int:
    """Process ``source`` and print stats, the cleanest chunk, and the noisiest chunk."""
    result = Pipeline(chunk_size=128, overlap=16).run(source)
    stats = result.stats

    print(f"documents:       {stats.total_documents}")
    print(f"chunks kept:     {stats.total_chunks}")
    print(f"duplicate ratio: {stats.duplicate_ratio:.0%}")

    ranked = sorted(result.scored_chunks, key=lambda chunk: chunk.score or 0.0)
    if ranked:
        for label, chunk in (("noisiest", ranked[0]), ("cleanest", ranked[-1])):
            print(
                f"{label}: {chunk.source_document}#{chunk.chunk_index} "
                f"score={chunk.score} warnings={chunk.warnings}"
            )

    result.save_report("preembed-report.html")
    print("report written to preembed-report.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:]))
