from pr_reviewer.context.models import RepositoryContext
from pr_reviewer.review.deduplicator import FindingDeduplicator
from pr_reviewer.review.framework_fact_validator import FrameworkFactValidator
from pr_reviewer.review.models import (
    ChangedFile,
    ChangedLine,
    Finding,
    Severity,
)
from pr_reviewer.review.normalizer import FindingNormalizer


def cf(path: str, content: str, line: int = 1) -> ChangedFile:
    return ChangedFile(
        file_path=path,
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path=path,
                line_number=line,
                content=(
                    content.splitlines()[0]
                    if content.splitlines()
                    else ""
                ),
            )
        ],
        full_content=content,
    )


def finding(
    path: str,
    line: int,
    rule: str,
    message: str,
    severity=Severity.HIGH,
    suggestion: str | None = None,
) -> Finding:
    return Finding(
        file_path=path,
        line_number=line,
        severity=severity,
        rule_id=rule,
        message=message,
        suggestion=suggestion,
    )


def react_context() -> RepositoryContext:
    return RepositoryContext(
        languages={"typescript"},
        framework="react",
        project_type="frontend-web",
        build_tools={"vite"},
        metadata_files=["vite.config.ts"],
    )


def test_framework_prefixed_secret_normalizes_to_canonical_secret():
    normalizer = FindingNormalizer()

    assert (
        normalizer.normalize_rule_id(
            "react-hardcoded-secret"
        )
        == "hardcoded-secret"
    )

    assert (
        normalizer.normalize_rule_id(
            "security-hardcoded-secret"
        )
        == "hardcoded-secret"
    )

    assert (
        normalizer.normalize_rule_id(
            "typescript-hardcoded-secret"
        )
        == "hardcoded-secret"
    )


def test_prefixed_secret_deduplicates_with_static_finding():
    normalizer = FindingNormalizer()
    deduplicator = FindingDeduplicator()

    static = finding(
        "src/App.tsx",
        23,
        "hardcoded-secret",
        "Hardcoded secret detected.",
        Severity.CRITICAL,
    )

    ai = finding(
        "src/App.tsx",
        22,
        "react-hardcoded-secret",
        "A hardcoded secret is present.",
        Severity.HIGH,
    )

    result = deduplicator.deduplicate(
        [
            normalizer.normalize(static),
            normalizer.normalize(ai),
        ]
    )

    assert len(result) == 1
    assert result[0].rule_id == "hardcoded-secret"
    assert result[0].severity == Severity.CRITICAL


def test_rejects_false_every_render_claim_for_empty_dependency_array():
    validator = FrameworkFactValidator()

    app = cf(
        "src/App.tsx",
        """
import { useEffect } from 'react';

useEffect(() => {
  console.log(count);
}, []);
""".strip(),
        4,
    )

    result = validator.validate(
        finding=finding(
            "src/App.tsx",
            4,
            "react-empty-dependency-array",
            (
                "The useEffect hook is triggered on every "
                "render because its dependency array is empty."
            ),
        ),
        changed_file=app,
        changed_files=[app],
        repository_context=react_context(),
    )

    assert result.accepted is False
    assert any(
        "empty dependency array"
        in reason
        for reason in result.reasons
    )


def test_preserves_correct_missing_dependency_explanation():
    validator = FrameworkFactValidator()

    app = cf(
        "src/App.tsx",
        """
import { useEffect } from 'react';

useEffect(() => {
  console.log(count);
}, []);
""".strip(),
        4,
    )

    result = validator.validate(
        finding=finding(
            "src/App.tsx",
            4,
            "react-use-effect-dependency",
            (
                "The effect captures count but count is "
                "missing from the dependency array, so the "
                "effect can observe a stale value."
            ),
        ),
        changed_file=app,
        changed_files=[app],
        repository_context=react_context(),
    )

    assert result.accepted is True


def test_rejects_hook_claim_when_hook_absent():
    validator = FrameworkFactValidator()

    main = cf(
        "src/main.tsx",
        """
import { createRoot } from 'react-dom/client';
createRoot(document.getElementById('root')!).render(<App />);
""".strip(),
        2,
    )

    result = validator.validate(
        finding=finding(
            "src/main.tsx",
            2,
            "react-use-effect-cleanup",
            "The useEffect hook is missing cleanup.",
        ),
        changed_file=main,
        changed_files=[main],
        repository_context=react_context(),
    )

    assert result.accepted is False


def test_generic_unknown_rule_is_not_stripped_aggressively():
    normalizer = FindingNormalizer()

    assert (
        normalizer.normalize_rule_id(
            "react-custom-business-rule"
        )
        == "react-custom-business-rule"
    )
