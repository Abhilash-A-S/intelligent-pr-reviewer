import pytest

from pr_reviewer.review.finding_policy import (
    FindingPolicy,
)
from pr_reviewer.review.models import (
    Finding,
    Severity,
)


def create_finding(
    rule_id: str = "runtime-error",
    severity: Severity = Severity.MEDIUM,
    file_path: str = "src/app.js",
    line_number: int = 10,
    message: str = "Concrete issue detected.",
    suggestion: str | None = "Fix the concrete issue.",
) -> Finding:

    return Finding(
        file_path=file_path,
        line_number=line_number,
        severity=severity,
        rule_id=rule_id,
        message=message,
        suggestion=suggestion,
    )


def test_accepts_normal_finding():
    policy = FindingPolicy()

    finding = create_finding(
        rule_id="runtime-error",
        severity=Severity.HIGH,
    )

    result = policy.apply(
        finding
    )

    assert result is not None

    assert (
        result.rule_id
        == "runtime-error"
    )

    assert (
        result.severity
        == Severity.HIGH
    )


def test_rejects_exact_low_value_rule():
    policy = FindingPolicy()

    finding = create_finding(
        rule_id="unnecessary-uppercase-heading",
        severity=Severity.LOW,
    )

    result = policy.apply(
        finding
    )

    assert result is None


def test_rejects_typography_rule_prefix():
    policy = FindingPolicy()

    finding = create_finding(
        rule_id="typography-heading-case",
        severity=Severity.MEDIUM,
    )

    result = policy.apply(
        finding
    )

    assert result is None


def test_rejects_cosmetic_rule_prefix():
    policy = FindingPolicy()

    finding = create_finding(
        rule_id="cosmetic-spacing-improvement",
        severity=Severity.LOW,
    )

    result = policy.apply(
        finding
    )

    assert result is None


def test_rejects_consistency_rule_prefix():
    policy = FindingPolicy()

    finding = create_finding(
        rule_id="consistent-font-weight",
        severity=Severity.LOW,
    )

    result = policy.apply(
        finding
    )

    assert result is None


def test_rejects_visual_preference_rule_prefix():
    policy = FindingPolicy()

    finding = create_finding(
        rule_id="visual-preference-color",
        severity=Severity.LOW,
    )

    result = policy.apply(
        finding
    )

    assert result is None


# ======================================================
# Empty code / no-op suggestions
# ======================================================


@pytest.mark.parametrize(
    "rule_id",
    [
        "suggestion-empty-block",
        "suggestion-empty-function",
        "empty-block",
        "empty-function",
        "unnecessary-empty-block",
        "unnecessary-empty-function",
        "empty-code-block",
        "empty-method",
        "empty-callback",
    ],
)
def test_rejects_empty_code_noise(
    rule_id: str,
):
    policy = FindingPolicy()

    finding = create_finding(
        rule_id=rule_id,
        severity=Severity.LOW,
        message=(
            "The block is empty."
        ),
        suggestion=(
            "Add a comment explaining why "
            "the block is empty."
        ),
    )

    result = policy.apply(
        finding
    )

    assert result is None


def test_rejects_unknown_suggestion_empty_rule_by_prefix():
    policy = FindingPolicy()

    finding = create_finding(
        rule_id="suggestion-empty-handler",
        severity=Severity.LOW,
    )

    result = policy.apply(
        finding
    )

    assert result is None


def test_does_not_reject_real_error_inside_function():
    """
    We reject empty-code suggestions, not genuine
    correctness findings involving a function.
    """

    policy = FindingPolicy()

    finding = create_finding(
        rule_id="error-handling",
        severity=Severity.HIGH,
        message=(
            "The function ignores an error returned "
            "by the database operation."
        ),
        suggestion=(
            "Handle or propagate the database error."
        ),
    )

    result = policy.apply(
        finding
    )

    assert result is not None

    assert (
        result.rule_id
        == "error-handling"
    )


def test_does_not_reject_framework_lifecycle_issue():
    """
    Framework-specific correctness issues must remain
    eligible even when the code happens to involve a
    lifecycle method.
    """

    policy = FindingPolicy()

    finding = create_finding(
        rule_id="subscription-cleanup",
        severity=Severity.HIGH,
        file_path="src/app.component.ts",
        message=(
            "The subscription remains active after "
            "the component is destroyed."
        ),
        suggestion=(
            "Dispose the subscription during component "
            "destruction."
        ),
    )

    result = policy.apply(
        finding
    )

    assert result is not None


# ======================================================
# Accessibility
# ======================================================


def test_preserves_real_accessibility_finding():
    policy = FindingPolicy()

    finding = create_finding(
        rule_id="missing-form-label",
        severity=Severity.MEDIUM,
        message=(
            "The form control has no accessible label."
        ),
    )

    result = policy.apply(
        finding
    )

    assert result is not None

    assert (
        result.rule_id
        == "missing-form-label"
    )


def test_caps_generic_accessibility_severity():
    policy = FindingPolicy()

    finding = create_finding(
        rule_id="accessibility",
        severity=Severity.HIGH,
    )

    result = policy.apply(
        finding
    )

    assert result is not None

    assert (
        result.severity
        == Severity.MEDIUM
    )


# ======================================================
# Unused code
# ======================================================


def test_caps_unused_variable_to_low():
    policy = FindingPolicy()

    finding = create_finding(
        rule_id="unused-variable",
        severity=Severity.HIGH,
    )

    result = policy.apply(
        finding
    )

    assert result is not None

    assert (
        result.severity
        == Severity.LOW
    )


def test_normalizes_unused_variable_alias():
    policy = FindingPolicy()

    finding = create_finding(
        rule_id="unused-constant",
        severity=Severity.MEDIUM,
    )

    result = policy.apply(
        finding
    )

    assert result is not None

    assert (
        result.rule_id
        == "unused-variable"
    )

    assert (
        result.severity
        == Severity.LOW
    )


def test_normalizes_unnecessary_constant_alias():
    policy = FindingPolicy()

    finding = create_finding(
        rule_id="unnecessary-constant",
        severity=Severity.MEDIUM,
    )

    result = policy.apply(
        finding
    )

    assert result is not None

    assert (
        result.rule_id
        == "unused-variable"
    )

    assert (
        result.severity
        == Severity.LOW
    )


# ======================================================
# Console logging
# ======================================================


def test_normalizes_console_alias():
    policy = FindingPolicy()

    finding = create_finding(
        rule_id="console-log",
        severity=Severity.HIGH,
    )

    result = policy.apply(
        finding
    )

    assert result is not None

    assert (
        result.rule_id
        == "no-console"
    )

    assert (
        result.severity
        == Severity.LOW
    )


def test_normalizes_console_log_statement_alias():
    policy = FindingPolicy()

    finding = create_finding(
        rule_id="console-log-statement",
        severity=Severity.MEDIUM,
    )

    result = policy.apply(
        finding
    )

    assert result is not None

    assert (
        result.rule_id
        == "no-console"
    )

    assert (
        result.severity
        == Severity.LOW
    )


# ======================================================
# Debugger
# ======================================================


def test_caps_debugger_to_medium():
    policy = FindingPolicy()

    finding = create_finding(
        rule_id="debugger",
        severity=Severity.CRITICAL,
    )

    result = policy.apply(
        finding
    )

    assert result is not None

    assert (
        result.severity
        == Severity.MEDIUM
    )


def test_normalizes_debugger_alias():
    policy = FindingPolicy()

    finding = create_finding(
        rule_id="debugger-statement",
        severity=Severity.HIGH,
    )

    result = policy.apply(
        finding
    )

    assert result is not None

    assert (
        result.rule_id
        == "debugger"
    )

    assert (
        result.severity
        == Severity.MEDIUM
    )


# ======================================================
# Severity ceilings
# ======================================================


def test_does_not_raise_existing_severity():
    policy = FindingPolicy()

    finding = create_finding(
        rule_id="performance",
        severity=Severity.LOW,
    )

    result = policy.apply(
        finding
    )

    assert result is not None

    # Maximum is MEDIUM, but an existing LOW finding
    # must remain LOW.
    assert (
        result.severity
        == Severity.LOW
    )


def test_caps_performance_to_medium():
    policy = FindingPolicy()

    finding = create_finding(
        rule_id="performance",
        severity=Severity.CRITICAL,
    )

    result = policy.apply(
        finding
    )

    assert result is not None

    assert (
        result.severity
        == Severity.MEDIUM
    )


def test_caps_duplicate_logic_to_medium():
    policy = FindingPolicy()

    finding = create_finding(
        rule_id="duplicate-logic",
        severity=Severity.HIGH,
    )

    result = policy.apply(
        finding
    )

    assert result is not None

    assert (
        result.severity
        == Severity.MEDIUM
    )


def test_caps_maintainability_to_medium():
    policy = FindingPolicy()

    finding = create_finding(
        rule_id="maintainability",
        severity=Severity.CRITICAL,
    )

    result = policy.apply(
        finding
    )

    assert result is not None

    assert (
        result.severity
        == Severity.MEDIUM
    )


def test_password_strength_is_non_blocking():
    policy = FindingPolicy()

    finding = create_finding(
        rule_id="missing-password-strength-check",
        severity=Severity.HIGH,
    )

    result = policy.apply(
        finding
    )

    assert result is not None

    assert (
        result.severity
        == Severity.SUGGESTION
    )


# ======================================================
# Collections
# ======================================================


def test_apply_all_removes_rejected_findings():
    policy = FindingPolicy()

    findings = [
        create_finding(
            rule_id="runtime-error",
        ),
        create_finding(
            rule_id="unnecessary-uppercase-heading",
        ),
        create_finding(
            rule_id="formatting-spacing",
        ),
        create_finding(
            rule_id="suggestion-empty-function",
        ),
    ]

    result = policy.apply_all(
        findings
    )

    assert len(result) == 1

    assert (
        result[0].rule_id
        == "runtime-error"
    )


def test_apply_all_preserves_order():
    policy = FindingPolicy()

    first = create_finding(
        rule_id="runtime-error",
        line_number=10,
    )

    rejected = create_finding(
        rule_id="suggestion-empty-block",
        line_number=20,
    )

    second = create_finding(
        rule_id="error-handling",
        line_number=30,
    )

    result = policy.apply_all(
        [
            first,
            rejected,
            second,
        ]
    )

    assert result == [
        first,
        second,
    ]

def test_caps_generic_error_handling_to_medium():
    policy = FindingPolicy()
    finding = create_finding(rule_id="error-handling", severity=Severity.CRITICAL)
    result = policy.apply(finding)
    assert result is not None
    assert result.severity == Severity.MEDIUM


def test_caps_generic_return_value_handling_to_low():
    policy = FindingPolicy()
    finding = create_finding(rule_id="return-value-handling", severity=Severity.HIGH)
    result = policy.apply(finding)
    assert result is not None
    assert result.severity == Severity.LOW
