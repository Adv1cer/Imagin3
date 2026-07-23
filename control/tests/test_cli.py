import json

import httpx
import pytest

from imagin.cli import (
    PrerequisiteError,
    check_comfyui_reachable,
    check_qr_target_url,
    check_schema_up_to_date,
    get_head_revision,
    load_node_map,
    load_workflow,
    main,
    parse_args,
    resolve_node_map_path,
    resolve_prompt,
    resolve_qr_target_url,
    resolve_workflow_path,
)
from imagin.comfyui_client import WorkflowNodeMap

REAL_WORKFLOW = {
    "3": {"class_type": "KSampler", "inputs": {"seed": 0, "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}},
    "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "placeholder positive"}},
}
REAL_NODE_MAP = {
    "prompt_node_id": "6", "prompt_input_key": "text",
    "seed_node_id": "3", "seed_input_key": "seed",
    "width_node_id": "5", "width_input_key": "width",
    "height_node_id": "5", "height_input_key": "height",
}


# --- argument / environment resolution -------------------------------------

def test_resolve_prompt_prefers_cli_arg_over_env_over_default(monkeypatch):
    monkeypatch.setenv("PROMPT", "env prompt")
    args = parse_args(["cli prompt"])
    assert resolve_prompt(args) == "cli prompt"

    args = parse_args([])
    assert resolve_prompt(args) == "env prompt"

    monkeypatch.delenv("PROMPT")
    args = parse_args([])
    assert "UTCC" in resolve_prompt(args)


def test_resolve_workflow_and_node_map_paths_prefer_flag_over_env_over_default(monkeypatch, tmp_path):
    monkeypatch.delenv("WORKFLOW_PATH", raising=False)
    monkeypatch.delenv("NODE_MAP_PATH", raising=False)

    args = parse_args(["--workflow", str(tmp_path / "flag.json")])
    assert resolve_workflow_path(args) == tmp_path / "flag.json"

    monkeypatch.setenv("WORKFLOW_PATH", str(tmp_path / "env.json"))
    args = parse_args([])
    assert resolve_workflow_path(args) == tmp_path / "env.json"

    monkeypatch.delenv("WORKFLOW_PATH")
    args = parse_args([])
    assert resolve_workflow_path(args).name == "qwen_image_txt2img.json"

    monkeypatch.setenv("NODE_MAP_PATH", str(tmp_path / "env_nodemap.json"))
    args = parse_args([])
    assert resolve_node_map_path(args) == tmp_path / "env_nodemap.json"


def test_check_qr_target_url_rejects_missing_and_passes_through_value():
    with pytest.raises(PrerequisiteError):
        check_qr_target_url(None)
    with pytest.raises(PrerequisiteError):
        check_qr_target_url("")

    assert check_qr_target_url("https://example.ac.th/verified") == "https://example.ac.th/verified"


def test_resolve_qr_target_url_prefers_flag_over_env(monkeypatch):
    monkeypatch.setenv("QR_TARGET_URL", "https://from-env.example/x")
    args = parse_args(["--qr-target-url", "https://from-flag.example/y"])
    assert resolve_qr_target_url(args) == "https://from-flag.example/y"

    args = parse_args([])
    assert resolve_qr_target_url(args) == "https://from-env.example/x"


# --- workflow / node map loading ---------------------------------------------

def test_load_workflow_raises_when_file_missing(tmp_path):
    with pytest.raises(PrerequisiteError, match="not found"):
        load_workflow(tmp_path / "does_not_exist.json")


def test_load_workflow_raises_when_still_placeholder(tmp_path):
    path = tmp_path / "workflow.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(PrerequisiteError, match="placeholder"):
        load_workflow(path)


def test_load_workflow_raises_on_invalid_json(tmp_path):
    path = tmp_path / "workflow.json"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(PrerequisiteError, match="not valid JSON"):
        load_workflow(path)


def test_load_workflow_returns_parsed_dict_for_real_content(tmp_path):
    path = tmp_path / "workflow.json"
    path.write_text(json.dumps(REAL_WORKFLOW), encoding="utf-8")
    assert load_workflow(path) == REAL_WORKFLOW


def test_load_node_map_raises_when_file_missing(tmp_path):
    with pytest.raises(PrerequisiteError, match="not found"):
        load_node_map(tmp_path / "does_not_exist.json")


def test_load_node_map_raises_when_still_placeholder(tmp_path):
    path = tmp_path / "nodemap.json"
    path.write_text(json.dumps({**REAL_NODE_MAP, "prompt_node_id": "REPLACE_WITH_REAL_X"}), encoding="utf-8")
    with pytest.raises(PrerequisiteError, match="placeholder"):
        load_node_map(path)


def test_load_node_map_raises_on_schema_mismatch(tmp_path):
    path = tmp_path / "nodemap.json"
    incomplete = {k: v for k, v in REAL_NODE_MAP.items() if k != "height_input_key"}
    path.write_text(json.dumps(incomplete), encoding="utf-8")
    with pytest.raises(PrerequisiteError, match="WorkflowNodeMap schema"):
        load_node_map(path)


def test_load_node_map_returns_workflow_node_map_for_real_content(tmp_path):
    path = tmp_path / "nodemap.json"
    path.write_text(json.dumps(REAL_NODE_MAP), encoding="utf-8")
    assert load_node_map(path) == WorkflowNodeMap(**REAL_NODE_MAP)


# --- ComfyUI reachability -----------------------------------------------------

def test_check_comfyui_reachable_passes_on_200():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/system_stats"
        return httpx.Response(200, json={"system": {}}, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    check_comfyui_reachable("http://dgx:8188", client)  # must not raise


def test_check_comfyui_reachable_raises_on_http_error_status():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503, request=r)))
    with pytest.raises(PrerequisiteError, match="503"):
        check_comfyui_reachable("http://dgx:8188", client)


def test_check_comfyui_reachable_raises_when_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(PrerequisiteError, match="not reachable"):
        check_comfyui_reachable("http://dgx:8188", client)


# --- Alembic/schema preflight --------------------------------------------------

def test_check_schema_up_to_date_raises_when_current_revision_is_none(monkeypatch):
    monkeypatch.setattr("imagin.cli.get_current_db_revision", lambda database_url: None)
    with pytest.raises(PrerequisiteError, match="not up to date"):
        check_schema_up_to_date("postgresql+psycopg2://placeholder:placeholder@placeholder/placeholder")


def test_check_schema_up_to_date_passes_when_current_matches_head(monkeypatch):
    database_url = "postgresql+psycopg2://placeholder:placeholder@placeholder/placeholder"
    head = get_head_revision(database_url)  # reads migrations/versions on disk, no DB connection needed
    monkeypatch.setattr("imagin.cli.get_current_db_revision", lambda database_url: head)
    check_schema_up_to_date(database_url)  # must not raise


def test_check_schema_up_to_date_raises_when_current_is_stale(monkeypatch):
    database_url = "postgresql+psycopg2://placeholder:placeholder@placeholder/placeholder"
    monkeypatch.setattr("imagin.cli.get_current_db_revision", lambda database_url: "some-old-revision")
    with pytest.raises(PrerequisiteError, match="not up to date"):
        check_schema_up_to_date(database_url)


# --- main() preflight ordering (never reaches the real pipeline/network/db) --

def test_main_fails_closed_when_qr_target_url_missing(monkeypatch, capsys):
    monkeypatch.delenv("QR_TARGET_URL", raising=False)
    exit_code = main(["some prompt"])
    assert exit_code == 1
    assert "QR target URL" in capsys.readouterr().err


def test_main_fails_closed_when_workflow_is_placeholder(monkeypatch, tmp_path, capsys):
    workflow_path = tmp_path / "workflow.json"
    workflow_path.write_text("{}", encoding="utf-8")

    exit_code = main([
        "--qr-target-url", "https://example.ac.th/verified",
        "--workflow", str(workflow_path),
    ])

    assert exit_code == 1
    assert "placeholder" in capsys.readouterr().err


def test_main_fails_closed_when_node_map_is_placeholder(monkeypatch, tmp_path, capsys):
    workflow_path = tmp_path / "workflow.json"
    workflow_path.write_text(json.dumps(REAL_WORKFLOW), encoding="utf-8")
    node_map_path = tmp_path / "nodemap.json"
    node_map_path.write_text(json.dumps({**REAL_NODE_MAP, "seed_node_id": "REPLACE_WITH_REAL_X"}), encoding="utf-8")

    exit_code = main([
        "--qr-target-url", "https://example.ac.th/verified",
        "--workflow", str(workflow_path),
        "--node-map", str(node_map_path),
    ])

    assert exit_code == 1
    assert "placeholder" in capsys.readouterr().err


def test_main_fails_closed_when_comfyui_unreachable(monkeypatch, tmp_path, capsys):
    workflow_path = tmp_path / "workflow.json"
    workflow_path.write_text(json.dumps(REAL_WORKFLOW), encoding="utf-8")
    node_map_path = tmp_path / "nodemap.json"
    node_map_path.write_text(json.dumps(REAL_NODE_MAP), encoding="utf-8")

    # Neutralize any ambient proxy env vars so plain httpx.Client() construction
    # in main() can't pick up an environment-specific proxy transport (e.g. a
    # sandboxed CI/dev environment routing all traffic through a SOCKS proxy)
    # unrelated to what's under test here.
    for proxy_var in ("ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
        monkeypatch.delenv(proxy_var, raising=False)

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://placeholder:placeholder@placeholder/placeholder")
    monkeypatch.setenv("OBJECT_STORE_ROOT", str(tmp_path))
    monkeypatch.setenv("COMFYUI_BASE_URL", "http://unreachable-host-for-test:8188")
    monkeypatch.setenv("UTCC_OFFICIAL_DOMAIN", "utcc.ac.th")

    def _always_unreachable(base_url, client, timeout=10.0):
        raise PrerequisiteError(f"ComfyUI endpoint {base_url} is not reachable (simulated)")

    monkeypatch.setattr("imagin.cli.check_comfyui_reachable", _always_unreachable)

    exit_code = main([
        "--qr-target-url", "https://example.ac.th/verified",
        "--workflow", str(workflow_path),
        "--node-map", str(node_map_path),
    ])

    assert exit_code == 1
    assert "not reachable" in capsys.readouterr().err
