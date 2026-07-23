"""Human-review scaffolding and status-aware aggregation.

Technical QA (geometry, OCR, QR, provenance) is NOT visual approval. Every
candidate gets a blank review.json for a human to fill; the aggregator
rolls those human scores up alongside machine metrics.

Status taxonomy — each candidate lands in exactly ONE bucket, and these are
never conflated:
  - generation_error    : the pipeline failed to produce a poster (infra/
                          brand/background). NOT a human quality rejection.
  - technical_qa_failure: a poster was produced but a hard QA gate failed.
  - pending_review      : technically OK, no human decision yet. A blank
                          review is pending — never counted as score 0 or
                          as a rejection.
  - human_rejected      : a reviewer explicitly rejected it.
  - approved            : a reviewer explicitly approved it.

No native/pipeline imports.
"""

import json
from pathlib import Path

# 1–5 scores a reviewer fills in; approve/reject is the gate decision.
REVIEW_SCORE_FIELDS = (
    "prompt_adherence",
    "semantic_correctness",
    "composition",
    "visual_quality",
    "brand_correctness",
    "typography",
)

STATUS_GENERATION_ERROR = "generation_error"
STATUS_TECHNICAL_FAILURE = "technical_qa_failure"
STATUS_PENDING_REVIEW = "pending_review"
STATUS_HUMAN_REJECTED = "human_rejected"
STATUS_APPROVED = "approved"

STATUS_ORDER = (
    STATUS_GENERATION_ERROR,
    STATUS_TECHNICAL_FAILURE,
    STATUS_PENDING_REVIEW,
    STATUS_HUMAN_REJECTED,
    STATUS_APPROVED,
)


def blank_review() -> dict:
    """A reviewer fills scores (1–5), the approve/reject decision, and
    notes. Left null so an un-reviewed candidate is unambiguous — never
    silently counted as approved, rejected, or scored zero."""
    review: dict = {name: None for name in REVIEW_SCORE_FIELDS}
    review["approved"] = None      # true | false | null (null == not yet reviewed)
    review["reviewer_notes"] = ""
    return review


def candidate_status(record: dict, review: dict) -> str:
    """Collapse a candidate's machine verdict + human decision into exactly
    one taxonomy bucket. Order matters: a generation error or technical
    failure is decided before any human dimension, so an infrastructure
    error can never be mistaken for a human rejection."""
    overall = record.get("overall_status")
    if overall == "error":
        return STATUS_GENERATION_ERROR
    if overall == "fail":
        return STATUS_TECHNICAL_FAILURE
    approved = review.get("approved")
    if approved is None:
        return STATUS_PENDING_REVIEW
    return STATUS_APPROVED if approved else STATUS_HUMAN_REJECTED


def _mean(values: list[float]) -> float | None:
    nums = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return round(sum(nums) / len(nums), 3) if nums else None


def _new_bucket() -> dict:
    bucket = {"candidates": 0, **{status: 0 for status in STATUS_ORDER}}
    bucket["_scores"] = {name: [] for name in REVIEW_SCORE_FIELDS}
    return bucket


def _group_add(groups: dict, key: str, record: dict, review: dict) -> None:
    bucket = groups.setdefault(key, _new_bucket())
    bucket["candidates"] += 1
    bucket[candidate_status(record, review)] += 1
    # Scores only ever come from a human who entered a number. Blank
    # (None) contributes nothing — it is NOT a zero.
    for name in REVIEW_SCORE_FIELDS:
        val = review.get(name)
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            bucket["_scores"][name].append(val)


def _finalize(groups: dict) -> dict:
    out: dict = {}
    for key, bucket in groups.items():
        scores = {name: _mean(vals) for name, vals in bucket.pop("_scores").items()}
        out[key] = {**bucket, "mean_scores": scores}
    return out


def aggregate_run(run_dir: str | Path) -> dict:
    """Read every candidate.json + review.json under a run directory and
    aggregate by template, category, seed, and failure type — with the
    status taxonomy kept distinct in every group."""
    run_dir = Path(run_dir)
    by_template: dict = {}
    by_category: dict = {}
    by_seed: dict = {}
    by_failure: dict = {}
    totals = {status: 0 for status in STATUS_ORDER}
    total = 0

    for candidate_file in sorted(run_dir.rglob("candidate.json")):
        record = json.loads(candidate_file.read_text(encoding="utf-8"))
        review_file = candidate_file.with_name("review.json")
        review = json.loads(review_file.read_text(encoding="utf-8")) if review_file.exists() else blank_review()
        total += 1
        totals[candidate_status(record, review)] += 1

        _group_add(by_template, record.get("resolved_template", "?"), record, review)
        _group_add(by_category, record.get("category", "?"), record, review)
        _group_add(by_seed, str(record.get("seed", "?")), record, review)
        failure = record.get("failure_type")
        if failure:
            _group_add(by_failure, failure, record, review)

    return {
        "totalCandidates": total,
        "statusTotals": totals,
        "byTemplate": _finalize(by_template),
        "byCategory": _finalize(by_category),
        "bySeed": _finalize(by_seed),
        "byFailureType": _finalize(by_failure),
    }


def render_summary_markdown(aggregate: dict) -> str:
    lines = ["# Benchmark summary", "", f"Total candidates: {aggregate['totalCandidates']}", ""]
    st = aggregate.get("statusTotals", {})
    lines.append("## Status totals")
    lines.append("")
    lines.append("| status | count |")
    lines.append("|---|---|")
    for status in STATUS_ORDER:
        lines.append(f"| {status} | {st.get(status, 0)} |")
    lines.append("")
    lines.append(
        "_Note: pending_review means a technically-valid candidate awaiting a "
        "human decision — it is not a rejection and contributes no score._"
    )
    lines.append("")

    for title, key in (("By template", "byTemplate"), ("By category", "byCategory"),
                       ("By seed", "bySeed"), ("By failure type", "byFailureType")):
        section = aggregate.get(key, {})
        lines.append(f"## {title}")
        lines.append("")
        if not section:
            lines.append("_none_")
            lines.append("")
            continue
        lines.append("| group | candidates | approved | rejected | pending | tech_fail | gen_error |")
        lines.append("|---|---|---|---|---|---|---|")
        for name, b in sorted(section.items()):
            lines.append(
                f"| {name} | {b['candidates']} | {b[STATUS_APPROVED]} | "
                f"{b[STATUS_HUMAN_REJECTED]} | {b[STATUS_PENDING_REVIEW]} | "
                f"{b[STATUS_TECHNICAL_FAILURE]} | {b[STATUS_GENERATION_ERROR]} |"
            )
        lines.append("")
    return "\n".join(lines)
