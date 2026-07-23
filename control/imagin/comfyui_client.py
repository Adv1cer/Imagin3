import time
import uuid
from dataclasses import dataclass

import httpx


class ComfyUiError(RuntimeError):
    pass


class ComfyUiTimeoutError(ComfyUiError):
    pass


class UnknownWorkflowNodeError(ComfyUiError):
    pass


@dataclass(frozen=True)
class WorkflowNodeMap:
    """Explicit, hand-written contract naming exactly which node IDs and input
    keys to patch in a specific ComfyUI workflow export.

    This replaces graph-shape inference (walking class_type/link structure to
    guess which nodes hold the prompt text and width/height) because that
    approach silently patches the wrong node — or nothing — for any graph
    shaped differently than one sample workflow. A WorkflowNodeMap must be
    hand-written against the real qwen_image_txt2img.json once it exists; it
    is never inferred from workflow structure.
    """
    prompt_node_id: str
    prompt_input_key: str
    seed_node_id: str
    seed_input_key: str
    width_node_id: str
    width_input_key: str
    height_node_id: str
    height_input_key: str
    # Optional: the negative-prompt CLIPTextEncode node. When present, the
    # pipeline's image-only constraints ("no text, no letters, no logo,
    # no watermark, ...") are written into the workflow's real negative
    # prompt instead of being silently dropped. Optional so existing node
    # maps stay valid; the OCR background gate enforces text-free output
    # either way — the negative prompt just raises the odds of a clean
    # generation on the first attempt.
    negative_prompt_node_id: str | None = None
    negative_prompt_input_key: str | None = None


def _validate_and_set(workflow: dict, node_id: str, input_key: str, value) -> None:
    node = workflow.get(node_id)
    if node is None:
        raise UnknownWorkflowNodeError(f"node_map references node id {node_id!r}, which does not exist in this workflow")
    if input_key not in node.get("inputs", {}):
        raise UnknownWorkflowNodeError(f"node_map references input key {input_key!r} on node {node_id!r}, which that node does not have")
    node["inputs"][input_key] = value


def patch_qwen_image_workflow(
    workflow: dict,
    node_map: WorkflowNodeMap,
    prompt_text: str,
    seed: int,
    width: int,
    height: int,
    negative_prompt_text: str | None = None,
) -> dict:
    patched = {node_id: {**node, "inputs": dict(node["inputs"])} for node_id, node in workflow.items()}

    _validate_and_set(patched, node_map.prompt_node_id, node_map.prompt_input_key, prompt_text)
    _validate_and_set(patched, node_map.seed_node_id, node_map.seed_input_key, seed)
    _validate_and_set(patched, node_map.width_node_id, node_map.width_input_key, width)
    _validate_and_set(patched, node_map.height_node_id, node_map.height_input_key, height)

    if (
        negative_prompt_text is not None
        and node_map.negative_prompt_node_id is not None
        and node_map.negative_prompt_input_key is not None
    ):
        _validate_and_set(
            patched,
            node_map.negative_prompt_node_id,
            node_map.negative_prompt_input_key,
            negative_prompt_text,
        )

    return patched


class ComfyUiClient:
    def __init__(self, base_url: str, client: httpx.Client | None = None):
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client()

    def submit(self, workflow: dict) -> str:
        response = self._client.post(
            f"{self._base_url}/prompt",
            json={"prompt": workflow, "client_id": str(uuid.uuid4())},
            timeout=30.0,
        )
        if response.status_code >= 400:
            raise ComfyUiError(f"ComfyUI /prompt returned {response.status_code}: {response.text}")
        return response.json()["prompt_id"]

    def wait_for_completion(self, prompt_id: str, timeout_seconds: float = 300.0, poll_interval: float = 2.0) -> dict:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            response = self._client.get(f"{self._base_url}/history/{prompt_id}", timeout=10.0)
            response.raise_for_status()
            history = response.json()
            if prompt_id in history and history[prompt_id].get("outputs"):
                return history[prompt_id]
            time.sleep(poll_interval)
        raise ComfyUiTimeoutError(f"ComfyUI job {prompt_id} did not complete within {timeout_seconds}s")

    def fetch_output_image(self, history_entry: dict) -> bytes:
        for node_output in history_entry["outputs"].values():
            for image in node_output.get("images", []):
                response = self._client.get(
                    f"{self._base_url}/view",
                    params={"filename": image["filename"], "subfolder": image.get("subfolder", ""), "type": image.get("type", "output")},
                    timeout=30.0,
                )
                response.raise_for_status()
                return response.content
        raise ComfyUiError("ComfyUI history entry contained no output images")

    def generate_image(
        self,
        workflow: dict,
        node_map: WorkflowNodeMap,
        prompt_text: str,
        seed: int,
        width: int,
        height: int,
        negative_prompt_text: str | None = None,
    ) -> bytes:
        patched = patch_qwen_image_workflow(
            workflow, node_map, prompt_text, seed, width, height,
            negative_prompt_text=negative_prompt_text,
        )
        prompt_id = self.submit(patched)
        history_entry = self.wait_for_completion(prompt_id)
        return self.fetch_output_image(history_entry)
