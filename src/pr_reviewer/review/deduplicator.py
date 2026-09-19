import re

from pr_reviewer.review.models import Finding, Severity, FindingSource


class FindingDeduplicator:
    """Remove exact and conservative semantic duplicates without dropping distinct subjects."""

    SEVERITY_ORDER = {
        Severity.SUGGESTION: 0,
        Severity.LOW: 1,
        Severity.MEDIUM: 2,
        Severity.HIGH: 3,
        Severity.CRITICAL: 4,
    }

    RULE_FAMILIES = {
        "hardcoded-secret": {
            "hardcoded-secret", "security-hardcoded-secret", "hardcoded-credential",
            "hardcoded-credentials", "embedded-secret", "exposed-secret",
            "credential-hardcoded",
        },
        "unused-value": {
            "unused-variable", "unused-code", "unused-constant",
            "unnecessary-constant", "unused-declaration",
        },
        "unused-parameter": {
            "unused-parameter", "unused-function-parameter", "unused-function-argument",
            "unused-method-parameter", "unused-argument",
        },
        "console": {"no-console", "console-log", "console-statement"},
        "effect-cleanup": {
            "missing-effect-cleanup", "react-use-effect-cleanup",
            "react-effect-cleanup", "hook-cleanup", "effect-cleanup",
        },
        "effect-dependency": {
            "react-use-effect-dependency", "react-hooks-missing-dependency",
            "missing-hook-dependency", "hook-dependency", "effect-dependency",
        },
        "loose-equality": {
            "loose-equality", "javascript-loose-equality", "typescript-loose-equality",
            "non-strict-equality", "non-strict-comparison", "eqeqeq",
        },
        "json-parse": {
            "json-parse", "json-parse-error", "json-parsing-error",
            "json-parse-without-error-handling", "unsafe-json-parsing",
        },
        "timer-reference": {
            "setinterval", "set-interval", "setinterval-without-timer-reference",
            "setinterval-without-retaining-timer-reference",
            "set-interval-without-retaining-timer-reference",
            "setinterval-without-referencing-timer",
            "set-interval-without-referencing-timer",
        },
        "global-listener": {
            "global-event-listener", "global-listener", "window-event-listener",
            "global-event-listener-without-removal",
        },
        "html-injection": {
            "unsafe-inner-html", "xss-vulnerability", "dom-xss",
            "unsafe-html", "unsanitized-html",
        },
        "jwt-verification": {
            "jwt-signature-verification-disabled", "jwt-verification", "insecure-jwt", "security", "data-validation"
        },
        "empty-catch": {
            "empty-catch-block", "no-empty-catch", "empty-catch",
            "swallowed-exception", "bare-except", "bare-exception-handler", "error-handling", "exception-handling"
        },
        "authorization": {
            "authorization", "missing-endpoint-authorization", "role-check",
            "access-control", "permission-check", "api-misuse", "security",
        },
    }

    AUTHORITATIVE_SOURCES = {FindingSource.STATIC, FindingSource.FRAMEWORK, FindingSource.COMPILER}

    SEMANTIC_LINE_DISTANCE = 2
    SUBJECT_LINE_DISTANCE = 10
    SUBJECT_SENSITIVE_FAMILIES = {"hardcoded-secret", "unused-value", "unused-parameter"}

    def deduplicate(
        self,
        findings: list[Finding],
        changed_files: list | None = None,
    ) -> list[Finding]:
        changed_file_map = {
            self._normalize_path(changed_file.file_path): changed_file
            for changed_file in (changed_files or [])
        }
        result: list[Finding] = []
        for finding in findings:
            duplicate_index = self._find_duplicate_index(result, finding, changed_file_map)
            if duplicate_index is None:
                result.append(finding)
                continue
            existing = result[duplicate_index]
            if self._is_stronger(finding, existing):
                result[duplicate_index] = finding
        return result

    def _find_duplicate_index(self, findings: list[Finding], candidate: Finding, changed_file_map: dict | None = None) -> int | None:
        candidate_path = self._normalize_path(candidate.file_path)
        candidate_rule = candidate.rule_id.strip().lower()
        candidate_family = self._rule_family(candidate_rule)
        candidate_subject = self._quoted_subject(candidate.message)

        for index, existing in enumerate(findings):
            if self._normalize_path(existing.file_path) != candidate_path:
                continue

            existing_rule = existing.rule_id.strip().lower()
            existing_family = self._rule_family(existing_rule)
            existing_subject = self._quoted_subject(existing.message)
            same_line = existing.line_number == candidate.line_number

            # Exact same canonical rule + line is normally a duplicate, but not when a
            # single statement/signature contains multiple distinct named subjects
            # (for example two unused parameters on one function declaration).
            if same_line and existing_rule == candidate_rule:
                if candidate_family in self.SUBJECT_SENSITIVE_FAMILIES:
                    if existing_subject and candidate_subject and existing_subject != candidate_subject:
                        continue
                    if (existing_subject is None or candidate_subject is None) and self._ambiguous_subjects(
                        findings, candidate_path, candidate_family, candidate.line_number
                    ):
                        continue
                return index

            line_distance = abs(existing.line_number - candidate.line_number)

            # Reject AI findings overlapping deterministic findings on the same construct
            candidate_auth = candidate.source in self.AUTHORITATIVE_SOURCES
            existing_auth = existing.source in self.AUTHORITATIVE_SOURCES
            if candidate_auth != existing_auth:
                if line_distance <= 4:
                    return index

            if candidate_family is None or existing_family != candidate_family:
                continue

            # Subject-sensitive rules can tolerate larger LLM anchor drift only when
            # both findings explicitly identify the same variable/parameter/secret.
            if candidate_family in self.SUBJECT_SENSITIVE_FAMILIES:
                if existing_subject and candidate_subject:
                    if existing_subject != candidate_subject:
                        continue
                    if line_distance <= self.SUBJECT_LINE_DISTANCE:
                        return index
                    continue

                # Generic hardcoded-secret reports may be anchored one line away by
                # different analyzers. Keep the old conservative behavior, but never
                # use generic proximity to merge unused values/parameters.
                if candidate_family == "hardcoded-secret" and line_distance <= self.SEMANTIC_LINE_DISTANCE:
                    if not self._ambiguous_subjects(findings, candidate_path, candidate_family, candidate.line_number):
                        return index
                continue

            if candidate_family == "effect-cleanup":
                candidate_effect = self._effect_block_key(
                    changed_file_map or {}, candidate_path, candidate.line_number
                )
                existing_effect = self._effect_block_key(
                    changed_file_map or {}, candidate_path, existing.line_number
                )
                if candidate_effect is not None and candidate_effect == existing_effect:
                    return index

            if line_distance > self.SEMANTIC_LINE_DISTANCE:
                continue

            if candidate_family in {"loose-equality", "effect-cleanup", "effect-dependency", "json-parse", "timer-reference", "global-listener", "html-injection", "empty-catch", "jwt-verification"}:
                return index

            if same_line:
                return index

        return None


    @classmethod
    def _effect_block_key(cls, changed_file_map: dict, normalized_path: str, line_number: int):
        changed_file = changed_file_map.get(normalized_path)
        if changed_file is None or not getattr(changed_file, "full_content", None):
            return None
        content = changed_file.full_content
        for match in re.finditer(r"\buse(?:Layout)?Effect\s*\(", content):
            open_paren = content.find("(", match.start())
            if open_paren < 0:
                continue
            close_paren = cls._find_matching_paren(content, open_paren)
            if close_paren is None:
                continue
            start_line = content.count("\n", 0, match.start()) + 1
            end_line = content.count("\n", 0, close_paren) + 1
            if start_line <= line_number <= end_line:
                return (start_line, end_line)
        return None

    @staticmethod
    def _find_matching_paren(content: str, start: int) -> int | None:
        depth = 0
        quote = None
        escaped = False
        index = start
        while index < len(content):
            char = content[index]
            if quote is not None:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
                index += 1
                continue
            if char in "'\"`":
                quote = char
                index += 1
                continue
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return index
            index += 1
        return None
    @classmethod
    def _ambiguous_subjects(
        cls,
        findings: list[Finding],
        normalized_path: str,
        family: str | None,
        line_number: int,
    ) -> bool:
        if family is None:
            return False
        subjects = {
            cls._quoted_subject(f.message)
            for f in findings
            if cls._normalize_path(f.file_path) == normalized_path
            and cls._rule_family(f.rule_id.strip().lower()) == family
            and abs(f.line_number - line_number) <= cls.SEMANTIC_LINE_DISTANCE
            and cls._quoted_subject(f.message) is not None
        }
        return len(subjects) > 1

    @classmethod
    def _rule_family(cls, rule_id: str) -> str | None:
        normalized = rule_id.strip().lower()
        for family_name, family_rules in cls.RULE_FAMILIES.items():
            if normalized in family_rules:
                return family_name
        return None

    @staticmethod
    def _quoted_subject(message: str) -> str | None:
        match = re.search(r"[`'\"]([A-Za-z_$][A-Za-z0-9_$]*)[`'\"]", message or "")
        return match.group(1).lower() if match else None

    @classmethod
    def _is_stronger(cls, candidate: Finding, existing: Finding) -> bool:
        candidate_auth = candidate.source in cls.AUTHORITATIVE_SOURCES
        existing_auth = existing.source in cls.AUTHORITATIVE_SOURCES
        if candidate_auth and not existing_auth:
            return True
        if existing_auth and not candidate_auth:
            return False
        return cls.SEVERITY_ORDER[candidate.severity] > cls.SEVERITY_ORDER[existing.severity]

    @staticmethod
    def _normalize_path(file_path: str) -> str:
        return file_path.strip().replace("\\", "/").lower()
