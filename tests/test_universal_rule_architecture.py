from pr_reviewer.review.finding_ownership_validator import FindingOwnershipValidator
from pr_reviewer.review.finding_policy import FindingPolicy
from pr_reviewer.review.models import (
    ChangedFile,
    ChangedLine,
    Finding,
    FindingSource,
    Severity,
)
from pr_reviewer.review.normalizer import FindingNormalizer
from pr_reviewer.review.processor import FindingProcessor
from pr_reviewer.review.rules import DEFAULT_RULE_REGISTRY, AIPolicy, RuleOwner


def finding(
    rule_id: str,
    *,
    line: int = 10,
    message: str = "Concrete issue.",
    source: FindingSource = FindingSource.LLM,
    severity: Severity = Severity.MEDIUM,
) -> Finding:
    return Finding(
        file_path="src/example.ts",
        line_number=line,
        severity=severity,
        rule_id=rule_id,
        message=message,
        suggestion="Fix the concrete issue.",
        source=source,
    )


def test_registry_is_capability_based_not_language_based():
    rule = DEFAULT_RULE_REGISTRY.get("unused-variable")
    assert rule is not None
    assert rule.owner == RuleOwner.STATIC
    assert "symbol-analysis" in rule.capabilities
    assert not hasattr(rule, "languages")


def test_registry_canonicalizes_llm_equality_wording():
    assert DEFAULT_RULE_REGISTRY.resolve("equality-comparison") == "loose-equality"
    assert DEFAULT_RULE_REGISTRY.resolve("comparison_operator") == "loose-equality"


def test_registry_exposes_only_ai_creatable_semantic_categories():
    ai_rules = set(DEFAULT_RULE_REGISTRY.ai_creatable_rule_ids())
    assert "logic-error" in ai_rules
    assert "error-handling" in ai_rules
    assert "api-misuse" in ai_rules
    assert "unused-variable" not in ai_rules
    assert "hardcoded-secret" not in ai_rules


def test_unknown_llm_rule_is_rejected():
    result = FindingOwnershipValidator().validate(
        finding("made-up-language-specific-rule"),
        authoritative_findings=[],
    )
    assert result.accepted is False
    assert "not registered" in result.reasons[0]


def test_llm_cannot_invent_static_owned_rule_without_authoritative_evidence():
    result = FindingOwnershipValidator().validate(
        finding("unused-variable", message="Variable 'result' is never used."),
        authoritative_findings=[],
    )
    assert result.accepted is False
    assert "owned by deterministic/framework analysis" in result.reasons[0]


def test_llm_duplicate_of_static_owned_rule_is_admitted_for_deduplication():
    static = finding(
        "unused-variable",
        line=10,
        message="Variable 'result' is declared but never used.",
        source=FindingSource.STATIC,
        severity=Severity.LOW,
    )
    ai = finding(
        "unused-var",
        line=12,
        message="The variable 'result' is assigned but never used.",
    )
    ai = FindingNormalizer().normalize(ai)

    result = FindingOwnershipValidator().validate(ai, [static])
    assert result.accepted is True


def test_subject_sensitive_static_rule_does_not_match_different_identifier():
    static = finding(
        "unused-variable",
        line=10,
        message="Variable 'count' is declared but never used.",
        source=FindingSource.STATIC,
        severity=Severity.LOW,
    )
    ai = finding(
        "unused-variable",
        line=11,
        message="Variable 'result' is declared but never used.",
    )

    result = FindingOwnershipValidator().validate(ai, [static])
    assert result.accepted is False


def test_registered_semantic_ai_rule_can_continue_to_evidence_validation():
    result = FindingOwnershipValidator().validate(
        finding("logic-error", message="The success branch returns the failure value."),
        authoritative_findings=[],
    )
    assert result.accepted is True
    assert DEFAULT_RULE_REGISTRY.get("logic-error").ai_policy == AIPolicy.VALIDATE


def test_normalizer_preserves_finding_provenance():
    normalized = FindingNormalizer().normalize(
        finding("comparison-operator", source=FindingSource.LLM)
    )
    assert normalized.rule_id == "loose-equality"
    assert normalized.source == FindingSource.LLM


def test_policy_uses_registry_severity_ceiling():
    result = FindingPolicy().apply(
        finding(
            "explicit-any",
            severity=Severity.HIGH,
            source=FindingSource.STATIC,
        )
    )
    assert result is not None
    assert result.severity == Severity.LOW


def test_processor_blocks_typescript_llm_static_noise_and_unknown_rule():
    changed = ChangedFile(
        file_path="src/example.ts",
        status="modified",
        changed_lines=[
            ChangedLine("src/example.ts", 10, "const result = 1;"),
            ChangedLine("src/example.ts", 20, "if (a == b) return true;"),
            ChangedLine("src/example.ts", 30, "await doWork();"),
        ],
        full_content=(
            "\n" * 9
            + "const result = 1;\n"
            + "\n" * 9
            + "if (a == b) return true;\n"
            + "\n" * 9
            + "await doWork();\n"
        ),
    )

    static_unused = finding(
        "unused-variable",
        line=10,
        message="Variable 'result' is declared but never used.",
        source=FindingSource.STATIC,
        severity=Severity.LOW,
    )
    static_equality = finding(
        "loose-equality",
        line=20,
        message="Loose equality comparison was added.",
        source=FindingSource.STATIC,
    )
    ai_duplicate_unused = finding(
        "unused-variable",
        line=10,
        message="Variable 'result' is assigned a value but never used.",
    )
    ai_duplicate_equality = finding(
        "equality-comparison",
        line=20,
        message="Using loose equality can compare different data types.",
    )
    ai_invented = finding(
        "async-await",
        line=30,
        message="Using await without a local catch may reject.",
    )

    result = FindingProcessor().process(
        [
            static_unused,
            static_equality,
            ai_duplicate_unused,
            ai_duplicate_equality,
            ai_invented,
        ],
        [changed],
    )

    assert [(item.rule_id, item.line_number) for item in result] == [
        ("unused-variable", 10),
        ("loose-equality", 20),
    ]


def test_framework_owned_rule_requires_authoritative_framework_finding():
    validator = FindingOwnershipValidator()
    ai = finding("effect-cleanup", message="Effect starts a timer without cleanup.")
    assert validator.validate(ai, []).accepted is False

    framework = finding(
        "effect-cleanup",
        message="Effect starts a timer without cleanup.",
        source=FindingSource.FRAMEWORK,
    )
    assert validator.validate(ai, [framework]).accepted is True


def test_current_typescript_llm_noise_cannot_expand_rule_vocabulary():
    validator = FindingOwnershipValidator()
    assert validator.validate(
        finding("unused-promise", line=200, message="The returned Promise is not being handled."),
        [],
    ).accepted is False
    assert validator.validate(
        finding("async-await", line=204, message="Await without local catch can reject."),
        [],
    ).accepted is False
