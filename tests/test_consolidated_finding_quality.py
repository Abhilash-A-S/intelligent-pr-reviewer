from pr_reviewer.context.models import RepositoryContext
from pr_reviewer.detection.project import ProjectContext
from pr_reviewer.review.finding_policy import FindingPolicy
from pr_reviewer.review.finding_validator import FindingValidator
from pr_reviewer.review.framework_facts.angular import AngularFactValidator
from pr_reviewer.review.models import (
    ChangedFile,
    ChangedLine,
    Finding,
    Severity,
)


def make_finding(
    *,
    file_path: str,
    line_number: int,
    rule_id: str,
    message: str,
    suggestion: str | None = None,
    severity: Severity = Severity.MEDIUM,
) -> Finding:
    return Finding(
        file_path=file_path,
        line_number=line_number,
        severity=severity,
        rule_id=rule_id,
        message=message,
        suggestion=suggestion,
    )


def angular_context() -> RepositoryContext:
    return RepositoryContext(
        languages={"typescript", "html", "json"},
        framework="angular",
        project_type="frontend-web",
    )


def test_generic_validator_rejects_hypothetical_may_throw_claim():
    changed_file = ChangedFile(
        file_path="src/config.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/config.ts",
                line_number=10,
                content="const config = mergeConfig(a, b);",
            )
        ],
    )

    finding = make_finding(
        file_path="src/config.ts",
        line_number=10,
        rule_id="error-handling",
        severity=Severity.HIGH,
        message=(
            "The mergeConfig call may throw an error if the "
            "configuration is invalid, but it is not handled."
        ),
    )

    result = FindingValidator().validate(
        finding=finding,
        changed_file=changed_file,
    )

    assert result.accepted is False
    assert "Finding is speculative." in result.reasons


def test_generic_validator_rejects_explicit_uncertainty():
    changed_file = ChangedFile(
        file_path="src/view.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/view.ts",
                line_number=4,
                content="renderOutlet();",
            )
        ],
    )

    finding = make_finding(
        file_path="src/view.ts",
        line_number=4,
        rule_id="unnecessary-code",
        message=(
            "It is not clear whether this outlet is necessary "
            "and it can potentially be removed."
        ),
    )

    result = FindingValidator().validate(
        finding=finding,
        changed_file=changed_file,
    )

    assert result.accepted is False
    assert "Finding is speculative." in result.reasons


def test_generic_validator_preserves_certain_error_finding():
    changed_file = ChangedFile(
        file_path="src/parser.py",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/parser.py",
                line_number=12,
                content="value = payload['required']",
            )
        ],
    )

    finding = make_finding(
        file_path="src/parser.py",
        line_number=12,
        rule_id="missing-key-handling",
        message=(
            "The code directly indexes 'required'; when the key "
            "is absent this raises KeyError before fallback logic."
        ),
    )

    result = FindingValidator().validate(
        finding=finding,
        changed_file=changed_file,
    )

    assert result.accepted is True


def test_policy_rejects_known_low_value_review_noise():
    policy = FindingPolicy()

    for rule_id in (
        "font-family-optimization",
        "font-family-duplication",
        "unnecessary-router-outlet",
    ):
        finding = make_finding(
            file_path="src/example.html",
            line_number=1,
            rule_id=rule_id,
            message="Optional cleanup without a correctness defect.",
        )

        assert policy.apply(finding) is None


def test_policy_caps_generic_environment_variable_hardening_to_low():
    finding = make_finding(
        file_path="src/server.ts",
        line_number=55,
        rule_id="environment-variable-usage",
        severity=Severity.HIGH,
        message=(
            "Validate the PORT environment variable before use."
        ),
    )

    result = FindingPolicy().apply(finding)

    assert result is not None
    assert result.severity == Severity.LOW


def test_angular_rejects_required_with_component_input_binding_claim():
    changed_file = ChangedFile(
        file_path="src/app/app.config.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app/app.config.ts",
                line_number=11,
                content="provideRouter(routes),",
            )
        ],
        full_content=(
            "import { ApplicationConfig } from '@angular/core';\n"
            "import { provideRouter } from '@angular/router';\n"
            "export const appConfig: ApplicationConfig = {\n"
            "  providers: [provideRouter(routes)],\n"
            "};\n"
        ),
    )

    finding = make_finding(
        file_path="src/app/app.config.ts",
        line_number=11,
        rule_id="missing-dependency-injection",
        severity=Severity.HIGH,
        message=(
            "The provideRouter(routes) call is missing the "
            "withComponentInputBindings operator, which is "
            "recommended for standalone components."
        ),
        suggestion=(
            "Add withComponentInputBindings to provideRouter."
        ),
    )

    reasons = AngularFactValidator().validate(
        finding=finding,
        changed_file=changed_file,
        changed_files=[changed_file],
        repository_context=angular_context(),
    )

    assert reasons
    assert "optional Angular Router feature" in reasons[0]


def test_angular_rejects_false_root_host_claim_with_selector_evidence():
    index_file = ChangedFile(
        file_path="src/index.html",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/index.html",
                line_number=11,
                content="<app-root></app-root>",
            )
        ],
        full_content=(
            "<!doctype html>\n"
            "<html>\n"
            "<body>\n"
            "  <app-root></app-root>\n"
            "</body>\n"
            "</html>\n"
        ),
    )

    component_file = ChangedFile(
        file_path="src/app/app.ts",
        status="modified",
        full_content=(
            "import { Component } from '@angular/core';\n"
            "@Component({\n"
            "  selector: 'app-root',\n"
            "  standalone: true,\n"
            "  template: '<h1>Hello</h1>',\n"
            "})\n"
            "export class App {}\n"
        ),
    )

    finding = make_finding(
        file_path="src/index.html",
        line_number=11,
        rule_id="angular-template-syntax",
        message=(
            "The use of <app-root> without proper Angular "
            "component interaction can lead to unexpected behavior."
        ),
        suggestion=(
            "Ensure that <app-root> is properly defined."
        ),
    )

    reasons = AngularFactValidator().validate(
        finding=finding,
        changed_file=index_file,
        changed_files=[index_file, component_file],
        repository_context=angular_context(),
    )

    assert reasons
    assert "bootstrap-host evidence" in reasons[0]


def test_angular_fact_validation_is_project_aware_in_monorepo():
    react_file = ChangedFile(
        file_path="apps/react/package.json",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="apps/react/package.json",
                line_number=2,
                content='"name": "react-app"',
            )
        ],
        full_content='{"name":"react-app"}',
    )

    context = RepositoryContext(
        framework="angular",
        workspace="nx",
        projects=[
            ProjectContext(
                name="angular-app",
                root="apps/angular",
                framework="angular",
                project_type="frontend-web",
            ),
            ProjectContext(
                name="react-app",
                root="apps/react",
                framework="react",
                project_type="frontend-web",
            ),
        ],
    )

    finding = make_finding(
        file_path="apps/react/package.json",
        line_number=2,
        rule_id="project-name-folder-mismatch",
        message=(
            "The project name must match the folder name."
        ),
    )

    reasons = AngularFactValidator().validate(
        finding=finding,
        changed_file=react_file,
        changed_files=[react_file],
        repository_context=context,
    )

    assert reasons == []
