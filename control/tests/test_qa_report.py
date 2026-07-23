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
