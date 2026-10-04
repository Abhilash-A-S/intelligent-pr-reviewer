from pr_reviewer.review.finding_ownership_validator import FindingOwnershipValidator
from pr_reviewer.review.models import Finding, FindingSource, Severity


def finding(rule_id, line, message, source=FindingSource.LLM, **kwargs):
    return Finding(
        file_path="src/example.ts",
        line_number=line,
        severity=Severity.MEDIUM,
        rule_id=rule_id,
        message=message,
        source=source,
        **kwargs,
    )


def test_ai_duplicate_logic_cannot_repeat_authoritative_unreachable_root_cause():
    validator = FindingOwnershipValidator()
    authoritative = finding(
        "unreachable-code",
        245,
        "This statement is unreachable because control flow exits earlier.",
        FindingSource.STATIC,
    )
    ai = finding(
        "duplicate-logic",
        243,
        "The console.log statement is unreachable and will never be executed.",
        issue="The console.log statement is unreachable and will never be executed.",
        evidence='Changed line 243: return "ACTIVE";',
    )

    result = validator.validate(ai, [authoritative])

    assert result.accepted is False
    assert "same root cause" in result.reasons[0]


def test_ai_maintainability_wording_cannot_repeat_authoritative_unreachable_root_cause():
    validator = FindingOwnershipValidator()
    authoritative = finding(
        "unreachable-code",
        50,
        "This statement is unreachable.",
        FindingSource.STATIC,
    )
    ai = finding(
        "maintainability",
        48,
        "Code after this return will never be executed.",
        issue="Dead code after return makes the function harder to understand.",
    )

    assert validator.validate(ai, [authoritative]).accepted is False


def test_legitimate_duplicate_logic_near_unreachable_finding_is_not_suppressed():
    validator = FindingOwnershipValidator()
    authoritative = finding(
        "unreachable-code",
        50,
        "This statement is unreachable.",
        FindingSource.STATIC,
    )
    ai = finding(
        "duplicate-logic",
        52,
        "The same validation branch is duplicated in two separate conditions.",
        issue="Two conditions implement the same validation logic.",
    )

    assert validator.validate(ai, [authoritative]).accepted is True


def test_ai_semantic_timer_cleanup_cannot_repeat_authoritative_timer_root_cause():
    validator = FindingOwnershipValidator()
    authoritative = finding(
        "setinterval-without-timer-reference",
        100,
        "setInterval is started without retaining the returned timer reference.",
        FindingSource.STATIC,
    )
    ai = finding(
        "resource-cleanup",
        102,
        "The timer cannot be cleaned up because the setInterval handle is not retained.",
        suggestion="Store the timer handle and call clearInterval.",
    )

    assert validator.validate(ai, [authoritative]).accepted is False


def test_ai_different_resource_cleanup_is_not_suppressed_by_timer_finding():
    validator = FindingOwnershipValidator()
    authoritative = finding(
        "setinterval-without-timer-reference",
        100,
        "setInterval is started without retaining the returned timer reference.",
        FindingSource.STATIC,
    )
    ai = finding(
        "resource-cleanup",
        102,
        "A file handle opened here is never closed on the error path.",
        suggestion="Close the file handle in a finally block.",
    )

    assert validator.validate(ai, [authoritative]).accepted is True


def test_subject_sensitive_root_causes_do_not_merge_distinct_adjacent_secrets():
    validator = FindingOwnershipValidator()
    authoritative = finding(
        "hardcoded-secret",
        10,
        "Hardcoded credential or secret detected in 'apiKey'.",
        FindingSource.STATIC,
    )
    ai = finding(
        "security",
        11,
        "A hard-coded secret is present in 'databasePassword'.",
    )

    assert validator.validate(ai, [authoritative]).accepted is True
