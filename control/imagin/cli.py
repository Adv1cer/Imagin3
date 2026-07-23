import argparse
import json
import os
import sys
from pathlib import Path

import httpx
from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.orm import Session

from .comfyui_client import ComfyUiClient, WorkflowNodeMap
from .config import MissingConfigError, load_settings
from .db import get_engine
from .object_store import LocalObjectStore

# NOTE: imagin.pipeline is imported lazily inside main(), not here at module
# level. pipeline.py imports the compositor, which imports PyGObject (`gi`)
# — a native dependency that's only available inside the real Docker image
# (see Task 0/12). Keeping that import out of this module's top level means
# `import imagin.cli` and all the preflight-checking functions below (path
# validation, QR target check, ComfyUI reachability, Alembic schema check)
# stay importable and unit-testable even in an environment that doesn't
# have PyGObject installed — exactly the CLI preflight test this file ships
# alongside. The real pipeline run still requires the full native stack;
# that requirement isn't being hidden, just not forced onto every import.

DEFAULT_PROMPT = "ทำโปสเตอร์โปรโมต UTCC สำหรับนักเรียน ม.ปลาย"
DEFAULT_ORG_NAME = "University of the Thai Chamber of Commerce"

CONTROL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WORKFLOW_PATH = CONTROL_ROOT / "workflows" / "qwen_image_txt2img.json"
DEFAULT_NODE_MAP_PATH = CONTROL_ROOT / "workflows" / "qwen_image_txt2img.nodemap.json"
ALEMBIC_INI_PATH = CONTROL_ROOT / "alembic.ini"
OUTPUT_DIR = Path("output")

# Sentinel still present in the placeholder nodemap.json shipped in this repo
# (see workflows/README.md) — if this string is still in the file, nobody
# has hand-filled in the real node IDs yet.
PLACEHOLDER_NODE_MAP_MARKER = "REPLACE_WITH_REAL"


class PrerequisiteError(RuntimeError):
    """Raised when a precondition for running the pipeline isn't met.

    Every case below is a thing this CLI refuses to guess or fabricate on
    the caller's behalf (workflow export, node mapping, QR destination,
    reachable ComfyUI, migrated schema) — main() catches this once, prints
    a clear message, and exits 1. It never catches anything broader.
    """


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Imagin Week 1 poster-generation pipeline against a real ComfyUI/DGX endpoint."
    )
    parser.add_argument(
        "prompt", nargs="?", default=None,
        help=f"Poster prompt (default: $PROMPT env var, else the fixed Week 1 prompt: {DEFAULT_PROMPT!r}).",
    )
    parser.add_argument(
        "--workflow", type=Path, default=None,
        help="Path to the ComfyUI 'Save (API Format)' workflow JSON export (default: $WORKFLOW_PATH, else workflows/qwen_image_txt2img.json).",
    )
    parser.add_argument(
        "--node-map", type=Path, default=None,
        help="Path to the WorkflowNodeMap JSON naming that workflow's real node IDs (default: $NODE_MAP_PATH, else workflows/qwen_image_txt2img.nodemap.json).",
    )
    parser.add_argument(
        "--qr-target-url", default=None,
        help="QR destination URL you have personally verified resolves (default: $QR_TARGET_URL). Never guessed.",
    )
    parser.add_argument("--org-name", default=DEFAULT_ORG_NAME, help="Organization name to resolve brand for.")
    parser.add_argument("--seed", type=int, default=42, help="ComfyUI generation seed.")
    return parser.parse_args


def parse_args(argv: list[str]) -> argparse.Namespace:
    return build_arg_parser()(argv)


def resolve_prompt(args: argparse.Namespace) -> str:
    return args.prompt or os.environ.get("PROMPT") or DEFAULT_PROMPT


def resolve_workflow_path(args: argparse.Namespace) -> Path:
    return args.workflow or Path(os.environ.get("WORKFLOW_PATH", str(DEFAULT_WORKFLOW_PATH)))


def resolve_node_map_path(args: argparse.Namespace) -> Path:
    return args.node_map or Path(os.environ.get("NODE_MAP_PATH", str(DEFAULT_NODE_MAP_PATH)))


def resolve_qr_target_url(args: argparse.Namespace) -> str | None:
    return args.qr_target_url or os.environ.get("QR_TARGET_URL")


def check_qr_target_url(qr_target_url: str | None) -> str:
    if not qr_target_url:
        raise PrerequisiteError(
            "no QR target URL supplied. Pass --qr-target-url or set QR_TARGET_URL to a destination "
            "you have personally verified resolves right now — never guessed or reused from an old "
            "placeholder (PROD.md §7.4: QR destination must be validated fresh, every export)."
        )
    return qr_target_url


def load_workflow(path: Path) -> dict:
    if not path.exists():
        raise PrerequisiteError(
            f"workflow file not found: {path}. See {path.parent / 'README.md'} for how to export it from ComfyUI."
        )
    try:
        workflow = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PrerequisiteError(f"{path} is not valid JSON: {exc}") from exc
    if not workflow:
        raise PrerequisiteError(
            f"{path} is still the placeholder ('{{}}') — drop your real ComfyUI 'Save (API Format)' "
            f"export there before running (see {path.parent / 'README.md'})."
        )
    return workflow


def load_node_map(path: Path) -> WorkflowNodeMap:
    if not path.exists():
        raise PrerequisiteError(
            f"node map file not found: {path}. See {path.parent / 'README.md'} for how to fill it in."
        )
    raw = path.read_text(encoding="utf-8")
    if PLACEHOLDER_NODE_MAP_MARKER in raw:
        raise PrerequisiteError(
            f"{path} still has placeholder node IDs ('{PLACEHOLDER_NODE_MAP_MARKER}...') — open the real "
            "workflow export and fill in its actual node IDs; do not copy IDs from the test fixtures."
        )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PrerequisiteError(f"{path} is not valid JSON: {exc}") from exc
    try:
        return WorkflowNodeMap(**data)
    except TypeError as exc:
        raise PrerequisiteError(f"{path} does not match the WorkflowNodeMap schema: {exc}") from exc


def check_comfyui_reachable(base_url: str, client: httpx.Client, timeout: float = 10.0) -> None:
    url = f"{base_url.rstrip('/')}/system_stats"
    try:
        response = client.get(url, timeout=timeout)
    except httpx.HTTPError as exc:
        raise PrerequisiteError(
            f"ComfyUI endpoint {url} is not reachable ({exc}). If you're tunneling from the DGX, confirm "
            "`curl -sf http://localhost:8188/system_stats` succeeds on this PC first — host.docker.internal "
            "can only ever be as reachable as localhost already is on the host."
        ) from exc
    if response.status_code >= 400:
        raise PrerequisiteError(f"ComfyUI endpoint {url} returned HTTP {response.status_code}")


def get_head_revision(database_url: str) -> str | None:
    config = AlembicConfig(str(ALEMBIC_INI_PATH))
    config.set_main_option("sqlalchemy.url", database_url)
    script = ScriptDirectory.from_config(config)
    return script.get_current_head()


def get_current_db_revision(database_url: str) -> str | None:
    engine = get_engine(database_url)
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        return context.get_current_revision()


def check_schema_up_to_date(database_url: str) -> None:
    """Alembic/schema preflight. Compares the migrations directory's head
    revision against what's actually stamped in the target database, so a
    never-migrated or stale database fails fast with a clear, actionable
    message instead of a confusing SQL error deep inside pipeline logic
    (e.g. `relation "organizations" does not exist`).
    """
    head_revision = get_head_revision(database_url)
    current_revision = get_current_db_revision(database_url)
    if current_revision != head_revision:
        raise PrerequisiteError(
            f"database schema is not up to date (current={current_revision!r}, head={head_revision!r}). "
            "Run: docker compose run --rm control alembic upgrade head"
        )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    try:
        prompt = resolve_prompt(args)
        qr_target_url = check_qr_target_url(resolve_qr_target_url(args))
        workflow = load_workflow(resolve_workflow_path(args))
        node_map = load_node_map(resolve_node_map_path(args))

        settings = load_settings()

        http_client = httpx.Client()
        check_comfyui_reachable(settings.comfyui_base_url, http_client)
        check_schema_up_to_date(settings.database_url)
    except (PrerequisiteError, MissingConfigError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    from .pipeline import run_poster_generation  # see NOTE at top of file

    engine = get_engine(settings.database_url)
    object_store = LocalObjectStore(settings.object_store_root)
    comfyui_client = ComfyUiClient(settings.comfyui_base_url, client=http_client)

    with Session(engine) as session:
        result = run_poster_generation(
            session=session, object_store=object_store, http_client=http_client,
            comfyui_client=comfyui_client, workflow=workflow, node_map=node_map, prompt=prompt,
            org_name=args.org_name, official_domain=settings.utcc_official_domain,
            qr_target_url=qr_target_url, seed=args.seed,
        )

    OUTPUT_DIR.mkdir(exist_ok=True)
    poster_bytes = object_store.get(result.poster_png_storage_key)
    (OUTPUT_DIR / "poster.png").write_bytes(poster_bytes)
    (OUTPUT_DIR / "qa_report.json").write_text(
        json.dumps({
            "overallStatus": result.qa_report.overall_status,
            "checks": [c.__dict__ for c in result.qa_report.checks],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"overall_status={result.qa_report.overall_status}")
    for check in result.qa_report.checks:
        print(f"  {check.name}: {'PASS' if check.passed else 'FAIL'} — {check.detail}")
    print("wrote output/poster.png and output/qa_report.json")
    return 0 if result.qa_report.overall_status != "fail" else 2


if __name__ == "__main__":
    raise SystemExit(main())
