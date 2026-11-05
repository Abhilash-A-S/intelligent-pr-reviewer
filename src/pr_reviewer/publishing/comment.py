from pr_reviewer.review.models import Finding, Severity


class InlineCommentFormatter:

    SEVERITY_DISPLAY = {
        Severity.CRITICAL: (
            "🔴",
            "Critical",
            "Must fix",
        ),
        Severity.HIGH: (
            "🟠",
            "High",
            "Should fix before merge",
        ),
        Severity.MEDIUM: (
            "🟡",
            "Medium",
            "Recommended to fix",
        ),
        Severity.LOW: (
            "🔵",
            "Low",
            "Minor improvement",
        ),
        Severity.SUGGESTION: (
            "🟢",
            "Suggestion",
            "Optional improvement",
        ),
    }

    @classmethod
    def format(
        cls,
        finding: Finding,
    ) -> str:

        icon, severity_name, meaning = (
            cls.SEVERITY_DISPLAY[finding.severity]
        )

        lines: list[str] = []

        # Hidden marker used later for duplicate detection.
        marker = (
            f"<!-- intelligent-pr-reviewer:"
            f"{finding.rule_id}:"
            f"{finding.file_path}:"
            f"{finding.line_number} -->"
        )

        lines.append(marker)
        lines.append("")

        lines.append(
            f"{icon} **{severity_name}** — {meaning}"
        )

        lines.append("")
        if finding.category:
            lines.append(
                f"**Category:** {finding.category}"
            )
            lines.append("")

        lines.append(
            f"**Issue:** {(finding.issue or finding.message).strip()}"
        )

        if finding.impact:
            lines.append("")
            lines.append(
                f"**Impact:** {finding.impact.strip()}"
            )

        if finding.evidence:
            lines.append("")
            lines.append(
                f"**Evidence:** {finding.evidence.strip()}"
            )

        if finding.suggestion:
            lines.append("")
            lines.append("💡 **Suggestion**")
            lines.append("")
            lines.append(
                finding.suggestion.strip()
            )

        lines.append("")
        lines.append(
            f"_Rule: `{finding.rule_id}`_"
        )

        return "\n".join(lines)

    @classmethod
    def format_group(cls, findings: list[Finding]) -> str:
        """Format distinct root causes on one changed line as one comment."""
        if len(findings) == 1:
            return cls.format(findings[0])
        sections = [
            f"### Intelligent PR Reviewer — {len(findings)} findings on this line"
        ]
        for finding in findings:
            sections.extend(("", "---", "", cls.format(finding)))
        return "\n".join(sections)
