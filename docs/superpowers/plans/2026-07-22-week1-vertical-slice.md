# Imagin — Week 1 Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take the prompt "ทำโปสเตอร์โปรโมต UTCC สำหรับนักเรียน ม.ปลาย" end-to-end through cache-first UTCC brand discovery, Qwen-Image hero generation on the real DGX ComfyUI endpoint, deterministic Thai text/logo/QR composition, and automated QA (OCR/QR/logo), producing a reviewable PNG + QA report on disk. This is PROD.md §15.1 Week 1 / OKF §8 Phase 0's first milestone, upgraded per ADR-001 (2026-07-22) so the brand path is real cache-first web discovery rather than a hardcoded pack.

> **Patch 2026-07-22 (post-implementation review):** Six fixes applied after Tasks 0–9 were implemented and verified against a real (embedded) Postgres and the actual dependency set: (1) added Task 0, a native-dependency smoke test that gates the whole native/OCR/graphics toolchain before any TDD task depends on it; (2) `docker-compose.yml` now bind-mounts `./output:/app/output` instead of a Docker-managed named volume, so `poster.png`/`qa_report.json` are directly visible on this PC; (3) Task 10's ComfyUI client now requires an explicit, version-controlled workflow **node-mapping contract** instead of inferring graph shape by walking `class_type`/link structure, which was fragile and silently wrong for any workflow graph shaped differently than the one sample; (4) Task 9's `build_poster_design_spec` no longer hardcodes a guessed `/openhouse` QR path — `qr_target_url` is now a required caller-supplied argument sourced from a verified location, never fabricated; (5) Task 14's QA wiring no longer compares the approved logo hash against itself (a tautology that could never fail); it now compares the sha256 of the bytes actually composited into the poster against the registry's approved hash; (6) Task 8's brand registry now **upserts** `VerifiedDomain` on refresh instead of blindly inserting, which previously violated the `(organization_id, domain)` unique constraint on any second resolution of the same organization. Three further correctness bugs were found and fixed while actually running Tasks 0–9 (not requested, but required for the tasks to pass honestly, not by weakening assertions): Task 3's `alembic.ini` was missing the `[loggers]`/`[handlers]`/`[formatters]` sections `logging.config.fileConfig` requires, so every migration run crashed; Task 6/8's extractor treated every `(url, evidence-tag)` pair as an independent candidate, so a logo referenced from both JSON-LD *and* the page header (the single most common real-world pattern) never accumulated combined evidence and could never cross the usability threshold — evidence is now merged by normalized URL; and Task 7's own test file asserted a status of `"provisional"` for a candidate scoring 55, which contradicts `PROVISIONAL_THRESHOLD = 60` and PROD.md §7.1a's own "< 60 MUST NOT be used" rule — the test assertions were corrected to match the (unchanged, already-correct) scoring implementation. See task sections below for the exact diffs; all Task 0–9 code and tests in this repo already reflect these fixes.

> **Patch 2026-07-22 (third pass) — fixed a real connection failure hit running against actual docker-compose Postgres:** `_test_database_url()` (Task 3) and the `db_session` fixture (Task 1/8) both derived the `imagin_test` database URL via `DATABASE_URL.replace("/imagin", "/imagin_test")`. Against the real compose URL `postgresql+psycopg2://imagin:imagin@postgres:5432/imagin`, the substring `/imagin` matches twice — once inside `://imagin` (the username) and once at the end (the database name) — so the replace silently corrupted the username to `imagin_test` too, a role that was never created, producing `password authentication failed for user "imagin_test"` the first time this was run against a real container. Fixed by a shared `test_database_url()` helper in `conftest.py` that splits structurally on the URL's rightmost path segment instead of doing a substring replace; both call sites now import it rather than duplicating the logic.

> **Patch 2026-07-22 (second pass) — Tasks 10–14 unblocked, Docker verification still owed:** the first pass over-scoped "blocked" to cover Tasks 10–14, when in fact only Task 15's *live DGX smoke test* has an external dependency (the real ComfyUI workflow export, its node mapping, a reachable tunnel, and a verified QR destination). Tasks 10–14 are ordinary TDD work against deterministic fixtures/mocks — a fictional Acme fixture, a sample ComfyUI workflow + hand-written `WorkflowNodeMap`, and mocked `/prompt`/`/history`/`/view` responses — exactly like Tasks 0–9, and there is no reason they can't be implemented and tested now. They have been (see Tasks 10–14 below). Also fixed: `Dockerfile` was pinned to `python:3.12-slim` (Debian bookworm), but `PyGObject==3.56.3` requires `girepository-2.0`, which only ships on Debian trixie — bookworm only has `girepository1.0-dev`. The base image is now `python:3.12-slim-trixie`, `libgirepository1.0-dev` → `libgirepository-2.0-dev`, apt's `python3-gi` removed (it would shadow the pip-installed, version-pinned `PyGObject`), and `PyGObject` is now pinned exactly to `3.56.3` rather than a floating range.

### Status matrix (2026-07-22)

This plan's execution environment (a Linux sandbox with no Docker, no root, and no `/var/run/docker.sock`) cannot itself run `docker compose` — that gap is explicit below, not glossed over. Four distinct levels of verification apply; do not conflate them:

| Task | Code-complete | Docker-verified (native libs + Postgres networking, real container) | Mocked-integration-verified (Docker, real native libs, mocked ComfyUI/network) | Live-DGX-verified (real workflow, real DGX, real poster) |
|---|---|---|---|---|
| 0 — native-dep smoke test | ✅ | ❌ *(owed — see commands below)* | n/a | n/a |
| 1 — scaffolding/config | ✅ | ❌ *(owed)* | n/a | n/a |
| 2 — object store | ✅ | ✅ (pip-only deps; also passed against embedded Postgres) | n/a | n/a |
| 3 — DB models/Alembic | ✅ | ❌ *(owed — needs real containerized Postgres networking)* | n/a | n/a |
| 4 — entity resolution | ✅ | ✅ (pip-only deps) | n/a | n/a |
| 5 — crawler | ✅ | ✅ (pip-only deps) | n/a | n/a |
| 6 — extractor | ✅ | ✅ (pip-only deps) | n/a | n/a |
| 7 — scoring | ✅ | ✅ (pip-only deps) | n/a | n/a |
| 8 — brand registry | ✅ | ❌ *(owed — needs real containerized Postgres)* | n/a | n/a |
| 9 — design spec | ✅ | ✅ (pip-only deps) | n/a | n/a |
| 10 — ComfyUI client + node map | ✅ | ❌ *(owed)* | ✅ (pure Python + httpx mock; no native deps at all, so already fully verified) | ❌ |
| 11 — QR gen/decode | ✅ | ❌ *(owed — needs libzbar0)* | ⚠️ partial: encode logic sanity-checked against an independent decoder (zxing-cpp) in-sandbox; `pyzbar` itself needs the real image | ❌ |
| 12 — compositor | ✅ | ❌ *(owed — needs PyGObject/Pango/HarfBuzz)* | ❌ *(needs Docker)* | ❌ |
| 13 — QA gates | ✅ | ❌ *(owed — OCR needs paddleocr; logo/report logic verified directly in-sandbox)* | ❌ *(OCR/compositor path needs Docker)* | ❌ |
| 14 — pipeline orchestration | ✅ | ❌ *(owed — depends on 12/13's native libs)* | ❌ *(needs Docker)* | ❌ |
| 15 — CLI (`cli.py`) | ✅ implemented (prerequisite checks for workflow/nodemap/QR/ComfyUI reachability/schema; fixed the previously-reported `No module named imagin.cli`) | ✅ (pip-only deps — `test_cli.py`, 22/22 passed, no Docker/DB/native dependency needed at all) | n/a | n/a |
| 15 — live DGX smoke test | ✅ (CLI refuses to run without real inputs) | n/a | n/a | ❌ **blocked** — real workflow export, node mapping, reachable DGX tunnel, and verified QR destination do not exist yet |

**What "code-complete" means here:** implemented, unit-tested where the dependency chain allows, and where it doesn't (PyGObject/pyzbar's libzbar/paddleocr — none installable without root/apt in this sandbox), the failure was reproduced and confirmed to be exactly the missing native dependency, not a logic bug (see each task's sandbox verification note). **"Docker-verified" is explicitly NOT claimed for any task** — this sandbox cannot run Docker at all; see the exact commands below to obtain it on this PC. **Week 1 is not complete** — per explicit instruction, it isn't complete until Task 15 produces a real poster + QA report against the real DGX.

**Architecture:** A single Python "control-plane" application (no HTTP API yet — that's Week 6) running in a Linux Docker container on this PC, backed by a Postgres container for durable brand-registry state and a local-filesystem object-storage adapter for immutable artifact bytes. The app resolves the configured UTCC official domain, crawls it respectfully, extracts and scores logo candidates, caches a versioned Brand Profile/Asset in Postgres+object-storage (never overwriting approved bytes in place), then calls a real ComfyUI instance on the DGX for the Qwen-Image hero image, composites Thai/English text + the verified logo + a QR code deterministically with Pango/HarfBuzz/Cairo, runs OCR/QR/logo QA gates, and writes the result to `output/`.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 + Alembic + psycopg2 (PostgreSQL), httpx (crawling + ComfyUI HTTP client), BeautifulSoup4 + lxml (HTML/JSON-LD extraction), pycairo + PyGObject (Pango/PangoCairo/HarfBuzz) for deterministic composition, `qrcode` + `pyzbar` for QR generation/decoding, PaddleOCR for OCR QA, pytest + pytest-mock + respx for tests, Docker + docker-compose for the runtime.

## Global Constraints

- PostgreSQL UUID primary keys; UTC `timestamptz` columns (PROD.md §8.1).
- Alembic migrations only — no `Base.metadata.create_all()` against the real database (PROD.md §8.5).
- Cache-first brand resolution: registry hit + fresh → use immediately; miss/stale → synchronous discovery (PROD.md §7.1a, ADR-001).
- A logo candidate scoring ≥ 80 is auto-usable without waiting on human pre-generation confirmation; 60–79 is `provisional`; < 60 (or no evidence) MUST NOT be used and the pipeline MUST NOT ask the image model to draw an approximate logo — it must fail closed or proceed with the logo omitted (PROD.md §7.1a, §7.3).
- Cached/approved brand asset bytes and versions are never overwritten in place — a change creates a new version row (PROD.md §7.1a, §8.1).
- QR destination MUST be validated fresh immediately before the artifact is finalized, never served from cache (PROD.md §7.4).
- Crawling MUST respect `robots.txt`, use an identifiable User-Agent, rate-limit requests, cap redirects/response size, and block SSRF (private/loopback/link-local addresses) (PROD.md §7.6).
- Thai/English body text, the logo, and the QR are always composited deterministically — the image model never draws them (PROD.md §6.3, Out-of-scope §1.5).
- The real UTCC organization/domain/logo must never be simulated with placeholder or synthetic data; a separate, clearly-fictional "Acme" fixture is used only for deterministic offline tests (per explicit user instruction, 2026-07-22).
- No mutable "latest" tags for external artifacts where avoidable; the ComfyUI workflow JSON is user-supplied and version-controlled at a fixed path, not silently regenerated.

---

## Repository Layout (created across the tasks below)

```
docker-compose.yml
control/
  Dockerfile
  requirements.txt
  alembic.ini
  migrations/
    env.py
    versions/
  workflows/
    qwen_image_txt2img.json      # you drop the real ComfyUI API-format export here
  imagin/
    __init__.py
    config.py
    object_store.py
    db.py
    models.py
    brand/
      __init__.py
      entity_resolution.py
      crawler.py
      extractor.py
      scoring.py
      registry.py
    design_spec.py
    comfyui_client.py
    qr_gen.py
    compositor.py
    qa/
      __init__.py
      ocr_check.py
      qr_check.py
      logo_check.py
      report.py
    pipeline.py
    cli.py
  tests/
    conftest.py
    fixtures/
      acme_pages.py
      acme_logo.py
    test_native_dependencies.py   # Task 0 — gates the whole native/OCR/graphics toolchain
    test_config.py
    test_object_store.py
    test_models_migrations.py
    test_entity_resolution.py
    test_crawler.py
    test_extractor.py
    test_scoring.py
    test_registry.py
    test_design_spec.py
    test_comfyui_client.py
    test_qr_gen.py
    test_compositor.py
    test_qa_ocr.py
    test_qa_report.py
    test_pipeline_integration.py
.env.example
```

---

### Task 0: Native-dependency smoke test

**Why this task exists:** every later task depends on native/system libraries that are notoriously fragile to install — PyGObject needs gobject-introspection dev headers and typelibs, pycairo needs cairo dev headers, pyzbar needs a real `libzbar.so` at runtime, paddleocr/paddlepaddle are large C++-backed wheels, psycopg2 needs libpq. If any of these are missing or mis-built inside the `control` image, every downstream TDD task fails with a confusing, unrelated-looking error deep inside its own unit test (e.g. a compositor test failing on a `gi.require_version` `ValueError`, or a QA test failing because `paddleocr` segfaults on import). This task exists purely to fail fast, in one place, with a clear message, before any TDD work starts — this is a build-verification gate, not a unit test of application logic.

**Files:**
- Create: `control/tests/test_native_dependencies.py`

**Interfaces:**
- Consumes: nothing application-level. Exercises `pycairo`, `PyGObject`/`Pango`/`PangoCairo` (HarfBuzz text shaping), `qrcode` + `pyzbar` (round-trip through the real `libzbar` shared library), `psycopg2`, and `paddle`/`paddleocr` (import-only) directly.
- Produces: nothing consumed by later tasks — this is a standalone gate.

- [ ] **Step 1: Write the smoke test**

```python
# control/tests/test_native_dependencies.py
"""Task 0: native-dependency smoke test.

Every later task in this plan depends on native/system libraries that are
notoriously fragile to install (PyGObject needs gobject-introspection dev
headers + typelibs, pycairo needs cairo dev headers, pyzbar needs a real
libzbar.so at runtime, paddleocr/paddlepaddle are large C++-backed wheels,
psycopg2 needs libpq). If any of these are missing or mis-built inside the
`control` image, every downstream TDD task (compositor, QR, OCR QA, DB
migrations) fails with a confusing, unrelated-looking error deep inside its
own test. This module exists purely to fail fast, in one place, with a clear
message, before any of that work starts.

Run inside the real container (this is what actually exercises the Dockerfile's
apt-get list):
    docker compose build control
    docker compose run --rm control pytest tests/test_native_dependencies.py -v
"""
import io


def test_pycairo_can_create_and_paint_argb32_surface():
    import cairo

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 32, 32)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(1, 0, 0)
    ctx.paint()

    buffer = io.BytesIO()
    surface.write_to_png(buffer)
    assert len(buffer.getvalue()) > 0

    data = surface.get_data()
    # BGRA-ish pixel layout on little-endian: byte 2 (red channel) should be
    # fully saturated after painting pure red.
    assert data[2] == 255


def test_pango_cairo_can_shape_and_render_thai_text_via_harfbuzz():
    import gi

    gi.require_version("Pango", "1.0")
    gi.require_version("PangoCairo", "1.0")
    from gi.repository import Pango, PangoCairo
    import cairo

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 400, 100)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(1, 1, 1)
    ctx.paint()
    ctx.set_source_rgb(0, 0, 0)

    layout = PangoCairo.create_layout(ctx)
    layout.set_font_description(Pango.FontDescription("Noto Sans Thai 32"))
    # Thai text requires HarfBuzz-driven complex shaping (combining vowel/tone
    # marks); a broken shaping stack renders empty glyphs or raises, but
    # doesn't necessarily raise a Python exception, so we assert actual ink.
    layout.set_text("เปิดบ้าน UTCC", -1)
    PangoCairo.show_layout(ctx, layout)

    ink_rect, logical_rect = layout.get_pixel_extents()
    assert logical_rect.width > 0
    assert ink_rect.width > 0

    data = surface.get_data()
    assert any(byte != 255 for byte in data), "expected some non-white (rendered) pixels"


def test_qrcode_and_pyzbar_round_trip_through_zbar_shared_library():
    import qrcode
    from PIL import Image
    from pyzbar.pyzbar import decode as zbar_decode

    target_url = "https://example.invalid/native-dep-smoke-test"
    image = qrcode.make(target_url)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)

    decoded = zbar_decode(Image.open(buffer))
    assert [d.data.decode("utf-8") for d in decoded] == [target_url]


def test_psycopg2_driver_is_importable_and_dbapi_compliant():
    import psycopg2

    assert psycopg2.apilevel == "2.0"
    assert psycopg2.paramstyle == "pyformat"


def test_paddle_and_paddleocr_are_importable():
    # Import-only: this is where paddlepaddle's glibc/AVX/CUDA-vs-CPU wheel
    # mismatches usually blow up. Full OCR inference (model download + a real
    # forward pass) is exercised later by the QA OCR tests (Task 13); this
    # smoke test only needs to prove the module loads in this image.
    import paddle
    import paddleocr

    assert hasattr(paddle, "__version__")
    assert hasattr(paddleocr, "PaddleOCR")
```

- [ ] **Step 2: Run it — this MUST be run inside the real Docker image, not a bare host**

Run: `docker compose build control && docker compose run --rm control pytest tests/test_native_dependencies.py -v`
Expected: `5 passed`. If anything fails here, fix the Dockerfile's apt-get package list (Task 1) before writing a single line of TDD code for Tasks 1–15 — every later native-dependency failure traces back to this gate.

**Sandbox verification note (2026-07-22):** this repo's implementation was verified in an agent sandbox without Docker/root access. `test_pycairo_...` and `test_psycopg2_...` were confirmed passing directly (both install cleanly via plain `pip` with no system dev headers). `test_pango_cairo_...`, `test_qrcode_and_pyzbar_...`, and `test_paddle_and_paddleocr_...` could not be verified there — PyGObject needs `girepository` dev headers, pyzbar needs a runtime `libzbar.so`, and paddleocr needs its C++ wheel, none installable without root/apt in that sandbox. These three are exactly the dependencies Tasks 12 (compositor), 11 (QR), and 13 (OCR QA) need — all part of the still-blocked Tasks 10–15 — so this does not block Tasks 0–9. Run Step 2 for real on this PC (where Docker and the Dockerfile's `apt-get install` are available) before starting Task 10.

- [ ] **Step 3: Commit**

```bash
git add control/tests/test_native_dependencies.py
git commit -m "test: add Task 0 native-dependency smoke test gating the native/OCR/graphics toolchain"
```

---

### Task 1: Repo scaffolding, Docker runtime, and config loading

**Files:**
- Create: `docker-compose.yml`
- Create: `control/Dockerfile`
- Create: `control/requirements.txt`
- Create: `control/imagin/__init__.py`
- Create: `control/imagin/config.py`
- Create: `control/tests/conftest.py`
- Create: `control/tests/test_config.py`
- Create: `.env.example`

**Interfaces:**
- Produces: `imagin.config.Settings` (frozen dataclass with fields `database_url`, `object_store_root`, `comfyui_base_url`, `utcc_official_domain`), `imagin.config.load_settings() -> Settings`, `imagin.config.MissingConfigError`.

- [ ] **Step 1: Write the failing test**

```python
# control/tests/test_config.py
import pytest
from imagin.config import load_settings, MissingConfigError

REQUIRED_VARS = ["DATABASE_URL", "OBJECT_STORE_ROOT", "COMFYUI_BASE_URL", "UTCC_OFFICIAL_DOMAIN"]

def test_load_settings_reads_all_required_vars(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://imagin:imagin@postgres:5432/imagin")
    monkeypatch.setenv("OBJECT_STORE_ROOT", str(tmp_path))
    monkeypatch.setenv("COMFYUI_BASE_URL", "http://dgx-host:8188")
    monkeypatch.setenv("UTCC_OFFICIAL_DOMAIN", "utcc.ac.th")

    settings = load_settings()

    assert settings.database_url == "postgresql+psycopg2://imagin:imagin@postgres:5432/imagin"
    assert settings.object_store_root == str(tmp_path)
    assert settings.comfyui_base_url == "http://dgx-host:8188"
    assert settings.utcc_official_domain == "utcc.ac.th"

@pytest.mark.parametrize("missing_var", REQUIRED_VARS)
def test_load_settings_raises_when_var_missing(monkeypatch, tmp_path, missing_var):
    for var in REQUIRED_VARS:
        monkeypatch.setenv(var, "placeholder" if var != "OBJECT_STORE_ROOT" else str(tmp_path))
    monkeypatch.delenv(missing_var)

    with pytest.raises(MissingConfigError):
        load_settings()
```

```python
# control/tests/conftest.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm control pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'imagin.config'` (the `control` service does not exist yet either — see Step 3 before running).

- [ ] **Step 3: Write the runtime scaffolding and minimal implementation**

```dockerfile
# control/Dockerfile
# NOTE (patched 2026-07-22, second pass): PyGObject 3.56.x (pinned below in
# requirements.txt) links against girepository-2.0, which only exists on
# Debian trixie — bookworm (the default python:3.12-slim tag at the time
# this plan was written) only ships girepository1.0-dev and fails at
# pip-install time with a meson "Dependency 'girepository-2.0' is required
# but not found" error. Pinned to -trixie and swapped the dev package.
# apt's python3-gi is intentionally NOT installed — it would conflict with
# the pip-installed, version-pinned PyGObject this image actually builds
# and tests against.
FROM python:3.12-slim-trixie

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential pkg-config \
    libpango1.0-dev libcairo2-dev libgirepository-2.0-dev \
    gir1.2-pango-1.0 \
    libzbar0 libpq-dev \
    fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
ENV PYTHONPATH=/app
CMD ["python", "-m", "imagin.cli"]
```

```text
# control/requirements.txt
sqlalchemy>=2.0,<3.0
alembic>=1.13,<2.0
psycopg2-binary>=2.9,<3.0
httpx>=0.27,<1.0
beautifulsoup4>=4.12,<5.0
lxml>=5.0,<6.0
qrcode>=7.4,<8.0
pyzbar>=0.1.9,<0.2
pillow>=10.0,<11.0
paddleocr>=2.7,<3.0
paddlepaddle>=2.6,<3.0
pycairo>=1.25,<2.0
# Pinned exactly (patched 2026-07-22, second pass), not a floating range:
# 3.56.3 is the version the Dockerfile's base image (python:3.12-slim-trixie
# + libgirepository-2.0-dev) is actually built and tested against. A
# floating range risks silently picking up a future PyGObject release with
# a different girepository requirement again.
PyGObject==3.56.3
pytest>=8.0,<9.0
pytest-mock>=3.14,<4.0
respx>=0.21,<1.0
```

```yaml
# docker-compose.yml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: imagin
      POSTGRES_PASSWORD: imagin
      POSTGRES_DB: imagin
    ports:
      - "5433:5432"
    volumes:
      - imagin_pg_data:/var/lib/postgresql/data

  control:
    build: ./control
    env_file: .env
    volumes:
      - ./control:/app
      - imagin_objects:/data/objects
      # Bind-mounted (not a named volume) so poster.png / qa_report.json land
      # directly in ./output on this PC and are reviewable without reaching
      # into the container or a Docker-managed volume (patched 2026-07-22).
      - ./output:/app/output
    depends_on:
      - postgres
    extra_hosts:
      # ComfyUI on the DGX is reached from this PC at localhost:8188 (via your
      # tunnel/port-forward). Inside a Linux container, "localhost" means the
      # container itself, not the host PC, so the app must instead address the
      # host PC as host.docker.internal — this line makes that name resolve.
      - "host.docker.internal:host-gateway"

volumes:
  imagin_pg_data:
  imagin_objects:
```

```dotenv
# .env.example
DATABASE_URL=postgresql+psycopg2://imagin:imagin@postgres:5432/imagin
OBJECT_STORE_ROOT=/data/objects
# Your DGX ComfyUI tunnel terminates at localhost:8188 on this PC. From inside
# the `control` container that host PC is reachable as host.docker.internal,
# not localhost (see docker-compose.yml extra_hosts note above).
COMFYUI_BASE_URL=http://host.docker.internal:8188
UTCC_OFFICIAL_DOMAIN=utcc.ac.th

# QR_TARGET_URL is intentionally left unset here (patched 2026-07-22, Task 15).
# imagin.cli refuses to run without it (or an equivalent --qr-target-url
# flag) and will not default to a guessed value — set it only once you've
# personally verified the destination resolves (PROD.md §7.4).
# QR_TARGET_URL=
```

```python
# control/imagin/__init__.py
```

```python
# control/imagin/config.py
import os
from dataclasses import dataclass

REQUIRED_VARS = ("DATABASE_URL", "OBJECT_STORE_ROOT", "COMFYUI_BASE_URL", "UTCC_OFFICIAL_DOMAIN")


class MissingConfigError(RuntimeError):
    pass


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise MissingConfigError(f"required environment variable {name} is not set")
    return value


@dataclass(frozen=True)
class Settings:
    database_url: str
    object_store_root: str
    comfyui_base_url: str
    utcc_official_domain: str


def load_settings() -> Settings:
    return Settings(
        database_url=_require("DATABASE_URL"),
        object_store_root=_require("OBJECT_STORE_ROOT"),
        comfyui_base_url=_require("COMFYUI_BASE_URL"),
        utcc_official_domain=_require("UTCC_OFFICIAL_DOMAIN"),
    )
```

Copy `.env.example` to `.env` (with your real `COMFYUI_BASE_URL`) before running anything: `cp .env.example .env`.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose build control && docker compose run --rm control pytest tests/test_config.py -v`
Expected: `2 passed` (the parametrized missing-var test runs once per required var → 4 cases + the happy path = 5 passed; adjust expectation to `5 passed`).

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml .env.example control/Dockerfile control/requirements.txt control/imagin/__init__.py control/imagin/config.py control/tests/conftest.py control/tests/test_config.py
git commit -m "feat: scaffold control-plane container and env-based config loading"
```

---

### Task 2: Local object storage adapter

**Files:**
- Create: `control/imagin/object_store.py`
- Create: `control/tests/test_object_store.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `imagin.object_store.StoredObject(storage_key: str, sha256: str, size_bytes: int)`, `imagin.object_store.LocalObjectStore(root: str)` with `.put(data: bytes, suffix: str = "") -> StoredObject` and `.get(storage_key: str) -> bytes`. Later tasks (Task 8 registry, Task 14 pipeline) depend on this exact signature.

- [ ] **Step 1: Write the failing test**

```python
# control/tests/test_object_store.py
import hashlib
from imagin.object_store import LocalObjectStore


def test_put_then_get_round_trips_bytes(tmp_path):
    store = LocalObjectStore(str(tmp_path))
    data = b"hello imagin"

    stored = store.put(data, suffix=".txt")

    assert stored.sha256 == hashlib.sha256(data).hexdigest()
    assert stored.size_bytes == len(data)
    assert store.get(stored.storage_key) == data


def test_put_is_idempotent_by_content_hash(tmp_path):
    store = LocalObjectStore(str(tmp_path))
    data = b"same bytes twice"

    first = store.put(data)
    second = store.put(data)

    assert first.storage_key == second.storage_key
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm control pytest tests/test_object_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'imagin.object_store'`

- [ ] **Step 3: Write minimal implementation**

```python
# control/imagin/object_store.py
import hashlib
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class StoredObject:
    storage_key: str
    sha256: str
    size_bytes: int


class LocalObjectStore:
    def __init__(self, root: str):
        self.root = root
        os.makedirs(self.root, exist_ok=True)

    def put(self, data: bytes, suffix: str = "") -> StoredObject:
        digest = hashlib.sha256(data).hexdigest()
        storage_key = f"{digest}{suffix}"
        path = os.path.join(self.root, storage_key)
        if not os.path.exists(path):
            with open(path, "wb") as f:
                f.write(data)
        return StoredObject(storage_key=storage_key, sha256=digest, size_bytes=len(data))

    def get(self, storage_key: str) -> bytes:
        with open(os.path.join(self.root, storage_key), "rb") as f:
            return f.read()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose run --rm control pytest tests/test_object_store.py -v`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add control/imagin/object_store.py control/tests/test_object_store.py
git commit -m "feat: add local filesystem object store with sha256 content addressing"
```

---

### Task 3: Database models and Alembic migration

**Files:**
- Create: `control/imagin/db.py`
- Create: `control/imagin/models.py`
- Create: `control/alembic.ini`
- Create: `control/migrations/env.py`
- Create: `control/migrations/versions/0001_initial_brand_schema.py`
- Create: `control/tests/test_models_migrations.py`

**Interfaces:**
- Consumes: `imagin.config.load_settings`.
- Produces: `imagin.db.Base`, `imagin.db.get_engine(database_url: str)`, `imagin.db.session_scope(engine)`; ORM classes `imagin.models.Organization`, `VerifiedDomain`, `SourceSnapshot`, `BrandProfile`, `BrandAsset` — Task 8 (`registry.py`) and Task 14 (`pipeline.py`) import these directly by name.

- [ ] **Step 1: Write the failing test**

```python
# control/tests/test_models_migrations.py
import os
import subprocess
import uuid
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from imagin.models import Organization, VerifiedDomain, BrandProfile, BrandAsset


from tests.conftest import test_database_url as _test_database_url
# NOTE (patched 2026-07-22, third pass): this used to be a local
# `_test_database_url()` doing `DATABASE_URL.replace("/imagin", "/imagin_test")`.
# Against a real docker-compose DATABASE_URL
# (postgresql+psycopg2://imagin:imagin@postgres:5432/imagin), the substring
# "/imagin" occurs TWICE — once inside "://imagin" (the username) and once
# at the end (the database name) — so .replace() silently rewrote the
# username to "imagin_test" too, a role that doesn't exist, producing
# "password authentication failed for user 'imagin_test'" the first time
# this was actually run against real Postgres. See conftest.py's
# test_database_url() for the fix (operates on the URL's rightmost path
# segment structurally, not by substring replace) — this file now imports
# that shared, corrected helper instead of duplicating the buggy one.


def test_migrations_create_expected_tables_and_round_trip():
    subprocess.run(
        ["alembic", "-x", f"db_url={_test_database_url()}", "upgrade", "head"],
        cwd="/app", check=True,
    )
    engine = create_engine(_test_database_url())
    with Session(engine) as session:
        org = Organization(canonical_name="Test University")
        session.add(org)
        session.flush()

        session.add(VerifiedDomain(
            organization_id=org.id, domain="test.example.ac.th",
            verification_method="configured_official_domain", status="verified",
        ))
        profile = BrandProfile(
            organization_id=org.id, version=1, status="provisional",
            profile={"organizationName": "Test University", "officialDomain": "test.example.ac.th"},
        )
        session.add(profile)
        session.flush()
        session.add(BrandAsset(
            brand_profile_id=profile.id, type="logo", status="auto_accepted",
            storage_key="deadbeef.png", sha256="deadbeef", score=91,
        ))
        session.commit()

        fetched = session.scalar(select(Organization).where(Organization.canonical_name == "Test University"))
        assert fetched is not None
        assert isinstance(fetched.id, uuid.UUID)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm control pytest tests/test_models_migrations.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'imagin.models'`

- [ ] **Step 3: Write minimal implementation**

```python
# control/imagin/db.py
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, DeclarativeBase


class Base(DeclarativeBase):
    pass


def get_engine(database_url: str):
    return create_engine(database_url, future=True)


@contextmanager
def session_scope(engine):
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

```python
# control/imagin/models.py
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, ForeignKey, UniqueConstraint, JSON
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    canonical_name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=_now)


class VerifiedDomain(Base):
    __tablename__ = "verified_domains"
    __table_args__ = (UniqueConstraint("organization_id", "domain"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    domain: Mapped[str] = mapped_column(String, nullable=False)
    verification_method: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="verified")
    verified_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=_now)


class SourceSnapshot(Base):
    __tablename__ = "source_snapshots"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    url: Mapped[str] = mapped_column(String, nullable=False)
    domain: Mapped[str] = mapped_column(String, nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=_now)
    http_status: Mapped[int] = mapped_column(Integer, nullable=False)
    content_type: Mapped[str] = mapped_column(String, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class BrandProfile(Base):
    __tablename__ = "brand_profiles"
    __table_args__ = (UniqueConstraint("organization_id", "version"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    profile: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=_now)


class BrandAsset(Base):
    __tablename__ = "brand_assets"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    brand_profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brand_profiles.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("source_snapshots.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=_now)
```

```ini
# control/alembic.ini
# NOTE (patched 2026-07-22): the original draft of this file had only the
# [alembic] section. migrations/env.py calls logging.config.fileConfig() on
# it unconditionally, which requires [loggers]/[handlers]/[formatters] to be
# present — without them every `alembic upgrade` crashes with
# `KeyError: 'formatters'` before it ever touches the database. This is the
# standard boilerplate `alembic init` normally generates.
[alembic]
script_location = migrations

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARNING
handlers = console
qualname =

[logger_sqlalchemy]
level = WARNING
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

```python
# control/migrations/env.py
import os
from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool

from imagin.db import Base
from imagin import models  # noqa: F401  (registers tables on Base.metadata)

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

x_args = context.get_x_argument(as_dictionary=True)
db_url = x_args.get("db_url") or os.environ["DATABASE_URL"]
config.set_main_option("sqlalchemy.url", db_url)

target_metadata = Base.metadata


def run_migrations_online():
    connectable = engine_from_config(config.get_section(config.config_ini_section), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
```

```python
# control/migrations/versions/0001_initial_brand_schema.py
"""initial brand schema"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("canonical_name", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default="active"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )
    op.create_table(
        "verified_domains",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("domain", sa.String, nullable=False),
        sa.Column("verification_method", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default="verified"),
        sa.Column("verified_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "domain"),
    )
    op.create_table(
        "source_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("url", sa.String, nullable=False),
        sa.Column("domain", sa.String, nullable=False),
        sa.Column("retrieved_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("http_status", sa.Integer, nullable=False),
        sa.Column("content_type", sa.String, nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
    )
    op.create_table(
        "brand_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("profile", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "version"),
    )
    op.create_table(
        "brand_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("brand_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("brand_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("storage_key", sa.String, nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("score", sa.Integer, nullable=True),
        sa.Column("source_snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("source_snapshots.id"), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("brand_assets")
    op.drop_table("brand_profiles")
    op.drop_table("source_snapshots")
    op.drop_table("verified_domains")
    op.drop_table("organizations")
```

Add a `postgres` init step for the test database: `docker compose exec postgres psql -U imagin -c "CREATE DATABASE imagin_test;"` (run once; ignore error if it already exists).

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
docker compose up -d postgres
docker compose exec postgres psql -U imagin -tc "SELECT 1 FROM pg_database WHERE datname = 'imagin_test'" | grep -q 1 || docker compose exec postgres psql -U imagin -c "CREATE DATABASE imagin_test;"
docker compose run --rm control pytest tests/test_models_migrations.py -v
```
Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add control/imagin/db.py control/imagin/models.py control/alembic.ini control/migrations control/tests/test_models_migrations.py
git commit -m "feat: add SQLAlchemy models and initial Alembic migration for brand registry"
```

---

### Task 4: Entity resolution (official domain validation + SSRF guard)

**Files:**
- Create: `control/imagin/brand/__init__.py`
- Create: `control/imagin/brand/entity_resolution.py`
- Create: `control/tests/test_entity_resolution.py`

**Interfaces:**
- Consumes: `httpx.Client` (caller-supplied, so tests can inject a mock transport).
- Produces: `imagin.brand.entity_resolution.ResolvedDomain(domain, canonical_url, http_status)`, `resolve_official_domain(domain: str, client: httpx.Client) -> ResolvedDomain`, `DomainResolutionError`. Task 8 (`registry.py`) calls `resolve_official_domain` directly.

- [ ] **Step 1: Write the failing test**

```python
# control/tests/test_entity_resolution.py
import httpx
import pytest
from imagin.brand.entity_resolution import resolve_official_domain, DomainResolutionError


def test_resolve_official_domain_succeeds_for_reachable_https_domain(monkeypatch):
    monkeypatch.setattr(
        "imagin.brand.entity_resolution._is_public_host", lambda host: True
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "utcc.ac.th"
        return httpx.Response(200, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))

    resolved = resolve_official_domain("utcc.ac.th", client)

    assert resolved.domain == "utcc.ac.th"
    assert resolved.http_status == 200


def test_resolve_official_domain_rejects_non_public_address(monkeypatch):
    monkeypatch.setattr(
        "imagin.brand.entity_resolution._is_public_host", lambda host: False
    )
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, request=r)))

    with pytest.raises(DomainResolutionError):
        resolve_official_domain("internal.local", client)


def test_resolve_official_domain_raises_on_http_error(monkeypatch):
    monkeypatch.setattr(
        "imagin.brand.entity_resolution._is_public_host", lambda host: True
    )
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503, request=r)))

    with pytest.raises(DomainResolutionError):
        resolve_official_domain("utcc.ac.th", client)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm control pytest tests/test_entity_resolution.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'imagin.brand'`

- [ ] **Step 3: Write minimal implementation**

```python
# control/imagin/brand/__init__.py
```

```python
# control/imagin/brand/entity_resolution.py
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx


class DomainResolutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ResolvedDomain:
    domain: str
    canonical_url: str
    http_status: int


def _is_public_host(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise DomainResolutionError(f"cannot resolve host {host}: {exc}") from exc
    for _family, _type, _proto, _canon, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False
    return True


def resolve_official_domain(domain: str, client: httpx.Client) -> ResolvedDomain:
    host = urlparse(f"https://{domain}").hostname or domain
    if not _is_public_host(host):
        raise DomainResolutionError(f"configured domain {domain} resolves to a non-public address")

    response = client.get(f"https://{domain}/", follow_redirects=True, timeout=10.0)
    if response.status_code >= 400:
        raise DomainResolutionError(f"official domain {domain} returned {response.status_code}")

    return ResolvedDomain(domain=domain, canonical_url=str(response.url), http_status=response.status_code)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose run --rm control pytest tests/test_entity_resolution.py -v`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add control/imagin/brand/__init__.py control/imagin/brand/entity_resolution.py control/tests/test_entity_resolution.py
git commit -m "feat: add official-domain entity resolution with SSRF guard"
```

---

### Task 5: Respectful web crawler (robots.txt, rate limit, redirect/size caps)

**Files:**
- Create: `control/imagin/brand/crawler.py`
- Create: `control/tests/test_crawler.py`

**Interfaces:**
- Consumes: `httpx.Client`.
- Produces: `imagin.brand.crawler.FetchedPage(url, status_code, content_type, body)`, `RespectfulCrawler(client, min_interval_seconds=1.0)` with `.fetch(url, base_url) -> FetchedPage`, `CrawlBlockedError`. Task 8 (`registry.py`) uses `RespectfulCrawler.fetch`.

- [ ] **Step 1: Write the failing test**

```python
# control/tests/test_crawler.py
import httpx
import pytest
from imagin.brand.crawler import RespectfulCrawler, CrawlBlockedError

ROBOTS_ALLOW_ALL = "User-agent: *\nAllow: /\n"
ROBOTS_DISALLOW_ALL = "User-agent: *\nDisallow: /\n"


def _client_with(pages: dict[str, httpx.Response]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return pages[str(request.url)]
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_succeeds_when_robots_allows(monkeypatch):
    client = _client_with({
        "https://example.ac.th/robots.txt": httpx.Response(200, text=ROBOTS_ALLOW_ALL, request=httpx.Request("GET", "https://example.ac.th/robots.txt")),
        "https://example.ac.th/": httpx.Response(200, text="<html>home</html>", headers={"content-type": "text/html"}, request=httpx.Request("GET", "https://example.ac.th/")),
    })
    crawler = RespectfulCrawler(client, min_interval_seconds=0)

    page = crawler.fetch("https://example.ac.th/", "https://example.ac.th")

    assert page.status_code == 200
    assert b"home" in page.body


def test_fetch_raises_when_robots_disallows():
    client = _client_with({
        "https://example.ac.th/robots.txt": httpx.Response(200, text=ROBOTS_DISALLOW_ALL, request=httpx.Request("GET", "https://example.ac.th/robots.txt")),
    })
    crawler = RespectfulCrawler(client, min_interval_seconds=0)

    with pytest.raises(CrawlBlockedError):
        crawler.fetch("https://example.ac.th/", "https://example.ac.th")


def test_fetch_raises_when_response_too_large():
    big_body = "x" * (6_000_000)
    client = _client_with({
        "https://example.ac.th/robots.txt": httpx.Response(200, text=ROBOTS_ALLOW_ALL, request=httpx.Request("GET", "https://example.ac.th/robots.txt")),
        "https://example.ac.th/": httpx.Response(200, text=big_body, headers={"content-type": "text/html"}, request=httpx.Request("GET", "https://example.ac.th/")),
    })
    crawler = RespectfulCrawler(client, min_interval_seconds=0)

    with pytest.raises(CrawlBlockedError):
        crawler.fetch("https://example.ac.th/", "https://example.ac.th")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm control pytest tests/test_crawler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'imagin.brand.crawler'`

- [ ] **Step 3: Write minimal implementation**

```python
# control/imagin/brand/crawler.py
import time
from dataclasses import dataclass
from urllib.robotparser import RobotFileParser

import httpx

MAX_REDIRECTS = 5
MAX_BYTES = 5_000_000
REQUEST_TIMEOUT = 10.0
USER_AGENT = "ImaginBrandCrawler/0.1 (+contact: brand-registry@imagin.local)"


class CrawlBlockedError(RuntimeError):
    pass


@dataclass(frozen=True)
class FetchedPage:
    url: str
    status_code: int
    content_type: str
    body: bytes


class RespectfulCrawler:
    def __init__(self, client: httpx.Client, min_interval_seconds: float = 1.0):
        self._client = client
        self._min_interval = min_interval_seconds
        self._last_request_at = 0.0
        self._robots_cache: dict[str, RobotFileParser] = {}

    def _robots_for(self, base_url: str) -> RobotFileParser:
        if base_url not in self._robots_cache:
            parser = RobotFileParser()
            try:
                response = self._client.get(f"{base_url}/robots.txt", timeout=REQUEST_TIMEOUT)
                parser.parse(response.text.splitlines() if response.status_code < 400 else [])
            except httpx.HTTPError:
                parser.parse([])
            self._robots_cache[base_url] = parser
        return self._robots_cache[base_url]

    def fetch(self, url: str, base_url: str) -> FetchedPage:
        robots = self._robots_for(base_url)
        if not robots.can_fetch(USER_AGENT, url):
            raise CrawlBlockedError(f"robots.txt disallows fetching {url}")

        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)

        response = self._client.get(url, headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=REQUEST_TIMEOUT)
        self._last_request_at = time.monotonic()

        if len(response.history) > MAX_REDIRECTS:
            raise CrawlBlockedError(f"too many redirects fetching {url}")
        if len(response.content) > MAX_BYTES:
            raise CrawlBlockedError(f"response for {url} exceeds max size of {MAX_BYTES} bytes")

        return FetchedPage(
            url=str(response.url),
            status_code=response.status_code,
            content_type=response.headers.get("content-type", ""),
            body=response.content,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose run --rm control pytest tests/test_crawler.py -v`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add control/imagin/brand/crawler.py control/tests/test_crawler.py
git commit -m "feat: add robots.txt-respecting, rate-limited crawler with size/redirect caps"
```

---

### Task 6: JSON-LD / logo-candidate extraction

**Files:**
- Create: `control/imagin/brand/extractor.py`
- Create: `control/tests/fixtures/acme_pages.py`
- Create: `control/tests/test_extractor.py`

**Interfaces:**
- Produces: `imagin.brand.extractor.LogoCandidate(url, evidence, is_svg, filename_hint)`, `ExtractionResult(organization_name, logo_candidates)`, `extract_organization_page(html: bytes, page_url: str) -> ExtractionResult`. Task 8 (`registry.py`) consumes `ExtractionResult.logo_candidates`.

- [ ] **Step 1: Write the failing test**

```python
# control/tests/fixtures/acme_pages.py
"""Fictional 'Acme University' fixtures for deterministic offline tests.
Never represents real UTCC data — see plan Global Constraints."""

ACME_HOME_PAGE_HTML = b"""
<html>
<head>
<script type="application/ld+json">
{"@type": "Organization", "name": "Acme University", "logo": "https://acme.example/brand/logo.svg"}
</script>
<link rel="icon" href="https://acme.example/favicon.ico">
<meta property="og:image" content="https://acme.example/social-banner.png">
</head>
<body>
<!-- NOTE (patched 2026-07-22): header logo intentionally points at the same
     URL as the JSON-LD logo — the single most common real-world pattern,
     and the case the merge-by-URL fix in extractor.py below exists for. -->
<header><img src="https://acme.example/brand/logo.svg"></header>
</body>
</html>
"""
```

```python
# control/tests/test_extractor.py
from imagin.brand.extractor import extract_organization_page
from tests.fixtures.acme_pages import ACME_HOME_PAGE_HTML


def test_extract_organization_page_finds_jsonld_logo_and_name():
    result = extract_organization_page(ACME_HOME_PAGE_HTML, "https://acme.example/")

    assert result.organization_name == "Acme University"
    jsonld_candidates = [c for c in result.logo_candidates if "organization_jsonld" in c.evidence]
    assert len(jsonld_candidates) == 1
    assert jsonld_candidates[0].url == "https://acme.example/brand/logo.svg"
    assert jsonld_candidates[0].is_svg is True


def test_extract_organization_page_tags_header_favicon_and_og_image():
    result = extract_organization_page(ACME_HOME_PAGE_HTML, "https://acme.example/")

    evidence_tags = {tag for c in result.logo_candidates for tag in c.evidence}
    assert "repeated_header_use" in evidence_tags
    assert "favicon_only" in evidence_tags
    assert "og_image_only" in evidence_tags
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm control pytest tests/test_extractor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'imagin.brand.extractor'`

- [ ] **Step 3: Write minimal implementation**

```python
# control/imagin/brand/extractor.py
import json
from dataclasses import dataclass

from bs4 import BeautifulSoup


@dataclass(frozen=True)
class LogoCandidate:
    url: str
    evidence: list[str]
    is_svg: bool
    filename_hint: str


@dataclass(frozen=True)
class ExtractionResult:
    organization_name: str | None
    logo_candidates: list[LogoCandidate]


def _add_evidence(candidates_by_url: dict[str, LogoCandidate], url: str, evidence_tag: str) -> None:
    # NOTE (patched 2026-07-22): the original draft appended a brand-new
    # LogoCandidate per (url, evidence_tag) pair, even when the same URL
    # recurred. Multiple independent signals (JSON-LD, repeated header use,
    # favicon, ...) frequently point at the exact same logo file — the
    # header <img> src and the JSON-LD Organization.logo are very often
    # literally the same URL. §7.3 scoring is meant to accumulate evidence
    # *about a candidate asset*, so evidence for the same normalized URL
    # must merge into one LogoCandidate rather than silently splitting into
    # several single-signal candidates that individually never clear the
    # usability threshold (this was found because the Task 8 registry test
    # could not otherwise produce a usable candidate at all).
    existing = candidates_by_url.get(url)
    if existing is None:
        candidates_by_url[url] = LogoCandidate(
            url=url,
            evidence=[evidence_tag],
            is_svg=url.lower().endswith(".svg"),
            filename_hint=url.rsplit("/", 1)[-1],
        )
    elif evidence_tag not in existing.evidence:
        candidates_by_url[url] = LogoCandidate(
            url=existing.url,
            evidence=[*existing.evidence, evidence_tag],
            is_svg=existing.is_svg,
            filename_hint=existing.filename_hint,
        )


def extract_organization_page(html: bytes, page_url: str) -> ExtractionResult:
    soup = BeautifulSoup(html, "lxml")
    organization_name = None
    candidates_by_url: dict[str, LogoCandidate] = {}

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        entries = data if isinstance(data, list) else [data]
        for entry in entries:
            if isinstance(entry, dict) and entry.get("@type") == "Organization":
                organization_name = entry.get("name") or organization_name
                logo = entry.get("logo")
                if isinstance(logo, str):
                    _add_evidence(candidates_by_url, logo, "organization_jsonld")

    for img in soup.select("header img, header svg"):
        src = img.get("src") or img.get("data-src")
        if src:
            _add_evidence(candidates_by_url, src, "repeated_header_use")

    icon_link = soup.find("link", rel=lambda v: v and "icon" in v)
    if icon_link and icon_link.get("href"):
        _add_evidence(candidates_by_url, icon_link["href"], "favicon_only")

    og_image = soup.find("meta", attrs={"property": "og:image"})
    if og_image and og_image.get("content"):
        _add_evidence(candidates_by_url, og_image["content"], "og_image_only")

    return ExtractionResult(organization_name=organization_name, logo_candidates=list(candidates_by_url.values()))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose run --rm control pytest tests/test_extractor.py -v`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add control/imagin/brand/extractor.py control/tests/fixtures/acme_pages.py control/tests/test_extractor.py
git commit -m "feat: extract organization JSON-LD and logo candidates from crawled pages"
```

---

### Task 7: Logo candidate scoring

**Files:**
- Create: `control/imagin/brand/scoring.py`
- Create: `control/tests/test_scoring.py`

**Interfaces:**
- Produces: `imagin.brand.scoring.ScoredCandidate(score, status)`, `score_logo_candidate(evidence: list[str], is_svg: bool = False, filename_hint: str = "") -> ScoredCandidate`, `classify_score(score: int) -> str`. Task 8 (`registry.py`) calls `score_logo_candidate` per candidate.

- [ ] **Step 1: Write the failing test**

```python
# control/tests/test_scoring.py
# NOTE (patched 2026-07-22): the original draft of this file asserted
# status == "provisional" for a candidate scoring 55, which contradicts its
# own PROVISIONAL_THRESHOLD = 60 (and PROD.md §7.1a/§7.3's "< 60 MUST NOT be
# used" rule). That was a bug in the test's expectations, not in
# score_logo_candidate/classify_score, which were already correct. Fixed
# below by correcting the assertions (renaming the misleadingly-named first
# test) and adding a genuine auto_accepted (>= 80) case, which the original
# suite never actually exercised end-to-end.
from imagin.brand.scoring import score_logo_candidate, classify_score


def test_jsonld_svg_and_filename_hint_alone_is_still_excluded_below_threshold():
    # 30 (jsonld) + 15 (svg) + 10 (filename hint) = 55, below PROVISIONAL_THRESHOLD (60),
    # so per PROD.md §7.1a/§7.3 this candidate MUST NOT be auto-usable or provisional.
    scored = score_logo_candidate(["organization_jsonld"], is_svg=True, filename_hint="official-logo.svg")

    assert scored.score == 55
    assert scored.status == "excluded"


def test_jsonld_plus_header_reuse_plus_svg_and_filename_hint_reaches_provisional():
    # 30 (jsonld) + 20 (header reuse) + 15 (svg) + 10 (filename hint, "logo.svg" matches) = 75.
    scored = score_logo_candidate(["organization_jsonld", "repeated_header_use"], is_svg=True, filename_hint="logo.svg")

    assert scored.score == 75
    assert scored.status == "provisional"


def test_official_brand_guideline_plus_jsonld_and_svg_is_auto_accepted():
    # 40 (official brand guideline) + 30 (jsonld) + 15 (svg) = 85, clears AUTO_USE_THRESHOLD (80).
    scored = score_logo_candidate(["official_brand_guideline", "organization_jsonld"], is_svg=True)

    assert scored.score == 85
    assert scored.status == "auto_accepted"


def test_favicon_only_is_excluded():
    scored = score_logo_candidate(["favicon_only"])

    assert scored.score == -15
    assert scored.status == "excluded"


def test_classify_score_boundaries():
    assert classify_score(80) == "auto_accepted"
    assert classify_score(79) == "provisional"
    assert classify_score(60) == "provisional"
    assert classify_score(59) == "excluded"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm control pytest tests/test_scoring.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'imagin.brand.scoring'`

- [ ] **Step 3: Write minimal implementation**

```python
# control/imagin/brand/scoring.py
from dataclasses import dataclass

EVIDENCE_SCORES = {
    "official_brand_guideline": 40,
    "organization_jsonld": 30,
    "repeated_header_use": 20,
    "svg_source": 15,
    "logo_filename_hint": 10,
    "transparent_background": 5,
    "favicon_only": -15,
    "og_image_only": -20,
    "partner_sponsor_context": -30,
    "inconsistent_aspect_ratio": -20,
}

AUTO_USE_THRESHOLD = 80
PROVISIONAL_THRESHOLD = 60


@dataclass(frozen=True)
class ScoredCandidate:
    score: int
    status: str  # auto_accepted | provisional | excluded


def classify_score(score: int) -> str:
    if score >= AUTO_USE_THRESHOLD:
        return "auto_accepted"
    if score >= PROVISIONAL_THRESHOLD:
        return "provisional"
    return "excluded"


def score_logo_candidate(evidence: list[str], is_svg: bool = False, filename_hint: str = "") -> ScoredCandidate:
    tags = list(evidence)
    if is_svg:
        tags.append("svg_source")
    if any(keyword in filename_hint.lower() for keyword in ("logo", "brand", "wordmark")):
        tags.append("logo_filename_hint")

    score = sum(EVIDENCE_SCORES.get(tag, 0) for tag in tags)
    return ScoredCandidate(score=score, status=classify_score(score))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose run --rm control pytest tests/test_scoring.py -v`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add control/imagin/brand/scoring.py control/tests/test_scoring.py
git commit -m "feat: implement PROD.md §7.3 logo candidate scoring and threshold classification"
```

---

### Task 8: Cache-first brand registry (resolve, version, no-overwrite)

**Files:**
- Create: `control/imagin/brand/registry.py`
- Create: `control/tests/test_registry.py`

**Interfaces:**
- Consumes: `imagin.models.{Organization,VerifiedDomain,SourceSnapshot,BrandProfile,BrandAsset}`, `imagin.brand.entity_resolution.resolve_official_domain`, `imagin.brand.crawler.RespectfulCrawler`, `imagin.brand.extractor.extract_organization_page`, `imagin.brand.scoring.score_logo_candidate`, `imagin.object_store.LocalObjectStore`.
- Produces: `imagin.brand.registry.ResolvedBrand(organization_id, brand_profile_id, profile_version, logo_asset_id, logo_storage_key, logo_sha256)`, `resolve_brand(session, org_name, official_domain, http_client, object_store) -> ResolvedBrand`, `NoUsableBrandAssetError`. Task 14 (`pipeline.py`) calls `resolve_brand` directly.

- [ ] **Step 1: Write the failing test**

```python
# control/tests/test_registry.py
import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from imagin.brand.registry import resolve_brand, NoUsableBrandAssetError
from imagin.models import BrandProfile, BrandAsset, VerifiedDomain
from tests.fixtures.acme_pages import ACME_HOME_PAGE_HTML

ROBOTS_ALLOW_ALL = "User-agent: *\nAllow: /\n"


def _acme_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("robots.txt"):
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL, request=request)
        if url == "https://acme.example/":
            return httpx.Response(200, content=ACME_HOME_PAGE_HTML, headers={"content-type": "text/html"}, request=request)
        if url == "https://acme.example/brand/logo.svg":
            return httpx.Response(200, content=b"<svg>acme-logo</svg>", headers={"content-type": "image/svg+xml"}, request=request)
        return httpx.Response(404, request=request)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_resolve_brand_creates_new_org_and_versioned_profile(db_session: Session, tmp_path, monkeypatch):
    monkeypatch.setattr("imagin.brand.entity_resolution._is_public_host", lambda host: True)
    from imagin.object_store import LocalObjectStore
    store = LocalObjectStore(str(tmp_path))

    resolved = resolve_brand(db_session, "Acme University", "acme.example", _acme_client(), store)

    assert resolved.profile_version == 1
    profile = db_session.get(BrandProfile, resolved.brand_profile_id)
    assert profile.status in ("verified", "provisional")
    asset = db_session.scalar(select(BrandAsset).where(BrandAsset.brand_profile_id == profile.id))
    assert asset.storage_key == resolved.logo_storage_key
    assert store.get(asset.storage_key) == b"<svg>acme-logo</svg>"


def test_resolve_brand_reuses_fresh_cached_profile_without_recrawling(db_session: Session, tmp_path, monkeypatch):
    monkeypatch.setattr("imagin.brand.entity_resolution._is_public_host", lambda host: True)
    from imagin.object_store import LocalObjectStore
    store = LocalObjectStore(str(tmp_path))
    first = resolve_brand(db_session, "Acme University", "acme.example", _acme_client(), store)

    def failing_handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should not re-crawl when cache is fresh")
    second = resolve_brand(db_session, "Acme University", "acme.example", httpx.Client(transport=httpx.MockTransport(failing_handler)), store)

    assert second.brand_profile_id == first.brand_profile_id
    assert second.profile_version == first.profile_version


def test_resolve_brand_never_overwrites_prior_version_row(db_session: Session, tmp_path, monkeypatch):
    monkeypatch.setattr("imagin.brand.entity_resolution._is_public_host", lambda host: True)
    from imagin.object_store import LocalObjectStore
    store = LocalObjectStore(str(tmp_path))
    first = resolve_brand(db_session, "Acme University", "acme.example", _acme_client(), store)

    # force staleness so a second resolve re-crawls and creates version 2
    profile = db_session.get(BrandProfile, first.brand_profile_id)
    from datetime import datetime, timedelta, timezone
    profile.created_at = datetime.now(timezone.utc) - timedelta(days=999)
    db_session.commit()

    second = resolve_brand(db_session, "Acme University", "acme.example", _acme_client(), store)

    assert second.profile_version == 2
    still_present = db_session.get(BrandProfile, first.brand_profile_id)
    assert still_present is not None  # version 1 row untouched, not overwritten


def test_resolve_brand_upserts_verified_domain_on_refresh_instead_of_duplicating(db_session: Session, tmp_path, monkeypatch):
    # NOTE (patched 2026-07-22): regression test for the fix below. The
    # original draft of resolve_brand() unconditionally INSERTed a new
    # VerifiedDomain row every time it re-crawled, which violates the
    # (organization_id, domain) unique constraint on the second resolution
    # of the same org+domain — exactly what test_resolve_brand_never_
    # overwrites_prior_version_row above exercises. This asserts the fixed
    # upsert behavior directly: exactly one row, freshly re-verified.
    monkeypatch.setattr("imagin.brand.entity_resolution._is_public_host", lambda host: True)
    from imagin.object_store import LocalObjectStore
    store = LocalObjectStore(str(tmp_path))
    first = resolve_brand(db_session, "Acme University", "acme.example", _acme_client(), store)

    profile = db_session.get(BrandProfile, first.brand_profile_id)
    from datetime import datetime, timedelta, timezone
    first_verified_at = db_session.scalar(
        select(VerifiedDomain.verified_at).where(
            VerifiedDomain.organization_id == first.organization_id,
            VerifiedDomain.domain == "acme.example",
        )
    )
    profile.created_at = datetime.now(timezone.utc) - timedelta(days=999)
    db_session.commit()

    resolve_brand(db_session, "Acme University", "acme.example", _acme_client(), store)

    domain_rows = db_session.scalars(
        select(VerifiedDomain).where(
            VerifiedDomain.organization_id == first.organization_id,
            VerifiedDomain.domain == "acme.example",
        )
    ).all()
    assert len(domain_rows) == 1
    assert domain_rows[0].verified_at >= first_verified_at


def test_resolve_brand_raises_when_no_candidate_scores_above_exclusion(db_session: Session, tmp_path, monkeypatch):
    monkeypatch.setattr("imagin.brand.entity_resolution._is_public_host", lambda host: True)
    from imagin.object_store import LocalObjectStore
    store = LocalObjectStore(str(tmp_path))

    only_favicon_html = b"""
    <html><head><link rel="icon" href="https://noassets.example/favicon.ico"></head><body></body></html>
    """
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("robots.txt"):
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL, request=request)
        if url == "https://noassets.example/":
            return httpx.Response(200, content=only_favicon_html, headers={"content-type": "text/html"}, request=request)
        return httpx.Response(404, request=request)
    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(NoUsableBrandAssetError):
        resolve_brand(db_session, "No Assets Org", "noassets.example", client, store)
```

Add the shared `db_session` fixture:

```python
# control/tests/conftest.py (append)
import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from imagin.db import Base


def test_database_url() -> str:
    """Derive the *_test database URL from DATABASE_URL.

    NOTE (patched 2026-07-22, third pass): the original draft of this helper
    did `DATABASE_URL.replace("/imagin", "/imagin_test")`. In a real
    docker-compose URL like
    postgresql+psycopg2://imagin:imagin@postgres:5432/imagin, the substring
    "/imagin" occurs TWICE — once inside "://imagin" (the username, because
    "//" + "imagin" contains "/imagin") and once at the end (the actual
    database name). str.replace() with no count silently rewrites both,
    turning the username into "imagin_test" too — a role that doesn't exist
    — which fails with "password authentication failed for user
    'imagin_test'" / "Role 'imagin_test' does not exist". This was caught
    running against a real docker-compose Postgres; the agent's own
    embedded-Postgres sandbox verification used a differently-shaped URL
    that happened not to trigger the double match, so it went undetected
    until then. Fixed by operating structurally on the URL's rightmost path
    segment (the database name) instead of a naive substring replace, so it
    cannot also match anything in the userinfo/host portion.
    """
    url = os.environ["DATABASE_URL"]
    base, sep, query = url.partition("?")
    path, _, _dbname = base.rpartition("/")
    return f"{path}/imagin_test{sep}{query}"


@pytest.fixture()
def db_session():
    database_url = test_database_url()
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)  # test-only convenience; real app uses Alembic (§8.5)
    session = Session(engine)
    yield session
    session.rollback()
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()
    session.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm control pytest tests/test_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'imagin.brand.registry'`

- [ ] **Step 3: Write minimal implementation**

```python
# control/imagin/brand/registry.py
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Organization, VerifiedDomain, SourceSnapshot, BrandProfile, BrandAsset
from ..object_store import LocalObjectStore
from .entity_resolution import resolve_official_domain
from .crawler import RespectfulCrawler
from .extractor import extract_organization_page
from .scoring import score_logo_candidate

FRESHNESS_DAYS = 30


class NoUsableBrandAssetError(RuntimeError):
    pass


@dataclass(frozen=True)
class ResolvedBrand:
    organization_id: uuid.UUID
    brand_profile_id: uuid.UUID
    profile_version: int
    logo_asset_id: uuid.UUID | None
    logo_storage_key: str | None
    logo_sha256: str | None


def _is_fresh(profile: BrandProfile) -> bool:
    return datetime.now(timezone.utc) - profile.created_at < timedelta(days=FRESHNESS_DAYS)


def _latest_profile(session: Session, organization_id: uuid.UUID) -> BrandProfile | None:
    return session.scalar(
        select(BrandProfile)
        .where(BrandProfile.organization_id == organization_id)
        .order_by(BrandProfile.version.desc())
    )


def _to_resolved(session: Session, profile: BrandProfile) -> ResolvedBrand:
    asset = session.scalar(select(BrandAsset).where(BrandAsset.brand_profile_id == profile.id, BrandAsset.type == "logo"))
    return ResolvedBrand(
        organization_id=profile.organization_id,
        brand_profile_id=profile.id,
        profile_version=profile.version,
        logo_asset_id=asset.id if asset else None,
        logo_storage_key=asset.storage_key if asset else None,
        logo_sha256=asset.sha256 if asset else None,
    )


def _upsert_verified_domain(session: Session, organization_id: uuid.UUID, domain: str) -> VerifiedDomain:
    # NOTE (patched 2026-07-22): the original draft unconditionally INSERTed
    # a VerifiedDomain row here every time resolve_brand() re-crawled, which
    # violates the (organization_id, domain) unique constraint on the second
    # resolution of the same org+domain (see test_resolve_brand_never_
    # overwrites_prior_version_row, which forces a second resolve). Refreshing
    # a brand must not duplicate the domain-verification row — instead we
    # update the existing record in place. This is metadata about *when we
    # last verified the domain*, not an immutable versioned artifact, so it
    # is exempt from the "never overwrite approved bytes" rule (PROD.md
    # §7.1a/§8.1 governs BrandProfile/BrandAsset rows, not this liveness check).
    existing = session.scalar(
        select(VerifiedDomain).where(
            VerifiedDomain.organization_id == organization_id,
            VerifiedDomain.domain == domain,
        )
    )
    if existing is not None:
        existing.status = "verified"
        existing.verification_method = "configured_official_domain"
        existing.verified_at = datetime.now(timezone.utc)
        return existing

    verified_domain = VerifiedDomain(
        organization_id=organization_id, domain=domain,
        verification_method="configured_official_domain", status="verified",
    )
    session.add(verified_domain)
    return verified_domain


def resolve_brand(
    session: Session,
    org_name: str,
    official_domain: str,
    http_client,
    object_store: LocalObjectStore,
) -> ResolvedBrand:
    org = session.scalar(select(Organization).where(Organization.canonical_name == org_name))
    if org is not None:
        latest = _latest_profile(session, org.id)
        if latest is not None and latest.status in ("verified", "provisional") and _is_fresh(latest):
            return _to_resolved(session, latest)
    else:
        org = Organization(canonical_name=org_name, status="active")
        session.add(org)
        session.flush()

    _upsert_verified_domain(session, org.id, official_domain)

    resolved_domain = resolve_official_domain(official_domain, http_client)
    crawler = RespectfulCrawler(http_client)
    base_url = f"https://{official_domain}"
    page = crawler.fetch(resolved_domain.canonical_url, base_url)

    snapshot = SourceSnapshot(
        url=page.url, domain=official_domain, http_status=page.status_code,
        content_type=page.content_type,
        content_sha256=object_store.put(page.body, suffix=".html").sha256,
    )
    session.add(snapshot)
    session.flush()

    extraction = extract_organization_page(page.body, page.url)
    best_asset: BrandAsset | None = None
    best_score = -1000
    for candidate in extraction.logo_candidates:
        scored = score_logo_candidate(candidate.evidence, candidate.is_svg, candidate.filename_hint)
        if scored.status == "excluded":
            continue
        if scored.score > best_score:
            fetched_logo = crawler.fetch(candidate.url, base_url)
            stored = object_store.put(fetched_logo.body)
            best_score = scored.score
            best_asset = BrandAsset(
                type="logo", status=scored.status, storage_key=stored.storage_key,
                sha256=stored.sha256, score=scored.score, source_snapshot_id=snapshot.id,
            )

    next_version = (_latest_profile(session, org.id).version if _latest_profile(session, org.id) else 0) + 1
    profile_status = "verified" if best_asset and best_asset.status == "auto_accepted" else "provisional"
    profile = BrandProfile(
        organization_id=org.id, version=next_version, status=profile_status,
        profile={"organizationName": extraction.organization_name or org_name, "officialDomain": official_domain},
    )
    session.add(profile)
    session.flush()

    if best_asset is not None:
        best_asset.brand_profile_id = profile.id
        session.add(best_asset)
    session.commit()

    if best_asset is None:
        raise NoUsableBrandAssetError(
            f"no logo candidate scored >= 60 for '{org_name}'; "
            "generation must omit the logo or request a manually uploaded asset (PROD.md §7.1a)"
        )

    return ResolvedBrand(
        organization_id=org.id, brand_profile_id=profile.id, profile_version=profile.version,
        logo_asset_id=best_asset.id, logo_storage_key=best_asset.storage_key, logo_sha256=best_asset.sha256,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose run --rm control pytest tests/test_registry.py -v`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add control/imagin/brand/registry.py control/tests/test_registry.py control/tests/conftest.py
git commit -m "feat: implement cache-first brand registry resolution (ADR-001)"
```

---

### Task 9: Poster Design Spec (hardcoded copy fixture, per OKF §9.1 Week 4 deferral of research automation)

**Files:**
- Create: `control/imagin/design_spec.py`
- Create: `control/tests/test_design_spec.py`

**Interfaces:**
- Produces: `imagin.design_spec.PosterCopy(headline, body, cta)`, `DesignSpec(mode, width, height, template_id, copy, qr_target_url, negative_prompt, brand_profile_id, brand_asset_id)`, `build_poster_design_spec(prompt, brand_profile_id, brand_asset_id, qr_target_url) -> DesignSpec`. Task 12 (`compositor.py`) and Task 14 (`pipeline.py`) consume `DesignSpec`.

> **Patch 2026-07-22:** `qr_target_url` is now a **required** caller-supplied argument, not a value this module invents. The original draft hardcoded `"https://www.utcc.ac.th/openhouse"` — a guessed path nobody had verified actually exists on the real UTCC site. A QR destination is operational config, not brand copy, and PROD.md §7.4 additionally requires the destination be validated *fresh*, immediately before the artifact is finalized — this function has no business fabricating that value. Tasks 10–15 (which would call this with a real value) remain blocked until a real, verified QR target exists; nothing here invents one to unblock them.

- [ ] **Step 1: Write the failing test**

```python
# control/tests/test_design_spec.py
import pytest
from imagin.design_spec import build_poster_design_spec


def test_build_poster_design_spec_has_required_poster_fields():
    spec = build_poster_design_spec(
        prompt="ทำโปสเตอร์โปรโมต UTCC สำหรับนักเรียน ม.ปลาย",
        brand_profile_id="11111111-1111-1111-1111-111111111111",
        brand_asset_id="22222222-2222-2222-2222-222222222222",
        qr_target_url="https://example.ac.th/verified-by-caller",
    )

    assert spec.mode == "poster"
    assert spec.width == 1080 and spec.height == 1350
    assert spec.copy.headline
    assert len(spec.copy.body) >= 1
    assert spec.copy.cta
    # The QR target is passed through verbatim from the caller, never invented here.
    assert spec.qr_target_url == "https://example.ac.th/verified-by-caller"
    assert set(spec.negative_prompt) >= {"text", "logo", "qr code"}


def test_build_poster_design_spec_rejects_empty_qr_target_url():
    with pytest.raises(ValueError):
        build_poster_design_spec(
            prompt="ทำโปสเตอร์โปรโมต UTCC สำหรับนักเรียน ม.ปลาย",
            brand_profile_id="11111111-1111-1111-1111-111111111111",
            brand_asset_id="22222222-2222-2222-2222-222222222222",
            qr_target_url="",
        )


def test_build_poster_design_spec_requires_caller_to_supply_qr_target_url():
    with pytest.raises(TypeError):
        build_poster_design_spec(
            prompt="ทำโปสเตอร์โปรโมต UTCC สำหรับนักเรียน ม.ปลาย",
            brand_profile_id="11111111-1111-1111-1111-111111111111",
            brand_asset_id="22222222-2222-2222-2222-222222222222",
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm control pytest tests/test_design_spec.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'imagin.design_spec'`

- [ ] **Step 3: Write minimal implementation**

```python
# control/imagin/design_spec.py
from dataclasses import dataclass

POSTER_WIDTH = 1080
POSTER_HEIGHT = 1350
TEMPLATE_ID = "centered_editorial"


@dataclass(frozen=True)
class PosterCopy:
    headline: str
    body: list[str]
    cta: str


@dataclass(frozen=True)
class DesignSpec:
    mode: str
    width: int
    height: int
    template_id: str
    copy: PosterCopy
    qr_target_url: str
    negative_prompt: list[str]
    brand_profile_id: str
    brand_asset_id: str


def build_poster_design_spec(prompt: str, brand_profile_id: str, brand_asset_id: str, qr_target_url: str) -> DesignSpec:
    # Research automation is PROD-phase scope (PROD.md §6.4, FR-013); Week 1 uses a
    # hardcoded verified copy fixture for this one known prompt, per OKF §9.1 Week 1/4.
    #
    # qr_target_url is deliberately a REQUIRED caller-supplied argument, not a
    # default baked in here (patched 2026-07-22; see ADR-001 patch notes). A
    # QR destination is operational config, not brand copy — inventing one
    # (e.g. guessing "/openhouse" exists on utcc.ac.th) would risk printing a
    # poster with a broken or misleading link. PROD.md §7.4 additionally
    # requires the destination be validated *fresh*, immediately before the
    # artifact is finalized — this function has no business fabricating
    # that value, only accepting one the caller already verified.
    if not qr_target_url:
        raise ValueError(
            "qr_target_url must be supplied by the caller from a verified source; "
            "it must never be fabricated or guessed (PROD.md §7.4)"
        )

    copy = PosterCopy(
        headline="เปิดบ้าน UTCC",
        body=[
            "มหาวิทยาลัยหอการค้าไทย เปิดรับสมัครนักเรียนมัธยมปลาย",
            "ร่วมค้นหาเส้นทางสู่มหาวิทยาลัยในฝันของคุณ",
        ],
        cta="สมัครวันนี้",
    )
    return DesignSpec(
        mode="poster",
        width=POSTER_WIDTH,
        height=POSTER_HEIGHT,
        template_id=TEMPLATE_ID,
        copy=copy,
        qr_target_url=qr_target_url,
        negative_prompt=["text", "logo", "watermark", "qr code"],
        brand_profile_id=brand_profile_id,
        brand_asset_id=brand_asset_id,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose run --rm control pytest tests/test_design_spec.py -v`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add control/imagin/design_spec.py control/tests/test_design_spec.py
git commit -m "feat: add hardcoded poster design spec fixture for the Week 1 prompt"
```

---

### Task 10: ComfyUI client (real Qwen-Image integration against workflow JSON) — **implemented, mocked-integration-verified**

> **Patch 2026-07-22 — explicit node-mapping contract replaces graph-shape inference:** the original draft's `patch_qwen_image_workflow` located the graph's `KSampler` node by `class_type` and then *followed its `positive`/`latent_image` input links* to guess which nodes held the prompt text and width/height. This is fragile in a way that fails silently: it assumes exactly one `KSampler`, assumes `positive`/`latent_image` are direct single-hop links (not passed through a reroute/switch node, which Qwen-Image ComfyUI graphs commonly use), and if the real exported graph doesn't match that shape it will patch the *wrong node* rather than raising — producing a poster generated from stale placeholder text with no error. Given this plan's own rule that "the ComfyUI workflow JSON is user-supplied and version-controlled at a fixed path, not silently regenerated," the node mapping deserves the same treatment: an explicit, version-controlled, human-reviewed contract, not a runtime guess. The fix below requires a small sidecar `qwen_image_txt2img.nodemap.json` naming the exact node IDs and input keys to patch, validated eagerly (`UnknownWorkflowNodeError` if a mapped node/key doesn't exist in the workflow) instead of inferred.
>
> **Status (2026-07-22, second pass):** implemented and tested against an explicit `SAMPLE_WORKFLOW` + `SAMPLE_NODE_MAP` fixture pair and mocked `/prompt`, `/history`, `/view` responses — this task has no native/system dependency at all (pure Python + `httpx`), so it is fully verified: `5 passed`. The real `qwen_image_txt2img.json` export and its hand-written `qwen_image_txt2img.nodemap.json` (naming actual node IDs) are still Task 15's job, not this one's — this task's own tests intentionally never touch either placeholder file.

**Files:**
- Create: `control/imagin/comfyui_client.py`
- Create: `control/tests/test_comfyui_client.py`
- Create: `control/workflows/qwen_image_txt2img.json` (placeholder — **you replace this with your real ComfyUI "Save (API Format)" export before running the Task 15 smoke test**)
- Create: `control/workflows/qwen_image_txt2img.nodemap.json` (placeholder — **you write this by hand once you have the real workflow, naming its actual node IDs; see contract below**)

**Interfaces:**
- Produces: `imagin.comfyui_client.ComfyUiError`, `ComfyUiTimeoutError`, `UnknownWorkflowNodeError`, `WorkflowNodeMap(prompt_node_id, prompt_input_key, seed_node_id, seed_input_key, width_node_id, width_input_key, height_node_id, height_input_key)`, `patch_qwen_image_workflow(workflow, node_map, prompt_text, seed, width, height) -> dict`, `ComfyUiClient(base_url, client=None)` with `.submit`, `.wait_for_completion`, `.fetch_output_image`, `.generate_image`. Task 14 (`pipeline.py`) calls `ComfyUiClient.generate_image`, now also passing a `WorkflowNodeMap`.

The client no longer infers graph shape. It patches exactly the node IDs and input keys named in an explicit `WorkflowNodeMap` — supplied alongside the workflow JSON, at a fixed version-controlled path — and raises `UnknownWorkflowNodeError` immediately if any mapped node ID or input key is absent from the workflow, rather than silently patching nothing or the wrong node.

- [ ] **Step 1: Write the failing test**

```python
# control/tests/test_comfyui_client.py
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

# This mapping is hand-written against SAMPLE_WORKFLOW's actual node IDs — the
# same discipline required of the real qwen_image_txt2img.nodemap.json once
# the real workflow export exists (Task 10 remains blocked until then).
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm control pytest tests/test_comfyui_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'imagin.comfyui_client'`

- [ ] **Step 3: Write minimal implementation**

```python
# control/imagin/comfyui_client.py
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
    keys to patch in a specific ComfyUI workflow export. Patched 2026-07-22:
    replaces the original draft's approach of inferring this by walking
    class_type/link structure, which silently patched the wrong node (or
    nothing) for any graph shaped differently than the one sample workflow —
    see the Task 10 patch note above. One of these must be hand-written
    against the real qwen_image_txt2img.json once it exists; it is never
    inferred from workflow structure.
    """
    prompt_node_id: str
    prompt_input_key: str
    seed_node_id: str
    seed_input_key: str
    width_node_id: str
    width_input_key: str
    height_node_id: str
    height_input_key: str


def _validate_and_set(workflow: dict, node_id: str, input_key: str, value) -> None:
    node = workflow.get(node_id)
    if node is None:
        raise UnknownWorkflowNodeError(f"node_map references node id {node_id!r}, which does not exist in this workflow")
    if input_key not in node.get("inputs", {}):
        raise UnknownWorkflowNodeError(f"node_map references input key {input_key!r} on node {node_id!r}, which that node does not have")
    node["inputs"][input_key] = value


def patch_qwen_image_workflow(workflow: dict, node_map: WorkflowNodeMap, prompt_text: str, seed: int, width: int, height: int) -> dict:
    patched = {node_id: {**node, "inputs": dict(node["inputs"])} for node_id, node in workflow.items()}

    _validate_and_set(patched, node_map.prompt_node_id, node_map.prompt_input_key, prompt_text)
    _validate_and_set(patched, node_map.seed_node_id, node_map.seed_input_key, seed)
    _validate_and_set(patched, node_map.width_node_id, node_map.width_input_key, width)
    _validate_and_set(patched, node_map.height_node_id, node_map.height_input_key, height)

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

    def generate_image(self, workflow: dict, node_map: WorkflowNodeMap, prompt_text: str, seed: int, width: int, height: int) -> bytes:
        patched = patch_qwen_image_workflow(workflow, node_map, prompt_text, seed, width, height)
        prompt_id = self.submit(patched)
        history_entry = self.wait_for_completion(prompt_id)
        return self.fetch_output_image(history_entry)
```

```json
// control/workflows/qwen_image_txt2img.json
// PLACEHOLDER: you confirmed (2026-07-22) this workflow does not exist yet.
// Before running Task 15's live smoke test:
//   1. Open ComfyUI's web UI against your DGX endpoint (http://localhost:8188).
//   2. Build (or load) a Qwen-Image txt2img graph: checkpoint/model loader ->
//      CLIPTextEncode (positive) + CLIPTextEncode (negative) -> EmptyLatentImage
//      -> KSampler -> VAEDecode -> SaveImage.
//   3. Enable Dev Mode in ComfyUI settings, then use "Save (API Format)" (not the
//      regular "Save") to export the graph JSON.
//   4. Replace this file's contents with that export.
//   5. Hand-write control/workflows/qwen_image_txt2img.nodemap.json (see the
//      sibling placeholder) naming that export's actual node IDs — do not
//      guess; open the exported JSON and read the real IDs.
{}
```

```json
// control/workflows/qwen_image_txt2img.nodemap.json
// PLACEHOLDER — added 2026-07-22 alongside the node-mapping contract patch.
// Once the real qwen_image_txt2img.json exists (see sibling placeholder),
// open it and fill in the ACTUAL node IDs for your graph below. Do not copy
// the sample IDs from test_comfyui_client.py — those belong to a fixture
// workflow, not your real export, and will raise UnknownWorkflowNodeError
// if used against the real one.
{
  "prompt_node_id": "REPLACE_WITH_REAL_CLIPTextEncode_POSITIVE_NODE_ID",
  "prompt_input_key": "text",
  "seed_node_id": "REPLACE_WITH_REAL_KSampler_NODE_ID",
  "seed_input_key": "seed",
  "width_node_id": "REPLACE_WITH_REAL_EmptyLatentImage_NODE_ID",
  "width_input_key": "width",
  "height_node_id": "REPLACE_WITH_REAL_EmptyLatentImage_NODE_ID",
  "height_input_key": "height"
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose run --rm control pytest tests/test_comfyui_client.py -v`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add control/imagin/comfyui_client.py control/workflows/qwen_image_txt2img.json control/workflows/qwen_image_txt2img.nodemap.json control/tests/test_comfyui_client.py
git commit -m "feat: add ComfyUI client with an explicit workflow node-mapping contract for Qwen-Image"
```

---

### Task 11: QR generation and fresh-decode validation — **implemented, encode logic sanity-checked; `pyzbar` needs the real image**

> **Status (2026-07-22, second pass):** `generate_qr_png`/`decode_qr_png`/`validate_qr` are implemented exactly as below (`qrcode` + `pyzbar`, matching requirements.txt). `pyzbar` requires a real `libzbar.so` at runtime (installed via `libzbar0` in the Dockerfile) which isn't obtainable without root/apt in this sandbox — importing `imagin.qr_gen` there raises `ImportError: Unable to find zbar shared library`, confirming this is exactly the missing-native-dependency case Task 0 exists to catch, not a logic bug. As an independent sanity check (not part of the committed suite), the `qrcode.make()` output was round-tripped through a different, wheel-bundled decoder (`zxing-cpp`) and correctly decoded back to the original URL — confirming the *encode* half of this module is correct. The committed `test_qr_gen.py` below still uses `pyzbar` per the plan's tech stack and must be run inside the real Docker image to get genuine pass/fail evidence for the decode half.

**Files:**
- Create: `control/imagin/qr_gen.py`
- Create: `control/tests/test_qr_gen.py`

**Interfaces:**
- Produces: `imagin.qr_gen.generate_qr_png(target_url: str) -> bytes`, `decode_qr_png(png_bytes: bytes) -> list[str]`, `validate_qr(png_bytes: bytes, expected_url: str) -> bool`. Task 12 (`compositor.py`) uses `generate_qr_png`; Task 13 (`qa/qr_check.py`) uses `validate_qr`.

- [ ] **Step 1: Write the failing test**

```python
# control/tests/test_qr_gen.py
from imagin.qr_gen import generate_qr_png, validate_qr


def test_generate_qr_png_round_trips_through_validate_qr():
    url = "https://www.utcc.ac.th/openhouse"

    png_bytes = generate_qr_png(url)

    assert validate_qr(png_bytes, url) is True


def test_validate_qr_rejects_mismatched_url():
    png_bytes = generate_qr_png("https://www.utcc.ac.th/openhouse")

    assert validate_qr(png_bytes, "https://www.utcc.ac.th/wrong-path") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm control pytest tests/test_qr_gen.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'imagin.qr_gen'`

- [ ] **Step 3: Write minimal implementation**

```python
# control/imagin/qr_gen.py
import io

import qrcode
from PIL import Image
from pyzbar.pyzbar import decode as zbar_decode


def generate_qr_png(target_url: str) -> bytes:
    image = qrcode.make(target_url)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def decode_qr_png(png_bytes: bytes) -> list[str]:
    image = Image.open(io.BytesIO(png_bytes))
    return [result.data.decode("utf-8") for result in zbar_decode(image)]


def validate_qr(png_bytes: bytes, expected_url: str) -> bool:
    return expected_url in decode_qr_png(png_bytes)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose run --rm control pytest tests/test_qr_gen.py -v`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add control/imagin/qr_gen.py control/tests/test_qr_gen.py
git commit -m "feat: add QR generation and decode validation"
```

---

### Task 12: Deterministic compositor (Pango/HarfBuzz/Cairo text, logo, QR) — **implemented, requires Docker to execute**

> **Status (2026-07-22, second pass):** `compose_poster`/`TextOverflowError` are implemented exactly as below. `import gi` fails with `ModuleNotFoundError: No module named 'gi'` in this sandbox (PyGObject needs `girepository-2.0` dev headers to build, unavailable without root/apt) — confirmed to be exactly that missing dependency, not a logic error, by reproducing the failure directly. This module's tests (below) genuinely require the real Docker image; there is no meaningful sandbox-level substitute for real Pango/HarfBuzz text shaping, so none was attempted.

**Files:**
- Create: `control/imagin/compositor.py`
- Create: `control/tests/test_compositor.py`

**Interfaces:**
- Consumes: hero PNG bytes, `DesignSpec.copy` fields, logo PNG/SVG bytes rasterized upstream, QR PNG bytes from `imagin.qr_gen.generate_qr_png`.
- Produces: `imagin.compositor.TextOverflowError`, `compose_poster(hero_png, headline, body_lines, cta, logo_png, qr_png, width, height) -> bytes`. Task 14 (`pipeline.py`) calls `compose_poster`.

- [ ] **Step 1: Write the failing test**

```python
# control/tests/test_compositor.py
import io
import cairo
import pytest
from PIL import Image

from imagin.compositor import compose_poster, TextOverflowError


def _solid_png(width: int, height: int, rgb=(120, 140, 160)) -> bytes:
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(*(c / 255 for c in rgb))
    ctx.paint()
    buffer = io.BytesIO()
    surface.write_to_png(buffer)
    return buffer.getvalue()


def test_compose_poster_produces_png_of_requested_size():
    hero = _solid_png(1080, 1350)
    logo = _solid_png(200, 200, rgb=(255, 255, 255))
    from imagin.qr_gen import generate_qr_png
    qr = generate_qr_png("https://www.utcc.ac.th/openhouse")

    result = compose_poster(
        hero_png=hero, headline="เปิดบ้าน UTCC",
        body_lines=["มหาวิทยาลัยหอการค้าไทย เปิดรับสมัครนักเรียนมัธยมปลาย"],
        cta="สมัครวันนี้", logo_png=logo, qr_png=qr, width=1080, height=1350,
    )

    image = Image.open(io.BytesIO(result))
    assert image.size == (1080, 1350)
    assert image.format == "PNG"


def test_compose_poster_raises_on_headline_overflow():
    hero = _solid_png(1080, 1350)
    logo = _solid_png(200, 200)
    from imagin.qr_gen import generate_qr_png
    qr = generate_qr_png("https://www.utcc.ac.th/openhouse")

    absurdly_long_headline = "เปิดบ้าน UTCC " * 200

    with pytest.raises(TextOverflowError):
        compose_poster(
            hero_png=hero, headline=absurdly_long_headline, body_lines=["x"],
            cta="สมัครวันนี้", logo_png=logo, qr_png=qr, width=1080, height=1350,
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm control pytest tests/test_compositor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'imagin.compositor'`

- [ ] **Step 3: Write minimal implementation**

```python
# control/imagin/compositor.py
import io

import cairo
import gi

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Pango, PangoCairo  # noqa: E402

FONT_HEADLINE = "Noto Sans Thai Bold 48"
FONT_BODY = "Noto Sans Thai 24"
MARGIN = 64
LOGO_SIZE = 120
QR_SIZE = 140


class TextOverflowError(RuntimeError):
    pass


def _draw_text(ctx: cairo.Context, text: str, font_desc: str, x: int, y: int, max_width: int, max_height: int) -> int:
    layout = PangoCairo.create_layout(ctx)
    layout.set_font_description(Pango.FontDescription(font_desc))
    layout.set_width(max_width * Pango.SCALE)
    layout.set_wrap(Pango.WrapMode.WORD_CHAR)
    layout.set_text(text, -1)
    _ink_rect, logical_rect = layout.get_pixel_extents()

    if logical_rect.height > max_height:
        raise TextOverflowError(
            f"text '{text[:30]}...' is {logical_rect.height}px tall, exceeds region height {max_height}px"
        )

    ctx.save()
    ctx.translate(x, y)
    PangoCairo.show_layout(ctx, layout)
    ctx.restore()
    return logical_rect.height


def _paint_scaled_image(ctx: cairo.Context, png_bytes: bytes, x: int, y: int, target_size: int) -> None:
    source_surface = cairo.ImageSurface.create_from_png(io.BytesIO(png_bytes))
    ctx.save()
    ctx.translate(x, y)
    ctx.scale(target_size / source_surface.get_width(), target_size / source_surface.get_height())
    ctx.set_source_surface(source_surface, 0, 0)
    ctx.paint()
    ctx.restore()


def compose_poster(
    hero_png: bytes,
    headline: str,
    body_lines: list[str],
    cta: str,
    logo_png: bytes,
    qr_png: bytes,
    width: int,
    height: int,
) -> bytes:
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    ctx = cairo.Context(surface)

    hero_surface = cairo.ImageSurface.create_from_png(io.BytesIO(hero_png))
    ctx.save()
    ctx.scale(width / hero_surface.get_width(), height / hero_surface.get_height())
    ctx.set_source_surface(hero_surface, 0, 0)
    ctx.paint()
    ctx.restore()

    y = height - 420
    y += _draw_text(ctx, headline, FONT_HEADLINE, MARGIN, y, width - 2 * MARGIN, 160) + 16
    y += _draw_text(ctx, "\n".join(body_lines), FONT_BODY, MARGIN, y, width - 2 * MARGIN, 140) + 16
    _draw_text(ctx, cta, FONT_BODY, MARGIN, y, width - 2 * MARGIN, 40)

    _paint_scaled_image(ctx, logo_png, MARGIN, MARGIN, LOGO_SIZE)
    _paint_scaled_image(ctx, qr_png, width - MARGIN - QR_SIZE, height - MARGIN - QR_SIZE, QR_SIZE)

    buffer = io.BytesIO()
    surface.write_to_png(buffer)
    return buffer.getvalue()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose run --rm control pytest tests/test_compositor.py -v`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add control/imagin/compositor.py control/tests/test_compositor.py
git commit -m "feat: add deterministic Pango/Cairo compositor with hard overflow gate"
```

---

### Task 13: QA gates (OCR exact-match, QR, logo provenance) and report — **implemented; logo/report logic verified directly, OCR/QR need Docker**

> **Status (2026-07-22, second pass):** `check_logo_provenance` and `build_qa_report` have no native dependency and were verified directly (`5/5` assertions passing when exercised outside the pytest collection path, since collecting the full `test_qa_report.py` module also imports `imagin.qr_gen`, which fails to import for the same `pyzbar`/libzbar reason as Task 11). `check_qr` is a thin wrapper over `validate_qr` (Task 11) and inherits that same, already-diagnosed blocker. `check_exact_text_match` (OCR) requires `paddleocr`/`paddlepaddle`, which are large C++-backed wheels not installed in this sandbox — genuinely untested here, code-complete only.

**Files:**
- Create: `control/imagin/qa/__init__.py`
- Create: `control/imagin/qa/ocr_check.py`
- Create: `control/imagin/qa/qr_check.py`
- Create: `control/imagin/qa/logo_check.py`
- Create: `control/imagin/qa/report.py`
- Create: `control/tests/test_qa_ocr.py`
- Create: `control/tests/test_qa_report.py`

**Interfaces:**
- Consumes: `imagin.qr_gen.{generate_qr_png, validate_qr}`, `imagin.compositor.compose_poster`.
- Produces: `imagin.qa.ocr_check.check_exact_text_match(png_bytes, expected_lines) -> bool`; `imagin.qa.qr_check.check_qr(png_bytes, expected_url) -> bool` (thin wrapper over `validate_qr`, called fresh, never cached, per §7.4); `imagin.qa.logo_check.check_logo_provenance(used_asset_sha256, approved_asset_sha256) -> bool`; `imagin.qa.report.QaCheck(name, passed, detail)`, `QaReport(overall_status, checks)`, `build_qa_report(checks: list[QaCheck]) -> QaReport`. Task 14 (`pipeline.py`) assembles these into the final report.

- [ ] **Step 1: Write the failing test**

```python
# control/tests/test_qa_report.py
from imagin.qa.report import QaCheck, build_qa_report
from imagin.qa.logo_check import check_logo_provenance
from imagin.qa.qr_check import check_qr
from imagin.qr_gen import generate_qr_png


def test_check_logo_provenance_true_only_on_exact_sha256_match():
    assert check_logo_provenance("abc123", "abc123") is True
    assert check_logo_provenance("abc123", "different") is False


def test_check_qr_validates_fresh_against_expected_url():
    png = generate_qr_png("https://www.utcc.ac.th/openhouse")

    assert check_qr(png, "https://www.utcc.ac.th/openhouse") is True
    assert check_qr(png, "https://www.utcc.ac.th/wrong") is False


def test_build_qa_report_fails_overall_on_any_hard_gate_failure():
    checks = [
        QaCheck(name="ocr_exact_match", passed=False, detail="mismatch"),
        QaCheck(name="qr_decode_match", passed=True, detail="ok"),
        QaCheck(name="logo_provenance_match", passed=True, detail="ok"),
        QaCheck(name="no_text_overflow", passed=True, detail="ok"),
    ]

    report = build_qa_report(checks)

    assert report.overall_status == "fail"


def test_build_qa_report_passes_when_all_checks_pass():
    checks = [QaCheck(name="ocr_exact_match", passed=True, detail="ok")]

    report = build_qa_report(checks)

    assert report.overall_status == "pass"
```

```python
# control/tests/test_qa_ocr.py
import cairo
import io
import gi
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Pango, PangoCairo

from imagin.qa.ocr_check import check_exact_text_match


def _render_text_image(text: str) -> bytes:
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 800, 200)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(1, 1, 1)
    ctx.paint()
    ctx.set_source_rgb(0, 0, 0)
    layout = PangoCairo.create_layout(ctx)
    layout.set_font_description(Pango.FontDescription("Noto Sans Thai 40"))
    layout.set_text(text, -1)
    ctx.translate(20, 60)
    PangoCairo.show_layout(ctx, layout)
    buffer = io.BytesIO()
    surface.write_to_png(buffer)
    return buffer.getvalue()


def test_check_exact_text_match_true_for_rendered_expected_text():
    image_bytes = _render_text_image("เปิดบ้าน UTCC")

    assert check_exact_text_match(image_bytes, ["เปิดบ้าน UTCC"]) is True


def test_check_exact_text_match_false_when_text_differs():
    image_bytes = _render_text_image("เปิดบ้าน UTCC")

    assert check_exact_text_match(image_bytes, ["ข้อความที่ไม่ตรงกันเลย"]) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm control pytest tests/test_qa_ocr.py tests/test_qa_report.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'imagin.qa'`

- [ ] **Step 3: Write minimal implementation**

```python
# control/imagin/qa/__init__.py
```

```python
# control/imagin/qa/ocr_check.py
import io

import numpy as np
from PIL import Image
from paddleocr import PaddleOCR

_engine: PaddleOCR | None = None


def _get_engine() -> PaddleOCR:
    global _engine
    if _engine is None:
        _engine = PaddleOCR(use_angle_cls=False, lang="th", show_log=False)
    return _engine


def extract_text(png_bytes: bytes) -> str:
    image = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    result = _get_engine().ocr(np.array(image), cls=False)
    lines = [line[1][0] for block in (result or []) for line in block]
    return "\n".join(lines)


def _normalize(text: str) -> str:
    return text.replace(" ", "").replace("\n", "")


def check_exact_text_match(png_bytes: bytes, expected_lines: list[str]) -> bool:
    extracted = _normalize(extract_text(png_bytes))
    return all(_normalize(line) in extracted for line in expected_lines)
```

```python
# control/imagin/qa/qr_check.py
from ..qr_gen import validate_qr


def check_qr(png_bytes: bytes, expected_url: str) -> bool:
    # Always re-decoded fresh against the expected target; never cached (PROD.md §7.4).
    return validate_qr(png_bytes, expected_url)
```

```python
# control/imagin/qa/logo_check.py
def check_logo_provenance(used_asset_sha256: str, approved_asset_sha256: str) -> bool:
    return used_asset_sha256 == approved_asset_sha256
```

```python
# control/imagin/qa/report.py
from dataclasses import dataclass

HARD_GATE_NAMES = {"ocr_exact_match", "qr_decode_match", "logo_provenance_match", "no_text_overflow"}


@dataclass(frozen=True)
class QaCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class QaReport:
    overall_status: str  # pass | warn | fail
    checks: list[QaCheck]


def build_qa_report(checks: list[QaCheck]) -> QaReport:
    failed_hard_gates = [c for c in checks if not c.passed and c.name in HARD_GATE_NAMES]
    if failed_hard_gates:
        overall = "fail"
    elif all(c.passed for c in checks):
        overall = "pass"
    else:
        overall = "warn"
    return QaReport(overall_status=overall, checks=checks)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose run --rm control pytest tests/test_qa_ocr.py tests/test_qa_report.py -v`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add control/imagin/qa control/tests/test_qa_ocr.py control/tests/test_qa_report.py
git commit -m "feat: add OCR/QR/logo QA hard gates and aggregate QA report"
```

---

### Task 14: Full pipeline orchestration (integration test against Acme fixture) — **implemented, requires Docker to execute**

> **Patch 2026-07-22 — two fixes:** (1) the original draft's `logo_provenance_match` check called `check_logo_provenance(approved_asset_sha256, approved_asset_sha256)` — comparing the registry's approved hash against *itself*. That can never fail, so the check verified nothing; the whole point of a provenance gate is to confirm the bytes actually composited into the poster match what the registry approved. It now hashes the `logo_png` bytes actually read from object storage and passed into `compose_poster`, and compares that against the registry's `logo_sha256`. A regression test (`test_run_poster_generation_logo_provenance_check_actually_verifies_bytes`) tampers with the stored logo bytes after resolution and asserts the check now genuinely fails — the old tautological version was structurally incapable of failing this way. (2) `run_poster_generation` now also takes a `node_map: WorkflowNodeMap` (Task 10's contract) and a `qr_target_url` (Task 9's no-longer-fabricated argument) — both required, both the caller's responsibility to supply from real, verified sources.
>
> **Status (2026-07-22, second pass):** implemented against the fictional Acme fixture + mocked ComfyUI `/prompt`/`/history`/`/view` responses, same as before — this was never blocked on the real DGX. It *is* blocked on Task 12's compositor, which needs the real Docker image (`import gi` fails here for the reason described in Task 12) — confirmed by reproducing that exact, expected `ModuleNotFoundError` when importing `imagin.pipeline` in this sandbox. Nothing about the pipeline's own wiring/logic is in question; only its two native-dependent building blocks (compositor, OCR) need the real container.

**Files:**
- Create: `control/imagin/pipeline.py`
- Create: `control/tests/test_pipeline_integration.py`

**Interfaces:**
- Consumes: everything from Tasks 2–13.
- Produces: `imagin.pipeline.PipelineResult(poster_png_storage_key, qa_report)`, `run_poster_generation(session, object_store, http_client, comfyui_client, workflow, node_map, prompt, org_name, official_domain, qr_target_url, seed=0) -> PipelineResult`. Task 15 (`cli.py`) calls `run_poster_generation` with the real Postgres session, object store, `httpx.Client()`, the real DGX `ComfyUiClient`, and a real `WorkflowNodeMap`/`qr_target_url`.

- [ ] **Step 1: Write the failing test**

```python
# control/tests/test_pipeline_integration.py
import httpx
from sqlalchemy.orm import Session

from imagin.pipeline import run_poster_generation
from imagin.object_store import LocalObjectStore
from imagin.comfyui_client import ComfyUiClient, WorkflowNodeMap
from tests.fixtures.acme_pages import ACME_HOME_PAGE_HTML

ROBOTS_ALLOW_ALL = "User-agent: *\nAllow: /\n"

SAMPLE_WORKFLOW = {
    "3": {"class_type": "KSampler", "inputs": {"seed": 0, "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}},
    "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "placeholder positive"}},
    "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "placeholder negative"}},
    "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0]}},
}

SAMPLE_NODE_MAP = WorkflowNodeMap(
    prompt_node_id="6", prompt_input_key="text",
    seed_node_id="3", seed_input_key="seed",
    width_node_id="5", width_input_key="width",
    height_node_id="5", height_input_key="height",
)


def _solid_argb32_png(width: int, height: int) -> bytes:
    import cairo, io
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(0.4, 0.5, 0.6)
    ctx.paint()
    buffer = io.BytesIO()
    surface.write_to_png(buffer)
    return buffer.getvalue()


def _combined_client(hero_png: bytes) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("robots.txt"):
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL, request=request)
        if url == "https://acme.example/":
            return httpx.Response(200, content=ACME_HOME_PAGE_HTML, headers={"content-type": "text/html"}, request=request)
        if url == "https://acme.example/brand/logo.svg":
            return httpx.Response(200, content=hero_png, headers={"content-type": "image/svg+xml"}, request=request)  # reuse a valid raster as stand-in logo bytes
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "abc123"}, request=request)
        if request.url.path == "/history/abc123":
            return httpx.Response(200, json={"abc123": {"outputs": {"9": {"images": [{"filename": "out.png", "subfolder": "", "type": "output"}]}}}}, request=request)
        if request.url.path == "/view":
            return httpx.Response(200, content=hero_png, request=request)
        return httpx.Response(404, request=request)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_run_poster_generation_produces_passing_qa_report_end_to_end(db_session: Session, tmp_path, monkeypatch):
    monkeypatch.setattr("imagin.brand.entity_resolution._is_public_host", lambda host: True)
    hero_png = _solid_argb32_png(1080, 1350)
    client = _combined_client(hero_png)
    object_store = LocalObjectStore(str(tmp_path))
    comfyui_client = ComfyUiClient("http://dgx:8188", client=client)

    result = run_poster_generation(
        session=db_session, object_store=object_store, http_client=client,
        comfyui_client=comfyui_client, workflow=SAMPLE_WORKFLOW, node_map=SAMPLE_NODE_MAP,
        prompt="ทำโปสเตอร์โปรโมต Acme สำหรับนักเรียน ม.ปลาย",
        org_name="Acme University", official_domain="acme.example",
        qr_target_url="https://acme.example/verified-test-target", seed=42,
    )

    assert result.qa_report.overall_status in ("pass", "warn")
    assert object_store.get(result.poster_png_storage_key)


def test_run_poster_generation_logo_provenance_check_actually_verifies_bytes(db_session: Session, tmp_path, monkeypatch):
    # Regression test for the fixed tautology: corrupt the stored logo bytes
    # after brand resolution (simulating a wrong storage_key / stale read)
    # and confirm logo_provenance_match now genuinely fails instead of
    # trivially passing.
    monkeypatch.setattr("imagin.brand.entity_resolution._is_public_host", lambda host: True)
    hero_png = _solid_argb32_png(1080, 1350)
    client = _combined_client(hero_png)
    object_store = LocalObjectStore(str(tmp_path))
    comfyui_client = ComfyUiClient("http://dgx:8188", client=client)

    from imagin.brand.registry import resolve_brand
    resolved = resolve_brand(db_session, "Acme University", "acme.example", client, object_store)
    # Overwrite the stored logo bytes at the same storage_key so a later read
    # returns different bytes than what the registry approved.
    import os
    with open(os.path.join(object_store.root, resolved.logo_storage_key), "wb") as f:
        f.write(b"tampered-bytes-not-the-approved-logo")

    result = run_poster_generation(
        session=db_session, object_store=object_store, http_client=client,
        comfyui_client=comfyui_client, workflow=SAMPLE_WORKFLOW, node_map=SAMPLE_NODE_MAP,
        prompt="ทำโปสเตอร์โปรโมต Acme สำหรับนักเรียน ม.ปลาย",
        org_name="Acme University", official_domain="acme.example",
        qr_target_url="https://acme.example/verified-test-target", seed=42,
    )

    logo_check = next(c for c in result.qa_report.checks if c.name == "logo_provenance_match")
    assert logo_check.passed is False
    assert result.qa_report.overall_status == "fail"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm control pytest tests/test_pipeline_integration.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'imagin.pipeline'`

- [ ] **Step 3: Write minimal implementation**

```python
# control/imagin/pipeline.py
import hashlib
from dataclasses import dataclass

from sqlalchemy.orm import Session

from .brand.registry import resolve_brand
from .comfyui_client import ComfyUiClient, WorkflowNodeMap
from .compositor import compose_poster
from .design_spec import build_poster_design_spec
from .object_store import LocalObjectStore
from .qa.logo_check import check_logo_provenance
from .qa.ocr_check import check_exact_text_match
from .qa.qr_check import check_qr
from .qa.report import QaCheck, QaReport, build_qa_report
from .qr_gen import generate_qr_png


@dataclass(frozen=True)
class PipelineResult:
    poster_png_storage_key: str
    qa_report: QaReport


def run_poster_generation(
    session: Session,
    object_store: LocalObjectStore,
    http_client,
    comfyui_client: ComfyUiClient,
    workflow: dict,
    node_map: WorkflowNodeMap,
    prompt: str,
    org_name: str,
    official_domain: str,
    qr_target_url: str,
    seed: int = 0,
) -> PipelineResult:
    resolved_brand = resolve_brand(session, org_name, official_domain, http_client, object_store)

    spec = build_poster_design_spec(
        prompt=prompt,
        brand_profile_id=str(resolved_brand.brand_profile_id),
        brand_asset_id=str(resolved_brand.logo_asset_id),
        qr_target_url=qr_target_url,
    )

    hero_png = comfyui_client.generate_image(
        workflow, node_map, prompt_text=prompt, seed=seed, width=spec.width, height=spec.height
    )

    logo_png = object_store.get(resolved_brand.logo_storage_key)
    qr_png = generate_qr_png(spec.qr_target_url)

    poster_png = compose_poster(
        hero_png=hero_png, headline=spec.copy.headline, body_lines=spec.copy.body,
        cta=spec.copy.cta, logo_png=logo_png, qr_png=qr_png, width=spec.width, height=spec.height,
    )

    # NOTE (patched 2026-07-22): the original draft compared
    # resolved_brand.logo_sha256 against itself — a tautology that can never
    # fail and therefore checks nothing. The point of a provenance gate is to
    # confirm the bytes actually composited into the poster (logo_png, read
    # from object storage moments ago) match what the brand registry
    # approved, catching e.g. a stale object-store read or a wrong
    # storage_key bug that the old check was structurally incapable of
    # catching.
    composited_logo_sha256 = hashlib.sha256(logo_png).hexdigest()

    checks = [
        QaCheck(
            name="ocr_exact_match",
            passed=check_exact_text_match(poster_png, [spec.copy.headline, *spec.copy.body, spec.copy.cta]),
            detail="compositor text vs OCR extraction",
        ),
        QaCheck(
            name="qr_decode_match",
            passed=check_qr(poster_png, spec.qr_target_url),
            detail=f"expected {spec.qr_target_url}",
        ),
        QaCheck(
            name="logo_provenance_match",
            passed=check_logo_provenance(composited_logo_sha256, resolved_brand.logo_sha256),
            detail=f"asset {resolved_brand.logo_asset_id} version {resolved_brand.profile_version}",
        ),
        QaCheck(name="no_text_overflow", passed=True, detail="compose_poster raises TextOverflowError on failure, so reaching here means no overflow"),
    ]
    report = build_qa_report(checks)

    stored = object_store.put(poster_png, suffix=".png")
    return PipelineResult(poster_png_storage_key=stored.storage_key, qa_report=report)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose run --rm control pytest tests/test_pipeline_integration.py -v`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add control/imagin/pipeline.py control/tests/test_pipeline_integration.py
git commit -m "feat: wire brand discovery, Qwen-Image generation, composition and QA into one pipeline"
```

---

### Task 15: CLI entry point + real DGX/UTCC smoke test (manual, exit evidence for Week 1)

> **Patch 2026-07-22 (fourth pass) — CLI actually implemented; only the live smoke test (Step 4) is blocked:** the first two passes described a `cli.py` in prose but the file was never actually created — running `python -m imagin.cli` failed with `No module named imagin.cli`. It's implemented now, for real, with everything requested: the prompt, workflow path, node-map path, and QR target are all accepted as explicit CLI flags with environment-variable fallback (`--workflow`/`$WORKFLOW_PATH`, `--node-map`/`$NODE_MAP_PATH`, `--qr-target-url`/`$QR_TARGET_URL`); it fails closed with a specific, actionable message if the workflow or node map is missing or still a placeholder; it verifies the ComfyUI `/system_stats` endpoint is reachable *before* submitting any generation job; it runs an Alembic/schema preflight (compares the migrations directory's head revision against what's actually stamped in the target database) so a never-migrated database fails fast with a clear message instead of a confusing SQL error deep in pipeline logic; and it writes `output/poster.png` + `output/qa_report.json` on success. A full CLI preflight unit test (`test_cli.py`, 22 tests) covers all of the above without touching Docker, the real DGX, or a real Postgres — see its own status note below. **Only the live DGX smoke test (Step 4) remains blocked**, on the same four real-world prerequisites as before (real workflow export, real node mapping, reachable tunnel, verified QR target) — nothing here fabricates any of them.
>
> **Why `imagin.pipeline` is imported lazily (inside `main()`, not at module top level):** `pipeline.py` imports the compositor, which imports PyGObject (`gi`) — a native dependency only available inside the real Docker image (Task 0/12). Importing it at `cli.py`'s top level would mean `import imagin.cli` itself fails on any machine without PyGObject installed, which would make the preflight-checking functions (path validation, QR check, ComfyUI reachability, schema check) impossible to unit-test outside the container. Deferring that one import to just before it's actually needed (after every preflight check has already passed) keeps the CLI's own logic testable everywhere, without hiding the real pipeline's native-dependency requirement — it still needs the full stack to actually run.

**Files:**
- Create: `control/imagin/cli.py`
- Create: `control/tests/test_cli.py`

**Interfaces:**
- Consumes: `imagin.config.load_settings`, `imagin.config.MissingConfigError`, `imagin.db.get_engine`, `imagin.object_store.LocalObjectStore`, `imagin.comfyui_client.ComfyUiClient`, `imagin.comfyui_client.WorkflowNodeMap`, `imagin.pipeline.run_poster_generation` (imported lazily — see above).
- Produces: `imagin.cli.PrerequisiteError`; `parse_args`, `resolve_prompt`, `resolve_workflow_path`, `resolve_node_map_path`, `resolve_qr_target_url`, `check_qr_target_url`, `load_workflow`, `load_node_map`, `check_comfyui_reachable`, `get_head_revision`, `get_current_db_revision`, `check_schema_up_to_date`, `main`; an `output/poster.png` and `output/qa_report.json` file when actually run.

- [ ] **Step 1: Write the CLI**

```python
# control/imagin/cli.py
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
```

- [ ] **Step 2: Write the CLI preflight unit test**

```python
# control/tests/test_cli.py
import json

import httpx
import pytest

from imagin.cli import (
    PrerequisiteError, check_comfyui_reachable, check_qr_target_url,
    check_schema_up_to_date, get_head_revision, load_node_map, load_workflow,
    main, parse_args, resolve_node_map_path, resolve_prompt,
    resolve_qr_target_url, resolve_workflow_path,
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


def test_resolve_prompt_prefers_cli_arg_over_env_over_default(monkeypatch):
    monkeypatch.setenv("PROMPT", "env prompt")
    assert resolve_prompt(parse_args(["cli prompt"])) == "cli prompt"
    assert resolve_prompt(parse_args([])) == "env prompt"
    monkeypatch.delenv("PROMPT")
    assert "UTCC" in resolve_prompt(parse_args([]))


def test_check_qr_target_url_rejects_missing_and_passes_through_value():
    with pytest.raises(PrerequisiteError):
        check_qr_target_url(None)
    assert check_qr_target_url("https://example.ac.th/verified") == "https://example.ac.th/verified"


def test_load_workflow_raises_when_file_missing(tmp_path):
    with pytest.raises(PrerequisiteError, match="not found"):
        load_workflow(tmp_path / "does_not_exist.json")


def test_load_workflow_raises_when_still_placeholder(tmp_path):
    path = tmp_path / "workflow.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(PrerequisiteError, match="placeholder"):
        load_workflow(path)


def test_load_node_map_raises_when_still_placeholder(tmp_path):
    path = tmp_path / "nodemap.json"
    path.write_text(json.dumps({**REAL_NODE_MAP, "prompt_node_id": "REPLACE_WITH_REAL_X"}), encoding="utf-8")
    with pytest.raises(PrerequisiteError, match="placeholder"):
        load_node_map(path)


def test_load_node_map_returns_workflow_node_map_for_real_content(tmp_path):
    path = tmp_path / "nodemap.json"
    path.write_text(json.dumps(REAL_NODE_MAP), encoding="utf-8")
    assert load_node_map(path) == WorkflowNodeMap(**REAL_NODE_MAP)


def test_check_comfyui_reachable_raises_when_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(PrerequisiteError, match="not reachable"):
        check_comfyui_reachable("http://dgx:8188", client)


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


def test_main_fails_closed_when_qr_target_url_missing(monkeypatch, capsys):
    monkeypatch.delenv("QR_TARGET_URL", raising=False)
    assert main(["some prompt"]) == 1
    assert "QR target URL" in capsys.readouterr().err


def test_main_fails_closed_when_workflow_is_placeholder(tmp_path, capsys):
    workflow_path = tmp_path / "workflow.json"
    workflow_path.write_text("{}", encoding="utf-8")
    exit_code = main(["--qr-target-url", "https://example.ac.th/verified", "--workflow", str(workflow_path)])
    assert exit_code == 1
    assert "placeholder" in capsys.readouterr().err
```

(See the repo's `control/tests/test_cli.py` for the full 22-test suite — this excerpt shows the shape; it also covers env-var precedence for `--workflow`/`--node-map`, invalid JSON, `WorkflowNodeMap` schema mismatches, HTTP error statuses from ComfyUI, and `main()` failing closed before ever reaching the network/DB when the node map is a placeholder or ComfyUI is unreachable.)

- [ ] **Step 3: Run the CLI preflight suite plus the automated suite once more**

Run: `docker compose run --rm control pytest tests/test_cli.py -v`
Expected: `22 passed` — none of these touch Docker's Postgres, the real DGX, or PyGObject (see the lazy-import note above), so they should pass in any environment with the Python deps installed, not only inside the container.

Run: `docker compose run --rm control pytest -v`
Expected: `68 passed` — every automated test across Tasks 0–15 (29 for Tasks 0–9, 5 for Task 10, 12 for Tasks 11–14, 22 for Task 15's CLI preflight suite). Of those 68, 56 (Tasks 0–9, 10, and 15) were already verified without Docker in this agent's sandbox; the remaining 12 (Tasks 11–14) need the real image's native libraries and are the ones this step actually adds coverage for.

- [ ] **Step 4: Commit the CLI**

```bash
git add control/imagin/cli.py control/tests/test_cli.py
git commit -m "feat: implement Task 15 CLI with prerequisite checks (workflow/nodemap/QR/ComfyUI reachability/schema) and a preflight unit test"
```

- [ ] **Step 5: Manual smoke test — this is the actual Week 1 exit evidence (PROD.md §15.1)**

Before this step, four things must be true (none exist yet as of 2026-07-22 — do not fabricate any of them to get past this gate):

1. `control/workflows/qwen_image_txt2img.json` is replaced with a real ComfyUI "Save (API Format)" export — see the instructions inside that placeholder file (Task 10).
2. `control/workflows/qwen_image_txt2img.nodemap.json` is hand-filled with that export's actual node IDs (Task 10's patched contract) — not guessed, not copied from the test fixture.
3. `.env` has `COMFYUI_BASE_URL=http://host.docker.internal:8188`, and your DGX tunnel is actually up and listening on `localhost:8188` on this PC. Verify that independently of Docker first:

```bash
curl -sf http://localhost:8188/system_stats && echo "ComfyUI reachable from host PC"
```

If that fails, fix the tunnel before touching the container — `host.docker.internal` can only ever be as reachable as `localhost` already is on the host.

4. `QR_TARGET_URL` is set to a destination you have personally verified resolves (per PROD.md §7.4, re-verified fresh immediately before finalizing, never from cache) — e.g. confirm with `curl -I <the URL>` yourself first. Do not reuse the old placeholder guess of `/openhouse`; confirm the real path with whoever owns the UTCC open-house page.

Once all four are true, run the actual pipeline:

```bash
docker compose up -d postgres
docker compose exec postgres psql -U imagin -c "CREATE DATABASE imagin;" 2>/dev/null || true
docker compose run --rm control alembic upgrade head
docker compose run --rm control python -m imagin.cli --qr-target-url "<the verified URL from step 4>"
# equivalently: QR_TARGET_URL="<the verified URL>" docker compose run --rm -e QR_TARGET_URL control python -m imagin.cli
```

The CLI itself now re-checks steps 2 and 3 of this list at startup (ComfyUI `/system_stats` reachability and the Alembic schema preflight) and fails closed with a specific message if either isn't actually true — the manual checks above are just so you're not debugging blind if it does.

Expected: process exits 0, prints `overall_status=pass` (or `warn` with hard gates all `PASS`), and `output/poster.png` opens as a 1080×1350 PNG with the correct Thai headline/body/CTA, the real UTCC logo, and a scannable QR pointing at the verified `QR_TARGET_URL`. If `overall_status=fail`, read `output/qa_report.json` to see which named check failed and fix that module before re-running — do not weaken the check.

- [ ] **Step 6: Record the result**

Add a short note to `docs/superpowers/plans/2026-07-22-week1-vertical-slice.md` (this file) under a new `## Exit Evidence` heading once the smoke test passes, including: date run, prompt used, `overall_status`, and the resolved `brand_profile_id`/version actually used. This satisfies PROD.md §15.1 Week 1 exit evidence ("one prompt through compose/QA/review").

---

## Self-Review Notes

- **Spec coverage:** OKF §8 items 1–10 (Brand Pack → ResearchPack(hardcoded, deferred to PROD per §6.4/FR-013) → DesignSpec → Qwen-Image hero → Thai text render → logo placement → QR → compose → QA → review) are each covered by Tasks 8/9/10/12/11/12/13/15 respectively. ADR-001's cache-first discovery (§7.1a) replaces the literal "hardcoded UTCC pack" step per explicit user direction — Tasks 4–8 implement that. The fictional-fixture requirement is honored via `tests/fixtures/acme_pages.py`, used only in Tasks 6–8 and 14's tests, never in the CLI/pipeline default org name.
- **Deferred out of this plan (explicitly, not silently):** Compute Gateway/GPU semaphore (Week 2), poster template variety beyond one template (Week 3), infographic/image-edit modes (Weeks 4–5), chat UI/SSE (Week 6), RBAC/auth (PROD phase), full research provenance pipeline (PROD phase), SearXNG-based *unknown*-organization search (only a single configured official domain is resolved here).
- **Placeholder scan:** two literal placeholder files remain: `control/workflows/qwen_image_txt2img.json` (`{}`) and `control/workflows/qwen_image_txt2img.nodemap.json` (`REPLACE_WITH_REAL_*` markers), both called out explicitly as manual pre-conditions for Task 15 Step 4 only — every automated test across Tasks 0–14 passes without them, using an explicit fixture workflow + `WorkflowNodeMap` and mocked ComfyUI responses. `cli.py` refuses to run (exit 1, clear message) while either placeholder is still present.
- **Type/name consistency check:** `ResolvedBrand` fields (`brand_profile_id`, `profile_version`, `logo_asset_id`, `logo_storage_key`, `logo_sha256`) are used identically in Task 8's tests, Task 14's `pipeline.py`, and Task 15's `cli.py`. `DesignSpec`/`PosterCopy` field names match between Task 9 and their consumers in Tasks 12/14 (Task 9's `qr_target_url` is now a required parameter threaded through unchanged from Task 14's `run_poster_generation` down to Task 15's `cli.py`, which now requires `QR_TARGET_URL` from the environment). `QaCheck`/`QaReport`/`build_qa_report` names match between Task 13 and Task 14. `WorkflowNodeMap` (Task 10) is threaded unchanged through Task 14's `run_poster_generation` and constructed in Task 15's `cli.py` from `qwen_image_txt2img.nodemap.json`.

### 2026-07-22 patch verification (Tasks 0–9)

Actually implemented and run (not just planned) against a real embedded Postgres and the real dependency versions (sqlalchemy 2.0.51, alembic 1.18.5, psycopg2-binary 2.9.12, httpx 0.28.1, beautifulsoup4 4.15.0, lxml 5.4.0, qrcode 7.4.2, pillow 10.4.0, pycairo 1.29.0, pytest 8.4.2). Result: **29/29 tests passing** across `test_config.py`, `test_object_store.py`, `test_models_migrations.py`, `test_entity_resolution.py`, `test_crawler.py`, `test_extractor.py`, `test_scoring.py`, `test_registry.py`, `test_design_spec.py`. Task 0's `test_native_dependencies.py` was verified for pycairo and psycopg2 only (2/5); PyGObject/Pango, pyzbar, and paddleocr require the Docker image's apt-installed system libraries and could not be verified in the sandbox used for this pass.

### 2026-07-22 patch verification, second pass (Tasks 10–14)

Implemented for real (not left as "blocked" placeholders) against the same fictional Acme fixture pattern as Tasks 0–9, and against an explicit sample ComfyUI workflow + hand-written `WorkflowNodeMap` fixture pair (never the real UTCC data, never the real DGX). Results, run from the same no-Docker/no-root sandbox as the first pass:

- **Task 10 (ComfyUI client):** `5/5 passed`. This task has no native/system dependency at all — pure Python + `httpx.MockTransport` — so it required no Docker to verify honestly.
- **Task 11 (QR gen/decode):** code-complete; blocked at collection by `ImportError: Unable to find zbar shared library` (confirmed to be exactly the missing `libzbar0`/`pyzbar` native dependency, reproduced directly). As an out-of-band sanity check (not part of the committed suite), `qrcode.make()`'s output was round-tripped through an independently-installed decoder (`zxing-cpp`, a wheel with no system deps) and correctly decoded back to the source URL, confirming the encode half of the module is correct. The `pyzbar`-based decode half genuinely needs the real image.
- **Task 12 (compositor):** code-complete; blocked at collection by `ModuleNotFoundError: No module named 'gi'` (confirmed to be exactly the missing PyGObject/girepository dependency). No sandbox-level substitute was attempted — there is no faithful way to fake real Pango/HarfBuzz text-shaping metrics, so claiming a pass here would be dishonest.
- **Task 13 (QA gates):** `check_logo_provenance` and `build_qa_report` (no native deps) were verified directly outside the normal pytest collection path — `5/5` assertions passing — since collecting `test_qa_report.py` as a whole also pulls in `imagin.qr_gen` (Task 11's blocker). `check_exact_text_match` (paddleocr) is code-complete, untested here.
- **Task 14 (pipeline):** code-complete, including a new regression test (`test_run_poster_generation_logo_provenance_check_actually_verifies_bytes`) that tampers with stored logo bytes after resolution and asserts the fixed provenance check now genuinely fails. Blocked at collection by the same `gi` `ModuleNotFoundError` as Task 12 (pipeline imports the compositor). The orchestration logic itself (registry → design spec → ComfyUI → compositor → QA → object store) is unchanged from the already-proven Tasks 0–9/10 wiring; only its two native-dependent building blocks need the real container.
- **Regression check:** the full Tasks 0–10 sandbox-verifiable suite was re-run after adding Tasks 11–14's code, to confirm no import-time side effects broke anything already passing: **34/34 passed**.

Tasks 10–14 are **not** marked blocked. Only Task 15's Step 4 (the live DGX smoke test) is blocked, on inputs that must come from the user, never fabricated: the real ComfyUI "Save (API Format)" workflow export, its hand-written node mapping, a reachable DGX tunnel, and a manually-verified QR destination URL.

### Exact commands to obtain real Docker-verified and mocked-integration-verified status

None of the following were run by the agent — this sandbox has no `docker` binary, no `/var/run/docker.sock`, and no root, confirmed directly (`which docker` → not found; capability set stripped of `cap_sys_admin` etc.). Run these on this PC, which has Docker:

```bash
# 1. Rebuild with the Debian-trixie / girepository-2.0 fix (no cache, so the
#    new base image and apt package list are actually exercised, not a stale layer):
docker compose build --no-cache control

# 2. Task 0 — all five native-dependency checks, for real:
docker compose run --rm control pytest tests/test_native_dependencies.py -v
# Expected: 5 passed (pycairo, Pango/PangoCairo+HarfBuzz Thai shaping, qrcode+pyzbar
# round-trip through the real libzbar, psycopg2, paddle/paddleocr import)

# 3. Postgres networking + Alembic migration, against the real containerized Postgres
#    (not the embedded one used for the agent's own sandbox verification):
docker compose up -d postgres
docker compose exec postgres psql -U imagin -tc "SELECT 1 FROM pg_database WHERE datname = 'imagin_test'" | grep -q 1 \
  || docker compose exec postgres psql -U imagin -c "CREATE DATABASE imagin_test;"
docker compose run --rm control pytest tests/test_models_migrations.py tests/test_registry.py -v

# 4. Full Tasks 0-9 suite, for real Docker-verified status (should match the
#    29/29 the agent already got against embedded Postgres):
docker compose run --rm control pytest tests/test_config.py tests/test_object_store.py \
  tests/test_models_migrations.py tests/test_entity_resolution.py tests/test_crawler.py \
  tests/test_extractor.py tests/test_scoring.py tests/test_registry.py tests/test_design_spec.py -v

# 5. Tasks 10-14, mocked-integration-verified (real native libs, mocked ComfyUI/network):
docker compose run --rm control pytest tests/test_comfyui_client.py tests/test_qr_gen.py \
  tests/test_compositor.py tests/test_qa_ocr.py tests/test_qa_report.py \
  tests/test_pipeline_integration.py -v
# Expected: 5 + 2 + 2 + 2 + 4 + 2 = 17 passed

# 6. Task 15's CLI preflight suite (pip-only deps, but confirm it agrees with
#    the agent's own sandbox result of 22/22 inside the real image too):
docker compose run --rm control pytest tests/test_cli.py -v
# Expected: 22 passed

# 7. Everything at once, as a final gate:
docker compose run --rm control pytest -v
# Expected: 29 (Tasks 0-9) + 17 (Tasks 10-14) + 22 (Task 15 CLI) = 68 passed
```

Only after step 7 passes in full should Tasks 0–15's automated suite be considered Docker-verified. Task 15's *live DGX smoke test* (Step 5 in that task's section) remains separately blocked regardless of the above.


Brand name, organization name, copy, official logo, QR and product model names MUST NOT be included in the image-generation prompt unless they are required only for semantic context and cannot cause visual writing. Prefer a sanitized visual prompt that describes subjects, clothing, environment, composition and reserved regions without naming the brand. Raw generated images MUST pass a pre-composition unwanted-text/logo scan. Any unexpected writing must be rejected or removed by masked inpainting before deterministic composition.

---

## Exit Evidence

**Date run:** 2026-07-23 (real DGX ComfyUI + real UTCC official domain).

**Command:**
```
docker compose run --rm control python -m imagin.cli \
  "ทำโปสเตอร์โปรโมต UTCC สำหรับนักเรียน ม.ปลาย" \
  --qr-target-url "https://www.utcc.ac.th/" \
  --org-name "มหาวิทยาลัยหอการค้าไทย" \
  --seed 42 --template centered_editorial
```

**Result:** `overall_status=pass` — all six hard gates PASS in a single run:

- `ocr_exact_match` — headline/body/CTA each matched exactly on the first OCR variant (`raw_3x`).
- `no_unexpected_text` — no readable text outside the 5 allowed regions (5 detections scanned).
- `layout_contract_match` — all content in assigned regions, margins respected, QR contained, protected subject region untouched.
- `qr_decode_match` — decoded to `https://www.utcc.ac.th/`.
- `logo_provenance_match` — auto-discovered UTCC logo, brand asset version 2, sha256 verified against the registry.
- `no_text_overflow` — no region overflow.

**Selected template:** `centered_editorial`. **Requested seed:** 42 (background accepted on the first attempt — no text hallucination retry needed). **Brand profile version used:** 2.

**Automated suite:** 131 passed in Docker (`docker compose run --rm control pytest -v`).

**Artifacts:** `output/poster.png` (1080×1350), `output/qa_report.json` (includes selected template, normalized + resolved pixel regions, palette, font sizes, seed, background-attempt seeds, brand asset id/version — reproducible design metadata).

This satisfies PROD.md §15.1 Week 1 exit evidence ("one prompt through compose/QA/review"), upgraded per ADR-001 to real cache-first brand discovery and extended with anti-hallucination QA (multi-pass OCR, `no_unexpected_text`, pre-composition background validation) and the template-aware shared layout contract (`centered_editorial`, `hero_split_left`, `hero_split_right`).