import re

from pr_reviewer.review.models import ChangedFile, Finding


class PythonRuntimeFactValidator:
    """Reject semantic claims contradicted by documented runtime defaults."""

    def validate(self, finding: Finding, changed_file: ChangedFile) -> list[str]:
        if not changed_file.file_path.lower().endswith((".py", ".pyw")):
            return []
        if finding.rule_id == "data-validation":
            target = next(
                (
                    line.content
                    for line in changed_file.changed_lines
                    if line.line_number == finding.line_number
                ),
                "",
            )
            if re.search(r"\braise\s+(?:ValueError|TypeError|ValidationError)\b", target):
                return [
                    "Raising an explicit validation exception does not prove missing or insecure data validation."
                ]
        if finding.rule_id != "missing-timeout":
            return []

        content = changed_file.full_content or ""
        if not re.search(r"\bhttpx\.(?:AsyncClient|Client)\s*\(", content):
            return []
        if re.search(
            r"\bhttpx\.(?:AsyncClient|Client)\s*\([^)]*timeout\s*=\s*None",
            content,
            flags=re.DOTALL,
        ):
            return []

        return [
            "HTTPX clients apply a finite default timeout; omission of a per-call "
            "timeout does not prove an unbounded request unless timeout handling "
            "is explicitly disabled."
        ]
