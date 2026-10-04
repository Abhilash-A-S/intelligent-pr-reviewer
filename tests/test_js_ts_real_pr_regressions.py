from pr_reviewer.review.deduplicator import FindingDeduplicator
from pr_reviewer.review.finding_validator import FindingValidator
from pr_reviewer.review.models import ChangedFile, ChangedLine, Finding, Severity
from pr_reviewer.review.normalizer import FindingNormalizer
from pr_reviewer.review.processor import FindingProcessor
from pr_reviewer.review.static_analyzer import StaticAnalyzer


def make_changed(path: str, content: str) -> ChangedFile:
    return ChangedFile(
        file_path=path,
        status="modified",
        changed_lines=[
            ChangedLine(file_path=path, line_number=i, content=line)
            for i, line in enumerate(content.splitlines(), start=1)
        ],
        full_content=content,
    )


def finding(path: str, line: int, rule: str, message: str, severity=Severity.MEDIUM, suggestion=None):
    return Finding(path, line, severity, rule, message, suggestion=suggestion)


def test_unused_function_parameter_alias_is_canonicalized():
    normalized = FindingNormalizer().normalize(
        finding("script.js", 10, "unused-function-parameter", "Parameter 'title' is unused.")
    )
    assert normalized.rule_id == "unused-parameter"


def test_two_unused_parameters_on_same_signature_are_not_collapsed():
    findings = [
        finding("review-test.ts", 35, "unused-parameter", "Parameter 'title' is declared but never used.", Severity.LOW),
        finding("review-test.ts", 35, "unused-parameter", "Parameter 'department' is declared but never used.", Severity.LOW),
    ]
    result = FindingDeduplicator().deduplicate(findings)
    assert len(result) == 2
    assert {f.message for f in result} == {f.message for f in findings}


def test_same_unused_variable_with_llm_line_drift_is_merged_by_subject():
    result = FindingDeduplicator().deduplicate([
        finding("script.js", 259, "unused-variable", "Variable 'unusedUserCount' is declared but never used.", Severity.LOW),
        finding("script.js", 262, "unused-variable", "The 'unusedUserCount' variable is unused and should be removed.", Severity.MEDIUM),
    ])
    assert len(result) == 1


def test_same_unused_class_field_with_larger_line_drift_is_merged_by_subject():
    result = FindingDeduplicator().deduplicate([
        finding("review-test.ts", 226, "unused-variable", "Variable 'unusedCounter' is declared but never used.", Severity.LOW),
        finding("review-test.ts", 235, "unused-variable", "The 'unusedCounter' variable is initialized but never used.", Severity.LOW),
    ])
    assert len(result) == 1


def test_comment_only_empty_catch_is_detected_statically():
    content = """async function load() {
  try {
    await fetch('/api');
  } catch (error) {
    // intentionally ignored
  }
}"""
    rules = StaticAnalyzer().analyze(make_changed("script.js", content))
    assert any(f.rule_id == "empty-catch-block" for f in rules)


def test_rejects_invalid_label_text_must_match_id_claim():
    content = '<label for="password">Minimum 8 characters</label>\n<input id="password" type="password">'
    changed = make_changed("index.html", content)
    f = finding(
        "index.html", 1, "password-input-label-mismatch",
        "The label for the password input should match the input's ID for better accessibility.",
    )
    result = FindingValidator().validate(f, changed)
    assert result.accepted is False
    assert any("does not need to match" in reason for reason in result.reasons)


def test_rejects_password_order_claim_when_matching_precedes_submit():
    content = """function register(password, confirmPassword) {
  if (password !== confirmPassword) return;
  handleFormSubmit();
}"""
    changed = make_changed("script.js", content)
    f = finding(
        "script.js", 2, "password-matching-check-order",
        "The password matching check should be performed before form submission.",
    )
    result = FindingValidator().validate(f, changed)
    assert result.accepted is False
    assert any("already checked before submission" in reason for reason in result.reasons)


def test_rejects_missing_implementation_claim_when_function_exists():
    content = """function startPolling() {
  setInterval(() => console.log('tick'), 1000);
}
startPolling();"""
    changed = make_changed("review-test.ts", content)
    f = finding(
        "review-test.ts", 4, "start-polling",
        "The 'startPolling' function is called but its implementation is not provided.",
    )
    result = FindingValidator().validate(f, changed)
    assert result.accepted is False
    assert any("implemented in this file" in reason for reason in result.reasons)


def test_rejects_duplicate_calculation_rule_with_unused_function_message():
    changed = make_changed("review-test.ts", "function duplicateCalculation() { return 1; }")
    f = finding(
        "review-test.ts", 1, "duplicate-calculation",
        "The function 'duplicateCalculation' is declared but not used within the file.",
    )
    result = FindingValidator().validate(f, changed)
    assert result.accepted is False
    assert any("does not support" in reason for reason in result.reasons)


def test_rejects_variable_scope_rule_that_only_describes_unused_value():
    changed = make_changed("review-test.ts", "let result: number; return result;")
    f = finding(
        "review-test.ts", 1, "variable-scope",
        "The variable 'result' is declared but not used within the function.",
    )
    result = FindingValidator().validate(f, changed)
    assert result.accepted is False


def test_rejects_vacuous_return_value_finding():
    changed = make_changed("review-test.ts", "function compareValues(a, b) { return a === b; }")
    f = finding(
        "review-test.ts", 1, "return-value",
        "The function 'compareValues' returns a boolean value without any specific logic.",
        suggestion="Ensure that the function logic is clear and returns the expected result.",
    )
    result = FindingValidator().validate(f, changed)
    assert result.accepted is False


def test_json_parse_alias_deduplicates_with_deterministic_finding():
    normalizer = FindingNormalizer()
    findings = [
        finding("review-test.ts", 10, "json-parse-without-error-handling", "JSON.parse is used without visible error handling.", Severity.MEDIUM),
        finding("review-test.ts", 10, "json-parse", "Parsing untrusted JSON data without validation can lead to security vulnerabilities.", Severity.LOW),
    ]
    result = FindingDeduplicator().deduplicate([normalizer.normalize(f) for f in findings])
    assert len(result) == 1
    assert result[0].severity == Severity.MEDIUM


def test_rejects_parse_user_data_callsite_duplicate():
    content = """function parseUserData(data: string) {
  return JSON.parse(data);
}
parseUserData('invalid json');"""
    changed = make_changed("review-test.ts", content)
    f = finding(
        "review-test.ts", 4, "parse-user-data",
        "Calling 'parseUserData' with an invalid JSON string will throw an exception.",
    )
    result = FindingValidator().validate(f, changed)
    assert result.accepted is False
    assert any("duplicates the JSON.parse root cause" in reason for reason in result.reasons)


def test_json_parse_error_alias_deduplicates_with_deterministic_finding():
    normalizer = FindingNormalizer()
    findings = [
        finding(
            "review-test.ts", 233, "json-parse-without-error-handling",
            "JSON.parse is used without visible error handling and can throw for invalid JSON.",
            Severity.MEDIUM,
        ),
        finding(
            "review-test.ts", 233, "json-parse-error",
            "Parsing invalid JSON data can lead to runtime errors.",
            Severity.LOW,
        ),
    ]
    normalized = [normalizer.normalize(item) for item in findings]
    assert normalized[1].rule_id == "json-parse-without-error-handling"
    result = FindingDeduplicator().deduplicate(normalized)
    assert len(result) == 1
    assert result[0].severity == Severity.MEDIUM


def test_generic_setinterval_alias_is_rejected_when_timer_handle_is_retained():
    content = """class ResourceManager {
  private timer?: ReturnType<typeof setInterval>;
  public start() {
    this.timer = setInterval(() => console.log('tick'), 1000);
  }
}"""
    changed = make_changed("review-test.ts", content)
    raw = finding(
        "review-test.ts", 4, "setinterval",
        "Using setInterval without a clear reason or mechanism to stop it can lead to memory leaks.",
        Severity.LOW,
    )
    normalized = FindingNormalizer().normalize(raw)
    assert normalized.rule_id == "setinterval-without-timer-reference"
    result = FindingValidator().validate(normalized, changed)
    assert result.accepted is False
    assert any("return value is retained" in reason for reason in result.reasons)


def test_generic_setinterval_alias_survives_when_timer_handle_is_not_retained():
    content = """function startPolling() {
  setInterval(() => console.log('tick'), 1000);
}"""
    changed = make_changed("script.js", content)
    raw = finding(
        "script.js", 2, "setinterval",
        "setInterval is started without retaining a reference to the timer.",
        Severity.MEDIUM,
    )
    normalized = FindingNormalizer().normalize(raw)
    result = FindingValidator().validate(normalized, changed)
    assert result.accepted is True


def test_unsafe_json_parse_alias_is_canonicalized_and_security_hallucination_rejected():
    content = """class UserService {
  public parse(data: string) {
    return JSON.parse(data);
  }
}"""
    changed = make_changed("review-test.ts", content)
    raw = finding(
        "review-test.ts",
        3,
        "unsafe-json-parse",
        "Parsing untrusted JSON can lead to injection attacks or other security vulnerabilities.",
        Severity.HIGH,
        suggestion="Validate the input JSON or use a safer JSON parsing library.",
    )
    normalized = FindingNormalizer().normalize(raw)
    assert normalized.rule_id == "json-parse-without-error-handling"
    result = FindingValidator().validate(normalized, changed)
    assert result.accepted is False
    assert any("dangerous sink" in reason for reason in result.reasons)


def test_json_security_rule_name_variants_collapse_to_one_canonical_family():
    normalizer = FindingNormalizer()
    variants = (
        "unsafe-json-parse",
        "unsafe-json-parsing",
        "insecure-json-parse",
        "insecure-json-parsing",
        "json-parse-security",
        "json-security",
        "json-injection",
    )
    for rule in variants:
        normalized = normalizer.normalize(
            finding(
                "review-test.ts",
                10,
                rule,
                "JSON.parse is used without error handling.",
                Severity.MEDIUM,
            )
        )
        assert normalized.rule_id == "json-parse-without-error-handling"


def test_json_parse_security_language_does_not_create_duplicate_finding():
    content = "function parse(data) { return JSON.parse(data); }"
    changed = make_changed("script.js", content)
    normalizer = FindingNormalizer()
    deterministic = normalizer.normalize(
        finding(
            "script.js", 1, "json-parse-without-error-handling",
            "JSON.parse is used without visible error handling and can throw for invalid JSON.",
            Severity.MEDIUM,
        )
    )
    llm = normalizer.normalize(
        finding(
            "script.js", 1, "unsafe-json-parse",
            "Parsing untrusted JSON can lead to injection attacks or other security vulnerabilities.",
            Severity.HIGH,
        )
    )
    validation = FindingValidator().validate(llm, changed)
    assert validation.accepted is False
    # If a future producer emits a correctly-grounded alias instead, canonical
    # identity still guarantees one final root-cause finding.
    result = FindingDeduplicator().deduplicate([deterministic, llm])
    assert len(result) == 1


def test_generic_error_handling_json_claim_canonicalizes_to_json_parse_rule():
    raw = finding(
        "script.js",
        267,
        "error-handling",
        "The function does not handle errors when parsing JSON, which can lead to silent failures.",
        Severity.HIGH,
        suggestion="Add appropriate error handling around JSON.parse.",
    )
    normalized = FindingNormalizer().normalize(raw)
    assert normalized.rule_id == "json-parse-without-error-handling"


def test_listener_rule_with_timer_wording_canonicalizes_to_timer_rule():
    raw = finding(
        "script.js",
        274,
        "global-event-listener",
        "The function registers a global event listener without retaining a reference to the timer, which can cause memory leaks.",
        Severity.HIGH,
        suggestion="Store a reference to the timer and clean it up when it's no longer needed.",
    )
    normalized = FindingNormalizer().normalize(raw)
    assert normalized.rule_id == "setinterval-without-timer-reference"


def test_real_global_listener_claim_remains_global_listener_rule():
    raw = finding(
        "src/App.js",
        66,
        "global-event-listener",
        "A global resize event listener is added without a visible removal path.",
        Severity.HIGH,
        suggestion="Remove the listener when it is no longer needed.",
    )
    normalized = FindingNormalizer().normalize(raw)
    assert normalized.rule_id == "global-event-listener-without-removal"


def test_global_listener_alias_deduplicates_with_canonical_finding():
    normalizer = FindingNormalizer()
    findings = [
        finding(
            "src/App.js", 66, "global-event-listener-without-removal",
            "A global event listener is added without a visible removal path.", Severity.MEDIUM,
        ),
        finding(
            "src/App.js", 67, "global-event-listener",
            "A global resize event listener is added without a visible removal path.", Severity.HIGH,
        ),
    ]
    normalized = [normalizer.normalize(item) for item in findings]
    result = FindingDeduplicator().deduplicate(normalized)
    assert len(result) == 1


def test_processor_prefers_canonical_json_finding_over_generic_error_handling_variant():
    content = """function parseUserData(userData) {
  return JSON.parse(userData);
}"""
    changed = make_changed("script.js", content)
    findings = [
        finding(
            "script.js", 2, "json-parse-without-error-handling",
            "JSON.parse is used without visible error handling and can throw for invalid JSON.",
            Severity.MEDIUM,
        ),
        finding(
            "script.js", 1, "error-handling",
            "The function does not handle errors when parsing JSON, which can lead to silent failures.",
            Severity.HIGH,
            suggestion="Add appropriate error handling around JSON.parse.",
        ),
    ]
    result = FindingProcessor().process(findings, [changed])
    json_findings = [f for f in result if f.rule_id == "json-parse-without-error-handling"]
    assert len(json_findings) == 1
    assert json_findings[0].severity == Severity.MEDIUM


def test_processor_reclassifies_confused_listener_timer_claim_and_caps_severity():
    content = """function startPolling() {
  setInterval(() => console.log('tick'), 1000);
}
function registerResizeListener() {
  window.addEventListener('resize', () => console.log('resize'));
}"""
    changed = make_changed("script.js", content)
    findings = [
        finding(
            "script.js", 2, "global-event-listener",
            "The function registers a global event listener without retaining a reference to the timer, which can cause memory leaks.",
            Severity.HIGH,
            suggestion="Store a reference to the timer and clean it up when it's no longer needed.",
        ),
    ]
    result = FindingProcessor().process(findings, [changed])
    assert len(result) == 1
    assert result[0].rule_id == "setinterval-without-timer-reference"
    assert result[0].severity == Severity.MEDIUM


def test_processor_keeps_real_react_listener_cleanup_finding_unchanged():
    content = """function App() {
  const addResizeListener = () => {
    window.addEventListener('resize', () => console.log('resize'));
  };
  return null;
}"""
    changed = make_changed("src/App.js", content)
    findings = [
        finding(
            "src/App.js", 3, "global-event-listener-without-removal",
            "A global event listener is added without a visible removal path.",
            Severity.MEDIUM,
        ),
    ]
    result = FindingProcessor().process(findings, [changed])
    assert len(result) == 1
    assert result[0].rule_id == "global-event-listener-without-removal"
    assert result[0].severity == Severity.MEDIUM
