import re

from pr_reviewer.review.react_static_analyzer import ReactStaticAnalyzer
from pr_reviewer.review.angular_template_usage import AngularTemplateUsageResolver
from pr_reviewer.review.angular_static_analyzer import AngularStaticAnalyzer
from pr_reviewer.review.python_static_analyzer import PythonStaticAnalyzer
from pr_reviewer.review.java_static_analyzer import JavaStaticAnalyzer
from pr_reviewer.review.dotnet_static_analyzer import DotNetStaticAnalyzer
from pr_reviewer.review.javascript_deep_static_analyzer import JavaScriptDeepStaticAnalyzer
from pr_reviewer.review.typescript_static_analyzer import TypeScriptStaticAnalyzer
from pr_reviewer.review.file_classifier import FileClassifier, FileCategory
from pr_reviewer.review.models import (
    ChangedFile,
    ChangedLine,
    Finding,
    Severity,
)


class StaticAnalyzer:
    """
    Deterministic analyzer for simple high-confidence issues.

    Generic checks:
    - hardcoded secrets / credentials

    JavaScript / TypeScript checks:
    - console.log
    - debugger statements
    - obvious unused variable declarations

    Important:
    - Only changed lines can produce findings.
    - Generic secret detection works across programming
      languages.
    - Unused-variable detection requires full file content.
    - The implementation is intentionally conservative.
    """

    JAVASCRIPT_EXTENSIONS = {
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".mjs",
        ".cjs",
    }

    # --------------------------------------------------
    # Generic secret detection
    # --------------------------------------------------

    SECRET_NAME_PATTERN = re.compile(
        r"""
        \b
        (
            password
            |
            passwd
            |
            pwd
            |
            secret
            |
            secret_key
            |
            secretkey
            |
            api_key
            |
            apikey
            |
            access_key
            |
            accesskey
            |
            auth_token
            |
            authtoken
            |
            token
            |
            client_secret
            |
            clientsecret
            |
            private_key
            |
            privatekey
        )
        \b
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    SECRET_ASSIGNMENT_PATTERN = re.compile(
        r"""
        (?P<name>
            [A-Za-z_$][A-Za-z0-9_$]*
        )
        \s*
        (?:
            :=
            |
            =
            |
            :
        )
        \s*
        (?P<quote>["'])
        (?P<value>[^"']+)
        (?P=quote)
        """,
        re.VERBOSE,
    )

    SAFE_SECRET_VALUES = {
        "",
        "password",
        "secret",
        "changeme",
        "change-me",
        "your-password",
        "your-secret",
        "your-api-key",
        "your-token",
        "example",
        "sample",
        "dummy",
        "test",
        "placeholder",
    }

    # --------------------------------------------------
    # JavaScript / TypeScript checks
    # --------------------------------------------------

    CONSOLE_LOG_PATTERN = re.compile(
        r"\bconsole\s*\.\s*log\s*\("
    )

    DEBUGGER_PATTERN = re.compile(
        r"^\s*debugger\s*;?\s*$"
    )

    LOOSE_EQUALITY_PATTERN = re.compile(r"(?<![=!])==(?!=)|(?<![!])!=(?!=)")
    EXPLICIT_ANY_PATTERN = re.compile(r"(?:\:\s*any\b|<\s*any\s*>)")
    DIRECT_DOM_PATTERN = re.compile(r"\bdocument\s*\.\s*(?:getElementById|querySelector|querySelectorAll)\s*\(")
    INNER_HTML_PATTERN = re.compile(r"\.\s*innerHTML\s*=")
    JSON_PARSE_PATTERN = re.compile(r"\bJSON\s*\.\s*parse\s*\(")
    DIRECT_SUBSCRIBE_PATTERN = re.compile(r"\.\s*subscribe\s*\(")
    SET_INTERVAL_PATTERN = re.compile(r"\bsetInterval\s*\(")
    GLOBAL_EVENT_LISTENER_PATTERN = re.compile(r"\b(?:window|document)\s*\.\s*addEventListener\s*\(")

    CLASS_FIELD_DECLARATION_PATTERN = re.compile(
        r"""
        ^\s*(?:(?:public|private|protected|readonly|static)\s+)+
        ([A-Za-z_$][A-Za-z0-9_$]*)
        (?:\s*[?!])?\s*(?::[^=;]+)?\s*=
        """, re.VERBOSE,
    )

    VARIABLE_DECLARATION_PATTERN = re.compile(
        r"""
        \b
        (?:const|let|var)
        \s+
        ([A-Za-z_$][A-Za-z0-9_$]*)
        \s*
        (?:=|;)
        """,
        re.VERBOSE,
    )

    def analyze(
        self,
        changed_file: ChangedFile,
    ) -> list[Finding]:
        """
        Analyze one changed file.

        Generic deterministic checks run for every changed
        text/source file.

        JavaScript/TypeScript-specific checks run only for
        supported JS/TS file extensions.
        """

        findings: list[Finding] = []

        classification = FileClassifier().classify(changed_file.file_path)
        if not classification.reviewable:
            return []

        for changed_line in changed_file.changed_lines:

            # --------------------------------------------------
            # Generic checks
            # --------------------------------------------------

            findings.extend(
                self._analyze_generic_line(
                    changed_line=changed_line,
                )
            )

            # --------------------------------------------------
            # JavaScript / TypeScript checks
            # --------------------------------------------------

            if self._supports_javascript_file(
                changed_file.file_path
            ):
                findings.extend(
                    self._analyze_javascript_line(
                        changed_file=changed_file,
                        changed_line=changed_line,
                    )
                )

        if self._supports_javascript_file(changed_file.file_path):
            findings.extend(self._analyze_javascript_file_structure(changed_file))
            findings.extend(ReactStaticAnalyzer().analyze(changed_file))
            findings.extend(AngularStaticAnalyzer().analyze(changed_file))
            findings.extend(JavaScriptDeepStaticAnalyzer().analyze(changed_file))

        if changed_file.file_path.lower().endswith((".ts", ".tsx")):
            findings.extend(TypeScriptStaticAnalyzer().analyze(changed_file))

        if changed_file.file_path.lower().endswith((".py", ".pyw")):
            findings.extend(PythonStaticAnalyzer().analyze(changed_file))

        if changed_file.file_path.lower().endswith(".java"):
            findings.extend(JavaStaticAnalyzer().analyze(changed_file))

        if changed_file.file_path.lower().endswith(".cs") or changed_file.file_path.lower().endswith("appsettings.json"):
            findings.extend(DotNetStaticAnalyzer().analyze(changed_file))

        return findings

    def analyze_files(
        self,
        changed_files: list[ChangedFile],
    ) -> list[Finding]:
        """
        Analyze multiple changed files.
        """

        findings: list[Finding] = []

        for changed_file in changed_files:
            findings.extend(
                self.analyze(
                    changed_file
                )
            )

        findings.extend(PythonStaticAnalyzer().analyze_project(changed_files))

        return AngularTemplateUsageResolver().suppress_template_used_unused_findings(
            changed_files, findings
        )

    def _analyze_generic_line(
        self,
        changed_line: ChangedLine,
    ) -> list[Finding]:
        """
        Run language-agnostic deterministic checks.
        """

        findings: list[Finding] = []

        secret_finding = (
            self._find_hardcoded_secret(
                changed_line
            )
        )

        if secret_finding is not None:
            findings.append(
                secret_finding
            )

        return findings

    def _analyze_javascript_line(
        self,
        changed_file: ChangedFile,
        changed_line: ChangedLine,
    ) -> list[Finding]:
        """
        Analyze one JavaScript/TypeScript changed line.
        """

        findings: list[Finding] = []

        content = changed_line.content

        multiline_secret = self._find_multiline_javascript_secret(
            changed_file=changed_file,
            changed_line=changed_line,
        )
        if multiline_secret is not None:
            findings.append(multiline_secret)

        # --------------------------------------------------
        # 1. console.log
        # --------------------------------------------------

        if self.CONSOLE_LOG_PATTERN.search(
            content
        ):
            findings.append(
                Finding(
                    file_path=changed_line.file_path,
                    line_number=(
                        changed_line.line_number
                    ),
                    severity=Severity.LOW,
                    rule_id="no-console",
                    message=(
                        "A console.log statement "
                        "was added."
                    ),
                    suggestion=(
                        "Remove the console.log "
                        "statement if it is not "
                        "required in production."
                    ),
                    diff_position=(
                        changed_line.diff_position
                    ),
                )
            )

        # --------------------------------------------------
        # 2. debugger
        # --------------------------------------------------

        if self.DEBUGGER_PATTERN.search(
            content
        ):
            findings.append(
                Finding(
                    file_path=changed_line.file_path,
                    line_number=(
                        changed_line.line_number
                    ),
                    severity=Severity.MEDIUM,
                    rule_id="debugger",
                    message=(
                        "A debugger statement "
                        "was added."
                    ),
                    suggestion=(
                        "Remove the debugger "
                        "statement before merging."
                    ),
                    diff_position=(
                        changed_line.diff_position
                    ),
                )
            )

        # --------------------------------------------------
        # 3. obvious unused variable
        # --------------------------------------------------

        unused_finding = (
            self._find_unused_variable(
                changed_file=changed_file,
                changed_line=changed_line,
            )
        )

        if unused_finding is not None:
            findings.append(unused_finding)

        # High-confidence JS/TS correctness and maintainability checks.
        if self.LOOSE_EQUALITY_PATTERN.search(content):
            findings.append(Finding(
                file_path=changed_line.file_path, line_number=changed_line.line_number,
                severity=Severity.MEDIUM, rule_id="loose-equality",
                message="Loose equality comparison was added.",
                suggestion="Use strict equality (=== or !==) unless coercion is intentionally required.",
                diff_position=changed_line.diff_position,
            ))

        if self.EXPLICIT_ANY_PATTERN.search(content):
            findings.append(Finding(
                file_path=changed_line.file_path, line_number=changed_line.line_number,
                severity=Severity.LOW, rule_id="explicit-any",
                message="An explicit 'any' type was added, bypassing TypeScript type safety.",
                suggestion="Use a concrete type or 'unknown' and narrow it before use.",
                diff_position=changed_line.diff_position,
            ))

        if self.INNER_HTML_PATTERN.search(content):
            findings.append(Finding(
                file_path=changed_line.file_path, line_number=changed_line.line_number,
                severity=Severity.HIGH, rule_id="unsafe-inner-html",
                message="A value is assigned through innerHTML, which can create an injection sink for untrusted content.",
                suggestion="Prefer textContent or framework rendering; sanitize explicitly when HTML is required.",
                diff_position=changed_line.diff_position,
            ))

        # Deterministic lifecycle ownership.  These two constructs must remain
        # separate canonical issues even when an LLM describes both as a
        # generic "memory leak" or "cleanup" problem.
        if self.SET_INTERVAL_PATTERN.search(content) and not self._setinterval_result_is_retained_on_line(content):
            findings.append(Finding(
                file_path=changed_line.file_path, line_number=changed_line.line_number,
                severity=Severity.MEDIUM, rule_id="setinterval-without-timer-reference",
                message="setInterval is started without retaining the returned timer reference.",
                suggestion="Store the timer handle and clear it with clearInterval when it is no longer needed.",
                diff_position=changed_line.diff_position,
            ))

        if self.GLOBAL_EVENT_LISTENER_PATTERN.search(content) and self._inline_listener_is_not_removable(content):
            findings.append(Finding(
                file_path=changed_line.file_path, line_number=changed_line.line_number,
                severity=Severity.MEDIUM, rule_id="global-event-listener-without-removal",
                message="A global event listener is registered with an inline callback and has no visible removal path.",
                suggestion="Keep a stable handler reference and remove the listener when it is no longer needed.",
                diff_position=changed_line.diff_position,
            ))

        return findings



    @staticmethod
    def _setinterval_result_is_retained_on_line(content: str) -> bool:
        """Return True when the setInterval handle is visibly kept or returned."""
        match = re.search(r"(?:\b(?:window|globalThis)\s*\.\s*)?setInterval\s*\(", content)
        if match is None:
            return False
        before = content[:match.start()]
        return bool(
            re.search(
                r"(?:\b(?:const|let|var)\s+[A-Za-z_$][A-Za-z0-9_$]*\s*=|"
                r"\b(?:this\s*\.\s*)?[A-Za-z_$][A-Za-z0-9_$]*\s*=|"
                r"\breturn)\s*$",
                before,
            )
        )

    @staticmethod
    def _inline_listener_is_not_removable(content: str) -> bool:
        """Conservative high-confidence global-listener lifecycle check.

        Anonymous/inline callbacks cannot later be removed with the same function
        identity unless an AbortSignal is used. Named handlers are left to the
        semantic reviewer because removal may exist elsewhere in the file.
        """
        if re.search(r"\bsignal\s*:", content):
            return False
        return bool(re.search(
            r"addEventListener\s*\(\s*['\"][^'\"]+['\"]\s*,\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][A-Za-z0-9_$]*)\s*=>|"
            r"addEventListener\s*\(\s*['\"][^'\"]+['\"]\s*,\s*(?:async\s+)?function\b",
            content,
        ))

    def _analyze_javascript_file_structure(self, changed_file: ChangedFile) -> list[Finding]:
        """
        Run conservative file-level JS/TS checks that need function/block context.

        Findings are emitted only when the reported line is part of the PR diff.
        This deliberately covers high-confidence constructs and avoids compiler-option
        dependent TypeScript diagnostics.
        """
        content = self._mask_angular_inline_resources(
            changed_file.full_content or ""
        )
        if not content:
            return []

        lines = content.splitlines()
        changed_by_line = {line.line_number: line for line in changed_file.changed_lines}
        findings: list[Finding] = []
        seen: set[tuple[int, str, str]] = set()

        def add(line_number: int, severity: Severity, rule_id: str, message: str, suggestion: str) -> None:
            changed = changed_by_line.get(line_number)
            if changed is None:
                return
            key = (line_number, rule_id, message)
            if key in seen:
                return
            seen.add(key)
            findings.append(Finding(
                file_path=changed_file.file_path,
                line_number=line_number,
                severity=severity,
                rule_id=rule_id,
                message=message,
                suggestion=suggestion,
                diff_position=changed.diff_position,
            ))

        # Empty catch blocks are syntactically provable and should never depend on LLM wording.
        # Treat comment-only catch bodies as empty too: they still swallow the error.
        catch_block = re.compile(
            r"catch\s*(?:\([^)]*\))?\s*\{(?P<body>.*?)\}",
            re.DOTALL,
        )
        for match in catch_block.finditer(content):
            body = match.group("body")
            body_without_comments = re.sub(r"/\*.*?\*/|//[^\n]*", "", body, flags=re.DOTALL)
            if body_without_comments.strip():
                continue
            line_number = content.count("\n", 0, match.start()) + 1
            add(line_number, Severity.MEDIUM, "empty-catch-block",
                "An empty catch block silently ignores an error.",
                "Handle the error, propagate it, or document explicitly why it is safe to ignore.")

        # JSON.parse outside a surrounding try block can throw on invalid input.
        # This is a local structural check, not a claim about remote exploitability.
        for idx, line in enumerate(lines, start=1):
            if not self.JSON_PARSE_PATTERN.search(line):
                continue
            line_offset = sum(len(previous) + 1 for previous in lines[:idx - 1])
            parse_match = self.JSON_PARSE_PATTERN.search(line)
            parse_offset = line_offset + (parse_match.start() if parse_match else 0)
            if self._offset_is_in_caught_try(content, parse_offset):
                continue
            add(idx, Severity.MEDIUM, "json-parse-without-error-handling",
                "JSON.parse is used without visible error handling and can throw for invalid JSON.",
                "Wrap parsing in appropriate error handling when the input is not guaranteed to be valid JSON.")

        # Unreachable executable statements immediately after return/throw in the same block.
        for idx, line in enumerate(lines[:-1], start=1):
            stripped = line.strip()
            # Conditional one-line exits (`if (x) return y`) do not make the
            # following sibling statement unreachable. Only a standalone
            # unconditional return/throw can terminate the current block.
            if not re.match(r"^(?:return|throw)\b", stripped):
                continue
            if stripped.rstrip().endswith(("{", "(", "[")):
                continue
            j = idx + 1
            while j <= len(lines) and (not lines[j-1].strip() or lines[j-1].lstrip().startswith("//")):
                j += 1
            if j > len(lines):
                continue
            nxt = lines[j-1].strip()
            if nxt.startswith("}") or nxt.startswith("case ") or nxt.startswith("default:"):
                continue
            if nxt.startswith((
                ".", "?.", ")", "]", ",", "&&", "||", "??",
                "+", "-", "*", "/", "%", "?", ":",
            )):
                # The return/throw expression continues on the next source line.
                continue
            if stripped.rstrip().endswith((
                ".", "?.", ",", "&&", "||", "??", "+", "-", "*", "/",
            )):
                continue
            add(j, Severity.MEDIUM, "unreachable-code",
                "This statement is unreachable because control flow exits earlier in the same block.",
                "Remove the unreachable statement or restructure the control flow.")

        # Unused parameters for ordinary function declarations/methods with brace-delimited bodies.
        func_pattern = re.compile(
            r"^[ \t]*(?:(?:public|private|protected|static|override)\s+)*"
            r"(?:async\s+)?(?:function\s+)?"
            r"(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\s*"
            r"\((?P<params>[^()]*)\)\s*(?::[^={]+)?\s*\{",
            re.MULTILINE,
        )
        for match in func_pattern.finditer(content):
            function_name = (match.group("name") or "").strip()
            if function_name in {"if", "for", "while", "switch", "catch", "with"}:
                continue
            params_text = match.group("params")
            if not params_text.strip():
                continue
            start_brace = content.find("{", match.end()-1)
            if start_brace < 0:
                continue
            depth = 0
            end = None
            quote = None
            escaped = False
            for pos in range(start_brace, len(content)):
                ch = content[pos]
                if quote:
                    if escaped:
                        escaped = False
                    elif ch == "\\":
                        escaped = True
                    elif ch == quote:
                        quote = None
                    continue
                if ch in "'\"`":
                    quote = ch
                    continue
                if ch == "{": depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = pos
                        break
            if end is None:
                continue
            body = content[start_brace+1:end]
            signature_line = content.count("\n", 0, match.start()) + 1
            for raw in self._split_javascript_parameters(params_text):
                raw = raw.strip()
                if not raw:
                    continue
                if raw.startswith("..."):
                    raw = raw[3:].strip()

                # TypeScript parameter properties may carry one or more modifiers:
                #   constructor(private http: HttpClient) {}
                #   constructor(private readonly api: ApiService) {}
                # `private`/`readonly` are modifiers, never parameter names.
                modifier_match = re.match(
                    r"(?P<mods>(?:(?:public|private|protected|readonly|override)\s+)*)"
                    r"(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\??",
                    raw,
                )
                if not modifier_match:
                    continue

                name = modifier_match.group("name")
                modifiers = {
                    token
                    for token in modifier_match.group("mods").split()
                    if token
                }
                is_parameter_property = bool(
                    modifiers.intersection(
                        {"public", "private", "protected", "readonly"}
                    )
                )

                if function_name == "constructor" and is_parameter_property:
                    # A constructor parameter property becomes a class member.
                    # Its meaningful use normally appears as `this.<name>` outside
                    # the constructor body, so function-body-only analysis is wrong.
                    signature_start = match.start()
                    signature_end = start_brace + 1
                    content_without_signature = (
                        content[:signature_start]
                        + content[signature_end:]
                    )
                    if re.search(
                        rf"\bthis\s*\.\s*{re.escape(name)}\b",
                        content_without_signature,
                    ):
                        continue
                elif re.search(rf"\b{re.escape(name)}\b", body):
                    continue

                add(signature_line, Severity.LOW, "unused-parameter",
                    f"Parameter '{name}' is declared but never used in this function.",
                    f"Remove the unused parameter '{name}' or use it in the function body.")

        return findings

    @staticmethod
    def _split_javascript_parameters(text: str) -> list[str]:
        """Split parameters only at top-level commas.

        Type annotations may contain commas inside tuples, generics, object
        types, and callback signatures. Treating those commas as parameter
        boundaries can turn a type name into a fake unused parameter.
        """
        result: list[str] = []
        start = 0
        depths = {"(": 0, "[": 0, "{": 0, "<": 0}
        closing = {")": "(", "]": "[", "}": "{", ">": "<"}
        quote: str | None = None
        escaped = False
        for index, char in enumerate(text):
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
            elif char in depths:
                depths[char] += 1
            elif char in closing:
                opener = closing[char]
                depths[opener] = max(0, depths[opener] - 1)
            elif char == "," and not any(depths.values()):
                result.append(text[start:index])
                start = index + 1
        result.append(text[start:])
        return result

    @classmethod
    def _offset_is_in_caught_try(cls, content: str, offset: int) -> bool:
        """Return whether an offset is protected by a structurally matched try/catch.

        This uses brace matching rather than nearby-text heuristics, so nested
        object literals and nested blocks inside the try body do not hide the
        enclosing error boundary.
        """
        for match in re.finditer(r"\btry\s*\{", content):
            opening = content.find("{", match.start(), match.end())
            closing = cls._matching_javascript_brace(content, opening)
            if closing is None or not (opening < offset < closing):
                continue
            if re.match(r"\s*catch\b", content[closing + 1:]):
                return True
        return False

    @staticmethod
    def _matching_javascript_brace(content: str, opening: int) -> int | None:
        """Match one JavaScript brace while ignoring strings and comments."""
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
    def _mask_angular_inline_resources(content: str) -> str:
        """Hide inline Angular template/style strings from TS regex checks."""

        if "@Component" not in content:
            return content

        pattern = re.compile(
            r"\b(?:template|styles?)\s*:\s*(?:\[(?P<array>.*?)\]|"
            r"(?P<single>`(?:\\.|[^`])*`|'(?:\\.|[^'])*'|"
            r'"(?:\\.|[^\"])*"))',
            re.DOTALL,
        )

        def mask(match: re.Match) -> str:
            return "".join(
                "\n" if char == "\n" else " "
                for char in match.group(0)
            )

        return pattern.sub(mask, content)

    def _find_hardcoded_secret(
        self,
        changed_line: ChangedLine,
    ) -> Finding | None:
        """
        Detect obvious hardcoded credentials/secrets.

        This check is language-agnostic and intentionally
        conservative.

        Supported assignment examples include:

            apiKey = "secret-key-123"
            password = "p@ssw0rd"
            token: "abc123xyz"
            apiKey := "secret-key-123"

        Placeholder/example values are ignored.
        """

        content = changed_line.content

        match = (
            self.SECRET_ASSIGNMENT_PATTERN.search(
                content
            )
        )

        if match is None:
            return None

        variable_name = (
            match.group("name")
        )

        secret_value = (
            match.group("value")
            .strip()
        )

        normalized_name = re.sub(
            r"[^a-z0-9]",
            "",
            variable_name.lower(),
        )
        secret_names = {
            "password", "passwd", "pwd", "secret", "secretkey",
            "apikey", "accesskey", "authtoken", "token",
            "clientsecret", "privatekey",
        }
        if not any(name in normalized_name for name in secret_names):
            return None

        normalized_value = (
            secret_value
            .strip()
            .lower()
        )

        if (
            normalized_value
            in self.SAFE_SECRET_VALUES
        ):
            return None

        if len(secret_value) < 6:
            return None

        return Finding(
            file_path=changed_line.file_path,
            line_number=changed_line.line_number,
            severity=Severity.CRITICAL,
            rule_id="hardcoded-secret",
            message=(
                f"Hardcoded credential or secret detected "
                f"in '{variable_name}'."
            ),
            suggestion=(
                "Move the secret to a secure configuration "
                "source such as an environment variable or "
                "secret-management service."
            ),
            diff_position=(
                changed_line.diff_position
            ),
        )

    def _find_multiline_javascript_secret(
        self,
        changed_file: ChangedFile,
        changed_line: ChangedLine,
    ) -> Finding | None:
        """Detect a JS/TS secret whose literal value is on the next line."""

        declaration = re.search(
            r"(?:\b(?:const|let|var)\s+|(?:public|private|protected|readonly|static)\s+)+"
            r"(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\s*(?::[^=;]+)?=\s*$",
            changed_line.content,
        )
        if declaration is None or not changed_file.full_content:
            return None

        variable_name = declaration.group("name")
        normalized_name = re.sub(r"[^a-z0-9]", "", variable_name.lower())
        secret_names = {
            "password", "passwd", "pwd", "secret", "secretkey",
            "apikey", "accesskey", "authtoken", "token",
            "clientsecret", "privatekey", "jwtsecret",
        }
        if not any(name in normalized_name for name in secret_names):
            return None

        lines = changed_file.full_content.splitlines()
        next_index = changed_line.line_number
        if next_index >= len(lines):
            return None

        next_line = lines[next_index].strip()
        value_match = re.match(r"[\"']([^\"']+)[\"']\s*;?\s*$", next_line)
        if value_match is None:
            return None

        secret_value = value_match.group(1).strip()
        if secret_value.lower() in self.SAFE_SECRET_VALUES or len(secret_value) < 6:
            return None

        return Finding(
            file_path=changed_line.file_path,
            line_number=changed_line.line_number,
            severity=Severity.CRITICAL,
            rule_id="hardcoded-secret",
            message=f"Hardcoded credential or secret detected in '{variable_name}'.",
            suggestion=(
                "Move the secret to a secure configuration source such as an "
                "environment variable or secret-management service."
            ),
            diff_position=changed_line.diff_position,
        )

    def _find_unused_variable(
        self,
        changed_file: ChangedFile,
        changed_line: ChangedLine,
    ) -> Finding | None:
        """
        Detect an obvious unused JavaScript/TypeScript
        variable.

        We report a variable only when:

        1. The changed line contains a simple
           const/let/var declaration.

        2. Complete current file content is available.

        3. The variable identifier occurs exactly once
           in the complete file.

        This is intentionally conservative.
        """

        match = self.VARIABLE_DECLARATION_PATTERN.search(changed_line.content)
        if match is None:
            match = self.CLASS_FIELD_DECLARATION_PATTERN.search(changed_line.content)
        if match is None:
            return None

        if re.match(r"^\s*export\b", changed_line.content):
            # Exported declarations are public API. Same-file occurrence counts
            # cannot prove that external consumers do not use the symbol.
            return None

        variable_name = match.group(1)

        # Resource handles such as timers should not be reported as ordinary
        # unused variables. Removing the handle would make cleanup harder; the
        # lifecycle/resource rule is the actionable finding instead.
        if re.search(r"\bset(?:Interval|Timeout)\s*\(", changed_line.content):
            return None

        full_content = changed_file.full_content

        if not full_content:
            return None

        identifier_pattern = re.compile(
            rf"\b{re.escape(variable_name)}\b"
        )

        occurrences = (
            identifier_pattern.findall(
                full_content
            )
        )

        if len(occurrences) != 1:
            return None

        return Finding(
            file_path=changed_line.file_path,
            line_number=changed_line.line_number,
            severity=Severity.LOW,
            rule_id="unused-variable",
            message=(
                f"Variable '{variable_name}' "
                f"is declared but never used."
            ),
            suggestion=(
                f"Remove the unused variable "
                f"'{variable_name}'."
            ),
            diff_position=(
                changed_line.diff_position
            ),
        )

    def _supports_javascript_file(
        self,
        file_path: str,
    ) -> bool:
        """
        Return True when JavaScript/TypeScript-specific
        deterministic checks should run.
        """

        normalized = file_path.lower()

        return any(
            normalized.endswith(extension)
            for extension
            in self.JAVASCRIPT_EXTENSIONS
        )
