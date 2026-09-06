from pr_reviewer.review.finding_validator import FindingValidator
from pr_reviewer.review.models import ChangedFile, ChangedLine, Finding, Severity


def cf(path: str, content: str, line: int) -> ChangedFile:
    lines = content.splitlines()
    return ChangedFile(
        file_path=path,
        status="modified",
        changed_lines=[ChangedLine(file_path=path, line_number=line, content=lines[line - 1])],
        full_content=content,
    )


def finding(path: str, line: int, rule: str, message: str, suggestion: str = "") -> Finding:
    return Finding(
        file_path=path,
        line_number=line,
        severity=Severity.MEDIUM,
        rule_id=rule,
        message=message,
        suggestion=suggestion,
    )


def test_valid_javascript_comment_rejects_invalid_comment_claim():
    changed = cf(
        "vite.config.js",
        "import { defineConfig } from 'vite'\n\n// https://vite.dev/config/\nexport default defineConfig({})",
        3,
    )
    item = finding(
        "vite.config.js", 3, "api-misuse",
        "The comment 'https://vite.dev/config/' is not a comment in valid JavaScript.",
    )
    result = FindingValidator().validate(item, changed)
    assert not result.accepted
    assert any("valid source comment" in r for r in result.reasons)


def test_valid_brace_expansion_glob_is_not_data_validation_defect():
    changed = cf(
        "eslint.config.js",
        "export default [{\n  files: ['**/*.{js,jsx}'],\n}]",
        2,
    )
    item = finding(
        "eslint.config.js", 2, "data-validation",
        "File patterns should be specific to avoid linting unintended files.",
        "Change to separate JavaScript and JSX patterns.",
    )
    result = FindingValidator().validate(item, changed)
    assert not result.accepted
    assert any("brace-expansion glob" in r for r in result.reasons)


def test_single_css_property_does_not_prove_duplicate():
    changed = cf(
        "src/index.css",
        "@media (max-width: 600px) {\n  .card {\n    margin: 20px 0;\n    padding: 8px;\n  }\n}",
        3,
    )
    item = finding(
        "src/index.css", 3, "duplicate-logic",
        "The margin property is defined twice for the same media query.",
    )
    result = FindingValidator().validate(item, changed)
    assert not result.accepted
    assert any("second declaration" in r for r in result.reasons)


def test_actual_duplicate_css_property_can_still_pass_evidence_check():
    changed = cf(
        "src/index.css",
        ".card {\n  margin: 20px 0;\n  padding: 8px;\n  margin: 10px 0;\n}",
        4,
    )
    item = finding(
        "src/index.css", 4, "duplicate-logic",
        "The margin property is defined twice in the same rule block.",
    )
    result = FindingValidator().validate(item, changed)
    assert result.accepted


def test_normal_non_comment_api_misuse_is_not_blanket_rejected():
    changed = cf("src/app.js", "dangerousApi(value)", 1)
    item = finding("src/app.js", 1, "api-misuse", "The API is called with an invalid argument.")
    result = FindingValidator().validate(item, changed)
    assert result.accepted
