from pr_reviewer.review.finding_validator import FindingValidator
from pr_reviewer.review.models import ChangedFile, ChangedLine, Finding, Severity


def changed_file(path: str, line_number: int, content: str) -> ChangedFile:
    return ChangedFile(
        file_path=path,
        status="modified",
        changed_lines=[ChangedLine(file_path=path, line_number=line_number, content=content)],
        full_content="\n" * (line_number - 1) + content + "\n",
    )


def finding(path: str, line_number: int, rule_id: str, message: str, suggestion: str = "") -> Finding:
    return Finding(
        file_path=path,
        line_number=line_number,
        severity=Severity.SUGGESTION,
        rule_id=rule_id,
        message=message,
        suggestion=suggestion,
    )


def test_rejects_decorative_html_separator_comment():
    path = "src/app/app.html"
    cf = changed_file(path, 7, "<!-- * * * * * * * * * * * * -->")
    f = finding(
        path, 7, "duplicate-logic",
        "The content above is a placeholder and can be replaced with actual content.",
        "Remove the placeholder and add actual content.",
    )
    result = FindingValidator().validate(f, cf)
    assert not result.accepted
    assert any("low-value" in reason.lower() for reason in result.reasons)


def test_rejects_decorative_javascript_separator_comment():
    path = "src/app.ts"
    cf = changed_file(path, 3, "// ------------------------------")
    f = finding(path, 3, "maintainability", "Decorative separator comment adds noise.")
    result = FindingValidator().validate(f, cf)
    assert not result.accepted


def test_rejects_placeholder_cleanup_on_comment_only_line():
    path = "src/example.py"
    cf = changed_file(path, 4, "# placeholder content")
    f = finding(
        path, 4, "maintainability",
        "This placeholder should be replaced with real content.",
        "Remove the placeholder.",
    )
    result = FindingValidator().validate(f, cf)
    assert not result.accepted


def test_does_not_reject_actionable_todo_comment_just_because_it_is_comment_only():
    path = "src/app.ts"
    cf = changed_file(path, 5, "// TODO: revoke temporary admin token after migration")
    f = finding(
        path, 5, "security",
        "A temporary admin token is documented as still active after the migration.",
        "Revoke the token when the migration completes.",
    )
    result = FindingValidator().validate(f, cf)
    # Other validators may reject unsupported semantic claims, but the new low-value
    # comment filter must not be the reason.
    assert not any("low-value" in reason.lower() for reason in result.reasons)


def test_does_not_reject_real_code_with_word_placeholder():
    path = "src/app.ts"
    cf = changed_file(path, 8, "const placeholder = unsafeInput;")
    f = finding(
        path, 8, "security",
        "The placeholder variable receives untrusted data before a dangerous sink.",
        "Validate the input before use.",
    )
    result = FindingValidator().validate(f, cf)
    assert not any("placeholder/decorative-comment" in reason.lower() for reason in result.reasons)
