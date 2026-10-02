from dataclasses import dataclass, field
from enum import Enum


class FindingSource(str, Enum):
    STATIC = "static"
    FRAMEWORK = "framework"
    COMPILER = "compiler"
    LLM = "llm"
    UNKNOWN = "unknown"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    SUGGESTION = "suggestion"


@dataclass
class PullRequest:
    provider: str
    repository: str
    number: int
    title: str
    author: str
    state: str
    base_branch: str
    head_branch: str
    head_commit: str


@dataclass
class ChangedLine:
    file_path: str
    line_number: int
    content: str
    diff_position: int | None = None


@dataclass
class ChangedFile:
    file_path: str
    status: str
    language: str | None = None
    patch: str | None = None
    changed_lines: list[ChangedLine] = field(
        default_factory=list
    )

    # Complete current file content from the PR head commit.
    # Used only as review context.
    full_content: str | None = None

    # Related framework files used only as analysis context (for example
    # an Angular component's external template). These files do not become
    # changed files and cannot produce inline findings by themselves.
    related_file_contents: dict[str, str] = field(default_factory=dict)


@dataclass
class Finding:
    file_path: str
    line_number: int
    severity: Severity
    rule_id: str
    message: str
    suggestion: str | None = None
    diff_position: int | None = None
    source: FindingSource = FindingSource.UNKNOWN
    category: str | None = None
    issue: str | None = None
    impact: str | None = None
    evidence: str | None = None
    confidence: str | None = None
    original_rule_id: str | None = None
