from textwrap import dedent

from pr_reviewer.review.models import ChangedFile, ChangedLine
from pr_reviewer.review.static_analyzer import StaticAnalyzer


def analyze(source: str):
    content = dedent(source).strip()
    lines = content.splitlines()
    changed = ChangedFile(
        file_path="safe-controls.js",
        status="added",
        changed_lines=[
            ChangedLine("safe-controls.js", number, line, number)
            for number, line in enumerate(lines, 1)
        ],
        full_content=content,
    )
    return StaticAnalyzer().analyze(changed)


def matching(source: str, rule_id: str):
    return [finding for finding in analyze(source) if finding.rule_id == rule_id]


def test_qualified_interval_handle_returned_cleanup_is_safe():
    source = """
        export function startPolling(callback, milliseconds) {
          const timerId = window.setInterval(callback, milliseconds);
          return function stopPolling() {
            window.clearInterval(timerId);
          };
        }
    """
    assert matching(source, "setinterval-without-timer-reference") == []


def test_globalthis_interval_handle_is_recognized():
    source = """
        const timerId = globalThis.setInterval(run, 1000);
        globalThis.clearInterval(timerId);
    """
    assert matching(source, "setinterval-without-timer-reference") == []


def test_unretained_qualified_interval_remains_unsafe():
    source = """
        export function startPolling(callback) {
          window.setInterval(callback, 1000);
        }
    """
    findings = matching(source, "setinterval-without-timer-reference")
    assert len(findings) == 1
    assert findings[0].line_number == 2


def test_json_parse_in_try_with_nested_result_object_is_safe():
    source = """
        export function parse(rawData) {
          try {
            return {
              ok: true,
              value: JSON.parse(rawData),
            };
          } catch {
            return { ok: false, error: 'invalid JSON' };
          }
        }
    """
    assert matching(source, "json-parse-without-error-handling") == []


def test_json_parse_after_unrelated_try_catch_remains_unsafe():
    source = """
        export function parse(rawData) {
          try {
            prepare();
          } catch {
            recover();
          }
          return JSON.parse(rawData);
        }
    """
    findings = matching(source, "json-parse-without-error-handling")
    assert len(findings) == 1
    assert findings[0].line_number == 7


def test_mixed_safe_and_unsafe_parsing_reports_only_unsafe_line():
    source = """
        export function safeParse(rawData) {
          try {
            return { value: JSON.parse(rawData) };
          } catch {
            return { value: null };
          }
        }

        export function unsafeParse(rawData) {
          return JSON.parse(rawData);
        }
    """
    findings = matching(source, "json-parse-without-error-handling")
    assert len(findings) == 1
    assert findings[0].line_number == 10


def test_braces_in_strings_and_comments_do_not_break_try_matching():
    source = r'''
        export function parse(rawData) {
          try {
            const ignored = "}";
            // } must not close the try block
            return { value: JSON.parse(rawData), ignored };
          } catch {
            return null;
          }
        }
    '''
    assert matching(source, "json-parse-without-error-handling") == []
