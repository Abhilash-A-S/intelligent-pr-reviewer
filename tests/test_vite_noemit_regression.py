from pr_reviewer.context.models import RepositoryContext
from pr_reviewer.review.framework_facts.typescript_build import (
    TypeScriptBuildFactValidator,
)
from pr_reviewer.review.models import (
    ChangedFile,
    ChangedLine,
    Finding,
    Severity,
)


def create_config(
    content: str,
    file_path: str = "tsconfig.app.json",
) -> ChangedFile:
    return ChangedFile(
        file_path=file_path,
        status="modified",
        language="json",
        patch="",
        changed_lines=[
            ChangedLine(
                file_path=file_path,
                line_number=1,
                content="{",
            )
        ],
        full_content=content,
    )


def create_finding(
    rule_id: str = "tsconfig-noemit",
    message: str = (
        "No emit mode can make debugging and "
        "incremental builds less efficient."
    ),
) -> Finding:
    return Finding(
        file_path="tsconfig.app.json",
        line_number=1,
        severity=Severity.MEDIUM,
        rule_id=rule_id,
        message=message,
        suggestion=(
            "Reconsider the use of noEmit if it "
            "is not strictly necessary."
        ),
    )


def vite_context() -> RepositoryContext:
    return RepositoryContext(
        framework="react",
        project_type="frontend-web",
        build_tools={"vite"},
        metadata_files=[
            "vite.config.ts",
            "tsconfig.app.json",
        ],
    )


def test_rejects_noemit_warning_for_vite_tsconfig():
    validator = (
        TypeScriptBuildFactValidator()
    )

    config = create_config(
        """
{
  "compilerOptions": {
    "noEmit": true,
    "strict": true
  },
  "include": ["src"]
}
""".strip()
    )

    reasons = validator.validate(
        finding=create_finding(),
        changed_file=config,
        changed_files=[config],
        repository_context=vite_context(),
    )

    assert reasons
    assert (
        "Vite/TypeScript"
        in reasons[0]
    )


def test_rejects_alternate_no_emit_rule_wording():
    validator = (
        TypeScriptBuildFactValidator()
    )

    config = create_config(
        """
{
  "compilerOptions": {
    "noEmit": true
  }
}
""".strip()
    )

    reasons = validator.validate(
        finding=create_finding(
            rule_id="typescript-no-emit-build-output",
            message=(
                "Disabling emit prevents TypeScript "
                "from producing build output."
            ),
        ),
        changed_file=config,
        changed_files=[config],
        repository_context=vite_context(),
    )

    assert reasons


def test_preserves_noemit_finding_when_noemit_is_false():
    validator = (
        TypeScriptBuildFactValidator()
    )

    config = create_config(
        """
{
  "compilerOptions": {
    "noEmit": false
  }
}
""".strip()
    )

    reasons = validator.validate(
        finding=create_finding(),
        changed_file=config,
        changed_files=[config],
        repository_context=vite_context(),
    )

    assert reasons == []


def test_preserves_noemit_finding_without_vite_evidence():
    validator = (
        TypeScriptBuildFactValidator()
    )

    config = create_config(
        """
{
  "compilerOptions": {
    "noEmit": true
  }
}
""".strip()
    )

    context = RepositoryContext(
        framework="unknown",
        build_tools=set(),
        metadata_files=[],
    )

    reasons = validator.validate(
        finding=create_finding(),
        changed_file=config,
        changed_files=[config],
        repository_context=context,
    )

    assert reasons == []


def test_preserves_unrelated_tsconfig_finding():
    validator = (
        TypeScriptBuildFactValidator()
    )

    config = create_config(
        """
{
  "compilerOptions": {
    "noEmit": true,
    "strict": false
  }
}
""".strip()
    )

    unrelated = Finding(
        file_path="tsconfig.app.json",
        line_number=1,
        severity=Severity.MEDIUM,
        rule_id="typescript-strict-disabled",
        message=(
            "Strict type checking is disabled."
        ),
    )

    reasons = validator.validate(
        finding=unrelated,
        changed_file=config,
        changed_files=[config],
        repository_context=vite_context(),
    )

    assert reasons == []
