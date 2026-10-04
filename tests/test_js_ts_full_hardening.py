from pr_reviewer.review.finding_policy import FindingPolicy
from pr_reviewer.review.models import ChangedFile, ChangedLine, Finding, Severity
from pr_reviewer.review.static_analyzer import StaticAnalyzer


def changed_file(path: str, content: str) -> ChangedFile:
    return ChangedFile(
        file_path=path,
        status="modified",
        changed_lines=[
            ChangedLine(path, index, line)
            for index, line in enumerate(content.splitlines(), start=1)
        ],
        full_content=content,
    )


def rules_for(path: str, content: str):
    return StaticAnalyzer().analyze(changed_file(path, content))


def test_js_empty_catch_is_detected_deterministically():
    content = """async function load() {
  try {
    await fetch('/api');
  } catch (error) {
  }
}"""
    findings = rules_for("script.js", content)
    assert any(f.rule_id == "empty-catch-block" and f.line_number == 4 for f in findings)


def test_ts_empty_catch_is_detected_deterministically():
    content = """async function loadConfiguration(): Promise<void> {
  try {
    await fetch('/config');
  } catch (error) {
  }
}"""
    findings = rules_for("review-test.ts", content)
    assert any(f.rule_id == "empty-catch-block" for f in findings)


def test_unused_parameters_are_detected_for_js_function():
    content = """function greetUser(name, title, department) {
  return `Hello ${name}`;
}"""
    findings = rules_for("script.js", content)
    messages = [f.message for f in findings if f.rule_id == "unused-parameter"]
    assert any("title" in message for message in messages)
    assert any("department" in message for message in messages)
    assert not any("name'" in message for message in messages)


def test_unused_parameters_are_detected_for_ts_function():
    content = """function greetUser(name: string, title: string, department: string): string {
  return `Hello ${name}`;
}"""
    findings = rules_for("review-test.ts", content)
    messages = [f.message for f in findings if f.rule_id == "unused-parameter"]
    assert any("title" in message for message in messages)
    assert any("department" in message for message in messages)


def test_control_flow_keywords_are_not_treated_as_functions():
    content = """function status(active) {
  if (active) {
    return 'ACTIVE';
  }
  return 'INACTIVE';
}"""
    findings = rules_for("script.js", content)
    assert not any(f.rule_id == "unused-parameter" and "active" in f.message for f in findings)


def test_unreachable_statement_after_return_is_detected():
    content = """function getStatus(active) {
  if (active) {
    return 'ACTIVE';
    console.log('never');
  }
  return 'INACTIVE';
}"""
    findings = rules_for("review-test.ts", content)
    assert any(f.rule_id == "unreachable-code" and f.line_number == 4 for f in findings)


def test_json_parse_without_visible_error_handling_is_detected():
    content = """function parseUserData(data: string) {
  return JSON.parse(data);
}"""
    findings = rules_for("review-test.ts", content)
    assert any(f.rule_id == "json-parse-without-error-handling" for f in findings)


def test_json_parse_inside_try_is_not_reported():
    content = """function parseUserData(data) {
  try {
    return JSON.parse(data);
  } catch (error) {
    return null;
  }
}"""
    findings = rules_for("script.js", content)
    assert not any(f.rule_id == "json-parse-without-error-handling" for f in findings)


def test_policy_caps_js_llm_overseverity_in_one_place():
    policy = FindingPolicy()
    for rule in (
        "loose-equality",
        "unreachable-code",
        "empty-catch-block",
        "json-parse-without-error-handling",
        "setinterval-without-retaining-timer-reference",
        "global-event-listener-without-removal",
    ):
        finding = Finding("script.js", 10, Severity.CRITICAL, rule, "message")
        adjusted = policy.apply(finding)
        assert adjusted is not None
        assert adjusted.severity == Severity.MEDIUM, rule


def test_all_adjacent_typescript_secrets_survive_static_analysis():
    content = """const apiKey = 'sk_live_123456789';
const databasePassword = 'Admin@123456';
const jwtSecret = 'super_secret_jwt_signing_key';"""
    findings = rules_for("review-test.ts", content)
    secrets = [f for f in findings if f.rule_id == "hardcoded-secret"]
    assert [(f.line_number, f.message) for f in secrets] == [
        (1, "Hardcoded credential or secret detected in 'apiKey'."),
        (2, "Hardcoded credential or secret detected in 'databasePassword'."),
        (3, "Hardcoded credential or secret detected in 'jwtSecret'."),
    ]
