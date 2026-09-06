from pr_reviewer.context.models import RepositoryContext
from pr_reviewer.review.finding_validator import FindingValidator
from pr_reviewer.review.framework_evidence_validator import FrameworkEvidenceValidator
from pr_reviewer.review.framework_fact_validator import FrameworkFactValidator
from pr_reviewer.review.models import ChangedFile, ChangedLine, Finding, Severity


def changed(path: str, line_no: int, line: str, full: str) -> ChangedFile:
    return ChangedFile(
        file_path=path,
        status="modified",
        changed_lines=[ChangedLine(file_path=path, line_number=line_no, content=line)],
        full_content=full,
    )


def finding(path: str, line_no: int, rule: str, message: str, suggestion: str = "") -> Finding:
    return Finding(
        file_path=path,
        line_number=line_no,
        severity=Severity.MEDIUM,
        rule_id=rule,
        message=message,
        suggestion=suggestion,
    )


def angular_context() -> RepositoryContext:
    return RepositoryContext(
        languages={"typescript", "html", "json"},
        framework="angular",
        project_type="frontend-web",
    )


def app_component(name: str = "App") -> ChangedFile:
    return ChangedFile(
        file_path="src/app/app.ts" if name == "App" else "src/app/components/review-test/review-test.ts",
        status="modified",
        full_content=(
            "import { Component } from '@angular/core';\n"
            "@Component({ selector: 'x-test', standalone: true, template: '' })\n"
            f"export class {name} {{}}\n"
        ),
    )


def test_rejects_runtime_rxjs_security_claim_on_json_config_independent_of_rule_id():
    file = changed(
        "angular.json",
        37,
        '"type": "initial",',
        '{\n  "budgets": [{\n    "type": "initial",\n    "maximumWarning": "500kB"\n  }]\n}',
    )
    item = finding(
        "angular.json",
        37,
        "security",
        "Potential security risk due to missing error handling in the RxJS subscription.",
        "Add error handling to the RxJS subscription to prevent unhandled errors.",
    )
    result = FindingValidator().validate(item, file)
    assert not result.accepted
    assert any("cannot prove the claimed executable runtime behavior" in r for r in result.reasons)


def test_preserves_legitimate_security_finding_on_json_config():
    file = changed(
        "config.json",
        2,
        '"apiKey": "sk_live_123",',
        '{\n  "apiKey": "sk_live_123"\n}',
    )
    item = finding(
        "config.json",
        2,
        "security",
        "A hardcoded API credential is present in configuration.",
        "Move the credential to secret storage.",
    )
    result = FindingValidator().validate(item, file)
    assert result.accepted


def _testbed_file(component_name: str, file_path: str = "src/app/app.spec.ts") -> ChangedFile:
    full = (
        "import { TestBed } from '@angular/core/testing';\n"
        f"import {{ {component_name} }} from './app';\n"
        "describe('test', () => {\n"
        "  beforeEach(async () => {\n"
        "    await TestBed.configureTestingModule({\n"
        f"      imports: [{component_name}],\n"
        "    }).compileComponents();\n"
        "  });\n"
        "});\n"
    )
    return changed(file_path, 6, f"imports: [{component_name}],", full)


def test_rejects_not_correct_usage_standalone_testbed_claim_under_duplicate_logic():
    test_file = _testbed_file("App")
    item = finding(
        test_file.file_path,
        6,
        "duplicate-logic",
        "The 'App' component is imported directly in the imports array, which is not the correct usage. It should be imported as a standalone component.",
        "Update the imports array to use the correct syntax for standalone components.",
    )
    result = FrameworkEvidenceValidator().validate(
        finding=item,
        changed_file=test_file,
        changed_files=[test_file, app_component("App")],
        repository_context=angular_context(),
    )
    assert not result.accepted
    assert any("standalone-component evidence" in r for r in result.reasons)


def test_framework_fact_layer_also_rejects_same_testbed_semantic_claim():
    test_file = _testbed_file("App")
    item = finding(
        test_file.file_path,
        6,
        "api-misuse",
        "Importing App directly is not correct usage for a standalone component.",
        "Use the correct standalone import syntax.",
    )
    result = FrameworkFactValidator().validate(
        finding=item,
        changed_file=test_file,
        changed_files=[test_file, app_component("App")],
        repository_context=angular_context(),
    )
    assert not result.accepted


def test_valid_non_standalone_testbed_misuse_is_not_blanket_suppressed():
    test_file = _testbed_file("LegacyComponent")
    legacy = ChangedFile(
        file_path="src/app/legacy.ts",
        status="modified",
        full_content=(
            "import { Component } from '@angular/core';\n"
            "@Component({ selector: 'legacy-x', standalone: false, template: '' })\n"
            "export class LegacyComponent {}\n"
        ),
    )
    item = finding(
        test_file.file_path,
        6,
        "api-misuse",
        "LegacyComponent is imported directly into TestBed imports, but it is not standalone.",
        "Declare it through its NgModule or declarations as appropriate.",
    )
    result = FrameworkEvidenceValidator().validate(
        finding=item,
        changed_file=test_file,
        changed_files=[test_file, legacy],
        repository_context=angular_context(),
    )
    assert result.accepted


def test_template_click_does_not_prove_generic_security_defect():
    html = changed(
        "src/app/review-test.html",
        23,
        '<button (click)="triggerDebugger()">Debug</button>',
        '<button (click)="triggerDebugger()">Debug</button>\n',
    )
    item = finding(
        html.file_path,
        23,
        "security",
        "The method triggerDebugger may expose sensitive debugging information if not properly secured.",
        "Secure the method.",
    )
    result = FrameworkEvidenceValidator().validate(
        finding=item,
        changed_file=html,
        changed_files=[html],
        repository_context=angular_context(),
    )
    assert not result.accepted
    assert any("template invocation" in r.lower() for r in result.reasons)


def test_rejects_template_text_as_proof_of_direct_dom_security_implementation():
    html = changed(
        "src/app/components/review-test/review-test.html",
        16,
        "Unsafe DOM",
        '<button (click)="unsafeDomManipulation()">Unsafe DOM</button>\n',
    )
    item = finding(
        html.file_path,
        16,
        "security",
        "The method 'unsafeDomManipulation' performs direct DOM manipulation, which can be unsafe and bypass Angular's security features.",
        "Use Angular's DOM manipulation methods instead of direct DOM manipulation.",
    )
    result = FindingValidator().validate(item, html)
    assert not result.accepted
    assert any("HTML alone" in r for r in result.reasons)


def test_rejects_testbed_component_imported_into_itself_hallucination():
    test_file = _testbed_file("ReviewTest", "src/app/components/review-test/review-test.spec.ts")
    item = finding(
        test_file.file_path,
        6,
        "duplicate-logic",
        "The component is being imported into itself, which is redundant and unnecessary.",
        "Remove the component from the imports array.",
    )
    result = FrameworkEvidenceValidator().validate(
        finding=item,
        changed_file=test_file,
        changed_files=[test_file, app_component("ReviewTest")],
        repository_context=angular_context(),
    )
    assert not result.accepted
    assert any("standalone-component evidence" in r for r in result.reasons)


def test_framework_fact_rejects_testbed_self_import_wording_too():
    test_file = _testbed_file("ReviewTest", "src/app/components/review-test/review-test.spec.ts")
    item = finding(
        test_file.file_path,
        6,
        "duplicate-logic",
        "The component is being imported into itself, which is redundant and unnecessary.",
        "Remove the component from the imports array.",
    )
    result = FrameworkFactValidator().validate(
        finding=item,
        changed_file=test_file,
        changed_files=[test_file, app_component("ReviewTest")],
        repository_context=angular_context(),
    )
    assert not result.accepted


def test_rejects_duplicate_calculation_claim_anchored_to_unrelated_method_signature():
    full = (
        "calculateTotal(): number {\n"
        "  const subtotal = this.price + this.tax;\n"
        "  const total = this.price + this.tax;\n"
        "  return total;\n"
        "}\n"
        "\n"
        "updateCount(): void {\n"
        "  this.count.update(v => v + 1);\n"
        "}\n"
    )
    file = changed(
        "src/app/components/review-test/review-test.ts",
        7,
        "updateCount(): void {",
        full,
    )
    item = finding(
        file.file_path,
        7,
        "duplicate-logic",
        "The 'total' variable is calculated twice with the same values, which is redundant.",
        "Remove the duplicate calculation and use the 'subtotal' variable.",
    )
    result = FindingValidator().validate(item, file)
    assert not result.accepted
    assert any("source construct 'total'" in r for r in result.reasons)


def test_preserves_duplicate_calculation_when_anchored_to_actual_duplicate_expression():
    full = (
        "calculateTotal(): number {\n"
        "  const subtotal = this.price + this.tax;\n"
        "  const total = this.price + this.tax;\n"
        "  return total;\n"
        "}\n"
    )
    file = changed(
        "src/app/components/review-test/review-test.ts",
        3,
        "  const total = this.price + this.tax;",
        full,
    )
    item = finding(
        file.file_path,
        3,
        "duplicate-logic",
        "The 'total' variable is calculated twice with the same values, which is redundant.",
        "Remove the duplicate calculation and use the 'subtotal' variable.",
    )
    result = FindingValidator().validate(item, file)
    assert result.accepted
