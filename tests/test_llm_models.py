import pytest
from pydantic import ValidationError

from pr_reviewer.llm.models import LLMFinding, ReviewResponse
from pr_reviewer.review.models import Severity


def test_llm_finding_model():
    finding = LLMFinding(
        line_number=10,
        severity=Severity.LOW,
        rule_id="unused-variable",
        message="The variable is not used.",
        suggestion="Remove the variable.",
    )

    assert finding.line_number == 10
    assert finding.severity == Severity.LOW
    assert finding.rule_id == "unused-variable"


def test_llm_finding_rejects_invalid_line_number():
    with pytest.raises(ValidationError):
        LLMFinding(
            line_number=0,
            severity=Severity.LOW,
            rule_id="unused-variable",
            message="Unused variable.",
        )


def test_llm_finding_rejects_invalid_severity():
    with pytest.raises(ValidationError):
        LLMFinding(
            line_number=1,
            severity="unknown",
            rule_id="test-rule",
            message="Test issue.",
        )


def test_review_response_model():
    response = ReviewResponse(
        findings=[
            LLMFinding(
                line_number=1,
                severity=Severity.HIGH,
                rule_id="security-issue",
                message="Security problem.",
            )
        ]
    )

    assert len(response.findings) == 1
    assert response.findings[0].severity == Severity.HIGH