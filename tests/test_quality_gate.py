from pr_reviewer.review.models import Finding, Severity
from pr_reviewer.review.quality_gate import (
    QualityGate,
    QualityGateDecision,
)


def create_finding(
    severity: Severity,
) -> Finding:
    return Finding(
        file_path="src/app.js",
        line_number=10,
        severity=severity,
        rule_id="test-rule",
        message="Test finding.",
    )


def test_no_findings_passes():
    gate = QualityGate()

    result = gate.evaluate([])

    assert result.decision == QualityGateDecision.PASS
    assert result.total_findings == 0
    assert result.should_block_merge is False
    assert result.should_request_changes is False


def test_critical_blocks_merge():
    gate = QualityGate()

    findings = [
        create_finding(Severity.CRITICAL),
    ]

    result = gate.evaluate(findings)

    assert result.decision == QualityGateDecision.BLOCK
    assert result.critical_count == 1
    assert result.should_block_merge is True
    assert result.should_request_changes is True


def test_high_requests_changes():
    gate = QualityGate()

    findings = [
        create_finding(Severity.HIGH),
    ]

    result = gate.evaluate(findings)

    assert (
        result.decision
        == QualityGateDecision.REQUEST_CHANGES
    )

    assert result.high_count == 1
    assert result.should_block_merge is False
    assert result.should_request_changes is True


def test_medium_recommends_review():
    gate = QualityGate()

    findings = [
        create_finding(Severity.MEDIUM),
    ]

    result = gate.evaluate(findings)

    assert (
        result.decision
        == QualityGateDecision.REVIEW_RECOMMENDED
    )

    assert result.medium_count == 1
    assert result.should_block_merge is False


def test_low_is_non_blocking():
    gate = QualityGate()

    findings = [
        create_finding(Severity.LOW),
    ]

    result = gate.evaluate(findings)

    assert (
        result.decision
        == QualityGateDecision.NON_BLOCKING
    )

    assert result.low_count == 1
    assert result.should_block_merge is False


def test_suggestion_is_optional():
    gate = QualityGate()

    findings = [
        create_finding(Severity.SUGGESTION),
    ]

    result = gate.evaluate(findings)

    assert (
        result.decision
        == QualityGateDecision.OPTIONAL
    )

    assert result.suggestion_count == 1


def test_highest_severity_wins():
    gate = QualityGate()

    findings = [
        create_finding(Severity.SUGGESTION),
        create_finding(Severity.LOW),
        create_finding(Severity.MEDIUM),
        create_finding(Severity.HIGH),
        create_finding(Severity.CRITICAL),
    ]

    result = gate.evaluate(findings)

    assert result.decision == QualityGateDecision.BLOCK

    assert result.critical_count == 1
    assert result.high_count == 1
    assert result.medium_count == 1
    assert result.low_count == 1
    assert result.suggestion_count == 1

    assert result.total_findings == 5


def test_counts_multiple_findings():
    gate = QualityGate()

    findings = [
        create_finding(Severity.MEDIUM),
        create_finding(Severity.MEDIUM),
        create_finding(Severity.LOW),
        create_finding(Severity.LOW),
        create_finding(Severity.LOW),
        create_finding(Severity.SUGGESTION),
    ]

    result = gate.evaluate(findings)

    assert (
        result.decision
        == QualityGateDecision.REVIEW_RECOMMENDED
    )

    assert result.critical_count == 0
    assert result.high_count == 0
    assert result.medium_count == 2
    assert result.low_count == 3
    assert result.suggestion_count == 1

    assert result.total_findings == 6