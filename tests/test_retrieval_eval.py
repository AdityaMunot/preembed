import json
from pathlib import Path

from benchmarks.retrieval_eval import evaluate_all, load_eval


ROOT = Path(__file__).resolve().parents[1]
EVAL_FILE = ROOT / "benchmarks" / "retrieval_eval.json"


def test_retrieval_eval_questions_have_required_fields():
    config = json.loads(EVAL_FILE.read_text(encoding="utf-8"))
    ids = [item["id"] for item in config["questions"]]

    assert len(ids) == len(set(ids))
    assert config["top_k"] > 0
    for item in config["questions"]:
        assert item["question"]
        assert item["answer"]
        assert item["source_document"]
        assert item["required_phrases"]


def test_retrieval_eval_runs_all_strategies():
    payload = evaluate_all(load_eval(EVAL_FILE))
    by_strategy = {result["strategy"]: result for result in payload["results"]}

    assert set(by_strategy) == {
        "raw_fixed_window",
        "clean_fixed_window",
        "preembed_pipeline",
    }
    for result in by_strategy.values():
        assert result["question_count"] == 9
        assert result["chunk_count"] > 0
        assert 0 <= result["hit_at_1"] <= 1
        assert 0 <= result["hit_at_3"] <= 1
        assert 0 <= result["mrr"] <= 1


def test_preembed_pipeline_retrieves_expected_sources_at_top_k():
    payload = evaluate_all(load_eval(EVAL_FILE))
    preembed = next(
        result
        for result in payload["results"]
        if result["strategy"] == "preembed_pipeline"
    )

    assert preembed["hit_at_3"] >= 0.8
    misses = [item["id"] for item in preembed["questions"] if not item["hit_at_3"]]
    assert not misses
