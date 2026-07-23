import json
from pathlib import Path

import pytest

from imagin.benchmark.dataset import BenchmarkCase, BenchmarkDataset, AspectRatio
from imagin.benchmark.harness import (
    EmptySelectionError,
    plan_run,
    run_benchmark,
    select_candidates,
)
from imagin.benchmark.manifest import CandidateSpec, GenerationOutput, expand_case
from imagin.benchmark.review import aggregate_run, blank_review, candidate_status


def _dataset() -> BenchmarkDataset:
    case = BenchmarkCase(
        id="case-a",
        category="university_open_house",
        prompt="โปสเตอร์เปิดบ้าน",
        org_name="Acme University",
        official_domain="acme.example",
        qr_url="https://acme.example/",
        templates=("centered_editorial", "auto"),
        aspect_ratios=(AspectRatio(1080, 1350),),
        seeds=(1, 2),
    )
    return BenchmarkDataset(version="1", cases=(case,), source_path="mem://test")


def _one_px_png() -> bytes:
    # Minimal valid PNG (1x1) — the harness only writes bytes; it never
    # decodes them, so a tiny valid file is enough for offline tests.
    import base64
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )


def _fake_generate_fn(calls: list) -> object:
    def generate_fn(spec: CandidateSpec) -> GenerationOutput:
        calls.append(spec.candidate_id)
        resolved = "centered_editorial" if spec.template == "auto" else spec.template
        # Make seed 2 deterministically "fail" a technical gate so failure
        # aggregation has something to group.
        passed = spec.seed != 2
        return GenerationOutput(
            poster_bytes=_one_px_png(),
            overall_status="pass" if passed else "fail",
            checks=[
                {"name": "ocr_exact_match", "passed": passed, "detail": "fake"},
                {"name": "qr_decode_match", "passed": True, "detail": "fake"},
            ],
            resolved_template=resolved,
            design_metadata={"template": resolved, "seed": spec.seed},
            peak_memory_mb=None,
        )
    return generate_fn


def test_expand_case_is_cartesian_product():
    dataset = _dataset()
    specs = expand_case(dataset.cases[0])
    assert len(specs) == 2 * 1 * 2  # templates x aspects x seeds
    assert {s.candidate_id for s in specs} == {
        "case-a__centered_editorial__1080x1350__seed1",
        "case-a__centered_editorial__1080x1350__seed2",
        "case-a__auto__1080x1350__seed1",
        "case-a__auto__1080x1350__seed2",
    }


def test_run_benchmark_writes_artifacts_and_manifest(tmp_path):
    dataset = _dataset()
    calls: list = []

    result = run_benchmark(dataset, _fake_generate_fn(calls), tmp_path, run_id="run1")

    assert len(calls) == 4
    # All 4 produced a technical verdict (seed-2 'fail' is a verdict, not a
    # generation error), so generated=4, failed=0.
    assert result.generated == 4 and result.failed == 0
    run_dir = Path(result.run_dir)

    # Per-candidate dir layout: <case>/<template>_<WxH>/seed_<seed>/
    candidate_dir = run_dir / "case-a" / "centered_editorial_1080x1350" / "seed_1"
    assert (candidate_dir / "poster.png").exists()
    assert (candidate_dir / "candidate.json").exists()
    assert (candidate_dir / "review.json").exists()

    record = json.loads((candidate_dir / "candidate.json").read_text())
    assert record["resolved_template"] == "centered_editorial"
    assert record["poster_path"] == "case-a/centered_editorial_1080x1350/seed_1/poster.png"
    assert record["overall_status"] == "pass"

    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    assert manifest["candidateCount"] == 4
    assert (run_dir / "summary.md").exists()

    # auto resolved and recorded.
    auto_record = json.loads(
        (run_dir / "case-a" / "auto_1080x1350" / "seed_1" / "candidate.json").read_text()
    )
    assert auto_record["requested_template"] == "auto"
    assert auto_record["resolved_template"] == "centered_editorial"


def test_resume_skips_completed_candidates(tmp_path):
    dataset = _dataset()

    first_calls: list = []
    run_benchmark(dataset, _fake_generate_fn(first_calls), tmp_path, run_id="run2")
    assert len(first_calls) == 4

    # Second run with resume: nothing should be regenerated.
    second_calls: list = []
    result = run_benchmark(dataset, _fake_generate_fn(second_calls), tmp_path, run_id="run2")
    assert second_calls == []
    assert result.skipped == 4 and result.generated == 0


def test_resume_regenerates_error_candidates(tmp_path):
    dataset = _dataset()

    def failing_fn(spec: CandidateSpec) -> GenerationOutput:
        raise RuntimeError("comfyui exploded")

    result = run_benchmark(dataset, failing_fn, tmp_path, run_id="run3")
    assert result.failed == 4 and result.generated == 0

    # An 'error' candidate is not 'complete' — resume retries it.
    retry_calls: list = []
    result2 = run_benchmark(dataset, _fake_generate_fn(retry_calls), tmp_path, run_id="run3")
    assert len(retry_calls) == 4 and result2.skipped == 0


def test_one_bad_candidate_does_not_abort_the_run(tmp_path):
    dataset = _dataset()

    def flaky_fn(spec: CandidateSpec) -> GenerationOutput:
        if spec.seed == 2:
            raise RuntimeError("boom on seed 2")
        return GenerationOutput(
            poster_bytes=_one_px_png(), overall_status="pass",
            checks=[{"name": "ocr_exact_match", "passed": True, "detail": "ok"}],
            resolved_template="centered_editorial",
        )

    result = run_benchmark(dataset, flaky_fn, tmp_path, run_id="run4")
    # 2 seed-1 candidates succeeded, 2 seed-2 candidates errored — run finished.
    assert result.generated == 2 and result.failed == 2


def test_aggregation_groups_and_reads_human_reviews(tmp_path):
    dataset = _dataset()
    run_benchmark(dataset, _fake_generate_fn([]), tmp_path, run_id="run5")
    run_dir = tmp_path / "run5"

    # A human fills one review with an approval + scores.
    review_file = run_dir / "case-a" / "centered_editorial_1080x1350" / "seed_1" / "review.json"
    review = blank_review()
    review["approved"] = True
    review["visual_quality"] = 4
    review["semantic_correctness"] = 2  # fixture copy mismatch, as expected
    review_file.write_text(json.dumps(review), encoding="utf-8")

    agg = aggregate_run(run_dir)

    assert agg["totalCandidates"] == 4
    # 'auto' resolves to centered_editorial, so grouping by RESOLVED template
    # puts all 4 candidates under centered_editorial.
    assert agg["byTemplate"]["centered_editorial"]["candidates"] == 4
    assert agg["byTemplate"]["centered_editorial"]["approved"] == 1
    # Failure grouping picked up the seed-2 technical fail.
    assert any("ocr_exact_match" in k for k in agg["byFailureType"])
    assert agg["byCategory"]["university_open_house"]["mean_scores"]["visual_quality"] == 4


# ---- Safety controls: filters, dry-run plan, status taxonomy --------------


def _multi_case_dataset() -> BenchmarkDataset:
    a = BenchmarkCase(
        id="case-a", category="open_house", prompt="p", org_name="O",
        official_domain="o.example", qr_url="https://o.example/",
        templates=("centered_editorial",), aspect_ratios=(AspectRatio(1080, 1350),), seeds=(1, 2),
    )
    b = BenchmarkCase(
        id="case-b", category="recruitment", prompt="p", org_name="O",
        official_domain="o.example", qr_url="https://o.example/",
        templates=("centered_editorial",), aspect_ratios=(AspectRatio(1080, 1350),), seeds=(2, 3),
    )
    return BenchmarkDataset(version="1", cases=(a, b), source_path="mem://multi")


def test_select_candidates_filters_by_case_and_seed_and_caps():
    dataset = _multi_case_dataset()

    assert len(select_candidates(dataset)) == 4
    assert {s.case_id for s in select_candidates(dataset, case_ids=["case-a"])} == {"case-a"}
    assert {s.seed for s in select_candidates(dataset, seeds=[2])} == {2}
    assert len(select_candidates(dataset, max_candidates=1)) == 1
    # Combined: case-b + seed 3 -> exactly one candidate.
    combined = select_candidates(dataset, case_ids=["case-b"], seeds=[3])
    assert len(combined) == 1 and combined[0].case_id == "case-b" and combined[0].seed == 3


def test_select_candidates_fails_safely_on_empty_selection():
    dataset = _multi_case_dataset()
    with pytest.raises(EmptySelectionError):
        select_candidates(dataset, seeds=[999])          # no such seed
    with pytest.raises(EmptySelectionError):
        select_candidates(dataset, case_ids=["nope"])    # unknown case id
    with pytest.raises(EmptySelectionError):
        select_candidates(dataset, max_candidates=0)     # non-positive cap


def test_run_benchmark_raises_on_empty_selection_before_creating_run_dir(tmp_path):
    dataset = _multi_case_dataset()
    with pytest.raises(EmptySelectionError):
        run_benchmark(dataset, _fake_generate_fn([]), tmp_path, run_id="empty", seeds=[999])
    assert not (tmp_path / "empty").exists()


def test_max_candidates_enforced_end_to_end(tmp_path):
    dataset = _multi_case_dataset()
    calls: list = []
    result = run_benchmark(dataset, _fake_generate_fn(calls), tmp_path, run_id="capped", max_candidates=2)
    assert len(calls) == 2 and (result.generated + result.failed) == 2


def test_dry_run_plan_counts_without_generating(tmp_path):
    dataset = _multi_case_dataset()

    plan = plan_run(dataset, tmp_path, run_id="planA")

    assert plan.total_expanded == 4
    assert plan.would_run == 4 and plan.would_skip == 0
    assert plan.by_case == {"case-a": 2, "case-b": 2}
    assert plan.by_seed == {"1": 1, "2": 2, "3": 1}
    assert plan.estimated_new_storage_bytes == 4 * plan.per_candidate_estimate_bytes
    # A dry run must not create any run directory or candidate files.
    assert not (tmp_path / "planA").exists()


def test_dry_run_respects_resume_after_a_real_run(tmp_path):
    dataset = _multi_case_dataset()
    run_benchmark(dataset, _fake_generate_fn([]), tmp_path, run_id="planB")  # completes 4

    plan = plan_run(dataset, tmp_path, run_id="planB", resume=True)

    assert plan.would_skip == 4 and plan.would_run == 0
    assert plan.estimated_new_storage_bytes == 0


def test_candidate_status_taxonomy_keeps_error_distinct_from_rejection():
    # Generation error is never a human rejection.
    assert candidate_status({"overall_status": "error"}, blank_review()) == "generation_error"
    # Technical QA failure is its own bucket.
    assert candidate_status({"overall_status": "fail"}, blank_review()) == "technical_qa_failure"
    # Technically OK + no human decision = pending (NOT zero, NOT rejected).
    assert candidate_status({"overall_status": "pass"}, blank_review()) == "pending_review"
    approved = {**blank_review(), "approved": True}
    rejected = {**blank_review(), "approved": False}
    assert candidate_status({"overall_status": "pass"}, approved) == "approved"
    assert candidate_status({"overall_status": "warn"}, rejected) == "human_rejected"


def test_blank_reviews_are_pending_not_zero_in_aggregation(tmp_path):
    dataset = _multi_case_dataset()
    run_benchmark(dataset, _fake_generate_fn([]), tmp_path, run_id="pend")  # nobody reviews

    agg = aggregate_run(tmp_path / "pend")

    # seed-2 candidates technically fail (2 of them); the rest are pending,
    # none are rejected, and no score was fabricated as zero.
    totals = agg["statusTotals"]
    assert totals["human_rejected"] == 0
    assert totals["pending_review"] + totals["technical_qa_failure"] == agg["totalCandidates"]
    for bucket in agg["byCategory"].values():
        for score in bucket["mean_scores"].values():
            assert score is None  # blank reviews contribute no numeric score
