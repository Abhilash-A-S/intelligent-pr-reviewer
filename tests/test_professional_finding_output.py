from pr_reviewer.publishing.comment import InlineCommentFormatter
from pr_reviewer.review.models import ChangedFile, ChangedLine, Finding, FindingSource, Severity
from pr_reviewer.review.professionalizer import FindingProfessionalizer


def test_professionalizer_adds_category_issue_impact_and_source_evidence():
    changed_file = ChangedFile(
        file_path="src/payment.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/payment.ts",
                line_number=84,
                content="catch (error) {}",
            )
        ],
    )
    finding = Finding(
        file_path="src/payment.ts",
        line_number=84,
        severity=Severity.MEDIUM,
        rule_id="empty-catch-block",
        message="An empty catch block silently ignores an error.",
        suggestion="Handle or propagate the error.",
        source=FindingSource.STATIC,
    )

    enriched = FindingProfessionalizer.enrich(finding, changed_file)

    assert enriched.category == "reliability"
    assert enriched.issue == finding.message
    assert "silently" in enriched.impact.lower()
    assert enriched.evidence == "Changed line 84: catch (error) {}"


def test_professional_comment_uses_structured_review_sections():
    finding = Finding(
        file_path="src/payment.ts",
        line_number=84,
        severity=Severity.HIGH,
        rule_id="logic-error",
        message="Payment failure is swallowed after the API call fails.",
        suggestion="Propagate the failure or return an explicit failure result.",
        category="reliability",
        issue="Payment failure is swallowed after the API call fails.",
        impact="The caller may continue as though the payment succeeded.",
        evidence="The catch block does not rethrow or return a failure result.",
        source=FindingSource.LLM,
    )

    result = InlineCommentFormatter.format(finding)

    assert "**Category:** reliability" in result
    assert "**Issue:** Payment failure is swallowed" in result
    assert "**Impact:** The caller may continue" in result
    assert "**Evidence:** The catch block does not rethrow" in result
    assert "💡 **Suggestion**" in result
    assert "_Rule: `logic-error`_" in result


def test_unknown_rule_still_gets_professional_fallback_metadata():
    finding = Finding(
        file_path="src/file.xyz",
        line_number=2,
        severity=Severity.LOW,
        rule_id="custom-rule",
        message="Custom issue.",
    )

    enriched = FindingProfessionalizer.enrich(finding, None)

    assert enriched.category == "general"
    assert enriched.issue == "Custom issue."
    assert enriched.impact
