import httpx
import pytest
from imagin.comfyui_client import (
    ComfyUiClient, WorkflowNodeMap, patch_qwen_image_workflow,
    ComfyUiError, ComfyUiTimeoutError, UnknownWorkflowNodeError,
)

SAMPLE_WORKFLOW = {
    "3": {"class_type": "KSampler", "inputs": {"seed": 0, "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}},
    "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "placeholder positive"}},
    "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "placeholder negative"}},
    "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0]}},
}

# Hand-written against SAMPLE_WORKFLOW's actual node IDs — same discipline
# required of the real qwen_image_txt2img.nodemap.json once a real workflow
# export exists.
SAMPLE_NODE_MAP = WorkflowNodeMap(
    prompt_node_id="6", prompt_input_key="text",
    seed_node_id="3", seed_input_key="seed",
    width_node_id="5", width_input_key="width",
    height_node_id="5", height_input_key="height",
)


def test_patch_qwen_image_workflow_sets_prompt_seed_and_dimensions():
    patched = patch_qwen_image_workflow(SAMPLE_WORKFLOW, SAMPLE_NODE_MAP, prompt_text="UTCC poster hero", seed=42, width=1080, height=1350)

    assert patched["6"]["inputs"]["text"] == "UTCC poster hero"
    assert patched["3"]["inputs"]["seed"] == 42
    assert patched["5"]["inputs"]["width"] == 1080
    assert patched["5"]["inputs"]["height"] == 1350
    # original untouched
    assert SAMPLE_WORKFLOW["6"]["inputs"]["text"] == "placeholder positive"


def test_patch_qwen_image_workflow_raises_on_unknown_mapped_node():
    bad_map = WorkflowNodeMap(
        prompt_node_id="does-not-exist", prompt_input_key="text",
        seed_node_id="3", seed_input_key="seed",
        width_node_id="5", width_input_key="width",
        height_node_id="5", height_input_key="height",
    )

    with pytest.raises(UnknownWorkflowNodeError):
        patch_qwen_image_workflow(SAMPLE_WORKFLOW, bad_map, prompt_text="x", seed=1, width=1080, height=1350)


def test_patch_qwen_image_workflow_raises_on_unknown_mapped_input_key():
    bad_map = WorkflowNodeMap(
        prompt_node_id="6", prompt_input_key="not_a_real_input_key",
        seed_node_id="3", seed_input_key="seed",
        width_node_id="5", width_input_key="width",
        height_node_id="5", height_input_key="height",
    )

    with pytest.raises(UnknownWorkflowNodeError):
        patch_qwen_image_workflow(SAMPLE_WORKFLOW, bad_map, prompt_text="x", seed=1, width=1080, height=1350)


def test_generate_image_submits_polls_and_fetches_bytes():
    calls = {"history_polls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "abc123"}, request=request)
        if request.url.path == "/history/abc123":
            calls["history_polls"] += 1
            if calls["history_polls"] < 2:
                return httpx.Response(200, json={}, request=request)
            return httpx.Response(200, json={"abc123": {"outputs": {"9": {"images": [{"filename": "out.png", "subfolder": "", "type": "output"}]}}}}, request=request)
        if request.url.path == "/view":
            return httpx.Response(200, content=b"PNGDATA", request=request)
        return httpx.Response(404, request=request)

    client = ComfyUiClient("http://dgx:8188", client=httpx.Client(transport=httpx.MockTransport(handler)))

    image_bytes = client.generate_image(SAMPLE_WORKFLOW, SAMPLE_NODE_MAP, prompt_text="UTCC poster hero", seed=42, width=1080, height=1350)

    assert image_bytes == b"PNGDATA"
    assert calls["history_polls"] == 2


def test_generate_image_raises_timeout_when_never_completes():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "abc123"}, request=request)
        return httpx.Response(200, json={}, request=request)

    client = ComfyUiClient("http://dgx:8188", client=httpx.Client(transport=httpx.MockTransport(handler)))

    with pytest.raises(ComfyUiTimeoutError):
        client.wait_for_completion("abc123", timeout_seconds=0.05, poll_interval=0.01)
