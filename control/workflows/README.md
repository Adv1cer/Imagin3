# Workflow files (both currently placeholders)

**`qwen_image_txt2img.json`** — currently `{}`. Before Task 15's live smoke test:

1. Open ComfyUI's web UI against your DGX endpoint (`http://localhost:8188`).
2. Build (or load) a Qwen-Image txt2img graph: checkpoint/model loader -> `CLIPTextEncode` (positive) + `CLIPTextEncode` (negative) -> `EmptyLatentImage` -> `KSampler` -> `VAEDecode` -> `SaveImage`.
3. Enable Dev Mode in ComfyUI settings, then use "Save (API Format)" (not the regular "Save") to export the graph JSON.
4. Replace `qwen_image_txt2img.json`'s contents with that export.

**`qwen_image_txt2img.nodemap.json`** — currently placeholder `REPLACE_WITH_REAL_*` values. Once the real workflow export exists, open it and fill in the *actual* node IDs for your graph. Do not copy the sample IDs from `tests/test_comfyui_client.py` — those belong to a fixture workflow, not your real export, and will raise `UnknownWorkflowNodeError` if used against the real one.

`imagin.cli` refuses to run (exit code 1, clear error message) while either file is still a placeholder.
