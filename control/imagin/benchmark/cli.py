"""Real-DGX benchmark command — SEPARATE from the deterministic unit tests.

`python -m imagin.benchmark.cli --dataset benchmarks/poster_cases.yaml`

Reuses the exact production pipeline (run_poster_generation) as the
generate-fn, one candidate at a time (concurrency 1). Requires the same
prerequisites as the main CLI (workflow, node map, reachable ComfyUI,
migrated schema) — imported lazily so this module stays importable (and
the harness stays testable) without the native stack.
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from .dataset import DatasetError, load_dataset
from .harness import EmptySelectionError, format_plan, plan_run, run_benchmark
from .manifest import CandidateSpec, GenerationOutput

CONTROL_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DATASET = CONTROL_ROOT / "benchmarks" / "poster_cases.yaml"
DEFAULT_OUTPUT_ROOT = Path("output") / "bench"


def _read_peak_memory_mb() -> float | None:
    """Best-effort GPU peak memory (POC-grade, 'when available'). Returns
    None if no CUDA/torch is present — the harness records None rather than
    failing. Real per-candidate DGX memory instrumentation is a later,
    explicitly-scoped concern; this only proves the hook exists."""
    try:
        import torch  # type: ignore

        if torch.cuda.is_available():
            mb = torch.cuda.max_memory_allocated() / (1024 * 1024)
            torch.cuda.reset_peak_memory_stats()
            return round(mb, 1)
    except Exception:
        return None
    return None


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the poster quality benchmark against the real DGX pipeline (concurrency 1)."
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET, help="Path to the benchmark YAML dataset.")
    parser.add_argument("--run-id", default=None, help="Run id (default: timestamp). Reused for resume.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT, help="Where run dirs are written.")
    parser.add_argument("--no-resume", action="store_true", help="Regenerate even completed candidates.")
    parser.add_argument("--background-retries", type=int, default=2, help="Max text-free background retries per candidate.")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would run (case/candidate counts, breakdown, storage estimate) and exit. No generation.",
    )
    parser.add_argument(
        "--case-id", action="append", default=None, dest="case_ids",
        help="Only run this case id (repeatable).",
    )
    parser.add_argument(
        "--seed", action="append", type=int, default=None, dest="seed_filter",
        help="Only run candidates with this seed (repeatable).",
    )
    parser.add_argument("--max-candidates", type=int, default=None, help="Cap the number of candidates run.")
    return parser


def _make_real_generate_fn(session, object_store, http_client, comfyui_client, workflow, node_map, background_retries):
    from ..pipeline import BackgroundTextError, run_poster_generation

    def generate_fn(spec: CandidateSpec) -> GenerationOutput:
        template_id = None if spec.template == "auto" else spec.template
        try:
            result = run_poster_generation(
                session=session, object_store=object_store, http_client=http_client,
                comfyui_client=comfyui_client, workflow=workflow, node_map=node_map,
                prompt=spec.prompt, org_name=spec.org_name, official_domain=spec.official_domain,
                qr_target_url=spec.qr_url, seed=spec.seed, template_id=template_id,
                width=spec.width, height=spec.height, background_max_retries=background_retries,
            )
        except BackgroundTextError as exc:
            return GenerationOutput(
                poster_bytes=None, overall_status="fail",
                checks=[{"name": "background_text_free", "passed": False, "detail": str(exc)}],
                resolved_template=template_id or "auto",
                error=str(exc), peak_memory_mb=_read_peak_memory_mb(),
            )
        poster_bytes = object_store.get(result.poster_png_storage_key)
        return GenerationOutput(
            poster_bytes=poster_bytes,
            overall_status=result.qa_report.overall_status,
            checks=[{"name": c.name, "passed": c.passed, "detail": c.detail} for c in result.qa_report.checks],
            resolved_template=result.selected_template,
            design_metadata=result.design_metadata,
            peak_memory_mb=_read_peak_memory_mb(),
        )

    return generate_fn


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(sys.argv[1:] if argv is None else argv)
    run_id = args.run_id or datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")

    # Dataset loads first and always — cheap, and required by both dry-run
    # and a real run.
    try:
        dataset = load_dataset(args.dataset)
    except DatasetError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    # --dry-run performs NO generation and needs NO DGX/DB/workflow: it only
    # plans. Short-circuit before any preflight so it's always runnable.
    if args.dry_run:
        try:
            plan = plan_run(
                dataset, args.output_root, run_id, resume=not args.no_resume,
                case_ids=args.case_ids, seeds=args.seed_filter, max_candidates=args.max_candidates,
            )
        except EmptySelectionError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        print(format_plan(plan))
        return 0

    # Lazy: reuse the main CLI's preflight + wiring so the real benchmark
    # has identical prerequisites to a normal run.
    import httpx
    from sqlalchemy.orm import Session

    from ..comfyui_client import ComfyUiClient
    from ..config import MissingConfigError, load_settings
    from ..db import get_engine
    from ..object_store import LocalObjectStore
    from ..cli import (
        DEFAULT_NODE_MAP_PATH, DEFAULT_WORKFLOW_PATH, PrerequisiteError,
        check_comfyui_reachable, check_schema_up_to_date, load_node_map, load_workflow,
    )

    try:
        workflow = load_workflow(DEFAULT_WORKFLOW_PATH)
        node_map = load_node_map(DEFAULT_NODE_MAP_PATH)
        settings = load_settings()
        http_client = httpx.Client()
        check_comfyui_reachable(settings.comfyui_base_url, http_client)
        check_schema_up_to_date(settings.database_url)
    except (PrerequisiteError, MissingConfigError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    engine = get_engine(settings.database_url)
    object_store = LocalObjectStore(settings.object_store_root)
    comfyui_client = ComfyUiClient(settings.comfyui_base_url, client=http_client)

    print(f"benchmark run_id={run_id} dataset={args.dataset} candidates={dataset.total_candidates}")

    with Session(engine) as session:
        generate_fn = _make_real_generate_fn(
            session, object_store, http_client, comfyui_client, workflow, node_map, args.background_retries
        )
        try:
            result = run_benchmark(
                dataset=dataset, generate_fn=generate_fn, output_root=args.output_root, run_id=run_id,
                generation_settings={
                    "workflow": str(DEFAULT_WORKFLOW_PATH.name),
                    "comfyuiBaseUrl": settings.comfyui_base_url,
                    "backgroundRetries": args.background_retries,
                },
                resume=not args.no_resume,
                case_ids=args.case_ids, seeds=args.seed_filter, max_candidates=args.max_candidates,
            )
        except EmptySelectionError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

    print(f"generated={result.generated} skipped={result.skipped} failed={result.failed}")
    print(f"manifest: {result.manifest_path}")
    print(f"summary:  {result.summary_path}")
    print("Fill each candidate's review.json, then re-run aggregation to roll up human scores.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
