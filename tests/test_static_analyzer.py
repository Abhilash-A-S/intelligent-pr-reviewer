from pr_reviewer.review.models import (
    ChangedFile,
    ChangedLine,
    Severity,
)
from pr_reviewer.review.static_analyzer import (
    StaticAnalyzer,
)


def create_changed_file(
    file_path: str = "script.js",
    changed_content: str = (
        'console.log("test");'
    ),
    line_number: int = 10,
    full_content: str | None = None,
) -> ChangedFile:

    if full_content is None:
        full_content = changed_content

    return ChangedFile(
        file_path=file_path,
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path=file_path,
                line_number=line_number,
                content=changed_content,
                diff_position=5,
            )
        ],
        full_content=full_content,
    )


# ======================================================
# JavaScript / TypeScript deterministic checks
# ======================================================


def test_detects_console_log():
    analyzer = StaticAnalyzer()

    changed_file = create_changed_file(
        changed_content=(
            'console.log("Application loaded");'
        )
    )

    findings = analyzer.analyze(
        changed_file
    )

    assert len(findings) == 1

    finding = findings[0]

    assert finding.rule_id == "no-console"
    assert finding.severity == Severity.LOW
    assert finding.line_number == 10
    assert finding.diff_position == 5


def test_detects_console_log_with_spacing():
    analyzer = StaticAnalyzer()

    changed_file = create_changed_file(
        changed_content=(
            'console . log ("debug");'
        )
    )

    findings = analyzer.analyze(
        changed_file
    )

    assert len(findings) == 1

    assert (
        findings[0].rule_id
        == "no-console"
    )


def test_detects_debugger():
    analyzer = StaticAnalyzer()

    changed_file = create_changed_file(
        changed_content="debugger;"
    )

    findings = analyzer.analyze(
        changed_file
    )

    assert len(findings) == 1

    finding = findings[0]

    assert finding.rule_id == "debugger"

    assert (
        finding.severity
        == Severity.MEDIUM
    )


def test_detects_debugger_without_semicolon():
    analyzer = StaticAnalyzer()

    changed_file = create_changed_file(
        changed_content="debugger"
    )

    findings = analyzer.analyze(
        changed_file
    )

    assert len(findings) == 1

    assert (
        findings[0].rule_id
        == "debugger"
    )


def test_detects_obvious_unused_const():
    analyzer = StaticAnalyzer()

    changed_file = create_changed_file(
        changed_content=(
            "const abc = 12346789;"
        ),
        full_content=(
            "function start() {\n"
            "    console.log('start');\n"
            "}\n"
            "\n"
            "const abc = 12346789;\n"
        ),
    )

    findings = analyzer.analyze(
        changed_file
    )

    assert len(findings) == 1

    finding = findings[0]

    assert (
        finding.rule_id
        == "unused-variable"
    )

    assert finding.severity == Severity.LOW
    assert "abc" in finding.message


def test_detects_obvious_unused_let():
    analyzer = StaticAnalyzer()

    changed_file = create_changed_file(
        changed_content=(
            'let temporary = "test";'
        ),
        full_content=(
            'let temporary = "test";\n'
            "runApplication();"
        ),
    )

    findings = analyzer.analyze(
        changed_file
    )

    assert len(findings) == 1

    assert (
        findings[0].rule_id
        == "unused-variable"
    )


def test_detects_obvious_unused_var():
    analyzer = StaticAnalyzer()

    changed_file = create_changed_file(
        changed_content=(
            "var temporaryValue = 100;"
        ),
        full_content=(
            "function run() {\n"
            "    return true;\n"
            "}\n"
            "\n"
            "var temporaryValue = 100;\n"
        ),
    )

    findings = analyzer.analyze(
        changed_file
    )

    assert len(findings) == 1

    assert (
        findings[0].rule_id
        == "unused-variable"
    )


def test_does_not_report_used_variable():
    analyzer = StaticAnalyzer()

    changed_file = create_changed_file(
        changed_content=(
            "const button = "
            'document.querySelector("#submit");'
        ),
        full_content=(
            "const button = "
            'document.querySelector("#submit");\n'
            "\n"
            "button.addEventListener("
            '"click", submitForm);'
        ),
    )

    findings = analyzer.analyze(
        changed_file
    )

    assert findings == []


def test_does_not_detect_unused_without_full_content():
    analyzer = StaticAnalyzer()

    changed_file = ChangedFile(
        file_path="script.js",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="script.js",
                line_number=10,
                content=(
                    "const abc = 123;"
                ),
                diff_position=5,
            )
        ],
        full_content=None,
    )

    findings = analyzer.analyze(
        changed_file
    )

    assert findings == []


def test_supports_typescript():
    analyzer = StaticAnalyzer()

    changed_file = create_changed_file(
        file_path="src/app.ts",
        changed_content=(
            'console.log("test");'
        ),
    )

    findings = analyzer.analyze(
        changed_file
    )

    assert len(findings) == 1

    assert (
        findings[0].rule_id
        == "no-console"
    )


def test_supports_tsx():
    analyzer = StaticAnalyzer()

    changed_file = create_changed_file(
        file_path="src/App.tsx",
        changed_content="debugger;",
    )

    findings = analyzer.analyze(
        changed_file
    )

    assert len(findings) == 1

    assert (
        findings[0].rule_id
        == "debugger"
    )


def test_supports_jsx():
    analyzer = StaticAnalyzer()

    changed_file = create_changed_file(
        file_path="src/App.jsx",
        changed_content=(
            'console.log("render");'
        ),
    )

    findings = analyzer.analyze(
        changed_file
    )

    assert len(findings) == 1

    assert (
        findings[0].rule_id
        == "no-console"
    )


# ======================================================
# Generic hardcoded-secret detection
# ======================================================


def test_detects_hardcoded_secret_in_java():
    analyzer = StaticAnalyzer()

    changed_file = create_changed_file(
        file_path="src/UserService.java",
        changed_content=(
            'private String apiKey = "secret-key-123";'
        ),
    )

    findings = analyzer.analyze(
        changed_file
    )

    assert len(findings) == 1

    finding = findings[0]

    assert (
        finding.rule_id
        == "hardcoded-secret"
    )

    assert (
        finding.severity
        == Severity.CRITICAL
    )

    assert "apiKey" in finding.message


def test_detects_hardcoded_secret_in_csharp():
    analyzer = StaticAnalyzer()

    changed_file = create_changed_file(
        file_path="src/UserService.cs",
        changed_content=(
            'private string clientSecret = '
            '"super-secret-value";'
        ),
    )

    findings = analyzer.analyze(
        changed_file
    )

    assert len(findings) == 1

    assert (
        findings[0].rule_id
        == "hardcoded-secret"
    )


def test_detects_hardcoded_secret_in_python():
    analyzer = StaticAnalyzer()

    changed_file = create_changed_file(
        file_path="src/service.py",
        changed_content=(
            'api_key = "secret-key-123"'
        ),
    )

    findings = analyzer.analyze(
        changed_file
    )

    assert len(findings) == 1

    assert (
        findings[0].rule_id
        == "hardcoded-secret"
    )


def test_detects_hardcoded_secret_in_go():
    analyzer = StaticAnalyzer()

    changed_file = create_changed_file(
        file_path="src/main.go",
        changed_content=(
            'apiKey := "secret-key-123"'
        ),
    )

    findings = analyzer.analyze(
        changed_file
    )

    assert len(findings) == 1

    assert (
        findings[0].rule_id
        == "hardcoded-secret"
    )


def test_detects_hardcoded_secret_in_ruby():
    analyzer = StaticAnalyzer()

    changed_file = create_changed_file(
        file_path="src/service.rb",
        changed_content=(
            'authToken = "secret-token-123"'
        ),
    )

    findings = analyzer.analyze(
        changed_file
    )

    assert len(findings) == 1

    assert (
        findings[0].rule_id
        == "hardcoded-secret"
    )


def test_detects_hardcoded_secret_in_php():
    analyzer = StaticAnalyzer()

    changed_file = create_changed_file(
        file_path="src/service.php",
        changed_content=(
            '$apiKey = "secret-key-123";'
        ),
    )

    findings = analyzer.analyze(
        changed_file
    )

    assert len(findings) == 1

    assert (
        findings[0].rule_id
        == "hardcoded-secret"
    )


def test_detects_password_assignment():
    analyzer = StaticAnalyzer()

    changed_file = create_changed_file(
        file_path="src/config.py",
        changed_content=(
            'password = "VerySecret123!"'
        ),
    )

    findings = analyzer.analyze(
        changed_file
    )

    assert len(findings) == 1

    assert (
        findings[0].rule_id
        == "hardcoded-secret"
    )


def test_detects_token_assignment():
    analyzer = StaticAnalyzer()

    changed_file = create_changed_file(
        file_path="src/config.cs",
        changed_content=(
            'string authToken = "abcdef123456";'
        ),
    )

    findings = analyzer.analyze(
        changed_file
    )

    assert len(findings) == 1

    assert (
        findings[0].rule_id
        == "hardcoded-secret"
    )


def test_secret_detector_preserves_changed_line_information():
    analyzer = StaticAnalyzer()

    changed_file = create_changed_file(
        file_path="src/UserService.java",
        changed_content=(
            'String apiKey = "secret-key-123";'
        ),
        line_number=42,
    )

    findings = analyzer.analyze(
        changed_file
    )

    assert len(findings) == 1

    finding = findings[0]

    assert finding.line_number == 42
    assert finding.diff_position == 5

    assert (
        finding.file_path
        == "src/UserService.java"
    )


# ======================================================
# Secret false-positive protection
# ======================================================


def test_ignores_placeholder_api_key():
    analyzer = StaticAnalyzer()

    changed_file = create_changed_file(
        file_path="src/config.py",
        changed_content=(
            'api_key = "your-api-key"'
        ),
    )

    findings = analyzer.analyze(
        changed_file
    )

    assert findings == []


def test_ignores_placeholder_password():
    analyzer = StaticAnalyzer()

    changed_file = create_changed_file(
        file_path="src/config.py",
        changed_content=(
            'password = "changeme"'
        ),
    )

    findings = analyzer.analyze(
        changed_file
    )

    assert findings == []


def test_ignores_short_secret_value():
    analyzer = StaticAnalyzer()

    changed_file = create_changed_file(
        file_path="src/config.py",
        changed_content=(
            'api_key = "abc"'
        ),
    )

    findings = analyzer.analyze(
        changed_file
    )

    assert findings == []


def test_does_not_treat_normal_string_as_secret():
    analyzer = StaticAnalyzer()

    changed_file = create_changed_file(
        file_path="src/UserService.java",
        changed_content=(
            'String userName = "Abhilash";'
        ),
    )

    findings = analyzer.analyze(
        changed_file
    )

    assert findings == []


def test_does_not_treat_identifier_without_secret_name_as_secret():
    analyzer = StaticAnalyzer()

    changed_file = create_changed_file(
        file_path="src/config.py",
        changed_content=(
            'endpoint = "https://api.example.com"'
        ),
    )

    findings = analyzer.analyze(
        changed_file
    )

    assert findings == []


# ======================================================
# Non-JS files remain free from JS-specific checks
# ======================================================


def test_html_does_not_run_javascript_console_check():
    analyzer = StaticAnalyzer()

    changed_file = create_changed_file(
        file_path="index.html",
        changed_content=(
            '<script>console.log("test")</script>'
        ),
    )

    findings = analyzer.analyze(
        changed_file
    )

    assert findings == []


def test_css_does_not_run_javascript_checks():
    analyzer = StaticAnalyzer()

    changed_file = create_changed_file(
        file_path="styles.css",
        changed_content=(
            ".button { cursor: pointer; }"
        ),
    )

    findings = analyzer.analyze(
        changed_file
    )

    assert findings == []


def test_java_does_not_run_js_unused_variable_check():
    analyzer = StaticAnalyzer()

    changed_file = create_changed_file(
        file_path="src/UserService.java",
        changed_content=(
            "String temporaryValue = \"hello\";"
        ),
        full_content=(
            "String temporaryValue = \"hello\";"
        ),
    )

    findings = analyzer.analyze(
        changed_file
    )

    assert findings == []


# ======================================================
# Multi-file analysis
# ======================================================


def test_analyze_files_combines_findings():
    analyzer = StaticAnalyzer()

    console_file = create_changed_file(
        file_path="first.js",
        changed_content=(
            'console.log("debug");'
        ),
    )

    debugger_file = create_changed_file(
        file_path="second.ts",
        changed_content="debugger;",
    )

    findings = analyzer.analyze_files(
        [
            console_file,
            debugger_file,
        ]
    )

    assert len(findings) == 2

    rule_ids = {
        finding.rule_id
        for finding in findings
    }

    assert rule_ids == {
        "no-console",
        "debugger",
    }


def test_analyze_files_combines_multiple_languages():
    analyzer = StaticAnalyzer()

    java_file = create_changed_file(
        file_path="UserService.java",
        changed_content=(
            'String apiKey = "secret-key-123";'
        ),
    )

    python_file = create_changed_file(
        file_path="service.py",
        changed_content=(
            'password = "super-secret-password"'
        ),
    )

    javascript_file = create_changed_file(
        file_path="app.js",
        changed_content=(
            'console.log("debug");'
        ),
    )

    findings = analyzer.analyze_files(
        [
            java_file,
            python_file,
            javascript_file,
        ]
    )

    assert len(findings) == 3

    assert [
        finding.rule_id
        for finding in findings
    ] == [
        "hardcoded-secret",
        "hardcoded-secret",
        "no-console",
    ]


# ======================================================
# Changed-line boundary
# ======================================================


def test_only_changed_lines_are_analyzed():
    analyzer = StaticAnalyzer()

    changed_file = ChangedFile(
        file_path="script.js",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="script.js",
                line_number=20,
                content=(
                    "const usedValue = 10;"
                ),
                diff_position=8,
            )
        ],
        full_content=(
            'console.log("old code");\n'
            "debugger;\n"
            'const apiKey = "secret-key-123";\n'
            "\n"
            "const usedValue = 10;\n"
            "console.log(usedValue);\n"
        ),
    )

    findings = analyzer.analyze(
        changed_file
    )

    assert findings == []


def test_preserves_changed_line_information():
    analyzer = StaticAnalyzer()

    changed_file = create_changed_file(
        file_path="src/example.js",
        changed_content=(
            'console.log("hello");'
        ),
        line_number=42,
    )

    findings = analyzer.analyze(
        changed_file
    )

    assert len(findings) == 1

    finding = findings[0]

    assert (
        finding.file_path
        == "src/example.js"
    )

    assert finding.line_number == 42
    assert finding.diff_position == 5

def test_detects_unretained_setinterval_independently_of_listener_cleanup():
    analyzer = StaticAnalyzer()
    changed_file = ChangedFile(
        file_path="script.js",
        status="modified",
        changed_lines=[
            ChangedLine(file_path="script.js", line_number=10, content="  setInterval(() => poll(), 1000);"),
            ChangedLine(file_path="script.js", line_number=20, content="  window.addEventListener('resize', () => render());"),
        ],
        full_content=(
            "function startPolling() {\n"
            "  setInterval(() => poll(), 1000);\n"
            "}\n"
            "function registerResize() {\n"
            "  window.addEventListener('resize', () => render());\n"
            "}\n"
        ),
    )

    findings = analyzer.analyze(changed_file)
    lifecycle = {(f.line_number, f.rule_id) for f in findings if f.rule_id in {
        "setinterval-without-timer-reference",
        "global-event-listener-without-removal",
    }}

    assert (10, "setinterval-without-timer-reference") in lifecycle
    assert (20, "global-event-listener-without-removal") in lifecycle


def test_does_not_report_setinterval_when_handle_is_retained():
    analyzer = StaticAnalyzer()
    changed_file = create_changed_file(
        changed_content="const timer = setInterval(() => poll(), 1000);",
        full_content="const timer = setInterval(() => poll(), 1000);\nclearInterval(timer);",
    )

    findings = analyzer.analyze(changed_file)
    assert not any(f.rule_id == "setinterval-without-timer-reference" for f in findings)


def test_typescript_constructor_parameter_property_uses_real_identifier_and_class_usage():
    analyzer = StaticAnalyzer()

    content = (
        "import { HttpClient } from '@angular/common/http';\n"
        "class Example {\n"
        "  constructor(private http: HttpClient) {}\n"
        "  load(): void {\n"
        "    this.http.get('/api/users').subscribe();\n"
        "  }\n"
        "}\n"
    )

    changed_file = ChangedFile(
        file_path="src/app/example.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app/example.ts",
                line_number=3,
                content="  constructor(private http: HttpClient) {}",
                diff_position=3,
            )
        ],
        full_content=content,
    )

    findings = analyzer.analyze(changed_file)

    assert not any(
        finding.rule_id == "unused-parameter"
        for finding in findings
    )


def test_typescript_constructor_private_readonly_parameter_property_is_parsed_correctly():
    analyzer = StaticAnalyzer()

    content = (
        "class Example {\n"
        "  constructor(private readonly api: ApiService) {}\n"
        "  load(): void {\n"
        "    this.api.load();\n"
        "  }\n"
        "}\n"
    )

    changed_file = ChangedFile(
        file_path="src/app/example.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app/example.ts",
                line_number=2,
                content="  constructor(private readonly api: ApiService) {}",
                diff_position=2,
            )
        ],
        full_content=content,
    )

    findings = analyzer.analyze(changed_file)

    assert not any(
        finding.rule_id == "unused-parameter"
        for finding in findings
    )


def test_angular_component_interval_subscription_without_cleanup_is_detected():
    analyzer = StaticAnalyzer()

    content = (
        "import { Component } from '@angular/core';\n"
        "import { interval } from 'rxjs';\n"
        "@Component({selector: 'x-test', template: ''})\n"
        "export class TestComponent {\n"
        "  start(): void {\n"
        "    interval(1000).subscribe(() => this.tick());\n"
        "  }\n"
        "  tick(): void {}\n"
        "}\n"
    )

    changed_file = ChangedFile(
        file_path="src/app/test.component.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app/test.component.ts",
                line_number=6,
                content="    interval(1000).subscribe(() => this.tick());",
                diff_position=6,
            )
        ],
        full_content=content,
    )

    findings = analyzer.analyze(changed_file)

    assert any(
        finding.rule_id == "rxjs-subscription-without-cleanup"
        and finding.line_number == 6
        for finding in findings
    )


def test_angular_component_interval_subscription_with_take_until_destroyed_is_safe():
    analyzer = StaticAnalyzer()

    content = (
        "import { Component } from '@angular/core';\n"
        "import { interval } from 'rxjs';\n"
        "import { takeUntilDestroyed } from '@angular/core/rxjs-interop';\n"
        "@Component({selector: 'x-test', template: ''})\n"
        "export class TestComponent {\n"
        "  start(): void {\n"
        "    interval(1000).pipe(takeUntilDestroyed()).subscribe(() => this.tick());\n"
        "  }\n"
        "  tick(): void {}\n"
        "}\n"
    )

    changed_file = ChangedFile(
        file_path="src/app/test.component.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app/test.component.ts",
                line_number=7,
                content=(
                    "    interval(1000).pipe(takeUntilDestroyed())."
                    "subscribe(() => this.tick());"
                ),
                diff_position=7,
            )
        ],
        full_content=content,
    )

    findings = analyzer.analyze(changed_file)

    assert not any(
        finding.rule_id == "rxjs-subscription-without-cleanup"
        for finding in findings
    )


def test_angular_component_retained_interval_subscription_with_unsubscribe_is_safe():
    analyzer = StaticAnalyzer()

    content = (
        "import { Component } from '@angular/core';\n"
        "import { interval, Subscription } from 'rxjs';\n"
        "@Component({selector: 'x-test', template: ''})\n"
        "export class TestComponent {\n"
        "  private subscription?: Subscription;\n"
        "  start(): void {\n"
        "    this.subscription = interval(1000).subscribe(() => this.tick());\n"
        "  }\n"
        "  ngOnDestroy(): void {\n"
        "    this.subscription?.unsubscribe();\n"
        "  }\n"
        "  tick(): void {}\n"
        "}\n"
    )

    changed_file = ChangedFile(
        file_path="src/app/test.component.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app/test.component.ts",
                line_number=7,
                content=(
                    "    this.subscription = interval(1000)."
                    "subscribe(() => this.tick());"
                ),
                diff_position=7,
            )
        ],
        full_content=content,
    )

    findings = analyzer.analyze(changed_file)

    assert not any(
        finding.rule_id == "rxjs-subscription-without-cleanup"
        for finding in findings
    )


def test_httpclient_subscription_is_not_misclassified_as_rxjs_lifecycle_leak():
    analyzer = StaticAnalyzer()

    content = (
        "import { Component } from '@angular/core';\n"
        "@Component({selector: 'x-test', template: ''})\n"
        "export class TestComponent {\n"
        "  constructor(private http: HttpClient) {}\n"
        "  load(): void {\n"
        "    this.http.get('/api/users').subscribe();\n"
        "  }\n"
        "}\n"
    )

    changed_file = ChangedFile(
        file_path="src/app/test.component.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app/test.component.ts",
                line_number=6,
                content="    this.http.get('/api/users').subscribe();",
                diff_position=6,
            )
        ],
        full_content=content,
    )

    findings = analyzer.analyze(changed_file)

    assert not any(
        finding.rule_id == "rxjs-subscription-without-cleanup"
        for finding in findings
    )


def test_conditional_return_does_not_mark_following_statement_unreachable():
    changed = ChangedFile(
        file_path="src/check.mjs",
        status="modified",
        full_content="""function decide(value) {\n  if (value) return true;\n  const next = compute();\n  return next;\n}\n""",
        changed_lines=[
            ChangedLine(file_path="src/check.mjs", line_number=2, content="  if (value) return true;", diff_position=1),
            ChangedLine(file_path="src/check.mjs", line_number=3, content="  const next = compute();", diff_position=2),
        ],
    )
    findings = StaticAnalyzer().analyze(changed)
    assert not any(f.rule_id == "unreachable-code" and f.line_number == 3 for f in findings)


def test_agent_helper_script_is_skipped_by_static_analysis():
    changed = ChangedFile(
        file_path="nx-angular-review/.agents/skills/monitor-ci/scripts/ci.mjs",
        status="modified",
        full_content="console.log('tooling');\n",
        changed_lines=[ChangedLine(file_path="nx-angular-review/.agents/skills/monitor-ci/scripts/ci.mjs", line_number=1, content="console.log('tooling');", diff_position=1)],
    )
    assert StaticAnalyzer().analyze(changed) == []
