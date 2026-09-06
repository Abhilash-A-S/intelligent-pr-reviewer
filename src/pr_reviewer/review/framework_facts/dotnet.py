import re

from pr_reviewer.review.models import ChangedFile, Finding


class DotNetRuntimeFactValidator:
    """Reject C# semantic claims contradicted by local source facts."""

    def validate(self, finding: Finding, changed_file: ChangedFile) -> list[str]:
        if not changed_file.file_path.lower().endswith(".cs"):
            return []
        content = changed_file.full_content or "\n".join(
            line.content for line in changed_file.changed_lines
        )
        lines = content.splitlines()
        target = next((line.content for line in changed_file.changed_lines
                       if line.line_number == finding.line_number), "")
        claim = " ".join(part for part in (finding.message, finding.issue, finding.suggestion) if part)
        method = self._enclosing_method(lines, finding.line_number)

        named_method = re.search(r"(?:the\s+)?[`']?([A-Z][A-Za-z0-9_]*Async|[A-Z][A-Za-z0-9_]*)[`']?\s+method", claim)
        target_method = self._method_name(lines, finding.line_number)
        if named_method and target_method and named_method.group(1) != target_method:
            return [
                f"The finding describes method '{named_method.group(1)}' but targets a changed line owned by method '{target_method}'."
            ]

        if re.search(r"(?:may|might|could|potential(?:ly)?)\s+(?:be\s+)?null", claim, re.I):
            subjects = re.findall(r"[`']([A-Za-z_][A-Za-z0-9_]*)[`']", claim)
            for subject in subjects:
                if re.search(rf"\bvar\s+{re.escape(subject)}\s*=\s*new\s+", method):
                    return [f"'{subject}' is assigned a newly constructed non-null instance in this method."]
                if re.search(rf"\bvar\s+{re.escape(subject)}\s*=\s*await\s+[^;]*\.ToListAsync\s*\(", method):
                    return [f"EF Core ToListAsync returns a collection instance rather than null for '{subject}'."]
            if "service" in claim.lower() and re.search(r"\bvar\s+service\s*=\s*new\s+", method):
                return ["The local service variable is assigned a newly constructed non-null instance."]

        # A claim about a symbol absent from both the target statement and its
        # owning method is not grounded merely because the symbol is nearby.
        quoted = re.findall(r"[`']([A-Za-z_][A-Za-z0-9_]*)[`']", claim)
        if quoted and any(word in claim.lower() for word in ("null", "disposed", "uninitialized")):
            subject = quoted[0]
            if subject not in target and not re.search(rf"\b{re.escape(subject)}\b", method):
                return [f"The claimed subject '{subject}' is not part of the targeted source construct."]
        return []

    @staticmethod
    def _method_start(lines: list[str], number: int) -> int | None:
        for index in range(number - 1, max(-1, number - 50), -1):
            line = lines[index]
            if re.search(r"\b(?:public|private|protected|internal)\b", line) and "(" in line:
                if not re.search(r"\b(?:class|record|struct|interface)\b", line):
                    return index
        return None

    @classmethod
    def _method_name(cls, lines: list[str], number: int) -> str | None:
        start = cls._method_start(lines, number)
        if start is None:
            return None
        signature = " ".join(lines[start:min(len(lines), start + 8)])
        match = re.search(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\([^)]*\)\s*(?:=>|\{)", signature)
        return match.group(1) if match else None

    @classmethod
    def _enclosing_method(cls, lines: list[str], number: int) -> str:
        start = cls._method_start(lines, number)
        if start is None:
            return lines[number - 1] if 0 < number <= len(lines) else ""
        if "=>" in " ".join(lines[start:min(len(lines), start + 4)]):
            return "\n".join(lines[start:min(len(lines), start + 5)])
        depth = 0
        opened = False
        for end in range(start, len(lines)):
            depth += lines[end].count("{") - lines[end].count("}")
            opened = opened or "{" in lines[end]
            if opened and depth <= 0:
                return "\n".join(lines[start:end + 1])
        return "\n".join(lines[start:])
