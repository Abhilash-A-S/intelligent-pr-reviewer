from pr_reviewer.publishing.comment import (
    InlineCommentFormatter,
)
from pr_reviewer.review.models import Finding, Severity


def create_finding(
    severity: Severity,
) -> Finding:
    return Finding(
        file_path="src/app.js",
        line_number=10,
        severity=severity,
        rule_id="test-rule",
        message="Test review message.",
        suggestion="Test improvement suggestion.",
    )


def test_critical_comment():
    finding = create_finding(
        Severity.CRITICAL
    )

    result = InlineCommentFormatter.format(
        finding
    )

    assert (
        "🔴 **Critical** — Must fix"
        in result
    )


def test_high_comment():
    finding = create_finding(
        Severity.HIGH
    )

    result = InlineCommentFormatter.format(
        finding
    )

    assert (
        "🟠 **High** — Should fix before merge"
        in result
    )


def test_medium_comment():
    finding = create_finding(
        Severity.MEDIUM
    )

    result = InlineCommentFormatter.format(
        finding
    )

    assert (
        "🟡 **Medium** — Recommended to fix"
        in result
    )


def test_low_comment():
    finding = create_finding(
        Severity.LOW
    )

    result = InlineCommentFormatter.format(
        finding
    )

    assert (
        "🔵 **Low** — Minor improvement"
        in result
    )


def test_suggestion_comment():
    finding = create_finding(
        Severity.SUGGESTION
    )

    result = InlineCommentFormatter.format(
        finding
    )

    assert (
        "🟢 **Suggestion** — Optional improvement"
        in result
    )


def test_comment_contains_message():
    finding = create_finding(
        Severity.LOW
    )

    result = InlineCommentFormatter.format(
        finding
    )

    assert "Test review message." in result


def test_comment_contains_suggestion():
    finding = create_finding(
        Severity.LOW
    )

    result = InlineCommentFormatter.format(
        finding
    )

    assert "💡 **Suggestion**" in result

    assert (
        "Test improvement suggestion."
        in result
    )


def test_comment_contains_rule_id():
    finding = create_finding(
        Severity.LOW
    )

    result = InlineCommentFormatter.format(
        finding
    )

    assert "_Rule: `test-rule`_" in result


def test_comment_contains_duplicate_marker():
    finding = create_finding(
        Severity.LOW
    )

    result = InlineCommentFormatter.format(
        finding
    )

    assert (
        "<!-- intelligent-pr-reviewer:"
        "test-rule:"
        "src/app.js:"
        "10 -->"
        in result
    )


def test_comment_without_suggestion():
    finding = Finding(
        file_path="src/app.js",
        line_number=10,
        severity=Severity.MEDIUM,
        rule_id="error-handling",
        message="Error handling is missing.",
        suggestion=None,
    )

    result = InlineCommentFormatter.format(
        finding
    )

    assert "Error handling is missing." in result
    assert "💡 **Suggestion**" not in result