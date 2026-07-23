"""Versioned benchmark dataset: typed loader + validation.

No pipeline/native imports on purpose — a dataset can be loaded and
validated anywhere. Template ids are validated against the real template
registry (plus the literal "auto" for automatic selection), so a typo in
the dataset fails loudly before any expensive generation runs.
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..templates import TEMPLATES

AUTO_TEMPLATE = "auto"


class DatasetError(ValueError):
    pass


@dataclass(frozen=True)
class AspectRatio:
    width: int
    height: int

    @property
    def label(self) -> str:
        return f"{self.width}x{self.height}"

    @property
    def orientation(self) -> str:
        return "portrait" if self.height >= self.width else "landscape"

    @classmethod
    def parse(cls, raw: str) -> "AspectRatio":
        try:
            w_str, h_str = str(raw).lower().split("x")
            w, h = int(w_str), int(h_str)
        except (ValueError, AttributeError) as exc:
            raise DatasetError(f"invalid aspect ratio {raw!r}; expected 'WIDTHxHEIGHT'") from exc
        if w <= 0 or h <= 0:
            raise DatasetError(f"aspect ratio {raw!r} must have positive dimensions")
        return cls(width=w, height=h)


@dataclass(frozen=True)
class BenchmarkCase:
    id: str
    category: str
    prompt: str
    org_name: str
    official_domain: str
    qr_url: str
    templates: tuple[str, ...]          # each is a template id or "auto"
    aspect_ratios: tuple[AspectRatio, ...]
    seeds: tuple[int, ...]
    audience: str = ""
    notes: str = ""

    @property
    def candidate_count(self) -> int:
        return len(self.templates) * len(self.aspect_ratios) * len(self.seeds)


@dataclass(frozen=True)
class BenchmarkDataset:
    version: str
    cases: tuple[BenchmarkCase, ...]
    source_path: str = ""

    @property
    def total_candidates(self) -> int:
        return sum(case.candidate_count for case in self.cases)


def _require(raw: dict, key: str, case_id: str):
    if key not in raw or raw[key] in (None, "", []):
        raise DatasetError(f"case {case_id!r} missing required field {key!r}")
    return raw[key]


def _validate_template_id(template_id: str, case_id: str) -> str:
    if template_id != AUTO_TEMPLATE and template_id not in TEMPLATES:
        options = ", ".join([AUTO_TEMPLATE, *sorted(TEMPLATES)])
        raise DatasetError(
            f"case {case_id!r} references unknown template {template_id!r}; available: {options}"
        )
    return template_id


def _parse_case(raw: dict) -> BenchmarkCase:
    if "id" not in raw or not raw["id"]:
        raise DatasetError("every case must have a non-empty 'id'")
    case_id = str(raw["id"])

    templates = tuple(_validate_template_id(str(t), case_id) for t in _require(raw, "templates", case_id))
    aspect_ratios = tuple(AspectRatio.parse(a) for a in _require(raw, "aspect_ratios", case_id))
    seeds_raw = _require(raw, "seeds", case_id)
    try:
        seeds = tuple(int(s) for s in seeds_raw)
    except (ValueError, TypeError) as exc:
        raise DatasetError(f"case {case_id!r} has non-integer seed(s): {seeds_raw!r}") from exc

    return BenchmarkCase(
        id=case_id,
        category=str(_require(raw, "category", case_id)),
        prompt=str(_require(raw, "prompt", case_id)),
        org_name=str(_require(raw, "org_name", case_id)),
        official_domain=str(_require(raw, "official_domain", case_id)),
        qr_url=str(_require(raw, "qr_url", case_id)),
        templates=templates,
        aspect_ratios=aspect_ratios,
        seeds=seeds,
        audience=str(raw.get("audience", "")),
        notes=str(raw.get("notes", "")),
    )


def load_dataset(path: str | Path) -> BenchmarkDataset:
    path = Path(path)
    if not path.exists():
        raise DatasetError(f"dataset file not found: {path}")

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise DatasetError("dataset root must be a mapping with 'version' and 'cases'")

    version = str(data.get("version") or "")
    if not version:
        raise DatasetError("dataset must declare a 'version'")

    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise DatasetError("dataset must contain a non-empty 'cases' list")

    cases = tuple(_parse_case(rc) for rc in raw_cases)

    seen: set[str] = set()
    for case in cases:
        if case.id in seen:
            raise DatasetError(f"duplicate case id {case.id!r}")
        seen.add(case.id)

    return BenchmarkDataset(version=version, cases=cases, source_path=str(path))
