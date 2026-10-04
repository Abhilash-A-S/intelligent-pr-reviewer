from pr_reviewer.publishing.summary import (
    ReviewSummaryFormatter,
)
from pr_reviewer.review.models import Finding, Severity
from pr_reviewer.review.quality_gate import QualityGate


def create_finding(
    severity: Severity,
    line_number: int,
    rule_id: str,
    message: str,
) -> Finding:
    return Finding(
        file_path="src/app.js",
        line_number=line_number,
        severity=severity,
        rule_id=rule_id,
        message=message,
    )


def test_summary_with_no_findings():
    gate = QualityGate()

    quality_result = gate.evaluate([])

    formatter = ReviewSummaryFormatter()

    result = formatter.format(
        findings=[],
        quality_gate=quality_result,
    )

    assert "🤖 Intelligent PR Review" in result
    assert "✅ Passed" in result
    assert "Total findings:** 0" in result
    assert "No meaningful issues" in result


def test_summary_contains_severity_counts():
    findings = [
        create_finding(
            Severity.CRITICAL,
            10,
            "hardcoded-secret",
            "Hardcoded secret detected.",
        ),
        create_finding(
            Severity.HIGH,
            20,
            "security-issue",
            "Security issue detected.",
        ),
        create_finding(
            Severity.MEDIUM,
            30,
            "error-handling",
            "Missing error handling.",
        ),
        create_finding(
            Severity.LOW,
            40,
            "no-console",
            "Console logging detected.",
        ),
        create_finding(
            Severity.SUGGESTION,
            50,
            "maintainability",
            "Code could be simplified.",
        ),
    ]

    gate = QualityGate()

    quality_result = gate.evaluate(
        findings
    )

    formatter = ReviewSummaryFormatter()

    result = formatter.format(
        findings=findings,
        quality_gate=quality_result,
    )

    assert "🔴 Critical: 1" in result
    assert "🟠 High: 1" in result
    assert "🟡 Medium: 1" in result
    assert "🔵 Low: 1" in result
    assert "🟢 Suggestion: 1" in result

    assert "Total findings:** 5" in result


def test_summary_uses_block_decision():
    findings = [
        create_finding(
            Severity.CRITICAL,
            10,
            "hardcoded-secret",
            "Secret detected.",
        )
    ]

    gate = QualityGate()

    quality_result = gate.evaluate(
        findings
    )

    formatter = ReviewSummaryFormatter()

    result = formatter.format(
        findings=findings,
        quality_gate=quality_result,
    )

    assert "❌ Block Merge" in result


def test_summary_groups_findings():
    findings = [
        create_finding(
            Severity.LOW,
            10,
            "no-console",
            "Console logging detected.",
        ),
        create_finding(
            Severity.LOW,
            20,
            "unused-variable",
            "Unused variable detected.",
        ),
    ]

    gate = QualityGate()

    quality_result = gate.evaluate(
        findings
    )

    formatter = ReviewSummaryFormatter()

    result = formatter.format(
        findings=findings,
        quality_gate=quality_result,
    )

    assert "#### 🔵 Low" in result

    assert (
        "`src/app.js:10` **no-console**"
        in result
    )

    assert (
        "`src/app.js:20` **unused-variable**"
        in result
    )


def test_summary_does_not_show_empty_severity_sections():
    findings = [
        create_finding(
            Severity.LOW,
            10,
            "no-console",
            "Console logging detected.",
        )
    ]

    gate = QualityGate()

    quality_result = gate.evaluate(
        findings
    )

    formatter = ReviewSummaryFormatter()

    result = formatter.format(
        findings=findings,
        quality_gate=quality_result,
    )

    assert "#### 🔵 Low" in result
    assert "#### 🔴 Critical" not in result
    assert "#### 🟠 High" not in result