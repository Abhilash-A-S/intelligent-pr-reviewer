from pr_reviewer.review.models import (
    ChangedFile,
    ChangedLine,
    Finding,
    PullRequest,
    Severity,
)


def test_severity_values():
    assert Severity.CRITICAL.value == "critical"
    assert Severity.HIGH.value == "high"
    assert Severity.MEDIUM.value == "medium"
    assert Severity.LOW.value == "low"
    assert Severity.SUGGESTION.value == "suggestion"


def test_pull_request_model():
    pull_request = PullRequest(
        provider="github",
        repository="example/repository",
        number=10,
        title="Add user authentication",
        author="developer",
        state="open",
        base_branch="main",
        head_branch="feature/auth",
        head_commit="abc123",
    )

    assert pull_request.provider == "github"
    assert pull_request.number == 10
    assert pull_request.head_commit == "abc123"


def test_changed_line_model():
    changed_line = ChangedLine(
        file_path="src/app.js",
        line_number=25,
        content='console.log("debug");',
        diff_position=30,
    )

    assert changed_line.file_path == "src/app.js"
    assert changed_line.line_number == 25
    assert changed_line.diff_position == 30


def test_changed_file_model():
    changed_line = ChangedLine(
        file_path="src/app.js",
        line_number=25,
        content='console.log("debug");',
    )

    changed_file = ChangedFile(
        file_path="src/app.js",
        status="modified",
        language="javascript",
        changed_lines=[changed_line],
    )

    assert changed_file.file_path == "src/app.js"
    assert changed_file.language == "javascript"
    assert len(changed_file.changed_lines) == 1


def test_finding_model():
    finding = Finding(
        file_path="src/app.js",
        line_number=25,
        severity=Severity.LOW,
        rule_id="no-console",
        message="Debug logging was added.",
        suggestion="Remove the console statement.",
        diff_position=30,
    )

    assert finding.severity == Severity.LOW
    assert finding.rule_id == "no-console"
    assert finding.diff_position == 30

def test_changed_file_supports_full_content():
    changed_file = ChangedFile(
        file_path="src/app.js",
        status="modified",
        full_content=(
            'const value = 10;\n'
            'console.log(value);\n'
        ),
    )

    assert changed_file.full_content is not None
    assert "console.log" in changed_file.full_content