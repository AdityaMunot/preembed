# Examples

`sample_corpus/` is a small, deliberately messy corpus for trying preembed end to end:

| File | What it exercises |
|---|---|
| `guides/account-recovery.md` | Clean markdown with headings and a code fence |
| `guides/account-recovery-copy.md` | Exact duplicate of the guide above (removed by dedupe) |
| `guides/rate-limits.md` | Clean markdown |
| `web/pricing.html` | Real content wrapped in `<script>`, `<style>`, `<nav>`, and `<footer>` noise |
| `web/footer.html` | Boilerplate-only page (cleans to nothing) |
| `logs/worker.log` | Repetitive log lines (flagged `low_information_density`) |

## Validate a corpus from the command line

```bash
pip install preembed
preembed check examples/sample_corpus --chunk-size 128 --overlap 16 --report report.html
preembed check examples/sample_corpus --max-duplicate-ratio 0.1   # exits 1: duplicates found
preembed export examples/sample_corpus -o chunks.jsonl --min-score 0.5
```

## Use the Python API

```bash
python examples/quickstart.py                 # bundled corpus
python examples/quickstart.py path/to/docs    # your own corpus
```
