from dataclasses import dataclass, field
import re

from pr_reviewer.review.models import ChangedFile, Finding, FindingSource


@dataclass(frozen=True)
class SemanticEvidenceResult:
    accepted: bool
    reasons: list[str] = field(default_factory=list)


class UniversalSemanticEvidenceValidator:
    """Validate universal AI concepts using language-neutral source shapes."""

    RULES = {
        "incorrect-result-handling",
        "async-blocking-operation",
        "missing-timeout",
        "authorization",
        "command-injection",
        "unsafe-code-execution",
        "cache-consistency",
        "insufficient-test-assertion",
        "sql-injection",
        "path-traversal",
        "unsafe-deserialization",
        "weak-cryptography",
        "resource-cleanup",
        "unowned-background-task",
        "exception-detail-exposure",
    }

    def validate(self, finding: Finding, changed_file: ChangedFile) -> SemanticEvidenceResult:
        if finding.source is not FindingSource.LLM:
            return SemanticEvidenceResult(True)

        full_finding_text = f"{finding.message} {finding.issue or ''} {finding.suggestion or ''}".lower()
        speculative_phrases = [
            "assume", "assumes", "assuming", "assumption",
            "probably", "might be", "could be", "should come from",
            "appears to be", "seems to", "without knowing", "come from a database",
        ]
        if any(phrase in full_finding_text for phrase in speculative_phrases):
            return SemanticEvidenceResult(False, ["Finding rejected because it is based on speculation or assumption."])

        if finding.rule_id not in self.RULES:
            return SemanticEvidenceResult(True)

        line = self._line(changed_file, finding.line_number)
        if line is None:
            return SemanticEvidenceResult(False, ["Universal semantic claim has no exact changed-line evidence."])

        text = f"{finding.message} {finding.suggestion or ''}".lower()
        lowered = line.lower()
        content = changed_file.full_content or "\n".join(item.content for item in changed_file.changed_lines)
        accepted = self._supports(finding.rule_id, lowered, text, content, finding.line_number)
        if accepted:
            return SemanticEvidenceResult(True)
        return SemanticEvidenceResult(
            False,
            ["Universal semantic category is not proven by the targeted changed line and source construct."],
        )

    @staticmethod
    def _supports(rule: str, line: str, claim: str, content: str, line_number: int) -> bool:
        if rule == "incorrect-result-handling":
            return bool(re.search(r"\b(return|update|save|delete|create|result|success)\b", line))

        if rule == "async-blocking-operation":
            return bool(re.search(r"(?:\btime\.sleep|\bthread\.sleep|\.wait\s*\(|\.result\b|readfilesync|execsync)", line, re.I))

        if rule == "missing-timeout":
            request = re.search(r"\b(?:get|post|put|patch|delete|request|send)\s*\(", line, re.I)
            if not request or "timeout" in line:
                return False
            lines = content.splitlines()
            window = " ".join(lines[max(0, line_number - 2): min(len(lines), line_number + 2)]).lower()
            return "timeout=" not in window and "timeout:" not in window

        if rule == "authorization":
            return bool(re.search(r"\b(role|permission|authori[sz]|claim|scope)\b", f"{line} {claim}", re.I)) and bool(re.search(r"\b(if|unless|require|check|==|!=|contains|includes)\b", line, re.I))

        if rule == "command-injection":
            return bool(re.search(r"\b(shell\s*=\s*true|exec|system|popen|check_output|process\.start)\b", line, re.I))

        if rule == "unsafe-code-execution":
            return bool(re.search(r"\b(eval|exec|compile|function)\s*\(", line, re.I))

        if rule == "cache-consistency":
            combined = f"{line} {claim}"
            return "cache" in combined and (
                "key" in line or "cache" in line or "memo" in line
            )

        if rule == "insufficient-test-assertion":
            assertion = bool(re.search(r"\b(assert|expect|verify|should)\b", line, re.I))
            narrow = bool(re.search(r"status(?:_code)?|called|true|not\s+none|not\s+null|assert\.(?:equal|notnull|istype)", line, re.I))
            # Normalization already established the semantic claim. Evidence
            # validation proves the narrow assertion shape and must not depend
            # on the LLM choosing one particular wording for "weak".
            return assertion and narrow

        if rule == "sql-injection":
            return bool(re.search(r"(?:\b(?:execute|executemany|raw|text)\s*\(|\.query\s*\(|fromsqlraw|executesqlraw)", line, re.I)) and bool(
                re.search(r"(?:f[\"']|\$\{|\.format\s*\(|%s|\+)", line)
                or "interpolat" in claim
            )

        if rule == "path-traversal":
            return bool(re.search(r"\b(open|read_text|read_bytes|readalltext|fileinputstream|physicalfile|file\.create|path\.(?:join|resolve))\b", f"{line} {claim}", re.I)) and bool(
                re.search(r"\b(path|file|directory|root|join|resolve|\.\./)\b", f"{line} {claim}", re.I)
            )

        if rule == "unsafe-deserialization":
            return bool(re.search(r"\b(pickle|dill|yaml)\.(?:load|loads)\s*\(", line, re.I))

        if rule == "weak-cryptography":
            return bool(re.search(r"\b(?:md5|sha1)(?:\.create)?\s*\(", line, re.I))

        if rule == "resource-cleanup":
            return bool(re.search(r"\b(open|clientsession|response|stream|reader|writer)\b", line, re.I)) and any(
                token in claim for token in ("close", "unclosed", "leak", "context manager", "cleanup")
            )

        if rule == "unowned-background-task":
            return bool(re.search(r"\b(?:create_task|run_in_executor|submit|task\.run|startnew)\s*\(", line, re.I))

        if rule == "exception-detail-exposure":
            return bool(re.search(r"\b(str\s*\([^)]*(?:error|exception|exc)|message|stacktrace)\b", line, re.I))

        return False

    @staticmethod
    def _line(changed_file: ChangedFile, line_number: int) -> str | None:
        for line in changed_file.changed_lines:
            if line.line_number == line_number:
                return line.content
        return None
