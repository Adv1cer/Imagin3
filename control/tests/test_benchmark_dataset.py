import textwrap
from pathlib import Path

import pytest

from imagin.benchmark.dataset import (
    AspectRatio,
    DatasetError,
    load_dataset,
)

CONTROL_ROOT = Path(__file__).resolve().parent.parent


def _write(tmp_path, text: str) -> Path:
    path = tmp_path / "cases.yaml"
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return path


def test_aspect_ratio_parse_and_orientation():
    assert AspectRatio.parse("1080x1350").orientation == "portrait"
    assert AspectRatio.parse("1350x1080").orientation == "landscape"
    with pytest.raises(DatasetError):
        AspectRatio.parse("wide")
    with pytest.raises(DatasetError):
        AspectRatio.parse("0x100")


def test_shipped_runnable_dataset_uses_only_approved_real_domain():
    dataset = load_dataset(CONTROL_ROOT / "benchmarks" / "poster_cases.yaml")

    assert dataset.version == "1"
    assert dataset.total_candidates == sum(c.candidate_count for c in dataset.cases)
    # Categories cover the required breadth.
    categories = {c.category for c in dataset.cases}
    assert {"university_open_house", "recruitment_admission", "information_dense"} <= categories
    # Both orientations are represented.
    orientations = {a.orientation for c in dataset.cases for a in c.aspect_ratios}
    assert orientations == {"portrait", "landscape"}
    # The RUNNABLE dataset must never contain known-unrunnable fictional
    # domains — every case targets the one approved real domain.
    domains = {c.official_domain for c in dataset.cases}
    assert domains == {"www.utcc.ac.th"}
    assert not any(d.endswith(".example") for d in domains)


def test_failure_dataset_is_separate_and_fictional():
    dataset = load_dataset(CONTROL_ROOT / "benchmarks" / "poster_failure_cases.yaml")

    # The failure dataset is exclusively unreachable *.example domains —
    # used only to exercise graceful failure handling, never a real run.
    domains = {c.official_domain for c in dataset.cases}
    assert domains and all(d.endswith(".example") for d in domains)


def test_unknown_template_id_fails_loudly(tmp_path):
    path = _write(tmp_path, """
        version: "1"
        cases:
          - id: bad
            category: test
            prompt: p
            org_name: o
            official_domain: o.example
            qr_url: https://o.example/
            templates: [not_a_real_template]
            aspect_ratios: ["1080x1350"]
            seeds: [1]
    """)
    with pytest.raises(DatasetError) as exc:
        load_dataset(path)
    assert "not_a_real_template" in str(exc.value)


def test_auto_template_is_accepted(tmp_path):
    path = _write(tmp_path, """
        version: "1"
        cases:
          - id: ok
            category: test
            prompt: p
            org_name: o
            official_domain: o.example
            qr_url: https://o.example/
            templates: [auto]
            aspect_ratios: ["1080x1350"]
            seeds: [1]
    """)
    dataset = load_dataset(path)
    assert dataset.cases[0].templates == ("auto",)


def test_duplicate_case_ids_rejected(tmp_path):
    path = _write(tmp_path, """
        version: "1"
        cases:
          - id: dup
            category: t
            prompt: p
            org_name: o
            official_domain: o.example
            qr_url: https://o.example/
            templates: [centered_editorial]
            aspect_ratios: ["1080x1350"]
            seeds: [1]
          - id: dup
            category: t
            prompt: p2
            org_name: o
            official_domain: o.example
            qr_url: https://o.example/
            templates: [centered_editorial]
            aspect_ratios: ["1080x1350"]
            seeds: [1]
    """)
    with pytest.raises(DatasetError):
        load_dataset(path)


def test_missing_required_field_rejected(tmp_path):
    path = _write(tmp_path, """
        version: "1"
        cases:
          - id: incomplete
            category: t
            prompt: p
            templates: [centered_editorial]
            aspect_ratios: ["1080x1350"]
            seeds: [1]
    """)
    with pytest.raises(DatasetError) as exc:
        load_dataset(path)
    assert "org_name" in str(exc.value)


def test_missing_version_rejected(tmp_path):
    path = _write(tmp_path, """
        cases:
          - id: x
            category: t
            prompt: p
            org_name: o
            official_domain: o.example
            qr_url: https://o.example/
            templates: [centered_editorial]
            aspect_ratios: ["1080x1350"]
            seeds: [1]
    """)
    with pytest.raises(DatasetError):
        load_dataset(path)
