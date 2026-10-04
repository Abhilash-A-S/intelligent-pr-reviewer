from pr_reviewer.context.models import (
    RepositoryContext,
)
from pr_reviewer.review.framework_evidence_validator import (
    FrameworkEvidenceValidator,
)
from pr_reviewer.review.models import (
    ChangedFile,
    ChangedLine,
    Finding,
    Severity,
)


def create_finding(
    rule_id: str = "standalone-component-import",
    message: str = (
        "Using the component itself as an import in "
        "TestBed configuration is not recommended."
    ),
    suggestion: str | None = (
        "Use a module instead."
    ),
) -> Finding:

    return Finding(
        file_path="src/app/app.spec.ts",
        line_number=8,
        severity=Severity.MEDIUM,
        rule_id=rule_id,
        message=message,
        suggestion=suggestion,
    )


def create_test_file() -> ChangedFile:

    return ChangedFile(
        file_path="src/app/app.spec.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app/app.spec.ts",
                line_number=8,
                content="imports: [App],",
            )
        ],
        full_content=(
            "import { TestBed } "
            "from '@angular/core/testing';\n"
            "import { App } from './app';\n"
            "\n"
            "describe('App', () => {\n"
            "  beforeEach(async () => {\n"
            "    await TestBed.configureTestingModule({\n"
            "      imports: [App],\n"
            "    }).compileComponents();\n"
            "  });\n"
            "});\n"
        ),
    )


def create_component_file(
    decorator_content: str,
) -> ChangedFile:

    return ChangedFile(
        file_path="src/app/app.ts",
        status="modified",
        full_content=(
            "import { Component } "
            "from '@angular/core';\n"
            "\n"
            "@Component({\n"
            f"{decorator_content}"
            "})\n"
            "export class App {}\n"
        ),
    )


def create_package_file(
    version: str,
) -> ChangedFile:

    return ChangedFile(
        file_path="package.json",
        status="modified",
        full_content=(
            "{\n"
            '  "dependencies": {\n'
            f'    "@angular/core": "{version}"\n'
            "  }\n"
            "}\n"
        ),
    )


def angular_context() -> RepositoryContext:

    return RepositoryContext(
        languages={
            "typescript",
        },
        framework="angular",
        project_type="frontend-web",
    )


def test_rejects_false_finding_for_explicit_standalone_component():
    validator = FrameworkEvidenceValidator()

    test_file = create_test_file()

    component_file = create_component_file(
        decorator_content=(
            "  selector: 'app-root',\n"
            "  standalone: true,\n"
        )
    )

    result = validator.validate(
        finding=create_finding(),
        changed_file=test_file,
        changed_files=[
            test_file,
            component_file,
        ],
        repository_context=angular_context(),
    )

    assert result.accepted is False

    assert (
        "contradicts Angular "
        "standalone-component evidence"
        in result.reasons[0]
    )


def test_rejects_false_finding_when_component_has_imports():
    validator = FrameworkEvidenceValidator()

    test_file = create_test_file()

    component_file = create_component_file(
        decorator_content=(
            "  selector: 'app-root',\n"
            "  imports: [RouterOutlet],\n"
        )
    )

    result = validator.validate(
        finding=create_finding(),
        changed_file=test_file,
        changed_files=[
            test_file,
            component_file,
        ],
        repository_context=angular_context(),
    )

    assert result.accepted is False


def test_rejects_false_finding_for_angular_19_default_standalone():
    validator = FrameworkEvidenceValidator()

    test_file = create_test_file()

    component_file = create_component_file(
        decorator_content=(
            "  selector: 'app-root',\n"
            "  template: '<h1>Hello</h1>',\n"
        )
    )

    package_file = create_package_file(
        "^19.2.0"
    )

    result = validator.validate(
        finding=create_finding(),
        changed_file=test_file,
        changed_files=[
            test_file,
            component_file,
            package_file,
        ],
        repository_context=angular_context(),
    )

    assert result.accepted is False


def test_rejects_angular_testbed_incorrect_import_rule():
    """
    Regression test for actual LLM output:

    angular-testbed-incorrect-import
    """

    validator = FrameworkEvidenceValidator()

    test_file = create_test_file()

    component_file = create_component_file(
        decorator_content=(
            "  selector: 'app-root',\n"
            "  imports: [RouterOutlet],\n"
            "  templateUrl: './app.html',\n"
        )
    )

    finding = create_finding(
        rule_id="angular-testbed-incorrect-import",
        message=(
            "The `App` module should not be imported "
            "directly into TestBed. Use a standalone "
            "component configuration instead."
        ),
        suggestion=(
            "Replace `imports: [App]` with "
            "`imports: [AppComponent]` where "
            "`AppComponent` is the standalone component "
            "being tested."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=test_file,
        changed_files=[
            test_file,
            component_file,
        ],
        repository_context=angular_context(),
    )

    assert result.accepted is False

    assert (
        "contradicts Angular "
        "standalone-component evidence"
        in result.reasons[0]
    )


def test_rejects_changed_llm_rule_id_when_message_proves_same_claim():
    """
    The validator should not depend on one exact LLM
    rule identifier.
    """

    validator = FrameworkEvidenceValidator()

    test_file = create_test_file()

    component_file = create_component_file(
        decorator_content=(
            "  selector: 'app-root',\n"
            "  standalone: true,\n"
        )
    )

    finding = create_finding(
        rule_id="angular-component-test-configuration",
        message=(
            "The component should not be imported "
            "directly into TestBed."
        ),
        suggestion=(
            "Use an NgModule instead."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=test_file,
        changed_files=[
            test_file,
            component_file,
        ],
        repository_context=angular_context(),
    )

    assert result.accepted is False


def test_preserves_finding_for_explicit_non_standalone_component():
    validator = FrameworkEvidenceValidator()

    test_file = create_test_file()

    component_file = create_component_file(
        decorator_content=(
            "  selector: 'app-root',\n"
            "  standalone: false,\n"
        )
    )

    package_file = create_package_file(
        "^20.0.0"
    )

    result = validator.validate(
        finding=create_finding(),
        changed_file=test_file,
        changed_files=[
            test_file,
            component_file,
            package_file,
        ],
        repository_context=angular_context(),
    )

    assert result.accepted is True
    assert result.reasons == []


def test_preserves_claim_when_standalone_state_cannot_be_proven():
    validator = FrameworkEvidenceValidator()

    test_file = create_test_file()

    component_file = create_component_file(
        decorator_content=(
            "  selector: 'app-root',\n"
            "  template: '<h1>Hello</h1>',\n"
        )
    )

    package_file = create_package_file(
        "^18.2.0"
    )

    result = validator.validate(
        finding=create_finding(),
        changed_file=test_file,
        changed_files=[
            test_file,
            component_file,
            package_file,
        ],
        repository_context=angular_context(),
    )

    assert result.accepted is True


def test_non_angular_repository_is_not_affected():
    validator = FrameworkEvidenceValidator()

    test_file = create_test_file()

    component_file = create_component_file(
        decorator_content=(
            "  selector: 'app-root',\n"
            "  standalone: true,\n"
        )
    )

    context = RepositoryContext(
        framework="react",
    )

    result = validator.validate(
        finding=create_finding(),
        changed_file=test_file,
        changed_files=[
            test_file,
            component_file,
        ],
        repository_context=context,
    )

    assert result.accepted is True


def test_unrelated_angular_finding_is_preserved():
    validator = FrameworkEvidenceValidator()

    changed_file = ChangedFile(
        file_path="src/app/app.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app/app.ts",
                line_number=30,
                content=(
                    "interval(1000).subscribe("
                    "value => this.counter = value);"
                ),
            )
        ],
    )

    finding = Finding(
        file_path="src/app/app.ts",
        line_number=30,
        severity=Severity.MEDIUM,
        rule_id="rxjs-subscription-cleanup",
        message=(
            "The interval subscription is not cleaned "
            "up when the component is destroyed."
        ),
        suggestion=(
            "Clean up the subscription when the "
            "component is destroyed."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
        changed_files=[
            changed_file
        ],
        repository_context=angular_context(),
    )

    assert result.accepted is True


def test_normal_non_test_file_is_not_affected():
    validator = FrameworkEvidenceValidator()

    changed_file = ChangedFile(
        file_path="src/app/app.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app/app.ts",
                line_number=20,
                content="saveUser();",
            )
        ],
    )

    finding = Finding(
        file_path="src/app/app.ts",
        line_number=20,
        severity=Severity.MEDIUM,
        rule_id="incorrect-api-usage",
        message=(
            "The API is called with an invalid argument."
        ),
        suggestion=(
            "Pass the expected argument."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
        changed_files=[
            changed_file
        ],
        repository_context=angular_context(),
    )

    assert result.accepted is True

def create_angular_template_finding(
    rule_id: str,
    message: str,
    suggestion: str,
    line_number: int,
) -> Finding:
    return Finding(
        file_path="src/app/review-test.component.html",
        line_number=line_number,
        severity=Severity.MEDIUM,
        rule_id=rule_id,
        message=message,
        suggestion=suggestion,
    )


def create_angular_template_file(line_number: int, line: str) -> ChangedFile:
    padding = ["<div></div>"] * (line_number - 1)
    content = "\n".join([*padding, line]) + "\n"
    return ChangedFile(
        file_path="src/app/review-test.component.html",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app/review-test.component.html",
                line_number=line_number,
                content=line,
                diff_position=line_number,
            )
        ],
        full_content=content,
    )


def test_rejects_listener_cleanup_claim_on_angular_template_event_binding():
    validator = FrameworkEvidenceValidator()
    template_file = create_angular_template_file(
        23,
        '<button (click)="triggerDebugger()">Debug</button>',
    )

    finding = create_angular_template_finding(
        rule_id="listener-cleanup",
        message=(
            "Potential memory leak. Ensure that the debugger is properly "
            "detached when no longer needed."
        ),
        suggestion="Detach the listener during cleanup.",
        line_number=23,
    )

    result = validator.validate(
        finding=finding,
        changed_file=template_file,
        changed_files=[template_file],
        repository_context=angular_context(),
    )

    assert result.accepted is False
    assert "managed by Angular" in result.reasons[0]


def test_rejects_implementation_error_handling_claim_anchored_only_to_template_call():
    validator = FrameworkEvidenceValidator()
    template_file = create_angular_template_file(
        11,
        '<button (click)="loadUserWithoutErrorHandler()">Load</button>',
    )

    finding = create_angular_template_finding(
        rule_id="error-handling",
        message="Missing error handling for loadUserWithoutErrorHandler.",
        suggestion="Add try-catch or other error handling.",
        line_number=11,
    )

    result = validator.validate(
        finding=finding,
        changed_file=template_file,
        changed_files=[template_file],
        repository_context=angular_context(),
    )

    assert result.accepted is False
    assert "component/service implementation" in result.reasons[0]


def test_does_not_reject_unrelated_template_finding_without_event_binding():
    validator = FrameworkEvidenceValidator()
    template_file = create_angular_template_file(
        4,
        '<img src="avatar.png">',
    )

    finding = create_angular_template_finding(
        rule_id="accessibility",
        message="Image is missing alternative text.",
        suggestion="Add an alt attribute.",
        line_number=4,
    )

    result = validator.validate(
        finding=finding,
        changed_file=template_file,
        changed_files=[template_file],
        repository_context=angular_context(),
    )

    assert result.accepted is True


def test_rejects_disguised_duplicate_logic_claim_for_valid_standalone_testbed_import():
    validator = FrameworkEvidenceValidator()
    test_file = create_test_file()
    component_file = create_component_file(
        decorator_content=(
            "  selector: 'app-root',\n"
            "  standalone: true,\n"
            "  template: '<h1>Hello</h1>',\n"
        )
    )

    finding = create_finding(
        rule_id="duplicate-logic",
        message=(
            "The 'App' component is imported directly in the imports array, "
            "which is unnecessary. Standalone components do not require an "
            "additional NgModule or AppModule for testing."
        ),
        suggestion=(
            "Replace 'App' with the actual standalone component class or "
            "provider if applicable."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=test_file,
        changed_files=[test_file, component_file],
        repository_context=angular_context(),
    )

    assert result.accepted is False
    assert any(
        "valid in TestBed imports" in reason
        for reason in result.reasons
    )


def test_rejects_security_claim_anchored_only_to_angular_template_method_call():
    validator = FrameworkEvidenceValidator()
    template_file = create_angular_template_file(
        23,
        '<button (click)="triggerDebugger()">Debug</button>',
    )

    finding = create_angular_template_finding(
        rule_id="security",
        message=(
            "The method 'triggerDebugger' may expose sensitive debugging "
            "information if not properly secured."
        ),
        suggestion=(
            "Remove or secure the triggerDebugger method to prevent "
            "sensitive information exposure."
        ),
        line_number=23,
    )

    result = validator.validate(
        finding=finding,
        changed_file=template_file,
        changed_files=[template_file],
        repository_context=angular_context(),
    )

    assert result.accepted is False
    assert any(
        "component/service implementation" in reason
        for reason in result.reasons
    )


def test_rejects_api_misuse_claim_that_standalone_component_cannot_be_in_testbed_imports():
    validator = FrameworkEvidenceValidator()
    test_file = create_test_file()
    component_file = create_component_file(
        decorator_content=(
            "  selector: 'app-root',\n"
            "  standalone: true,\n"
            "  template: '<h1>Hello</h1>',\n"
        )
    )

    finding = create_finding(
        rule_id="api-misuse",
        message=(
            "The component 'App' is being imported into the test "
            "configuration, which is incorrect. Standalone components "
            "should not be imported directly."
        ),
        suggestion=(
            "Use a different component reference in the imports array."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=test_file,
        changed_files=[test_file, component_file],
        repository_context=angular_context(),
    )

    assert result.accepted is False
    assert any(
        "valid in TestBed imports" in reason
        for reason in result.reasons
    )
