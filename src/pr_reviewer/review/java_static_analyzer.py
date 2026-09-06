import re

from pr_reviewer.review.models import ChangedFile, Finding, Severity


class JavaStaticAnalyzer:
    """Conservative Java/Spring source capability adapter.

    This is deliberately evidence based rather than a general Java linter.  It
    recognizes concrete Java APIs and compact control-flow shapes whose result
    is unambiguous, and it can emit only on a line added by the pull request.
    """

    JAVA_EXTENSIONS = (".java",)

    def analyze(self, changed_file: ChangedFile) -> list[Finding]:
        if not changed_file.file_path.lower().endswith(self.JAVA_EXTENSIONS):
            return []
        content = changed_file.full_content or "\n".join(
            line.content for line in changed_file.changed_lines
        )
        if not content.strip():
            return []

        lines = content.splitlines()
        changed = {line.line_number: line for line in changed_file.changed_lines}
        findings: list[Finding] = []
        seen: set[tuple[int, str]] = set()

        def add(number: int, severity: Severity, rule: str, message: str, suggestion: str) -> None:
            changed_line = changed.get(number)
            if changed_line is None or (number, rule) in seen:
                return
            seen.add((number, rule))
            findings.append(Finding(
                file_path=changed_file.file_path,
                line_number=number,
                severity=severity,
                rule_id=rule,
                message=message,
                suggestion=suggestion,
                diff_position=changed_line.diff_position,
            ))

        is_test = self._is_test_file(changed_file.file_path)
        for number, line in enumerate(lines, start=1):
            stripped = line.strip()

            if self._string_identity_comparison(lines, number):
                add(number, Severity.MEDIUM, "identity-comparison-literal",
                    "Java String values are compared by reference identity.",
                    "Use Objects.equals or String.equals for value comparison.")

            if ".orElse(null)" in line and self._enclosing_return_type(lines, number) not in {"Optional", ""}:
                add(number, Severity.MEDIUM, "null-safety",
                    "A repository lookup returns null through a non-optional method contract.",
                    "Return Optional, throw a domain-specific not-found exception, or declare and handle nullability explicitly.")

            if re.search(r"\b(?:page|pageNumber)\s*\*\s*(?:pageSize|size)\b", line):
                add(number, Severity.MEDIUM, "logic-error",
                    "A one-based page number is used directly as a zero-based offset.",
                    "Define the API indexing convention and use (page - 1) * pageSize for one-based pages.")

            if re.search(r"\b(?:cacheKey|key)\s*=.*\b(?:query|search|filter)\b", line, re.I):
                method = self._enclosing_method(lines, number)
                if re.search(r"\btenant(?:Id)?\b", method, re.I) and not re.search(r"\btenant(?:Id)?\b", line, re.I):
                    add(number, Severity.HIGH, "cache-consistency",
                        "Tenant identity is omitted from a cache key for tenant-scoped data.",
                        "Include the tenant identifier and every result-shaping input in the cache key.")

            if re.search(r"\bcatch\s*\([^)]*\)\s*\{\s*\}?\s*$", stripped):
                if self._block_is_empty(lines, number):
                    add(number, Severity.MEDIUM, "empty-catch-block",
                        "An empty catch block silently discards the failure.",
                        "Handle, log with useful context, translate, or propagate the exception.")

            if "Thread.sleep(" in line and self._has_annotation_before(lines, number, "@Async"):
                add(number, Severity.MEDIUM, "async-blocking-operation",
                    "Thread.sleep blocks a Spring asynchronous worker thread.",
                    "Use a scheduler or a non-blocking delay instead of occupying the async executor.")

            if re.search(r"Runtime\s*\.\s*getRuntime\(\)\s*\.\s*exec\s*\([^;]*\+", line):
                add(number, Severity.HIGH, "command-injection",
                    "Runtime.exec receives a command assembled with runtime input.",
                    "Use a fixed executable and validated argument list without shell-style command construction.")

            if re.search(r"Files\s*\.\s*(?:readAllBytes|readString|newInputStream)\s*\([^)]*\.resolve\s*\(", line):
                if not self._method_has_path_containment(lines, number):
                    add(number, Severity.HIGH, "path-traversal",
                        "A caller-controlled path is read without proving it remains inside the configured root.",
                        "Normalize the resolved path and verify that it starts with the normalized allowed root.")

            if self._dynamic_sql_assignment(line) and self._method_has_sql_sink(lines, number) and self._line_uses_parameter(lines, number):
                add(number, Severity.HIGH, "sql-injection",
                    "A SQL statement is assembled by concatenating runtime data before execution.",
                    "Use bind parameters and pass values separately from the SQL text.")

            if re.search(r"createNativeQuery\s*\([^;]*\+", line):
                add(number, Severity.HIGH, "sql-injection",
                    "A native query interpolates runtime data into SQL.",
                    "Use named or positional query parameters instead of concatenating values.")

            if "createNativeQuery(" in line:
                call_text = " ".join(lines[number - 1:min(len(lines), number + 3)])
                if "+" in call_text:
                    add(number, Severity.HIGH, "sql-injection",
                        "A native query interpolates runtime data into SQL.",
                        "Use named or positional query parameters instead of concatenating values.")

            if re.search(r"Files\s*\.\s*copy\s*\([^;]*\.resolve\s*\(\s*\w+\.getName\(\)\s*\)", line):
                add(number, Severity.HIGH, "path-traversal",
                    "A ZIP entry name is resolved beneath the destination without containment validation.",
                    "Normalize each output path and reject entries that escape the extraction directory.")

            if re.search(r"\b\w+\.readObject\s*\(\s*\)", line):
                add(number, Severity.HIGH, "unsafe-deserialization",
                    "Java object deserialization reconstructs attacker-controlled object graphs.",
                    "Use a schema-based data format, or apply a strict ObjectInputFilter before deserialization.")

            if re.search(r"MessageDigest\.getInstance\s*\(\s*[\"'](?:MD5|SHA-?1)[\"']", line, re.I):
                add(number, Severity.HIGH, "weak-cryptography",
                    "A cryptographically broken digest is used in security-sensitive token generation.",
                    "Generate tokens with SecureRandom; use a modern password KDF for stored credentials.")

            if re.search(r"new\s+Random\s*\(", line) and self._security_token_context(lines, number):
                add(number, Severity.HIGH, "weak-cryptography",
                    "java.util.Random produces a predictable security token or verification code.",
                    "Use SecureRandom or a dedicated cryptographic token generator.")

            if "Files.lines(" in line and "try (" not in line and not self._resource_closed_later(lines, number):
                add(number, Severity.MEDIUM, "resource-cleanup",
                    "The stream returned by Files.lines owns an open file and is not closed.",
                    "Consume the stream inside try-with-resources.")

            if (
                "DocumentBuilderFactory.newInstance()" in line
                and ".parse(" in self._method_text(lines, number)
                and not self._xml_factory_hardened(lines, number)
            ):
                add(number, Severity.HIGH, "security",
                    "The XML parser is used without disabling DTD and external entity access.",
                    "Disable DOCTYPE declarations and external DTD/schema access before parsing untrusted XML.")

            if re.search(r"ResponseEntity[^;]*error\.getMessage\s*\(", line):
                add(number, Severity.MEDIUM, "exception-detail-exposure",
                    "An internal exception message is returned to the HTTP client.",
                    "Return a stable public error response and log internal diagnostics server-side.")

            if (
                re.search(r"\.uri\s*\(\s*\w+\s*\)", line)
                and self._request_parameter_reaches_method(lines, number)
                and "RestClient.create()" in content
            ):
                add(number, Severity.HIGH, "security",
                    "A request-controlled URL reaches an outbound HTTP request.",
                    "Resolve destinations from an allow-list and block private, loopback, and metadata-network addresses.")

            if re.search(r"\.sendRedirect\s*\(\s*\w+\s*\)", line) and self._request_parameter_reaches_method(lines, number):
                add(number, Severity.MEDIUM, "security",
                    "A request-controlled destination is used directly for an HTTP redirect.",
                    "Allow-list local destinations or map stable identifiers to server-owned URLs.")

            if re.search(
                r"BeanUtils\.copyProperties\s*\(\s*\w*request\w*\s*,\s*\w*(?:account|entity|user|record)\w*",
                line,
                re.I,
            ):
                add(number, Severity.HIGH, "data-validation",
                    "Request fields are mass-assigned onto a domain or persistence object.",
                    "Map explicitly allow-listed editable fields and ignore privileged properties such as role and password.")

            if re.search(r"CompletableFuture\s*\.\s*(?:runAsync|supplyAsync)\s*\(", line):
                if self._is_discarded_expression(stripped):
                    add(number, Severity.MEDIUM, "unowned-background-task",
                        "A CompletableFuture is discarded without lifecycle or exception ownership.",
                        "Return, retain, join, or attach explicit completion and failure handling to the future.")

            if re.search(r"\b(?:log|logger)\w*\.(?:trace|debug|info|warn|error)\s*\([^;]*password", line, re.I):
                add(number, Severity.HIGH, "security",
                    "A password value is written to application logs.",
                    "Never log credentials; record only non-sensitive identifiers and operation outcomes.")

            if is_test:
                self._analyze_test_line(lines, number, add)

        self._ignored_update_success(lines, changed, add)
        self._weak_role_header(lines, changed, add)
        return findings

    @staticmethod
    def _is_test_file(path: str) -> bool:
        lowered = path.replace("\\", "/").lower()
        return "/src/test/" in f"/{lowered}" or lowered.endswith(("test.java", "tests.java"))

    @staticmethod
    def _enclosing_method(lines: list[str], number: int) -> str:
        signature = ""
        for index in range(number - 1, max(-1, number - 20), -1):
            signature = lines[index].strip() + " " + signature
            if "(" in lines[index] and re.search(r"\)\s*(?:throws\s+[^{]+)?\s*\{", signature):
                return signature
            if lines[index].strip().endswith(";"):
                signature = ""
        return signature

    @classmethod
    def _enclosing_return_type(cls, lines: list[str], number: int) -> str:
        signature = cls._enclosing_method(lines, number)
        match = re.search(r"(?:public|protected|private)\s+(?:static\s+)?([\w<>?, ]+)\s+\w+\s*\(", signature)
        return match.group(1).strip().split("<", 1)[0] if match else ""

    @classmethod
    def _string_identity_comparison(cls, lines: list[str], number: int) -> bool:
        line = lines[number - 1]
        if not re.search(r"(?<![=!])==(?!=)|(?<!!)!=(?!=)", line):
            return False
        signature = cls._enclosing_method(lines, number)
        string_names = re.findall(r"\bString\s+(\w+)", signature)
        return any(re.search(rf"\b{re.escape(name)}\b\s*(?:==|!=)|(?:==|!=)\s*\b{re.escape(name)}\b", line) for name in string_names)

    @staticmethod
    def _block_is_empty(lines: list[str], number: int) -> bool:
        tail = " ".join(line.strip() for line in lines[number - 1:number + 3])
        return bool(re.search(r"catch\s*\([^)]*\)\s*\{\s*\}", tail))

    @staticmethod
    def _has_annotation_before(lines: list[str], number: int, annotation: str) -> bool:
        return any(annotation in line for line in lines[max(0, number - 15):number])

    @classmethod
    def _method_bounds(cls, lines: list[str], number: int) -> tuple[int, int]:
        start = number - 1
        while start > 0 and "(" not in lines[start]:
            start -= 1
        depth = 0
        opened = False
        for end in range(start, len(lines)):
            depth += lines[end].count("{") - lines[end].count("}")
            opened = opened or "{" in lines[end]
            if opened and depth <= 0:
                return start, end + 1
        return start, min(len(lines), number + 20)

    @classmethod
    def _method_text(cls, lines: list[str], number: int) -> str:
        start, end = cls._method_bounds(lines, number)
        return "\n".join(lines[start:end])

    @classmethod
    def _method_has_path_containment(cls, lines: list[str], number: int) -> bool:
        text = cls._method_text(lines, number)
        return ".normalize()" in text and ".startsWith(" in text

    @staticmethod
    def _dynamic_sql_assignment(line: str) -> bool:
        return bool(re.search(r"\b(?:String|var)\s+\w*(?:sql|query)\w*\s*=.*(?:SELECT|INSERT|UPDATE|DELETE).*\+", line, re.I))

    @classmethod
    def _method_has_sql_sink(cls, lines: list[str], number: int) -> bool:
        return bool(re.search(r"\.(?:queryForList|query|update|execute)\s*\(", cls._method_text(lines, number)))

    @classmethod
    def _line_uses_parameter(cls, lines: list[str], number: int) -> bool:
        signature = cls._enclosing_method(lines, number)
        parameters_match = re.search(r"\(([^)]*)\)", signature)
        if not parameters_match:
            return False
        names = re.findall(r"(?:[\w<>?,.\[\]]+\s+)+(\w+)\s*(?:,|$)", parameters_match.group(1))
        line = lines[number - 1]
        return any(re.search(rf"\+\s*{re.escape(name)}\b|\b{re.escape(name)}\s*\+", line) for name in names)

    @classmethod
    def _security_token_context(cls, lines: list[str], number: int) -> bool:
        return bool(re.search(r"token|verification|otp|reset|code", cls._enclosing_method(lines, number), re.I))

    @classmethod
    def _resource_closed_later(cls, lines: list[str], number: int) -> bool:
        text = cls._method_text(lines, number)
        match = re.search(r"(?:Stream<[^>]+>|var)\s+(\w+)\s*=\s*Files\.lines", text)
        return bool(match and re.search(rf"\b{re.escape(match.group(1))}\.close\s*\(", text))

    @classmethod
    def _xml_factory_hardened(cls, lines: list[str], number: int) -> bool:
        text = cls._method_text(lines, number)
        return "disallow-doctype-decl" in text and "ACCESS_EXTERNAL_DTD" in text

    @classmethod
    def _request_parameter_reaches_method(cls, lines: list[str], number: int) -> bool:
        return "@RequestParam" in cls._enclosing_method(lines, number)

    @staticmethod
    def _is_discarded_expression(stripped: str) -> bool:
        return bool(re.match(r"^CompletableFuture\s*\.\s*(?:runAsync|supplyAsync)\s*\(", stripped)) and stripped.endswith(";")

    @classmethod
    def _ignored_update_success(cls, lines, changed, add) -> None:
        for number, line in enumerate(lines, start=1):
            if not re.search(r"\.ifPresent\s*\([^;]*\.save\s*\(", line):
                continue
            text = cls._method_text(lines, number)
            if re.search(r"return\s+true\s*;", text):
                add(number, Severity.MEDIUM, "incorrect-result-handling",
                    "The update result is ignored and the method reports success even when no record exists.",
                    "Return success only when the record was found and persistence completed, or raise a not-found error.")

    @classmethod
    def _weak_role_header(cls, lines, changed, add) -> None:
        for number, line in enumerate(lines, start=1):
            if re.search(r"\brole\b.*(?:isBlank|isEmpty)|(?:isBlank|isEmpty).*\brole\b", line, re.I):
                method = cls._method_text(lines, number)
                prefix = "\n".join(lines[max(0, number - 10):number])
                if not re.search(r"@RequestHeader\s*\([^)]*[\"']X-(?:Role|Admin)[\"']", prefix + method, re.I):
                    continue
                if re.search(r"hasRole|hasAuthority|@PreAuthorize|ROLE_ADMIN|equals\s*\([^)]*admin", prefix + method, re.I):
                    continue
                add(number, Severity.HIGH, "authorization",
                    "Any non-empty role header is accepted as authorization for an administrative operation.",
                    "Use authenticated server-side authorities and require the specific administrative permission.")
                return

    @classmethod
    def _analyze_test_line(cls, lines, number, add) -> None:
        line = lines[number - 1]
        text = cls._method_text(lines, number)
        if re.search(r"\.andExpect\s*\(\s*status\(\)", line) and text.count(".andExpect(") == 1:
            add(number, Severity.MEDIUM, "insufficient-test-assertion",
                "The endpoint test checks only HTTP status and does not verify the response contract.",
                "Assert the relevant response body, headers, and observable side effects.")
        if re.search(r"assertTrue\s*\([^;]*\.update\s*\(", line):
            add(number, Severity.MEDIUM, "insufficient-test-assertion",
                "The missing-record update test accepts a successful result.",
                "Assert the not-found contract and verify that persistence is not invoked.")
        if re.search(r"assertEquals\s*\([^;]*\.page\s*\(\s*\)", line) and "items()" not in text:
            add(number, Severity.MEDIUM, "insufficient-test-assertion",
                "The pagination test checks metadata without verifying which records were returned.",
                "Assert item boundaries and the first-page contents so offset errors are observable.")
