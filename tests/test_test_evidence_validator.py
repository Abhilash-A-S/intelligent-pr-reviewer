from pr_reviewer.review.models import (
    ChangedFile,
    ChangedLine,
    Finding,
    Severity,
)
from pr_reviewer.review.test_evidence_validator import (
    TestEvidenceValidator,
)


def create_finding(
    rule_id: str,
    message: str,
    suggestion: str | None = None,
    line_number: int = 20,
) -> Finding:

    return Finding(
        file_path="src/app/app.spec.ts",
        line_number=line_number,
        severity=Severity.HIGH,
        rule_id=rule_id,
        message=message,
        suggestion=suggestion,
    )


def create_test_file(
    full_content: str,
    line_number: int = 20,
    changed_content: str = "expect(value).toBe(true);",
) -> ChangedFile:

    return ChangedFile(
        file_path="src/app/app.spec.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app/app.spec.ts",
                line_number=line_number,
                content=changed_content,
            )
        ],
        full_content=full_content,
    )


def test_rejects_missing_async_wait_without_async_evidence():
    validator = TestEvidenceValidator()

    changed_file = create_test_file(
        full_content=(
            "it('renders the title', () => {\n"
            "  const fixture = createFixture();\n"
            "  fixture.detectChanges();\n"
            "  expect(fixture.componentInstance.title)\n"
            "    .toBe('Hello');\n"
            "});\n"
        )
    )

    finding = create_finding(
        rule_id="async-waiting",
        message=(
            "The test should wait for the component "
            "to be initialized before making assertions."
        ),
        suggestion=(
            "Add await fixture.whenStable() before "
            "the assertion."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
    )

    assert result.accepted is False

    assert (
        "without concrete async evidence"
        in result.reasons[0]
    )


def test_preserves_async_wait_finding_when_await_exists():
    validator = TestEvidenceValidator()

    changed_file = create_test_file(
        full_content=(
            "it('loads data', async () => {\n"
            "  await service.load();\n"
            "  expect(component.data).toBeTruthy();\n"
            "});\n"
        )
    )

    finding = create_finding(
        rule_id="async-waiting",
        message=(
            "The test may assert before asynchronous "
            "work has completed."
        ),
        suggestion=(
            "Wait for the asynchronous operation."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
    )

    assert result.accepted is True


def test_preserves_async_wait_finding_when_promise_exists():
    validator = TestEvidenceValidator()

    changed_file = create_test_file(
        full_content=(
            "it('loads data', () => {\n"
            "  Promise.resolve().then(() => {\n"
            "    component.ready = true;\n"
            "  });\n"
            "  expect(component.ready).toBe(true);\n"
            "});\n"
        )
    )

    finding = create_finding(
        rule_id="missing-async-wait",
        message=(
            "The assertion may run before the Promise "
            "callback finishes."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
    )

    assert result.accepted is True


def test_rejects_element_assumption_finding_for_intentional_assertion():
    validator = TestEvidenceValidator()

    changed_file = create_test_file(
        full_content=(
            "it('renders title', () => {\n"
            "  fixture.detectChanges();\n"
            "  const compiled = "
            "fixture.nativeElement as HTMLElement;\n"
            "  expect(\n"
            "    compiled.querySelector('h1')?.textContent\n"
            "  ).toContain('Hello');\n"
            "});\n"
        ),
        line_number=23,
        changed_content=(
            "compiled.querySelector('h1')?.textContent"
        ),
    )

    finding = create_finding(
        rule_id="content-selector",
        line_number=23,
        message=(
            "The test assumes the presence of an h1 "
            "element and could fail if it is missing."
        ),
        suggestion=(
            "Check if the element exists before making "
            "the assertion."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
    )

    assert result.accepted is False

    assert (
        "intentional test assertion"
        in result.reasons[0]
    )


def test_rejects_changed_rule_id_when_message_has_same_claim():
    validator = TestEvidenceValidator()

    changed_file = create_test_file(
        full_content=(
            "it('renders title', () => {\n"
            "  expect(\n"
            "    fixture.nativeElement"
            ".querySelector('h1')?.textContent\n"
            "  ).toContain('Hello');\n"
            "});\n"
        ),
    )

    finding = create_finding(
        rule_id="dom-test-safety",
        message=(
            "The test assumes the presence of the "
            "element before asserting against it."
        ),
        suggestion=(
            "Ensure the element exists before testing it."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
    )

    assert result.accepted is False


def test_preserves_selector_finding_without_assertion():
    validator = TestEvidenceValidator()

    changed_file = create_test_file(
        full_content=(
            "it('does something', () => {\n"
            "  const element = "
            "fixture.nativeElement.querySelector('h1');\n"
            "  element.remove();\n"
            "});\n"
        ),
    )

    finding = create_finding(
        rule_id="content-selector",
        message=(
            "The selector may return null before "
            "remove() is called."
        ),
        suggestion=(
            "Check for null first."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
    )

    assert result.accepted is True


def test_preserves_unrelated_test_finding():
    validator = TestEvidenceValidator()

    changed_file = create_test_file(
        full_content=(
            "it('calls service', () => {\n"
            "  service.save();\n"
            "  expect(service.save).toHaveBeenCalled();\n"
            "});\n"
        ),
    )

    finding = create_finding(
        rule_id="incorrect-mock-setup",
        message=(
            "The test calls a real service instead of "
            "the configured mock."
        ),
        suggestion=(
            "Use the mock service."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
    )

    assert result.accepted is True


def test_non_test_file_is_not_affected():
    validator = TestEvidenceValidator()

    changed_file = ChangedFile(
        file_path="src/app/app.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app/app.ts",
                line_number=20,
                content="save();",
            )
        ],
        full_content="save();",
    )

    finding = Finding(
        file_path="src/app/app.ts",
        line_number=20,
        severity=Severity.MEDIUM,
        rule_id="async-waiting",
        message=(
            "Wait before calling save."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
    )

    assert result.accepted is True