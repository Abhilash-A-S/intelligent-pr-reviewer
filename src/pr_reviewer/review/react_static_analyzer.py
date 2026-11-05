import re

from pr_reviewer.review.models import ChangedFile, ChangedLine, Finding, Severity


class ReactStaticAnalyzer:
    """Conservative deterministic checks for React component source files."""

    REACT_EXTENSIONS = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")

    def analyze(self, changed_file: ChangedFile) -> list[Finding]:
        if not self._is_react_file(changed_file):
            return []

        content = changed_file.full_content or ""
        if not content:
            return []

        lines = content.splitlines()
        changed_by_line = {line.line_number: line for line in changed_file.changed_lines}
        findings: list[Finding] = []
        seen: set[tuple[int, str, str]] = set()

        def add(
            line_number: int,
            severity: Severity,
            rule_id: str,
            message: str,
            suggestion: str,
        ) -> None:
            changed = changed_by_line.get(line_number)
            if changed is None:
                return
            key = (line_number, rule_id, message)
            if key in seen:
                return
            seen.add(key)
            findings.append(
                Finding(
                    file_path=changed_file.file_path,
                    line_number=line_number,
                    severity=severity,
                    rule_id=rule_id,
                    message=message,
                    suggestion=suggestion,
                    diff_position=changed.diff_position,
                )
            )

        self._check_effects(content, changed_by_line, add)
        self._check_direct_dom(content, add)
        self._check_arrow_parameters(content, add)
        self._check_global_listeners(content, lines, add)
        self._check_fetch_status(lines, add)

        return findings

    def _check_effects(self, content: str, changed_by_line: dict[int, ChangedLine], add) -> None:
        state_values = {
            match.group(1)
            for match in re.finditer(
                r"\bconst\s*\[\s*([A-Za-z_$][A-Za-z0-9_$]*)\s*,\s*"
                r"[A-Za-z_$][A-Za-z0-9_$]*\s*\]\s*=\s*useState\s*\(",
                content,
            )
        }

        for effect_match in re.finditer(r"\buseEffect\s*\(", content):
            open_paren = content.find("(", effect_match.start())
            close_paren = self._find_matching_delimiter(content, open_paren, "(", ")")
            if close_paren is None:
                continue

            inner = content[open_paren + 1 : close_paren]
            split = self._split_top_level_comma(inner)
            if split is None:
                continue

            callback, deps_text = split
            deps_text = deps_text.strip()
            if not (deps_text.startswith("[") and deps_text.endswith("]")):
                continue

            body_start = callback.find("{")
            if body_start < 0:
                continue
            body_end = self._find_matching_delimiter(callback, body_start, "{", "}")
            if body_end is None:
                continue
            body = callback[body_start + 1 : body_end]

            deps = set(
                re.findall(
                    r"\b[A-Za-z_$][A-Za-z0-9_$]*\b",
                    deps_text[1:-1],
                )
            )

            start_line = content.count("\n", 0, effect_match.start()) + 1
            end_line = content.count("\n", 0, close_paren) + 1
            anchor_line = next(
                (line for line in range(start_line, end_line + 1) if line in changed_by_line),
                start_line,
            )

            for name in sorted(state_values):
                if not re.search(rf"\b{re.escape(name)}\b", body):
                    continue
                if name in deps:
                    continue
                add(
                    anchor_line,
                    Severity.MEDIUM,
                    "effect-dependency",
                    f"React effect captures '{name}' but it is missing from the dependency array.",
                    f"Add '{name}' to the dependency array or restructure the effect so it does not capture a stale value.",
                )

            cleanup_pairs = (
                (r"\bsetInterval\s*\(", r"\bclearInterval\s*\(", "setInterval", "clearInterval"),
                (r"\bsetTimeout\s*\(", r"\bclearTimeout\s*\(", "setTimeout", "clearTimeout"),
                (
                    r"\b(?:window|document)\s*\.\s*addEventListener\s*\(",
                    r"\b(?:window|document)\s*\.\s*removeEventListener\s*\(",
                    "addEventListener",
                    "removeEventListener",
                ),
            )
            for start_pattern, cleanup_pattern, resource, cleanup in cleanup_pairs:
                if re.search(start_pattern, body) and not re.search(cleanup_pattern, body):
                    add(
                        anchor_line,
                        Severity.HIGH,
                        "effect-cleanup",
                        f"React effect starts {resource} but does not provide matching cleanup.",
                        f"Return a cleanup function from the effect and call {cleanup} when the effect is disposed.",
                    )
                    break

    @classmethod
    def _check_direct_dom(cls, content: str, add) -> None:
        """Report imperative DOM queries in React code, excluding framework bootstrap roots.

        React entry points legitimately query the host element in order to pass it to
        ``createRoot``/``hydrateRoot``.  That is framework bootstrap wiring, not
        component-level DOM manipulation.  The exemption is source-construct based
        rather than filename/build-tool based so it works for CRA, Vite, Webpack,
        Next custom entries, TypeScript, and future React tooling.
        """
        pattern = re.compile(
            r"\bdocument\s*\.\s*(?:getElementById|querySelector|querySelectorAll)\s*\("
        )
        for match in pattern.finditer(content):
            if cls._is_react_root_bootstrap_query(content, match.start()):
                continue
            line_number = content.count("\n", 0, match.start()) + 1
            add(
                line_number,
                Severity.MEDIUM,
                "direct-dom-manipulation",
                "Direct DOM access was added inside React component code.",
                "Prefer React refs or state-driven rendering instead of querying the DOM directly.",
            )

    @classmethod
    def _is_react_root_bootstrap_query(cls, content: str, query_start: int) -> bool:
        """Return True when a DOM query is an argument to React root bootstrap."""
        # Look only a short distance backwards for the nearest createRoot/hydrateRoot
        # invocation and prove that its opening parenthesis still encloses the query.
        prefix_start = max(0, query_start - 160)
        prefix = content[prefix_start:query_start]
        candidates = list(
            re.finditer(
                r"(?:\bReactDOM\s*\.\s*)?\b(?:createRoot|hydrateRoot)\s*\(",
                prefix,
            )
        )
        if not candidates:
            return False

        candidate = candidates[-1]
        open_paren = prefix_start + candidate.end() - 1
        close_paren = cls._find_matching_delimiter(content, open_paren, "(", ")")
        return close_paren is not None and query_start < close_paren

    def _check_arrow_parameters(self, content: str, add) -> None:
        pattern = re.compile(
            r"(?:const|let|var)\s+[A-Za-z_$][A-Za-z0-9_$]*\s*=\s*"
            r"(?:async\s*)?\((?P<params>[^()]*)\)\s*(?::[^=]+)?=>\s*\{",
            re.MULTILINE,
        )
        for match in pattern.finditer(content):
            start_brace = content.find("{", match.end() - 1)
            end_brace = self._find_matching_delimiter(content, start_brace, "{", "}")
            if start_brace < 0 or end_brace is None:
                continue
            body = content[start_brace + 1 : end_brace]
            signature_line = content.count("\n", 0, match.start()) + 1

            for raw in match.group("params").split(","):
                raw = raw.strip()
                if raw.startswith("..."):
                    raw = raw[3:].strip()
                param_match = re.match(
                    r"(?:public|private|protected|readonly\s+)*"
                    r"(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\??",
                    raw,
                )
                if not param_match:
                    continue
                name = param_match.group("name")
                if name.startswith("_"):
                    continue
                if re.search(rf"\b{re.escape(name)}\b", body):
                    continue
                add(
                    signature_line,
                    Severity.LOW,
                    "unused-parameter",
                    f"Parameter '{name}' is declared but never used in this function.",
                    f"Remove the unused parameter '{name}' or use it in the function body.",
                )

    @staticmethod
    def _check_global_listeners(content: str, lines: list[str], add) -> None:
        if re.search(
            r"\b(?:window|document)\s*\.\s*removeEventListener\s*\(",
            content,
        ):
            return
        for line_number, line in enumerate(lines, start=1):
            if not re.search(
                r"\b(?:window|document)\s*\.\s*addEventListener\s*\(",
                line,
            ):
                continue
            add(
                line_number,
                Severity.MEDIUM,
                "global-event-listener-without-removal",
                "A global event listener is added without a visible removal path.",
                "Remove the listener when it is no longer needed, or register it in an effect with cleanup.",
            )

    @staticmethod
    def _check_fetch_status(lines: list[str], add) -> None:
        for line_number, line in enumerate(lines, start=1):
            match = re.search(
                r"\b(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*"
                r"await\s+fetch\s*\(",
                line,
            )
            if not match:
                continue
            response_name = match.group(1)
            local_window = "\n".join(
                lines[line_number - 1 : min(len(lines), line_number + 12)]
            )
            consumes_body = re.search(
                rf"\b{re.escape(response_name)}\s*\.\s*"
                r"(?:json|text|blob|arrayBuffer|formData)\s*\(",
                local_window,
            )
            checks_status = re.search(
                rf"\b{re.escape(response_name)}\s*\.\s*(?:ok|status)\b",
                local_window,
            )
            if consumes_body and not checks_status:
                add(
                    line_number,
                    Severity.MEDIUM,
                    "fetch-status-not-checked",
                    f"The HTTP response '{response_name}' is consumed without checking whether the request returned a successful status.",
                    f"Check '{response_name}.ok' or its status before consuming the response body.",
                )

    @classmethod
    def _is_react_file(cls, changed_file: ChangedFile) -> bool:
        path = changed_file.file_path.lower().replace("\\", "/")
        if not path.endswith(cls.REACT_EXTENSIONS):
            return False
        content = changed_file.full_content or ""
        lowered = content.lower()
        return (
            bool(re.search(r"\bfrom\s+['\"]react['\"]", content))
            or "require('react')" in lowered
            or 'require("react")' in lowered
            or bool(
                re.search(
                    r"\buse(?:state|effect|layouteffect|memo|callback|ref)\s*\(",
                    content,
                    re.IGNORECASE,
                )
            )
        )

    @staticmethod
    def _find_matching_delimiter(
        content: str,
        start: int,
        opening: str,
        closing: str,
    ) -> int | None:
        if start < 0 or start >= len(content) or content[start] != opening:
            return None
        depth = 0
        quote: str | None = None
        escaped = False
        line_comment = False
        block_comment = False
        index = start

        while index < len(content):
            char = content[index]
            nxt = content[index + 1] if index + 1 < len(content) else ""

            if line_comment:
                if char == "\n":
                    line_comment = False
                index += 1
                continue
            if block_comment:
                if char == "*" and nxt == "/":
                    block_comment = False
                    index += 2
                    continue
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
            if char == "/" and nxt == "/":
                line_comment = True
                index += 2
                continue
            if char == "/" and nxt == "*":
                block_comment = True
                index += 2
                continue
            if char in "'\"`":
                quote = char
                index += 1
                continue

            if char == opening:
                depth += 1
            elif char == closing:
                depth -= 1
                if depth == 0:
                    return index
            index += 1

        return None

    @staticmethod
    def _split_top_level_comma(text: str) -> tuple[str, str] | None:
        paren = brace = bracket = 0
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
                continue
            if char == "(":
                paren += 1
            elif char == ")":
                paren -= 1
            elif char == "{":
                brace += 1
            elif char == "}":
                brace -= 1
            elif char == "[":
                bracket += 1
            elif char == "]":
                bracket -= 1
            elif char == "," and paren == brace == bracket == 0:
                return text[:index], text[index + 1 :]

        return None
