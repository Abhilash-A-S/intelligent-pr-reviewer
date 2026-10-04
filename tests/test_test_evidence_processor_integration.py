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


def repository_context() -> RepositoryContext:

    return RepositoryContext(
        languages={
            "typescript",
            "html",
        },
        framework="angular",
        project_type="frontend-web",
    )


def create_test_file() -> ChangedFile:

    return ChangedFile(
        file_path="src/app/app.spec.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app/app.spec.ts",
                line_number=20,
                content=(
                    "fixture.detectChanges();"
                ),
                diff_position=20,
            ),
            ChangedLine(
                file_path="src/app/app.spec.ts",
                line_number=23,
                content=(
                    "compiled.querySelector("
                    "'h1')?.textContent"
                ),
                diff_position=23,
            ),
        ],
        full_content=(
            "describe('App', () => {\n"
            "  it('renders title', () => {\n"
            "    const fixture = "
            "TestBed.createComponent(App);\n"
            "\n"
            "    fixture.detectChanges();\n"
            "\n"
            "    const compiled = "
            "fixture.nativeElement as HTMLElement;\n"
            "\n"
            "    expect(\n"
            "      compiled.querySelector("
            "'h1')?.textContent\n"
            "    ).toContain('Hello');\n"
            "  });\n"
            "});\n"
        ),
    )


def test_processor_rejects_unproven_async_wait_finding():
    processor = FindingProcessor()

    changed_file = create_test_file()

    finding = Finding(
        file_path="src/app/app.spec.ts",
        line_number=20,
        severity=Severity.HIGH,
        rule_id="async-waiting",
        message=(
            "The test should wait for the component "
            "to be initialized before making assertions."
        ),
        suggestion=(
            "Add await fixture.whenStable() before "
            "the assertion."
        ),
        diff_position=20,
    )

    result = processor.process(
        findings=[
            finding
        ],
        changed_files=[
            changed_file
        ],
        repository_context=repository_context(),
    )

    assert result == []


def test_processor_rejects_assertion_target_false_positive():
    processor = FindingProcessor()

    changed_file = create_test_file()

    finding = Finding(
        file_path="src/app/app.spec.ts",
        line_number=23,
        severity=Severity.HIGH,
        rule_id="content-selector",
        message=(
            "The test assumes the presence of an h1 "
            "element. This could fail if the component "
            "does not render an h1 element."
        ),
        suggestion=(
            "Check if the component actually renders "
            "an h1 element before making the assertion."
        ),
        diff_position=23,
    )

    result = processor.process(
        findings=[
            finding
        ],
        changed_files=[
            changed_file
        ],
        repository_context=repository_context(),
    )

    assert result == []


def test_processor_preserves_real_test_finding():
    processor = FindingProcessor()

    changed_file = ChangedFile(
        file_path="src/app/app.spec.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app/app.spec.ts",
                line_number=15,
                content="realService.deleteUser(10);",
                diff_position=15,
            )
        ],
        full_content=(
            "it('deletes user', () => {\n"
            "  realService.deleteUser(10);\n"
            "  expect(mockService.deleteUser)\n"
            "    .toHaveBeenCalledWith(10);\n"
            "});\n"
        ),
    )

    finding = Finding(
        file_path="src/app/app.spec.ts",
        line_number=15,
        severity=Severity.MEDIUM,
        rule_id="incorrect-mock-usage",
        message=(
            "The test invokes the real service while "
            "asserting against the mock service."
        ),
        suggestion=(
            "Invoke the configured mock or inject the "
            "mock service used by the assertion."
        ),
        diff_position=15,
    )

    result = processor.process(
        findings=[
            finding
        ],
        changed_files=[
            changed_file
        ],
        repository_context=repository_context(),
    )

    assert len(result) == 1

    assert (
        result[0].rule_id
        == "incorrect-mock-usage"
    )


def test_processor_preserves_real_async_test_problem():
    processor = FindingProcessor()

    changed_file = ChangedFile(
        file_path="src/app/app.spec.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app/app.spec.ts",
                line_number=12,
                content=(
                    "expect(component.loaded)"
                    ".toBe(true);"
                ),
                diff_position=12,
            )
        ],
        full_content=(
            "it('loads data', () => {\n"
            "  Promise.resolve().then(() => {\n"
            "    component.loaded = true;\n"
            "  });\n"
            "\n"
            "  expect(component.loaded).toBe(true);\n"
            "});\n"
        ),
    )

    finding = Finding(
        file_path="src/app/app.spec.ts",
        line_number=12,
        severity=Severity.MEDIUM,
        rule_id="missing-async-wait",
        message=(
            "The assertion executes before the "
            "Promise callback completes."
        ),
        suggestion=(
            "Wait for the Promise to complete before "
            "asserting the loaded state."
        ),
        diff_position=12,
    )

    result = processor.process(
        findings=[
            finding
        ],
        changed_files=[
            changed_file
        ],
        repository_context=repository_context(),
    )

    assert len(result) == 1

    assert (
        result[0].rule_id
        == "missing-async-wait"
    )


def test_processor_does_not_apply_test_rules_to_source_file():
    processor = FindingProcessor()

    changed_file = ChangedFile(
        file_path="src/app/app.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app/app.ts",
                line_number=30,
                content="loadData();",
                diff_position=30,
            )
        ],
        full_content=(
            "loadData();"
        ),
    )

    finding = Finding(
        file_path="src/app/app.ts",
        line_number=30,
        severity=Severity.MEDIUM,
        rule_id="async-waiting",
        message=(
            "The operation should wait before "
            "continuing."
        ),
        suggestion=(
            "Wait for completion."
        ),
        diff_position=30,
    )

    result = processor.process(
        findings=[
            finding
        ],
        changed_files=[
            changed_file
        ],
        repository_context=repository_context(),
    )

    assert len(result) == 1