from pr_reviewer.review.finding_validator import (
    FindingValidator,
)
from pr_reviewer.review.models import (
    ChangedFile,
    ChangedLine,
    Finding,
    Severity,
)


def create_changed_file(
    file_path: str = "src/app.js",
    line_number: int = 10,
    content: str = "const value = 10;",
    full_content: str | None = None,
) -> ChangedFile:

    return ChangedFile(
        file_path=file_path,
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path=file_path,
                line_number=line_number,
                content=content,
            )
        ],
        full_content=full_content,
    )


def create_finding(
    file_path: str = "src/app.js",
    line_number: int = 10,
    rule_id: str = "runtime-error",
    message: str = "Concrete issue detected.",
    suggestion: str | None = "Fix the issue.",
) -> Finding:

    return Finding(
        file_path=file_path,
        line_number=line_number,
        severity=Severity.MEDIUM,
        rule_id=rule_id,
        message=message,
        suggestion=suggestion,
    )


def test_accepts_valid_finding():
    validator = FindingValidator()

    changed_file = create_changed_file()

    finding = create_finding()

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
    )

    assert result.accepted is True
    assert result.reasons == []


def test_rejects_non_commentable_line():
    validator = FindingValidator()

    changed_file = create_changed_file(
        line_number=10,
    )

    finding = create_finding(
        line_number=20,
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
    )

    assert result.accepted is False

    assert (
        "Finding targets a non-commentable line."
        in result.reasons
    )


def test_rejects_speculative_finding():
    validator = FindingValidator()

    changed_file = create_changed_file()

    finding = create_finding(
        message=(
            "This might cause a runtime problem."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
    )

    assert result.accepted is False

    assert (
        "Finding is speculative."
        in result.reasons
    )


def test_rejects_placeholder_rule_id():
    validator = FindingValidator()

    changed_file = create_changed_file()

    finding = create_finding(
        rule_id="descriptive-kebab-case-id",
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
    )

    assert result.accepted is False

    assert (
        "Finding uses an invalid placeholder rule ID."
        in result.reasons
    )


def test_rejects_css_rule_for_javascript():
    validator = FindingValidator()

    changed_file = create_changed_file(
        file_path="src/app.js",
    )

    finding = create_finding(
        file_path="src/app.js",
        rule_id="color-contrast",
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
    )

    assert result.accepted is False

    assert (
        "CSS-specific finding reported "
        "for a non-CSS file."
        in result.reasons
    )


def test_rejects_javascript_rule_for_html():
    validator = FindingValidator()

    changed_file = create_changed_file(
        file_path="index.html",
        content="<div></div>",
    )

    finding = create_finding(
        file_path="index.html",
        rule_id="no-console",
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
    )

    assert result.accepted is False

    assert (
        "JavaScript-specific finding reported "
        "for a non-JavaScript file."
        in result.reasons
    )


def test_rejects_missing_functionality_from_html():
    validator = FindingValidator()

    changed_file = create_changed_file(
        file_path="index.html",
        line_number=83,
        content=(
            '<input id="confirmPassword" '
            'type="password">'
        ),
    )

    finding = create_finding(
        file_path="index.html",
        line_number=83,
        rule_id="missing-password-validation",
        message=(
            "Password validation is missing."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
    )

    assert result.accepted is False

    assert (
        "Behavioral functionality cannot be proven "
        "from HTML alone."
        in result.reasons
    )


def test_rejects_confirm_password_behavior_from_html():
    validator = FindingValidator()

    changed_file = create_changed_file(
        file_path="index.html",
        line_number=83,
        content=(
            '<input id="confirmPassword" '
            'type="password">'
        ),
    )

    finding = create_finding(
        file_path="index.html",
        line_number=83,
        rule_id="confirm-password-validation",
        message=(
            "The confirm password field does not "
            "validate that the entered password "
            "matches the original password."
        ),
        suggestion=(
            "Add a validation rule to ensure that "
            "the passwords match."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
    )

    assert result.accepted is False

    assert (
        "Behavioral functionality cannot be "
        "proven from HTML alone."
        in result.reasons
    )


def test_rejects_password_toggle_behavior_from_html():
    validator = FindingValidator()

    changed_file = create_changed_file(
        file_path="index.html",
        line_number=35,
        content=(
            '<button class="toggle-password">'
            "Show"
            "</button>"
        ),
    )

    finding = create_finding(
        file_path="index.html",
        line_number=35,
        rule_id="password-toggle-functionality",
        message=(
            "The password toggle functionality "
            "does not handle an empty password."
        ),
        suggestion=(
            "Add a check before toggling visibility."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
    )

    assert result.accepted is False

    assert (
        "Behavioral functionality cannot be "
        "proven from HTML alone."
        in result.reasons
    )


def test_rejects_behavior_claim_even_with_unknown_rule_id():
    validator = FindingValidator()

    changed_file = create_changed_file(
        file_path="index.html",
        line_number=50,
        content='<form id="loginForm">',
    )

    finding = create_finding(
        file_path="index.html",
        line_number=50,
        rule_id="form-problem",
        message=(
            "The form does not validate the user "
            "input before submission."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
    )

    assert result.accepted is False

    assert (
        "Behavioral functionality cannot be "
        "proven from HTML alone."
        in result.reasons
    )


def test_preserves_structural_html_finding():
    validator = FindingValidator()

    changed_file = create_changed_file(
        file_path="index.html",
        line_number=20,
        content='<img src="avatar.png">',
    )

    finding = create_finding(
        file_path="index.html",
        line_number=20,
        rule_id="missing-alt-text",
        message=(
            "The image element has no alt attribute."
        ),
        suggestion=(
            "Add an appropriate alt attribute."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
    )

    assert result.accepted is True


def test_preserves_html_label_finding():
    validator = FindingValidator()

    changed_file = create_changed_file(
        file_path="index.html",
        line_number=40,
        content=(
            '<input id="rememberMe" '
            'type="checkbox">'
        ),
    )

    finding = create_finding(
        file_path="index.html",
        line_number=40,
        rule_id="checkbox-label",
        message=(
            "The checkbox has no associated label."
        ),
        suggestion=(
            "Associate a label with the checkbox."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
    )

    assert result.accepted is True


def test_rejects_unproven_variable_initialization():
    validator = FindingValidator()

    changed_file = create_changed_file(
        file_path="src/app.js",
        line_number=10,
        content="let value;",
        full_content=(
            "let value;\n"
            "value = 10;\n"
            "console.log(value);\n"
        ),
    )

    finding = create_finding(
        file_path="src/app.js",
        line_number=10,
        rule_id="uninitialized-variable",
        message=(
            "Variable `value` is not initialized."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
    )

    assert result.accepted is False

    assert (
        "Variable initialization issue is not "
        "supported by read-before-assignment evidence."
        in result.reasons
    )


def test_accepts_real_read_before_assignment():
    validator = FindingValidator()

    changed_file = create_changed_file(
        file_path="src/app.js",
        line_number=2,
        content="console.log(value);",
        full_content=(
            "let value;\n"
            "console.log(value);\n"
            "value = 10;\n"
        ),
    )

    finding = create_finding(
        file_path="src/app.js",
        line_number=2,
        rule_id="variable-used-before-assignment",
        message=(
            "Variable `value` is read before assignment."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
    )

    assert result.accepted is True


def test_filter_findings_returns_only_accepted():
    validator = FindingValidator()

    changed_file = create_changed_file(
        file_path="src/app.js",
        line_number=10,
    )

    valid = create_finding(
        file_path="src/app.js",
        line_number=10,
        rule_id="runtime-error",
    )

    invalid = create_finding(
        file_path="src/app.js",
        line_number=20,
        rule_id="runtime-error",
    )

    result = validator.filter_findings(
        findings=[
            valid,
            invalid,
        ],
        changed_file=changed_file,
    )

    assert result == [valid]


# ======================================================
# Template / prompt leakage protection
# ======================================================


def test_rejects_template_rule_id():
    validator = FindingValidator()

    changed_file = create_changed_file(
        file_path="src/app.js",
        line_number=123,
        content="handleFormSubmit();",
    )

    finding = create_finding(
        file_path="src/app.js",
        line_number=123,
        rule_id="specific-kebab-case-rule",
        message=(
            "A concrete runtime problem exists."
        ),
        suggestion=(
            "Handle the runtime problem correctly."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
    )

    assert result.accepted is False

    assert (
        "Finding uses a template rule ID."
        in result.reasons
    )


def test_rejects_template_message():
    validator = FindingValidator()

    changed_file = create_changed_file(
        file_path="src/app.js",
        line_number=123,
        content="handleFormSubmit();",
    )

    finding = create_finding(
        file_path="src/app.js",
        line_number=123,
        rule_id="runtime-error",
        message=(
            "Concrete explanation supported by the code."
        ),
        suggestion=(
            "Handle the runtime problem correctly."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
    )

    assert result.accepted is False

    assert (
        "Finding uses a template message."
        in result.reasons
    )


def test_rejects_template_suggestion():
    validator = FindingValidator()

    changed_file = create_changed_file(
        file_path="src/app.js",
        line_number=123,
        content="handleFormSubmit();",
    )

    finding = create_finding(
        file_path="src/app.js",
        line_number=123,
        rule_id="runtime-error",
        message=(
            "The function can throw an uncaught error."
        ),
        suggestion="Practical fix.",
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
    )

    assert result.accepted is False

    assert (
        "Finding uses a template suggestion."
        in result.reasons
    )


def test_rejects_complete_template_finding():
    validator = FindingValidator()

    changed_file = create_changed_file(
        file_path="src/app.js",
        line_number=123,
        content="handleFormSubmit();",
    )

    finding = create_finding(
        file_path="src/app.js",
        line_number=123,
        rule_id="specific-kebab-case-rule",
        message=(
            "Concrete explanation supported by the code."
        ),
        suggestion="Practical fix.",
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
    )

    assert result.accepted is False

    assert (
        "Finding uses a template rule ID."
        in result.reasons
    )

    assert (
        "Finding uses a template message."
        in result.reasons
    )

    assert (
        "Finding uses a template suggestion."
        in result.reasons
    )


def test_does_not_reject_real_kebab_case_rule():
    """
    A real kebab-case rule ID must remain valid.

    We are rejecting the literal prompt placeholder
    'specific-kebab-case-rule', not kebab-case naming
    itself.
    """

    validator = FindingValidator()

    changed_file = create_changed_file(
        file_path="src/app.js",
        line_number=123,
        content="dangerousOperation();",
    )

    finding = create_finding(
        file_path="src/app.js",
        line_number=123,
        rule_id="missing-error-handling",
        message=(
            "The operation has no error handling."
        ),
        suggestion=(
            "Handle the error returned by the operation."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
    )

    assert result.accepted is True


def test_template_detection_is_case_insensitive():
    validator = FindingValidator()

    changed_file = create_changed_file(
        file_path="src/app.js",
        line_number=123,
        content="handleFormSubmit();",
    )

    finding = create_finding(
        file_path="src/app.js",
        line_number=123,
        rule_id="SPECIFIC-KEBAB-CASE-RULE",
        message=(
            "Concrete runtime problem exists."
        ),
        suggestion=(
            "Fix the runtime problem."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
    )

    assert result.accepted is False

    assert (
        "Finding uses a template rule ID."
        in result.reasons
    )

def test_rejects_generic_accessibility_aria_or_role_claim_on_native_button():
    validator = FindingValidator()
    changed_file = create_changed_file(
        file_path="index.html",
        line_number=17,
        content='<button id="registerTabBtn">Register</button>',
        full_content='<button id="registerTabBtn">Register</button>',
    )
    finding = create_finding(
        file_path="index.html",
        line_number=17,
        rule_id="accessibility",
        message="The register button does not have an aria-label or role for screen readers.",
        suggestion="Add an aria-label or role to the register button.",
    )
    result = validator.validate(finding=finding, changed_file=changed_file)
    assert result.accepted is False
    assert any("Generic accessibility claim" in reason for reason in result.reasons)


def test_rejects_generic_accessibility_aria_or_role_claim_on_message_container():
    validator = FindingValidator()
    changed_file = create_changed_file(
        file_path="index.html",
        line_number=12,
        content='<div id="toast"></div>',
        full_content='<div id="toast"></div>',
    )
    finding = create_finding(
        file_path="index.html",
        line_number=12,
        rule_id="accessibility",
        message="The toast message container does not have an aria-label or role for screen readers.",
        suggestion="Add an aria-label or role to the toast message container.",
    )
    result = validator.validate(finding=finding, changed_file=changed_file)
    assert result.accepted is False
    assert any("Generic accessibility claim" in reason for reason in result.reasons)


def test_rejects_unsupported_return_value_contract_for_side_effect_helper():
    validator = FindingValidator()
    source = """function validatePasswordMatch() {\n  updateMatchMessage();\n}\nvalidatePasswordMatch();\n"""
    changed_file = create_changed_file(
        file_path="script.js",
        line_number=1,
        content="function validatePasswordMatch() {",
        full_content=source,
    )
    finding = create_finding(
        file_path="script.js",
        line_number=1,
        rule_id="return-value-handling",
        message="The function 'validatePasswordMatch' does not handle the return value properly. It should return the result of the match check.",
        suggestion="Add return and ensure all paths return a boolean value.",
    )
    result = validator.validate(finding=finding, changed_file=changed_file)
    assert result.accepted is False
    assert any("Return-value requirement" in reason for reason in result.reasons)


def test_preserves_return_value_finding_when_callers_consume_result():
    validator = FindingValidator()
    source = """function validatePasswordMatch() {\n  updateMatchMessage();\n}\nif (validatePasswordMatch()) { submit(); }\n"""
    changed_file = create_changed_file(
        file_path="script.js",
        line_number=1,
        content="function validatePasswordMatch() {",
        full_content=source,
    )
    finding = create_finding(
        file_path="script.js",
        line_number=1,
        rule_id="return-value-handling",
        message="The function 'validatePasswordMatch' should return the boolean result expected by its caller.",
        suggestion="Return a boolean value on all paths.",
    )
    result = validator.validate(finding=finding, changed_file=changed_file)
    assert result.accepted is True


def test_rejects_generic_error_handling_duplicate_for_empty_catch():
    validator = FindingValidator()
    source = """try {\n  parseData();\n} catch (error) {\n}\n"""
    changed_file = create_changed_file(
        file_path="script.js",
        line_number=3,
        content="} catch (error) {",
        full_content=source,
    )
    finding = create_finding(
        file_path="script.js",
        line_number=3,
        rule_id="error-handling",
        message="Error is silently ignored, which can lead to unexpected behavior and potential security vulnerabilities.",
        suggestion="Handle the error appropriately.",
    )
    result = validator.validate(finding=finding, changed_file=changed_file)
    assert result.accepted is False
    assert any("duplicates the concrete empty-catch-block" in reason for reason in result.reasons)


def test_preserves_generic_error_handling_when_not_an_empty_catch_duplicate():
    validator = FindingValidator()
    source = "dangerousOperation();\n"
    changed_file = create_changed_file(
        file_path="script.js",
        line_number=1,
        content="dangerousOperation();",
        full_content=source,
    )
    finding = create_finding(
        file_path="script.js",
        line_number=1,
        rule_id="error-handling",
        message="The operation has no error handling.",
        suggestion="Handle or propagate the returned error.",
    )
    result = validator.validate(finding=finding, changed_file=changed_file)
    assert result.accepted is True


def test_rejects_redundant_unsafe_api_secret_exposure_when_hardcoded_secret_is_proven():
    validator = FindingValidator()
    content = """import React from 'react';
const apiKey = 'sk_live_1234567890';
function App() {
  return <p>API Key: {apiKey}</p>;
}
"""
    changed = ChangedFile(
        file_path="src/App.js",
        status="modified",
        changed_lines=[
            ChangedLine(file_path="src/App.js", line_number=4, content="  return <p>API Key: {apiKey}</p>;")
        ],
        full_content=content,
    )
    finding = Finding(
        file_path="src/App.js",
        line_number=4,
        severity=Severity.HIGH,
        rule_id="unsafe-api",
        message="The API key is being displayed directly in the UI, which exposes the secret.",
        suggestion="Remove the secret from the UI.",
    )
    result = validator.validate(finding=finding, changed_file=changed)
    assert result.accepted is False
    assert any("hardcoded-secret" in reason for reason in result.reasons)


def test_rejects_event_listener_claim_anchored_on_timer_source():
    validator = FindingValidator()
    changed_file = create_changed_file(
        line_number=10,
        content="setInterval(() => poll(), 1000);",
        full_content="setInterval(() => poll(), 1000);",
    )
    finding = create_finding(
        line_number=10,
        rule_id="global-event-listener-without-removal",
        message="Global event listener without removal can leak resources.",
    )

    result = validator.validate(finding=finding, changed_file=changed_file)

    assert result.accepted is False
    assert any("event-listener" in reason.lower() for reason in result.reasons)


def test_rejects_duplicate_logic_finding_anchored_outside_named_method():
    validator = FindingValidator()
    source = (
        "class Example {\n"
        "  calculateTotal(price: number, tax: number): number {\n"
        "    const subtotal = price + tax;\n"
        "    const total = price + tax;\n"
        "    return subtotal;\n"
        "  }\n"
        "\n"
        "  updateCount(): void {\n"
        "    this.count.set(this.count() + 1);\n"
        "  }\n"
        "}\n"
    )
    changed_file = create_changed_file(
        file_path="src/example.ts",
        line_number=9,
        content="    this.count.set(this.count() + 1);",
        full_content=source,
    )
    finding = create_finding(
        file_path="src/example.ts",
        line_number=9,
        rule_id="duplicate-logic",
        message=(
            "The 'calculateTotal' method contains duplicate logic. "
            "The subtotal calculation is repeated."
        ),
        suggestion="Refactor the calculateTotal method to calculate the value once.",
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
    )

    assert result.accepted is False
    assert any(
        "does not belong to the named method/function 'calculateTotal'" in reason
        for reason in result.reasons
    )


def test_preserves_duplicate_logic_finding_when_anchored_inside_named_method():
    validator = FindingValidator()
    source = (
        "class Example {\n"
        "  calculateTotal(price: number, tax: number): number {\n"
        "    const subtotal = price + tax;\n"
        "    const total = price + tax;\n"
        "    return subtotal;\n"
        "  }\n"
        "}\n"
    )
    changed_file = create_changed_file(
        file_path="src/example.ts",
        line_number=4,
        content="    const total = price + tax;",
        full_content=source,
    )
    finding = create_finding(
        file_path="src/example.ts",
        line_number=4,
        rule_id="duplicate-logic",
        message=(
            "The 'calculateTotal' method contains duplicate logic. "
            "The subtotal calculation is repeated."
        ),
        suggestion="Refactor the calculateTotal method to calculate the value once.",
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
    )

    assert not any(
        "does not belong to the named method/function" in reason
        for reason in result.reasons
    )


def test_rejects_runtime_subscription_cleanup_claim_on_declarative_json_config():
    validator = FindingValidator()
    changed_file = create_changed_file(
        file_path="angular.json",
        line_number=42,
        content='          "type": "anyComponentStyle",',
        full_content='{"budgets": [{"type": "anyComponentStyle"}]}',
    )
    finding = create_finding(
        file_path="angular.json",
        line_number=42,
        rule_id="resource-cleanup",
        message="The subscription is not being cleaned up. This could lead to memory leaks.",
        suggestion="Use takeUntil to clean up the subscription.",
    )

    result = validator.validate(finding=finding, changed_file=changed_file)

    assert result.accepted is False
    assert any("Declarative configuration" in reason for reason in result.reasons)


def test_rejects_generic_data_validation_claim_on_scalar_json_config():
    validator = FindingValidator()
    changed_file = create_changed_file(
        file_path="angular.json",
        line_number=50,
        content='          "optimization": false,',
        full_content='{"configurations": {"development": {"optimization": false}}}',
    )
    finding = create_finding(
        file_path="angular.json",
        line_number=50,
        rule_id="data-validation",
        message="The data validation logic is missing. This could lead to incorrect behavior.",
        suggestion="Add validation logic to ensure the data is correct before processing it.",
    )

    result = validator.validate(finding=finding, changed_file=changed_file)

    assert result.accepted is False
    assert any("scalar configuration property" in reason for reason in result.reasons)


def test_rejects_vague_business_validation_claim_on_plain_ts_property_assignment():
    validator = FindingValidator()
    changed_file = create_changed_file(
        file_path="src/app/save.ts",
        line_number=12,
        content="      username: this.username,",
        full_content=(
            "save(): void {\n"
            "  this.http.post('/api/save', {\n"
            "    username: this.username,\n"
            "  }).subscribe();\n"
            "}\n"
        ),
    )
    finding = create_finding(
        file_path="src/app/save.ts",
        line_number=12,
        rule_id="data-validation",
        message="The username is being sent without validation.",
        suggestion="Add validation to ensure the username meets the required criteria.",
    )

    result = validator.validate(finding=finding, changed_file=changed_file)

    assert result.accepted is False
    assert any("business-rule validation claim" in reason for reason in result.reasons)


def test_rejects_duplicate_calculation_claim_when_evidence_is_closing_brace_outside_method():
    validator = FindingValidator()
    source = (
        "class Example {\n"
        "  calculateTotal(price: number, tax: number): number {\n"
        "    const subtotal = price + tax;\n"
        "    const total = price + tax;\n"
        "    return subtotal;\n"
        "  }\n"
        "\n"
        "  updateCount(): void {\n"
        "    this.count.set(this.count() + 1);\n"
        "  }\n"
        "}\n"
    )
    changed_file = create_changed_file(
        file_path="src/example.ts",
        line_number=10,
        content="  }",
        full_content=source,
    )
    finding = create_finding(
        file_path="src/example.ts",
        line_number=10,
        rule_id="duplicate-logic",
        message="The same calculation is performed twice in the `calculateTotal` method.",
        suggestion="Refactor the method to avoid duplicate calculations.",
    )

    result = validator.validate(finding=finding, changed_file=changed_file)

    assert result.accepted is False
    assert any("calculateTotal" in reason for reason in result.reasons)


def test_rejects_duplicate_array_claim_when_symbol_occurs_only_once():
    validator = FindingValidator()
    source = (
        "describe('App', () => {\n"
        "  TestBed.configureTestingModule({\n"
        "    imports: [App],\n"
        "  });\n"
        "});\n"
    )
    changed_file = create_changed_file(
        file_path="src/app/app.spec.ts",
        line_number=3,
        content="    imports: [App],",
        full_content=source,
    )
    finding = create_finding(
        file_path="src/app/app.spec.ts",
        line_number=3,
        rule_id="duplicate-logic",
        message=(
            "The import of 'App' is duplicated in the 'imports' array. "
            "This can be refactored to avoid redundancy."
        ),
        suggestion="Remove the duplicate import from the imports array.",
    )

    result = validator.validate(finding=finding, changed_file=changed_file)

    assert result.accepted is False
    assert any(
        "not supported by a second occurrence of 'App'" in reason
        for reason in result.reasons
    )


def test_preserves_duplicate_array_claim_when_symbol_occurs_twice():
    validator = FindingValidator()
    source = (
        "const config = {\n"
        "  imports: [App, RouterTestingModule, App],\n"
        "};\n"
    )
    changed_file = create_changed_file(
        file_path="src/config.ts",
        line_number=2,
        content="  imports: [App, RouterTestingModule, App],",
        full_content=source,
    )
    finding = create_finding(
        file_path="src/config.ts",
        line_number=2,
        rule_id="duplicate-logic",
        message="The import of 'App' is duplicated in the imports array.",
        suggestion="Remove one duplicate App entry.",
    )

    result = validator.validate(finding=finding, changed_file=changed_file)

    assert not any(
        "Duplicate array/list claim" in reason
        for reason in result.reasons
    )


def test_duplicate_method_claim_is_not_forced_through_array_evidence():
    validator = FindingValidator()
    source = (
        "class Example {\n"
        "  calculateTotal(price: number, tax: number): number {\n"
        "    const subtotal = price + tax;\n"
        "    const total = price + tax;\n"
        "    return subtotal;\n"
        "  }\n"
        "}\n"
    )
    changed_file = create_changed_file(
        file_path="src/example.ts",
        line_number=4,
        content="    const total = price + tax;",
        full_content=source,
    )
    finding = create_finding(
        file_path="src/example.ts",
        line_number=4,
        rule_id="duplicate-logic",
        message=(
            "The 'calculateTotal' method contains duplicate logic. "
            "The same calculation is performed twice."
        ),
        suggestion="Calculate the expression once.",
    )

    result = validator.validate(finding=finding, changed_file=changed_file)

    assert not any(
        "Duplicate array/list claim" in reason
        for reason in result.reasons
    )
