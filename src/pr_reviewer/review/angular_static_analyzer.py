import re

from pr_reviewer.review.models import ChangedFile, Finding, Severity


class AngularStaticAnalyzer:
    """High-confidence Angular-specific deterministic checks.

    This adapter intentionally stays conservative. It only reports lifecycle
    issues when Angular component/directive source provides direct evidence.
    """

    ANGULAR_CLASS_PATTERN = re.compile(r"@(Component|Directive)\s*\(", re.MULTILINE)
    INTERVAL_SUBSCRIBE_PATTERN = re.compile(
        r"\binterval\s*\([^)]*\)\s*(?:"
        r"\.\s*pipe\s*\([^;]*?\)\s*)?"
        r"\.\s*subscribe\s*\(",
        re.DOTALL,
    )
    ASSIGNED_INTERVAL_SUBSCRIBE_PATTERN = re.compile(
        r"\bthis\s*\.\s*(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*"
        r"interval\s*\([^)]*\)\s*(?:"
        r"\.\s*pipe\s*\([^;]*?\)\s*)?"
        r"\.\s*subscribe\s*\(",
        re.DOTALL,
    )

    def analyze(self, changed_file: ChangedFile) -> list[Finding]:
        if not changed_file.file_path.lower().endswith(".ts"):
            return []

        content = changed_file.full_content or ""
        if not content or not self.ANGULAR_CLASS_PATTERN.search(content):
            return []

        changed_by_line = {
            line.line_number: line
            for line in changed_file.changed_lines
        }
        findings: list[Finding] = []
        seen: set[int] = set()

        for match in self.INTERVAL_SUBSCRIBE_PATTERN.finditer(content):
            line_number = content.count("\n", 0, match.start()) + 1
            changed = changed_by_line.get(line_number)
            if changed is None or line_number in seen:
                continue

            chain = match.group(0)
            if self._uses_automatic_teardown(chain):
                continue

            assigned = self._assignment_for_match(content, match.start())
            if assigned and self._has_explicit_unsubscribe(content, assigned):
                continue

            seen.add(line_number)
            findings.append(
                Finding(
                    file_path=changed_file.file_path,
                    line_number=line_number,
                    severity=Severity.MEDIUM,
                    rule_id="rxjs-subscription-without-cleanup",
                    message=(
                        "An interval Observable is subscribed to in an Angular "
                        "component without visible subscription teardown."
                    ),
                    suggestion=(
                        "Use takeUntilDestroyed/DestroyRef or unsubscribe from "
                        "the retained Subscription during component destruction."
                    ),
                    diff_position=changed.diff_position,
                )
            )

        return findings

    @staticmethod
    def _uses_automatic_teardown(chain: str) -> bool:
        normalized = re.sub(r"\s+", "", chain)
        return (
            "takeUntilDestroyed(" in normalized
            or "takeUntil(" in normalized
        )

    def _assignment_for_match(self, content: str, match_start: int) -> str | None:
        line_start = content.rfind("\n", 0, match_start) + 1
        prefix = content[line_start:match_start]
        assigned = re.search(
            r"\bthis\s*\.\s*([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*$",
            prefix,
        )
        return assigned.group(1) if assigned else None

    @staticmethod
    def _has_explicit_unsubscribe(content: str, name: str) -> bool:
        return bool(
            re.search(
                rf"\bthis\s*\.\s*{re.escape(name)}\s*(?:\?\.|\.)\s*unsubscribe\s*\(",
                content,
            )
        )
