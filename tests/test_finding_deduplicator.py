from pr_reviewer.review.deduplicator import (
    FindingDeduplicator,
)
from pr_reviewer.review.models import Finding, Severity


def make_finding(
    *,
    file_path: str = "src/app.js",
    line_number: int = 10,
    severity: Severity = Severity.LOW,
    rule_id: str = "no-console",
    message: str = "Finding message.",
) -> Finding:
    return Finding(
        file_path=file_path,
        line_number=line_number,
        severity=severity,
        rule_id=rule_id,
        message=message,
    )


def test_removes_exact_duplicate():
    deduplicator = FindingDeduplicator()

    result = deduplicator.deduplicate(
        [
            make_finding(
                message="Console statement detected.",
            ),
            make_finding(
                message="Console statement detected.",
            ),
        ]
    )

    assert len(result) == 1


def test_keeps_different_rules_on_same_line():
    deduplicator = FindingDeduplicator()

    result = deduplicator.deduplicate(
        [
            make_finding(
                rule_id="no-console",
            ),
            make_finding(
                severity=Severity.HIGH,
                rule_id="security-issue",
            ),
        ]
    )

    assert len(result) == 2


def test_keeps_different_lines_for_same_rule():
    deduplicator = FindingDeduplicator()

    result = deduplicator.deduplicate(
        [
            make_finding(
                line_number=10,
            ),
            make_finding(
                line_number=20,
            ),
        ]
    )

    assert len(result) == 2


def test_keeps_stronger_exact_duplicate():
    deduplicator = FindingDeduplicator()

    result = deduplicator.deduplicate(
        [
            make_finding(
                severity=Severity.LOW,
                rule_id="security-issue",
                message="Possible security issue.",
            ),
            make_finding(
                severity=Severity.HIGH,
                rule_id="security-issue",
                message="Confirmed security issue.",
            ),
        ]
    )

    assert len(result) == 1
    assert result[0].severity == Severity.HIGH
    assert (
        result[0].message
        == "Confirmed security issue."
    )


def test_canonicalized_rules_are_deduplicated():
    from pr_reviewer.review.normalizer import (
        FindingNormalizer,
    )

    normalizer = FindingNormalizer()
    deduplicator = FindingDeduplicator()

    static_finding = Finding(
        file_path="script.js",
        line_number=172,
        severity=Severity.LOW,
        rule_id="unused-variable",
        message=(
            "Variable 'abc' is declared "
            "but never used."
        ),
        suggestion=(
            "Remove the unused variable."
        ),
    )

    ai_finding = Finding(
        file_path="script.js",
        line_number=172,
        severity=Severity.SUGGESTION,
        rule_id="unnecessary-constant",
        message=(
            "The constant 'abc' is not used."
        ),
        suggestion=(
            "Remove the constant."
        ),
    )

    normalized = [
        normalizer.normalize(
            static_finding
        ),
        normalizer.normalize(
            ai_finding
        ),
    ]

    result = deduplicator.deduplicate(
        normalized
    )

    assert len(result) == 1
    assert (
        result[0].rule_id
        == "unused-variable"
    )
    assert (
        result[0].severity
        == Severity.LOW
    )


def test_semantic_secret_duplicate_on_nearby_lines_is_merged():
    deduplicator = FindingDeduplicator()

    static_finding = make_finding(
        file_path="src/App.tsx",
        line_number=23,
        severity=Severity.CRITICAL,
        rule_id="hardcoded-secret",
        message="Hardcoded secret detected.",
    )

    ai_finding = make_finding(
        file_path="src/App.tsx",
        line_number=22,
        severity=Severity.HIGH,
        rule_id="security-hardcoded-secret",
        message="A hardcoded secret is present.",
    )

    result = deduplicator.deduplicate(
        [
            static_finding,
            ai_finding,
        ]
    )

    assert len(result) == 1
    assert (
        result[0].rule_id
        == "hardcoded-secret"
    )
    assert (
        result[0].severity
        == Severity.CRITICAL
    )


def test_semantic_duplicate_keeps_stronger_ai_finding_when_needed():
    deduplicator = FindingDeduplicator()

    result = deduplicator.deduplicate(
        [
            make_finding(
                line_number=20,
                severity=Severity.MEDIUM,
                rule_id="hardcoded-secret",
            ),
            make_finding(
                line_number=21,
                severity=Severity.CRITICAL,
                rule_id="security-hardcoded-secret",
            ),
        ]
    )

    assert len(result) == 1
    assert (
        result[0].severity
        == Severity.CRITICAL
    )
    assert (
        result[0].rule_id
        == "security-hardcoded-secret"
    )


def test_same_semantic_family_far_apart_is_not_merged():
    deduplicator = FindingDeduplicator()

    result = deduplicator.deduplicate(
        [
            make_finding(
                line_number=10,
                rule_id="hardcoded-secret",
            ),
            make_finding(
                line_number=50,
                severity=Severity.HIGH,
                rule_id="security-hardcoded-secret",
            ),
        ]
    )

    assert len(result) == 2


def test_different_semantic_families_on_nearby_lines_are_not_merged():
    deduplicator = FindingDeduplicator()

    result = deduplicator.deduplicate(
        [
            make_finding(
                line_number=10,
                rule_id="unused-variable",
            ),
            make_finding(
                line_number=11,
                severity=Severity.HIGH,
                rule_id="react-use-effect-cleanup",
            ),
        ]
    )

    assert len(result) == 2


def test_paths_are_compared_cross_platform_and_case_insensitively():
    deduplicator = FindingDeduplicator()

    result = deduplicator.deduplicate(
        [
            make_finding(
                file_path=r"SRC\App.tsx",
                line_number=23,
                severity=Severity.CRITICAL,
                rule_id="hardcoded-secret",
            ),
            make_finding(
                file_path="src/app.tsx",
                line_number=22,
                severity=Severity.HIGH,
                rule_id="security-hardcoded-secret",
            ),
        ]
    )

    assert len(result) == 1


def test_loose_equality_static_and_ai_findings_on_nearby_lines_are_merged():
    deduplicator = FindingDeduplicator()
    result = deduplicator.deduplicate([
        make_finding(
            file_path="src/app.ts",
            line_number=20,
            severity=Severity.MEDIUM,
            rule_id="loose-equality",
            message="Loose equality comparison was added.",
        ),
        make_finding(
            file_path="src/app.ts",
            line_number=21,
            severity=Severity.HIGH,
            rule_id="typescript-loose-equality",
            message="Use of == can cause coercion bugs.",
        ),
    ])
    assert len(result) == 1
    assert result[0].severity == Severity.HIGH


def test_distinct_adjacent_secrets_are_not_merged():
    deduplicator = FindingDeduplicator()
    result = deduplicator.deduplicate([
        make_finding(line_number=12, severity=Severity.CRITICAL, rule_id="hardcoded-secret", message="Secret in 'apiKey'."),
        make_finding(line_number=13, severity=Severity.CRITICAL, rule_id="hardcoded-secret", message="Secret in 'databasePassword'."),
        make_finding(line_number=14, severity=Severity.CRITICAL, rule_id="hardcoded-secret", message="Secret in 'jwtSecret'."),
    ])
    assert len(result) == 3


def test_distinct_adjacent_unused_variables_are_not_merged():
    deduplicator = FindingDeduplicator()
    result = deduplicator.deduplicate([
        make_finding(line_number=12, rule_id="unused-variable", message="Variable 'apiKey' is unused."),
        make_finding(line_number=13, rule_id="unused-variable", message="Variable 'databasePassword' is unused."),
        make_finding(line_number=14, rule_id="unused-variable", message="Variable 'jwtSecret' is unused."),
    ])
    assert len(result) == 3
