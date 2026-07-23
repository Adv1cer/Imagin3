"""Sequential (concurrency-1) benchmark runner with resume.

The runner is generation-agnostic: it takes a `generate_fn(CandidateSpec)
-> GenerationOutput`. The real DGX runner (benchmark.cli) wraps the actual
pipeline; tests pass a deterministic fake. The runner only expands the
dataset, times/records each candidate, writes the per-candidate artifacts
(poster.png, candidate.json, blank review.json), maintains the run
manifest, and skips already-completed candidates on resume.
"""

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .dataset import BenchmarkDataset
from .manifest import (
    CandidateRecord,
    CandidateSpec,
    GenerationOutput,
    RunManifest,
    classify_failure,
    expand_case,
)
from .review import aggregate_run, blank_review, render_summary_markdown

GenerateFn = Callable[[CandidateSpec], GenerationOutput]

# Rough, DOCUMENTED, configurable storage estimate per candidate used ONLY
# by --dry-run. A 1080x1350 poster PNG is typically ~1.2–1.8 MB; candidate
# JSON + blank review add a few KB. This is a sizing aid, not a measured
# value, and it makes NO runtime claim — real timing only exists after a
# real run produces durations.
DEFAULT_CANDIDATE_STORAGE_ESTIMATE_BYTES = 1_600_000


class EmptySelectionError(ValueError):
    """Filters selected zero candidates — fail safely, never silently run
    nothing or (worse) fall back to running everything."""


def select_candidates(
    dataset: BenchmarkDataset,
    case_ids: list[str] | None = None,
    seeds: list[int] | None = None,
    max_candidates: int | None = None,
) -> list[CandidateSpec]:
    """Expand the dataset to candidates, then apply optional filters in a
    deterministic order (case → seed → cap). Raises EmptySelectionError if
    nothing is selected, including when a requested case id or seed does
    not exist in the dataset."""
    wanted_cases = set(case_ids) if case_ids else None
    wanted_seeds = set(seeds) if seeds else None

    if wanted_cases is not None:
        known = {c.id for c in dataset.cases}
        unknown = wanted_cases - known
        if unknown:
            raise EmptySelectionError(
                f"unknown case id(s): {sorted(unknown)}; available: {sorted(known)}"
            )

    specs: list[CandidateSpec] = []
    for case in dataset.cases:
        if wanted_cases is not None and case.id not in wanted_cases:
            continue
        for spec in expand_case(case):
            if wanted_seeds is not None and spec.seed not in wanted_seeds:
                continue
            specs.append(spec)

    if max_candidates is not None:
        if max_candidates <= 0:
            raise EmptySelectionError(f"--max-candidates must be positive, got {max_candidates}")
        specs = specs[:max_candidates]

    if not specs:
        raise EmptySelectionError(
            f"no candidates matched filters (case_ids={case_ids}, seeds={seeds}, "
            f"max_candidates={max_candidates})"
        )
    return specs


@dataclass(frozen=True)
class RunPlan:
    run_id: str
    selected_cases: int
    total_expanded: int
    would_skip: int
    would_run: int
    by_case: dict
    by_template: dict
    by_aspect: dict
    by_seed: dict
    estimated_new_storage_bytes: int
    per_candidate_estimate_bytes: int


def _tally(specs, key) -> dict:
    out: dict = {}
    for spec in specs:
        out[key(spec)] = out.get(key(spec), 0) + 1
    return dict(sorted(out.items()))


def plan_run(
    dataset: BenchmarkDataset,
    output_root: str | Path,
    run_id: str,
    resume: bool = True,
    case_ids: list[str] | None = None,
    seeds: list[int] | None = None,
    max_candidates: int | None = None,
    per_candidate_estimate_bytes: int = DEFAULT_CANDIDATE_STORAGE_ESTIMATE_BYTES,
) -> RunPlan:
    """Compute what a run WOULD do without generating anything (--dry-run)."""
    specs = select_candidates(dataset, case_ids, seeds, max_candidates)
    run_dir = Path(output_root) / run_id

    would_skip = would_run = 0
    for spec in specs:
        if resume and _candidate_is_complete(run_dir / spec.relative_dir):
            would_skip += 1
        else:
            would_run += 1

    return RunPlan(
        run_id=run_id,
        selected_cases=len({s.case_id for s in specs}),
        total_expanded=len(specs),
        would_skip=would_skip,
        would_run=would_run,
        by_case=_tally(specs, lambda s: s.case_id),
        by_template=_tally(specs, lambda s: s.template),
        by_aspect=_tally(specs, lambda s: f"{s.width}x{s.height}"),
        by_seed=_tally(specs, lambda s: str(s.seed)),
        estimated_new_storage_bytes=would_run * per_candidate_estimate_bytes,
        per_candidate_estimate_bytes=per_candidate_estimate_bytes,
    )


def format_plan(plan: RunPlan) -> str:
    mb = plan.estimated_new_storage_bytes / (1024 * 1024)
    lines = [
        f"DRY RUN — no generation performed (run_id={plan.run_id})",
        f"  selected cases:       {plan.selected_cases}",
        f"  expanded candidates:  {plan.total_expanded}",
        f"  would skip (resume):  {plan.would_skip}",
        f"  would run:            {plan.would_run}",
        f"  est. new storage:     ~{mb:.1f} MB "
        f"(@ ~{plan.per_candidate_estimate_bytes // 1000} KB/candidate, rough estimate)",
        "  NOTE: no runtime estimate is claimed until a real run produces timing data.",
        "  by case:     " + ", ".join(f"{k}={v}" for k, v in plan.by_case.items()),
        "  by template: " + ", ".join(f"{k}={v}" for k, v in plan.by_template.items()),
        "  by aspect:   " + ", ".join(f"{k}={v}" for k, v in plan.by_aspect.items()),
        "  by seed:     " + ", ".join(f"{k}={v}" for k, v in plan.by_seed.items()),
    ]
    return "\n".join(lines)


@dataclass(frozen=True)
class HarnessResult:
    run_dir: str
    manifest_path: str
    summary_path: str
    generated: int
    skipped: int
    failed: int


def _candidate_is_complete(candidate_dir: Path) -> bool:
    record_file = candidate_dir / "candidate.json"
    if not record_file.exists():
        return False
    try:
        record = json.loads(record_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    # A prior 'error' candidate is NOT considered complete — it should be
    # retried on resume; a candidate with a real technical verdict is.
    return record.get("overall_status") not in (None, "error")


def run_benchmark(
    dataset: BenchmarkDataset,
    generate_fn: GenerateFn,
    output_root: str | Path,
    run_id: str,
    generation_settings: dict | None = None,
    resume: bool = True,
    case_ids: list[str] | None = None,
    seeds: list[int] | None = None,
    max_candidates: int | None = None,
) -> HarnessResult:
    # Selection first: raises EmptySelectionError before creating any run
    # directory when filters match nothing.
    specs = select_candidates(dataset, case_ids, seeds, max_candidates)

    run_dir = Path(output_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    manifest = RunManifest(
        run_id=run_id,
        dataset_version=dataset.version,
        dataset_path=dataset.source_path,
        created_at=datetime.now(timezone.utc).isoformat(),
        generation_settings=generation_settings or {},
    )

    generated = skipped = failed = 0

    for spec in specs:  # strictly sequential — concurrency 1
        candidate_dir = run_dir / spec.relative_dir
        candidate_dir.mkdir(parents=True, exist_ok=True)
        record_file = candidate_dir / "candidate.json"

        if resume and _candidate_is_complete(candidate_dir):
            manifest.candidates.append(json.loads(record_file.read_text(encoding="utf-8")))
            skipped += 1
            continue

        start = time.monotonic()
        try:
            output = generate_fn(spec)
        except Exception as exc:  # noqa: BLE001 — one bad candidate must not kill the run
            output = GenerationOutput(
                poster_bytes=None, overall_status="error", checks=[],
                resolved_template=spec.template, error=f"{type(exc).__name__}: {exc}",
            )
        duration = round(time.monotonic() - start, 3)

        poster_path: str | None = None
        if output.poster_bytes is not None:
            poster_file = candidate_dir / "poster.png"
            poster_file.write_bytes(output.poster_bytes)
            poster_path = str(poster_file.relative_to(run_dir))

        record = CandidateRecord(
            candidate_id=spec.candidate_id,
            case_id=spec.case_id,
            category=spec.category,
            prompt=spec.prompt,
            org_name=spec.org_name,
            official_domain=spec.official_domain,
            qr_url=spec.qr_url,
            requested_template=spec.template,
            resolved_template=output.resolved_template,
            width=spec.width,
            height=spec.height,
            seed=spec.seed,
            overall_status=output.overall_status,
            checks=output.checks,
            duration_seconds=duration,
            peak_memory_mb=output.peak_memory_mb,
            poster_path=poster_path,
            error=output.error,
            failure_type=classify_failure(output.overall_status, output.checks, output.error),
        )
        record_file.write_text(
            json.dumps({**record.to_dict(), "designMetadata": output.design_metadata},
                       ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        # Blank human-review file — never overwrite one a reviewer touched.
        review_file = candidate_dir / "review.json"
        if not review_file.exists():
            review_file.write_text(json.dumps(blank_review(), ensure_ascii=False, indent=2), encoding="utf-8")

        manifest.candidates.append(record.to_dict())
        if output.overall_status == "error":
            failed += 1
        else:
            generated += 1

    manifest_path = run_dir / "run_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )

    summary_path = run_dir / "summary.md"
    summary_path.write_text(render_summary_markdown(aggregate_run(run_dir)), encoding="utf-8")

    return HarnessResult(
        run_dir=str(run_dir),
        manifest_path=str(manifest_path),
        summary_path=str(summary_path),
        generated=generated,
        skipped=skipped,
        failed=failed,
    )
