import re

from pr_reviewer.review.models import ChangedFile, Finding, Severity


class JavaScriptDeepStaticAnalyzer:
    """High-confidence browser and Node.js data-flow patterns.

    These checks require a concrete source-to-sink or ownership construct. They
    do not infer that an arbitrary callback is asynchronous and never produce a
    finding from unchanged context.
    """

    def analyze(self, changed_file: ChangedFile) -> list[Finding]:
        content = changed_file.full_content or "\n".join(
            line.content for line in changed_file.changed_lines
        )
        if not content:
            return []
        lines = content.splitlines()
        changed = {line.line_number: line for line in changed_file.changed_lines}
        findings: list[Finding] = []
        seen: set[tuple[int, str]] = set()
        path = changed_file.file_path.replace("\\", "/").lower()
        is_test = self._is_test(path)

        def add(number: int, severity: Severity, rule: str, message: str, suggestion: str) -> None:
            line = changed.get(number)
            if line is None or (number, rule) in seen:
                return
            seen.add((number, rule))
            findings.append(Finding(
                file_path=changed_file.file_path,
                line_number=number,
                severity=severity,
                rule_id=rule,
                message=message,
                suggestion=suggestion,
                diff_position=line.diff_position,
            ))

        for number, source_line in enumerate(lines, 1):
            line = source_line.strip()
            function = self._containing_function(lines, number)
            offset = self._line_offset(lines, number)

            fetch = re.search(r"\bfetch\s*\(", source_line)
            if fetch:
                call = self._balanced_call(content, self._line_offset(lines, number) + fetch.start())
                response_name = self._assigned_name(source_line, "fetch")
                if response_name and not re.search(
                    rf"\b{re.escape(response_name)}\s*\.\s*(?:ok|status)\b", function
                ):
                    add(number, Severity.MEDIUM, "fetch-status-not-checked",
                        "The fetch response is consumed without validating its HTTP status.",
                        "Check response.ok or an accepted status range before consuming the body.")
                signal_supplied = bool(re.search(r"\bsignal\b\s*(?::|[,}])", call))
                if self._fetch_requires_deadline(call) and not signal_supplied:
                    add(number, Severity.MEDIUM, "missing-timeout",
                        "The external request has no cancellation or timeout boundary.",
                        "Pass an AbortSignal and enforce an appropriate request deadline.")

            chained_dom = re.search(r"document\.getElementById\s*\([^)]*\)\s*\.\s*(?:value|innerHTML|textContent|classList)", source_line)
            if chained_dom:
                add(number, Severity.MEDIUM, "null-safety",
                    "A possibly missing DOM element is dereferenced without a presence or type check.",
                    "Validate the returned element before accessing its properties.")
            assigned_dom = re.search(r"\b(?:const|let|var)\s+(\w+)\s*=\s*document\.getElementById\s*\(", source_line)
            if assigned_dom:
                name = assigned_dom.group(1)
                if re.search(rf"\b{re.escape(name)}\s*\.", function) and not self._dom_guarded(function, name):
                    dereference_line = self._first_line_with(lines, number + 1, rf"\b{re.escape(name)}\s*\.")
                    if dereference_line:
                        add(dereference_line, Severity.MEDIUM, "null-safety",
                            "A possibly missing DOM element is dereferenced without a presence or type check.",
                            "Validate the returned element before accessing its properties.")

            if re.search(r"\b(?:window\s*\.\s*)?location\s*\.\s*href\s*=\s*\w+", source_line):
                add(number, Severity.MEDIUM, "open-redirect",
                    "An unvalidated runtime value controls browser navigation.",
                    "Resolve the destination and allow only trusted origins or local paths.")

            if re.search(r"\.postMessage\s*\([^,]+,\s*['\"]\*['\"]\s*\)", source_line):
                add(number, Severity.HIGH, "wildcard-postmessage",
                    "Cross-window data is sent with a wildcard target origin.",
                    "Send messages only to an explicitly trusted origin.")

            if re.search(r"\blocalStorage\.setItem\s*\(\s*['\"][^'\"]*(?:token|session|auth)[^'\"]*['\"]", source_line, re.I):
                add(number, Severity.HIGH, "browser-token-storage",
                    "A session or authentication token is persisted in script-readable storage.",
                    "Prefer a Secure, HttpOnly, SameSite cookie or a threat-modelled in-memory flow.")

            if re.search(r"\.query\s*\([^;]*(?:\+|\$\{)", source_line) and re.search(
                r"\b(?:select|insert|update|delete)\b", source_line, re.I
            ):
                add(number, Severity.HIGH, "sql-injection",
                    "Runtime data is concatenated into an SQL statement.",
                    "Use placeholders and bind external values through the database driver.")

            if re.search(r"\bexec\s*\([^;]*(?:\+|\$\{)", source_line):
                add(number, Severity.HIGH, "command-injection",
                    "Runtime data is concatenated into an operating-system command.",
                    "Use a fixed executable with validated argument-array entries and no shell.")

            path_join = re.search(r"\bpath\.join\s*\(([^,]+),\s*([^)]+)\)", source_line)
            if path_join and self._parameter_in_signature(function, path_join.group(2).strip()):
                if not self._has_path_containment(function):
                    add(number, Severity.HIGH, "path-traversal",
                        "A caller-controlled path is joined without canonical containment validation.",
                        "Resolve the canonical path and verify it remains under the allowed root.")

            if re.search(r"request\.headers\s*\[\s*['\"][^'\"]*(?:role|admin)[^'\"]*['\"]\s*\]", source_line, re.I):
                add(number, Severity.HIGH, "authorization",
                    "A caller-controlled request header is treated as authorization evidence.",
                    "Use authenticated server-side identity and an explicit authorization policy.")

            if re.search(r"\b(?:log|logger)\.(?:trace|debug|info|warn|error)\s*\([^;]*\bpassword\b", source_line, re.I):
                add(number, Severity.HIGH, "sensitive-data-logging",
                    "A password value is written to application logs.",
                    "Remove credentials and secrets from structured and interpolated log data.")

            if "Math.random(" in source_line and re.search(r"(?:reset|token|otp|verification|code)", function, re.I):
                add(number, Severity.HIGH, "predictable-random-token",
                    "A predictable pseudo-random generator creates a security code or token.",
                    "Use crypto.randomBytes, crypto.randomUUID, or Web Crypto randomness.")

            if re.search(r"\.addEventListener\s*\([^,]+,\s*async\s*\(", source_line):
                if not re.search(r"\btry\s*\{", function):
                    await_line = self._first_line_with(lines, number, r"\bawait\b") or number
                    add(await_line, Severity.MEDIUM, "async-issue",
                        "An asynchronous event callback has no rejection-handling boundary.",
                        "Catch expected failures inside the callback or delegate to an observed task.")
            lifecycle = self._reusable_listener_owner(content, offset)
            if (
                lifecycle
                and re.search(r"\.addEventListener\s*\(", source_line)
                and not re.search(
                    r"\bsignal\s*:|removeEventListener", f"{source_line}\n{lifecycle}"
                )
                and not re.search(
                    r"\b(?:window|document)\s*\.\s*addEventListener", source_line
                )
            ):
                add(number, Severity.MEDIUM, "listener-cleanup",
                    "Repeated setup can accumulate an element listener without a teardown path.",
                    "Return cleanup, remove the stable handler, or bind it to an AbortSignal.")

            if re.search(r"\.then\s*\(", source_line) and not re.search(r"\.catch\s*\(", function):
                add(number, Severity.MEDIUM, "async-issue",
                    "A promise chain has no rejection handling.",
                    "Await it inside try/catch or append a rejection handler.")

            if is_test and re.search(r"\bassert\.ok\s*\(\s*result\s*\)", source_line):
                add(number, Severity.MEDIUM, "insufficient-test-assertion",
                    "The test checks only truthiness rather than the expected domain value.",
                    "Assert the exact expected value and relevant side effects.")
            if is_test and re.search(r"\bassert\.equal\s*\(\s*result\s*,\s*undefined\s*\)", source_line):
                add(number, Severity.MEDIUM, "insufficient-test-assertion",
                    "The test accepts completion without verifying the security-sensitive navigation result.",
                    "Assert that unsafe destinations are rejected and safe local destinations are accepted.")

        return findings

    @staticmethod
    def _is_test(path: str) -> bool:
        return "/tests/" in f"/{path}" or any(marker in path for marker in (".test.", ".spec."))

    @staticmethod
    def _line_offset(lines: list[str], number: int) -> int:
        return sum(len(line) + 1 for line in lines[:number - 1])

    @staticmethod
    def _assigned_name(line: str, call: str) -> str | None:
        match = re.search(rf"\b(?:const|let|var)\s+(\w+)\s*=\s*await\s+{call}\s*\(", line)
        return match.group(1) if match else None

    @staticmethod
    def _fetch_requires_deadline(call: str) -> bool:
        """Require an explicit deadline for runtime-selected destinations.

        Fixed same-origin relative routes inherit the application's own HTTP
        boundary and are not automatically defects. Variable/absolute targets
        can reach an external dependency and need caller-controlled cancellation.
        """
        opening = call.find("(")
        if opening < 0:
            return False
        first_argument = call[opening + 1:].lstrip()
        if re.match(r"['\"`]/(?!/)", first_argument):
            return False
        return True

    @staticmethod
    def _balanced_call(content: str, call_offset: int) -> str:
        opening = content.find("(", call_offset)
        if opening < 0:
            return ""
        depth = 0
        quote = None
        escaped = False
        for index in range(opening, len(content)):
            char = content[index]
            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
                continue
            if char in "'\"`":
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return content[call_offset:index + 1]
        return content[call_offset:]

    @classmethod
    def _containing_function(cls, lines: list[str], number: int) -> str:
        start = number - 1
        while start >= 0:
            if re.search(r"\bfunction\b|=>\s*\{|\b(?:async\s+)?\w+\s*\([^)]*\)\s*\{", lines[start]):
                break
            start -= 1
        if start < 0:
            return "\n".join(lines)
        depth = 0
        opened = False
        for end in range(start, len(lines)):
            depth += lines[end].count("{") - lines[end].count("}")
            opened = opened or "{" in lines[end]
            if opened and depth <= 0:
                return "\n".join(lines[start:end + 1])
        return "\n".join(lines[start:])

    @classmethod
    def _reusable_listener_owner(cls, content: str, offset: int) -> str | None:
        """Return a proven repeatable lifecycle function containing ``offset``.

        Element listeners installed by a page's one-time bootstrap are owned by
        the document lifetime and do not inherently need manual removal. A
        cleanup finding is justified only when the registration sits in a
        reusable setup-style function that callers can invoke more than once.
        """
        owner: tuple[int, int, str] | None = None
        pattern = re.compile(
            r"(?:\bexport\s+)?(?:\basync\s+)?\bfunction\s+"
            r"(?P<name>[A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{"
        )
        lifecycle_name = re.compile(
            r"^(?:register|setup|mount|bind|attach|watch|observe|subscribe|connect)",
            re.IGNORECASE,
        )
        for match in pattern.finditer(content):
            if not lifecycle_name.search(match.group("name")):
                continue
            opening = content.find("{", match.start(), match.end())
            closing = cls._matching_brace(content, opening)
            if closing is None or not (opening < offset < closing):
                continue
            if owner is None or opening > owner[0]:
                owner = (opening, closing, content[match.start():closing + 1])
        return owner[2] if owner else None

    @staticmethod
    def _matching_brace(content: str, opening: int) -> int | None:
        if opening < 0 or opening >= len(content) or content[opening] != "{":
            return None
        depth = 0
        quote: str | None = None
        escaped = False
        line_comment = False
        block_comment = False
        index = opening
        while index < len(content):
            char = content[index]
            following = content[index + 1] if index + 1 < len(content) else ""
            if line_comment:
                if char == "\n":
                    line_comment = False
                index += 1
                continue
            if block_comment:
                if char == "*" and following == "/":
                    block_comment = False
                    index += 2
                else:
                    index += 1
                continue
            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
                index += 1
                continue
            if char == "/" and following == "/":
                line_comment = True
                index += 2
                continue
            if char == "/" and following == "*":
                block_comment = True
                index += 2
                continue
            if char in "'\"`":
                quote = char
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return index
            index += 1
        return None

    @staticmethod
    def _dom_guarded(function: str, name: str) -> bool:
        escaped = re.escape(name)
        return bool(re.search(
            rf"(?:if\s*\(\s*!\s*{escaped}\b|{escaped}\s+instanceof\s+\w+|{escaped}\s*===?\s*null)",
            function,
        ))

    @staticmethod
    def _first_line_with(lines: list[str], start: int, pattern: str) -> int | None:
        for index in range(max(0, start - 1), min(len(lines), start + 12)):
            if re.search(pattern, lines[index]):
                return index + 1
        return None

    @staticmethod
    def _parameter_in_signature(function: str, name: str) -> bool:
        signature = function.split("{", 1)[0]
        return bool(re.search(rf"\b{re.escape(name)}\b", signature))

    @staticmethod
    def _has_path_containment(function: str) -> bool:
        return "path.resolve(" in function and "startsWith(" in function
