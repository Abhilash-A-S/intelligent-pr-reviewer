import pytest

from pr_reviewer.review.models import (
    Finding,
    Severity,
)
from pr_reviewer.review.normalizer import (
    FindingNormalizer,
)


def create_finding(
    rule_id: str,
    severity: Severity = Severity.LOW,
    file_path: str = "src/app.js",
    line_number: int = 10,
    message: str = "Test finding.",
    suggestion: str | None = "Fix the issue.",
) -> Finding:

    return Finding(
        file_path=file_path,
        line_number=line_number,
        severity=severity,
        rule_id=rule_id,
        message=message,
        suggestion=suggestion,
    )


def test_normalizes_rule_id_format():
    assert (
        FindingNormalizer.normalize_rule_id(
            "Unused Variable"
        )
        == "unused-variable"
    )

    assert (
        FindingNormalizer.normalize_rule_id(
            "unused_variable"
        )
        == "unused-variable"
    )

    assert (
        FindingNormalizer.normalize_rule_id(
            "unused---variable"
        )
        == "unused-variable"
    )


@pytest.mark.parametrize(
    (
        "rule_id",
        "expected",
    ),
    [
        (
            "unused-var",
            "unused-variable",
        ),
        (
            "unused-constant",
            "unused-variable",
        ),
        (
            "unnecessary-variable",
            "unused-variable",
        ),
        (
            "unnecessary-constant",
            "unused-variable",
        ),
        (
            "dead-variable",
            "unused-variable",
        ),
        (
            "unused-local-variable",
            "unused-variable",
        ),
    ],
)
def test_canonicalizes_unused_variable_rules(
    rule_id: str,
    expected: str,
):
    assert (
        FindingNormalizer.normalize_rule_id(
            rule_id
        )
        == expected
    )


@pytest.mark.parametrize(
    "rule_id",
    [
        "console-log",
        "console-statement",
        "console-log-statement",
        "console-logging",
        "debug-console",
        "console-debug",
    ],
)
def test_canonicalizes_console_rules(
    rule_id: str,
):
    assert (
        FindingNormalizer.normalize_rule_id(
            rule_id
        )
        == "no-console"
    )


@pytest.mark.parametrize(
    "rule_id",
    [
        "debug-statement",
        "debugger-statement",
    ],
)
def test_canonicalizes_debugger_rules(
    rule_id: str,
):
    assert (
        FindingNormalizer.normalize_rule_id(
            rule_id
        )
        == "debugger"
    )


@pytest.mark.parametrize(
    "rule_id",
    [
        "unused-import-statement",
        "unnecessary-import",
        "redundant-import",
    ],
)
def test_canonicalizes_unused_import_rules(
    rule_id: str,
):
    assert (
        FindingNormalizer.normalize_rule_id(
            rule_id
        )
        == "unused-import"
    )


@pytest.mark.parametrize(
    "rule_id",
    [
        "unused-argument",
        "unused-function-argument",
        "unused-method-parameter",
    ],
)
def test_canonicalizes_unused_parameter_rules(
    rule_id: str,
):
    assert (
        FindingNormalizer.normalize_rule_id(
            rule_id
        )
        == "unused-parameter"
    )


@pytest.mark.parametrize(
    "rule_id",
    [
        "missing-await",
        "missing-async-await",
        "unhandled-promise",
        "async-await-issue",
        "async-error",
    ],
)
def test_canonicalizes_async_rules(
    rule_id: str,
):
    assert (
        FindingNormalizer.normalize_rule_id(
            rule_id
        )
        == "async-issue"
    )


@pytest.mark.parametrize(
    "rule_id",
    [
        "missing-error-handling",
        "unhandled-error",
        "unhandled-exception",
        "missing-exception-handling",
        "exception-not-handled",
    ],
)
def test_canonicalizes_error_handling_rules(
    rule_id: str,
):
    assert (
        FindingNormalizer.normalize_rule_id(
            rule_id
        )
        == "error-handling"
    )


@pytest.mark.parametrize(
    "rule_id",
    [
        "null-reference",
        "null-dereference",
        "possible-null-reference",
        "none-dereference",
        "nil-dereference",
    ],
)
def test_canonicalizes_null_safety_rules(
    rule_id: str,
):
    assert (
        FindingNormalizer.normalize_rule_id(
            rule_id
        )
        == "null-safety"
    )


@pytest.mark.parametrize(
    "rule_id",
    [
        "resource-leak",
        "missing-resource-cleanup",
        "resource-not-closed",
        "unclosed-resource",
    ],
)
def test_canonicalizes_resource_cleanup_rules(
    rule_id: str,
):
    assert (
        FindingNormalizer.normalize_rule_id(
            rule_id
        )
        == "resource-cleanup"
    )


@pytest.mark.parametrize(
    "rule_id",
    [
        "missing-unsubscribe",
        "subscription-leak",
        "unclosed-subscription",
    ],
)
def test_canonicalizes_subscription_cleanup_rules(
    rule_id: str,
):
    assert (
        FindingNormalizer.normalize_rule_id(
            rule_id
        )
        == "subscription-cleanup"
    )


@pytest.mark.parametrize(
    "rule_id",
    [
        "event-listener-leak",
        "missing-listener-cleanup",
    ],
)
def test_canonicalizes_listener_cleanup_rules(
    rule_id: str,
):
    assert (
        FindingNormalizer.normalize_rule_id(
            rule_id
        )
        == "listener-cleanup"
    )


@pytest.mark.parametrize(
    "rule_id",
    [
        "duplicate-code",
        "duplicated-code",
        "duplicated-logic",
        "code-duplication",
    ],
)
def test_canonicalizes_duplicate_logic_rules(
    rule_id: str,
):
    assert (
        FindingNormalizer.normalize_rule_id(
            rule_id
        )
        == "duplicate-logic"
    )


@pytest.mark.parametrize(
    "rule_id",
    [
        "performance-issue",
        "performance-problem",
        "performance-concern",
    ],
)
def test_canonicalizes_performance_rules(
    rule_id: str,
):
    assert (
        FindingNormalizer.normalize_rule_id(
            rule_id
        )
        == "performance"
    )


@pytest.mark.parametrize(
    "rule_id",
    [
        "code-maintainability",
        "maintainability-issue",
        "maintainability-problem",
    ],
)
def test_canonicalizes_maintainability_rules(
    rule_id: str,
):
    assert (
        FindingNormalizer.normalize_rule_id(
            rule_id
        )
        == "maintainability"
    )


@pytest.mark.parametrize(
    "rule_id",
    [
        "accessibility-issue",
        "accessibility-problem",
        "a11y",
        "a11y-issue",
    ],
)
def test_canonicalizes_accessibility_rules(
    rule_id: str,
):
    assert (
        FindingNormalizer.normalize_rule_id(
            rule_id
        )
        == "accessibility"
    )


def test_unknown_rule_is_preserved():

    result = (
        FindingNormalizer.normalize_rule_id(
            "sql-injection"
        )
    )

    assert result == "sql-injection"


def test_hardcoded_secret_gets_minimum_critical_severity():

    normalizer = FindingNormalizer()

    finding = create_finding(
        rule_id="hardcoded-password",
        severity=Severity.LOW,
    )

    result = normalizer.normalize(
        finding
    )

    assert (
        result.rule_id
        == "hardcoded-secret"
    )

    assert (
        result.severity
        == Severity.CRITICAL
    )


def test_hardcoded_secret_preserves_critical():

    normalizer = FindingNormalizer()

    finding = create_finding(
        rule_id="hardcoded-secret",
        severity=Severity.CRITICAL,
    )

    result = normalizer.normalize(
        finding
    )

    assert (
        result.severity
        == Severity.CRITICAL
    )


def test_normalize_trims_fields():

    normalizer = FindingNormalizer()

    finding = create_finding(
        rule_id=" unused-variable ",
        file_path=" src/app.js ",
        message=" Test message. ",
        suggestion=" Remove it. ",
    )

    result = normalizer.normalize(
        finding
    )

    assert (
        result.file_path
        == "src/app.js"
    )

    assert (
        result.rule_id
        == "unused-variable"
    )

    assert (
        result.message
        == "Test message."
    )

    assert (
        result.suggestion
        == "Remove it."
    )


def test_normalize_preserves_none_suggestion():

    normalizer = FindingNormalizer()

    finding = create_finding(
        rule_id="unused-variable",
        suggestion=None,
    )

    result = normalizer.normalize(
        finding
    )

    assert result.suggestion is None


def test_normalize_preserves_diff_position():

    normalizer = FindingNormalizer()

    finding = Finding(
        file_path="src/app.js",
        line_number=10,
        severity=Severity.LOW,
        rule_id="unused-var",
        message="Unused variable.",
        suggestion="Remove it.",
        diff_position=25,
    )

    result = normalizer.normalize(
        finding
    )

    assert result.diff_position == 25


def test_console_log_statement_matches_static_rule():

    normalizer = FindingNormalizer()

    ai_finding = create_finding(
        file_path="script.js",
        line_number=171,
        rule_id="console-log-statement",
        severity=Severity.LOW,
        message=(
            "Unnecessary console log statement."
        ),
    )

    result = normalizer.normalize(
        ai_finding
    )

    assert (
        result.rule_id
        == "no-console"
    )

    assert (
        result.severity
        == Severity.LOW
    )