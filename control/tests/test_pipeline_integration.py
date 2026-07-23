import io
import os

import cairo
import httpx
from sqlalchemy.orm import Session

from imagin.comfyui_client import ComfyUiClient, WorkflowNodeMap
from imagin.object_store import LocalObjectStore
from imagin.pipeline import run_poster_generation
from tests.fixtures.acme_pages import ACME_HOME_PAGE_HTML


ROBOTS_ALLOW_ALL = "User-agent: *\nAllow: /\n"


SAMPLE_WORKFLOW = {
    "3": {
        "class_type": "KSampler",
        "inputs": {
            "seed": 0,
            "positive": ["6", 0],
            "negative": ["7", 0],
            "latent_image": ["5", 0],
        },
    },
    "5": {
        "class_type": "EmptyLatentImage",
        "inputs": {
            "width": 512,
            "height": 512,
            "batch_size": 1,
        },
    },
    "6": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": "placeholder positive",
        },
    },
    "7": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": "placeholder negative",
        },
    },
    "9": {
        "class_type": "SaveImage",
        "inputs": {
            "images": ["8", 0],
        },
    },
}


SAMPLE_NODE_MAP = WorkflowNodeMap(
    prompt_node_id="6",
    prompt_input_key="text",
    seed_node_id="3",
    seed_input_key="seed",
    width_node_id="5",
    width_input_key="width",
    height_node_id="5",
    height_input_key="height",
)


def _solid_argb32_png(
    width: int,
    height: int,
    rgb: tuple[float, float, float] = (0.4, 0.5, 0.6),
) -> bytes:
    surface = cairo.ImageSurface(
        cairo.FORMAT_ARGB32,
        width,
        height,
    )

    context = cairo.Context(surface)
    context.set_source_rgb(*rgb)
    context.paint()

    buffer = io.BytesIO()
    surface.write_to_png(buffer)

    return buffer.getvalue()


def _combined_client(hero_png: bytes) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)

        if url.endswith("robots.txt"):
            return httpx.Response(
                200,
                text=ROBOTS_ALLOW_ALL,
                request=request,
            )

        if url == "https://acme.example/":
            return httpx.Response(
                200,
                content=ACME_HOME_PAGE_HTML,
                headers={"content-type": "text/html"},
                request=request,
            )

        if url == "https://acme.example/brand/logo.svg":
            # The fixture URL uses .svg for scoring evidence, but returns valid
            # raster PNG bytes because the current compositor consumes PNG.
            return httpx.Response(
                200,
                content=hero_png,
                headers={"content-type": "image/png"},
                request=request,
            )

        if request.url.path == "/prompt":
            return httpx.Response(
                200,
                json={"prompt_id": "abc123"},
                request=request,
            )

        if request.url.path == "/history/abc123":
            return httpx.Response(
                200,
                json={
                    "abc123": {
                        "outputs": {
                            "9": {
                                "images": [
                                    {
                                        "filename": "out.png",
                                        "subfolder": "",
                                        "type": "output",
                                    }
                                ]
                            }
                        }
                    }
                },
                request=request,
            )

        if request.url.path == "/view":
            return httpx.Response(
                200,
                content=hero_png,
                headers={"content-type": "image/png"},
                request=request,
            )

        return httpx.Response(
            404,
            request=request,
        )

    return httpx.Client(
        transport=httpx.MockTransport(handler)
    )


def test_run_poster_generation_produces_passing_qa_report_end_to_end(
    db_session: Session,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        "imagin.brand.entity_resolution._is_public_host",
        lambda host: True,
    )

    hero_png = _solid_argb32_png(
        1080,
        1350,
    )

    client = _combined_client(hero_png)
    object_store = LocalObjectStore(str(tmp_path))

    comfyui_client = ComfyUiClient(
        "http://dgx:8188",
        client=client,
    )

    result = run_poster_generation(
        session=db_session,
        object_store=object_store,
        http_client=client,
        comfyui_client=comfyui_client,
        workflow=SAMPLE_WORKFLOW,
        node_map=SAMPLE_NODE_MAP,
        prompt="ทำโปสเตอร์โปรโมต Acme สำหรับนักเรียน ม.ปลาย",
        org_name="Acme University",
        official_domain="acme.example",
        qr_target_url=(
            "https://acme.example/verified-test-target"
        ),
        seed=42,
    )

    assert result.qa_report.overall_status in (
        "pass",
        "warn",
    )

    assert object_store.get(
        result.poster_png_storage_key
    )


def test_run_poster_generation_logo_provenance_check_actually_verifies_bytes(
    db_session: Session,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        "imagin.brand.entity_resolution._is_public_host",
        lambda host: True,
    )

    hero_png = _solid_argb32_png(
        1080,
        1350,
    )

    client = _combined_client(hero_png)
    object_store = LocalObjectStore(str(tmp_path))

    comfyui_client = ComfyUiClient(
        "http://dgx:8188",
        client=client,
    )

    from imagin.brand.registry import resolve_brand

    resolved = resolve_brand(
        db_session,
        "Acme University",
        "acme.example",
        client,
        object_store,
    )

    # Replace the approved logo with another valid PNG. This lets the
    # compositor finish while ensuring the actual bytes have a different hash.
    tampered_logo_png = _solid_argb32_png(
        200,
        200,
        rgb=(1.0, 0.0, 0.0),
    )

    logo_path = os.path.join(
        object_store.root,
        resolved.logo_storage_key,
    )

    with open(logo_path, "wb") as file:
        file.write(tampered_logo_png)

    result = run_poster_generation(
        session=db_session,
        object_store=object_store,
        http_client=client,
        comfyui_client=comfyui_client,
        workflow=SAMPLE_WORKFLOW,
        node_map=SAMPLE_NODE_MAP,
        prompt="ทำโปสเตอร์โปรโมต Acme สำหรับนักเรียน ม.ปลาย",
        org_name="Acme University",
        official_domain="acme.example",
        qr_target_url=(
            "https://acme.example/verified-test-target"
        ),
        seed=42,
    )

    logo_check = next(
        check
        for check in result.qa_report.checks
        if check.name == "logo_provenance_match"
    )

    assert logo_check.passed is False
    assert result.qa_report.overall_status == "fail"