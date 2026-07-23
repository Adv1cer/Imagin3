from dataclasses import dataclass

HARD_GATE_NAMES = {
    "ocr_exact_match",
    "qr_decode_match",
    "logo_provenance_match",
    "no_text_overflow",
    "no_unexpected_text",
}


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
