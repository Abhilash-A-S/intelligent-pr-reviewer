from pr_reviewer.review.deduplicator import FindingDeduplicator
from pr_reviewer.review.finding_policy import FindingPolicy
from pr_reviewer.review.models import Finding, Severity
from pr_reviewer.review.normalizer import FindingNormalizer


def f(rule, message, line=10, severity=Severity.HIGH, suggestion=None):
    return Finding(
        file_path="script.js",
        line_number=line,
        severity=severity,
        rule_id=rule,
        message=message,
        suggestion=suggestion,
    )


def test_no_empty_catch_claim_is_canonicalized_and_deduped():
    n = FindingNormalizer()
    static = f("empty-catch-block", "An empty catch block silently ignores an error.", 224, Severity.MEDIUM)
    ai = n.normalize(f("no-empty-catch", "Empty catch blocks can silently ignore exceptions.", 225))
    assert ai.rule_id == "empty-catch-block"
    ai = FindingPolicy().apply(ai)
    out = FindingDeduplicator().deduplicate([static, ai])
    assert len(out) == 1
    assert out[0].severity == Severity.MEDIUM


def test_unhandled_interval_claim_is_canonicalized_and_capped():
    n = FindingNormalizer()
    p = FindingPolicy()
    finding = n.normalize(f(
        "unhandled-interval",
        "setInterval started without retaining timer reference, leading to potential memory leaks.",
        273,
    ))
    assert finding.rule_id == "setinterval-without-timer-reference"
    assert p.apply(finding).severity == Severity.MEDIUM


def test_unhandled_listener_claim_is_canonicalized_and_capped():
    n = FindingNormalizer()
    p = FindingPolicy()
    finding = n.normalize(f(
        "unhandled-event-listener",
        "Global event listener without removal can lead to memory leaks.",
        283,
    ))
    assert finding.rule_id == "global-event-listener-without-removal"
    assert p.apply(finding).severity == Severity.MEDIUM


def test_generic_error_handling_json_claim_owned_by_json_family():
    n = FindingNormalizer()
    finding = n.normalize(f(
        "error-handling",
        "The function does not handle errors when parsing JSON and JSON.parse may throw.",
        267,
    ))
    assert finding.rule_id == "json-parse-without-error-handling"


def test_mislabelled_listener_with_timer_language_becomes_timer():
    n = FindingNormalizer()
    finding = n.normalize(f(
        "global-event-listener",
        "The function registers a global event listener without retaining a reference to the timer.",
        274,
    ))
    assert finding.rule_id == "setinterval-without-timer-reference"


def test_password_label_copy_preference_is_rejected():
    p = FindingPolicy()
    finding = f(
        "password-input-label",
        "The password input label should be more descriptive.",
        severity=Severity.LOW,
    )
    assert p.apply(finding) is None


def test_unnecessary_else_style_refactor_is_rejected():
    p = FindingPolicy()
    finding = f(
        "unnecessary-else",
        "The else block is unnecessary after the return statement.",
        severity=Severity.LOW,
    )
    assert p.apply(finding) is None

from pr_reviewer.review.models import ChangedFile, ChangedLine
from pr_reviewer.review.processor import FindingProcessor


def _changed(content: str) -> ChangedFile:
    path = "script.js"
    return ChangedFile(
        file_path=path,
        status="modified",
        changed_lines=[
            ChangedLine(file_path=path, line_number=i, content=line)
            for i, line in enumerate(content.splitlines(), start=1)
        ],
        full_content=content,
    )


def test_processor_owns_known_js_issue_families_despite_llm_rule_drift():
    content = """function demo(raw) {
  try {
    JSON.parse(raw);
  } catch (error) {
  }
  setInterval(() => console.log('tick'), 1000);
  window.addEventListener('resize', () => console.log('resize'));
}
"""
    changed = _changed(content)
    findings = [
        # deterministic/root findings
        f("json-parse-without-error-handling", "JSON.parse is used without visible error handling and can throw for invalid JSON.", 3, Severity.MEDIUM),
        f("empty-catch-block", "An empty catch block silently ignores an error.", 4, Severity.MEDIUM),
        # free-form AI variants of the same/owned issue families
        f("error-handling", "The function does not handle errors when parsing JSON; JSON.parse may throw.", 3, Severity.HIGH),
        f("no-empty-catch", "Empty catch blocks can silently ignore exceptions.", 5, Severity.HIGH),
        f("unhandled-interval", "setInterval started without retaining timer reference, leading to potential memory leaks.", 6, Severity.HIGH),
        f("unhandled-event-listener", "Global event listener without removal can lead to memory leaks.", 7, Severity.HIGH),
        # low-value wording variants that should never become defects
        f("password-input-label", "The password input label should be more descriptive.", 1, Severity.LOW),
        f("unnecessary-else", "The else block is unnecessary after the return statement.", 1, Severity.LOW),
    ]
    result = FindingProcessor().process(findings, [changed])
    rules = [item.rule_id for item in result]
    assert rules.count("json-parse-without-error-handling") == 1
    assert rules.count("empty-catch-block") == 1
    assert rules.count("setinterval-without-timer-reference") == 1
    assert rules.count("global-event-listener-without-removal") == 1
    assert "error-handling" not in rules
    assert "no-empty-catch" not in rules
    assert "unhandled-interval" not in rules
    assert "unhandled-event-listener" not in rules
    assert "password-input-label" not in rules
    assert "unnecessary-else" not in rules
    assert all(item.severity != Severity.HIGH for item in result if item.rule_id in {
        "json-parse-without-error-handling", "empty-catch-block",
        "setinterval-without-timer-reference", "global-event-listener-without-removal"
    })
