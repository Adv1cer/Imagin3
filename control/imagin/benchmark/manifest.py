"""Typed candidate specs, generation outputs, and the run manifest.

Pure data + serialization; no pipeline/native imports. `GenerationOutput`
is the contract a generate-fn returns; the harness adds timing/paths and
records a `CandidateRecord`. Everything serializes to plain JSON so a run
is fully reproducible and inspectable without the code that produced it.
"""

from dataclasses import asdict, dataclass, field

from .dataset import AspectRatio, BenchmarkCase


def _slug(value: str) -> str:
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in value)


@dataclass(frozen=True)
class CandidateSpec:
    """One concrete generation request: a case fixed to a specific
    template, aspect ratio, and seed."""

    case_id: str
    category: str
    prompt: str
    org_name: str
    official_domain: str
    qr_url: str
    template: str          # a template id, or "auto" (resolved at run time)
    width: int
    height: int
    seed: int
    audience: str = ""

    @property
    def candidate_id(self) -> str:
        return f"{_slug(self.case_id)}__{_slug(self.template)}__{self.width}x{self.height}__seed{self.seed}"

    @property
    def relative_dir(self) -> str:
        # output_root/<run>/<case>/<template>_<WxH>/seed_<seed>/
        return f"{_slug(self.case_id)}/{_slug(self.template)}_{self.width}x{self.height}/seed_{self.seed}"


def expand_case(case: BenchmarkCase) -> list[CandidateSpec]:
    specs: list[CandidateSpec] = []
    for template in case.templates:
        for aspect in case.aspect_ratios:
            for seed in case.seeds:
                specs.append(
                    CandidateSpec(
                        case_id=case.id,
                        category=case.category,
                        prompt=case.prompt,
                        org_name=case.org_name,
                        official_domain=case.official_domain,
                        qr_url=case.qr_url,
                        template=template,
                        width=aspect.width,
                        height=aspect.height,
                        seed=seed,
                        audience=case.audience,
                    )
                )
    return specs


@dataclass(frozen=True)
class GenerationOutput:
    """What a generate-fn returns for one candidate. `poster_bytes` is None
    on a handled generation failure (e.g. text-contaminated background),
    in which case `error` explains it — the harness records the failure
    and continues instead of aborting the whole run."""

    poster_bytes: bytes | None
    overall_status: str                 # pass | warn | fail | error
    checks: list[dict]                  # [{name, passed, detail}, ...]
    resolved_template: str
    design_metadata: dict = field(default_factory=dict)
    peak_memory_mb: float | None = None
    error: str | None = None


@dataclass(frozen=True)
class CandidateRecord:
    candidate_id: str
    case_id: str
    category: str
    prompt: str
    org_name: str
    official_domain: str
    qr_url: str
    requested_template: str
    resolved_template: str
    width: int
    height: int
    seed: int
    overall_status: str
    checks: list[dict]
    duration_seconds: float
    peak_memory_mb: float | None
    poster_path: str | None
    error: str | None
    failure_type: str | None

    def to_dict(self) -> dict:
        return asdict(self)


def classify_failure(overall_status: str, checks: list[dict], error: str | None) -> str | None:
    """A single, coarse failure label for aggregation. Technical only —
    semantic/visual failures are a human-review concern, not this."""
    if error:
        return "generation_error"
    if overall_status not in ("fail",):
        return None
    failed = [c["name"] for c in checks if not c.get("passed", False)]
    return "+".join(sorted(failed)) if failed else "unknown_fail"


@dataclass
class RunManifest:
    run_id: str
    dataset_version: str
    dataset_path: str
    created_at: str
    generation_settings: dict
    candidates: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "runId": self.run_id,
            "datasetVersion": self.dataset_version,
            "datasetPath": self.dataset_path,
            "createdAt": self.created_at,
            "generationSettings": self.generation_settings,
            "candidateCount": len(self.candidates),
            "candidates": self.candidates,
        }
