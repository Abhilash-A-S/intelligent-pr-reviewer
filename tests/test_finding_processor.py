from pr_reviewer.context.models import (
    RepositoryContext,
)
from pr_reviewer.review.models import (
    ChangedFile,
    ChangedLine,
    Finding,
    Severity,
)
from pr_reviewer.review.processor import (
    FindingProcessor,
)


def create_changed_file(
    file_path: str = "src/app.js",
    line_number: int = 10,
) -> ChangedFile:

    return ChangedFile(
        file_path=file_path,
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path=file_path,
                line_number=line_number,
                content="const value = 10;",
                diff_position=5,
            )
        ],
    )


def create_finding(
    file_path: str = "src/app.js",
    line_number: int = 10,
    severity: Severity = Severity.LOW,
    rule_id: str = "no-console",
    message: str = (
        "Console logging was added."
    ),
) -> Finding:

    return Finding(
        file_path=file_path,
        line_number=line_number,
        severity=severity,
        rule_id=rule_id,
        message=message,
        suggestion=(
            "Remove the console statement."
        ),
        diff_position=5,
    )


def test_processor_normalizes_deduplicates_and_applies_policy():
    processor = FindingProcessor()

    changed_file = create_changed_file()

    findings = [
        create_finding(
            severity=Severity.LOW,
            rule_id="console-log",
            message="Console detected.",
        ),
        create_finding(
            severity=Severity.MEDIUM,
            rule_id="no-console",
            message="Debug console detected.",
        ),
    ]

    result = processor.process(
        findings=findings,
        changed_files=[
            changed_file
        ],
    )

    assert len(result) == 1

    finding = result[0]

    assert finding.rule_id == "no-console"

    assert (
        finding.severity
        == Severity.LOW
    )


def test_processor_rejects_speculative_finding():
    processor = FindingProcessor()

    changed_file = create_changed_file()

    findings = [
        create_finding(
            message=(
                "This might cause a runtime problem."
            )
        )
    ]

    result = processor.process(
        findings=findings,
        changed_files=[
            changed_file
        ],
    )

    assert result == []


def test_processor_rejects_non_commentable_line():
    processor = FindingProcessor()

    changed_file = create_changed_file(
        line_number=10
    )

    findings = [
        create_finding(
            line_number=99
        )
    ]

    result = processor.process(
        findings=findings,
        changed_files=[
            changed_file
        ],
    )

    assert result == []


def test_processor_rejects_wrong_file_type_rule():
    processor = FindingProcessor()

    changed_file = create_changed_file(
        file_path="src/app.js"
    )

    findings = [
        create_finding(
            file_path="src/app.js",
            rule_id="css-syntax",
            message=(
                "The CSS syntax is invalid."
            ),
        )
    ]

    result = processor.process(
        findings=findings,
        changed_files=[
            changed_file
        ],
    )

    assert result == []


def test_processor_keeps_valid_finding():
    processor = FindingProcessor()

    changed_file = create_changed_file()

    finding = create_finding(
        rule_id="unused-variable",
        severity=Severity.LOW,
        message=(
            "The variable is declared "
            "but never used."
        ),
    )

    result = processor.process(
        findings=[finding],
        changed_files=[
            changed_file
        ],
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


def test_processor_rejects_unknown_file():
    processor = FindingProcessor()

    changed_file = create_changed_file(
        file_path="src/app.js"
    )

    finding = create_finding(
        file_path="src/other.js",
        line_number=10,
    )

    result = processor.process(
        findings=[finding],
        changed_files=[
            changed_file
        ],
    )

    assert result == []


def test_processor_rejects_policy_blocked_rule():
    processor = FindingProcessor()

    changed_file = create_changed_file(
        file_path="index.html"
    )

    finding = create_finding(
        file_path="index.html",
        rule_id="external-css-not-minified",
        severity=Severity.HIGH,
        message=(
            "The linked stylesheet is not minified."
        ),
    )

    result = processor.process(
        findings=[finding],
        changed_files=[
            changed_file
        ],
    )

    assert result == []


def test_processor_caps_unused_variable_severity():
    processor = FindingProcessor()

    changed_file = create_changed_file()

    finding = create_finding(
        rule_id="unused-variable",
        severity=Severity.HIGH,
        message=(
            "The variable is declared "
            "but never used."
        ),
    )

    result = processor.process(
        findings=[finding],
        changed_files=[
            changed_file
        ],
    )

    assert len(result) == 1

    assert (
        result[0].severity
        == Severity.LOW
    )


def test_processor_rejects_false_angular_standalone_import_finding():
    processor = FindingProcessor()

    test_file = ChangedFile(
        file_path="src/app/app.spec.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app/app.spec.ts",
                line_number=8,
                content="imports: [App],",
                diff_position=8,
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

    app_file = ChangedFile(
        file_path="src/app/app.ts",
        status="modified",
        full_content=(
            "import { Component } "
            "from '@angular/core';\n"
            "import { RouterOutlet } "
            "from '@angular/router';\n"
            "\n"
            "@Component({\n"
            "  selector: 'app-root',\n"
            "  imports: [RouterOutlet],\n"
            "  templateUrl: './app.html',\n"
            "})\n"
            "export class App {}\n"
        ),
    )

    finding = Finding(
        file_path="src/app/app.spec.ts",
        line_number=8,
        severity=Severity.MEDIUM,
        rule_id="standalone-component-import",
        message=(
            "Using the component itself as an import "
            "in TestBed configuration is not recommended."
        ),
        suggestion=(
            "Use a standalone component or a module."
        ),
        diff_position=8,
    )

    context = RepositoryContext(
        languages={
            "typescript",
        },
        framework="angular",
        project_type="frontend-web",
    )

    result = processor.process(
        findings=[
            finding
        ],
        changed_files=[
            test_file,
            app_file,
        ],
        repository_context=context,
    )

    assert result == []


def test_processor_preserves_real_angular_rxjs_finding():
    processor = FindingProcessor()

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
                diff_position=30,
            )
        ],
        full_content=(
            "interval(1000).subscribe("
            "value => this.counter = value);"
        ),
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
        diff_position=30,
    )

    context = RepositoryContext(
        languages={
            "typescript",
        },
        framework="angular",
        project_type="frontend-web",
    )

    result = processor.process(
        findings=[
            finding
        ],
        changed_files=[
            changed_file
        ],
        repository_context=context,
    )

    assert len(result) == 1

    assert (
        result[0].rule_id
        == "rxjs-subscription-cleanup"
    )