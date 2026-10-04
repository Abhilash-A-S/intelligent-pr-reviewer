import re

from pr_reviewer.review.models import ChangedFile, Finding, Severity


class TypeScriptStaticAnalyzer:
    """Conservative TypeScript contract and control-flow checks.

    These rules use explicit source types and runtime behavior rather than an
    assumed tsconfig. Findings remain restricted to changed lines.
    """

    FUNCTION_PATTERN = re.compile(
        r"\bfunction\s+(?P<name>[A-Za-z_$][\w$]*)\s*"
        r"\((?P<params>.*?)\)\s*:\s*(?P<return>[^\{]+)\{",
        re.DOTALL,
    )

    def analyze(self, changed_file: ChangedFile) -> list[Finding]:
        path = changed_file.file_path.lower()
        if not path.endswith((".ts", ".tsx")) or path.endswith(".d.ts"):
            return []
        content = changed_file.full_content or "\n".join(
            line.content for line in changed_file.changed_lines
        )
        if not content:
            return []
        lines = content.splitlines()
        changed = {line.line_number: line for line in changed_file.changed_lines}
        findings: list[Finding] = []
        seen: set[tuple[int, str]] = set()

        def add(number: int, rule: str, message: str, suggestion: str) -> None:
            source = changed.get(number)
            if source is None or (number, rule) in seen:
                return
            seen.add((number, rule))
            findings.append(Finding(
                file_path=changed_file.file_path,
                line_number=number,
                severity=Severity.MEDIUM,
                rule_id=rule,
                message=message,
                suggestion=suggestion,
                diff_position=source.diff_position,
            ))

        optional_properties = set(re.findall(
            r"\b([A-Za-z_$][\w$]*)\?\s*:\s*[^;,}\n]+", content
        ))

        function_spans: list[tuple[int, int, str, str, int]] = []
        for match in self.FUNCTION_PATTERN.finditer(content):
            opening = content.find("{", match.start(), match.end())
            closing = self._matching_brace(content, opening)
            if closing is None:
                continue
            body = content[opening + 1:closing]
            prefix = content[match.start():closing + 1]
            start_line = content.count("\n", 0, opening) + 1
            params = self._parameters(match.group("params"))
            return_type = match.group("return").strip()
            function_spans.append((match.start(), closing, body, return_type, start_line))

            for name, type_text, optional in params:
                nullable = bool(re.search(r"\b(?:null|undefined)\b", type_text))
                if nullable and not self._value_guarded(prefix, name):
                    number = self._first_body_line(
                        body, start_line, rf"\b{re.escape(name)}\s*\.(?!\?)"
                    )
                    if number:
                        add(number, "typescript-null-dereference",
                            f"Possibly null or undefined value '{name}' is dereferenced.",
                            f"Narrow '{name}' before access or use an explicit safe fallback.")

                if optional:
                    number = self._first_body_line(
                        body, start_line,
                        rf"(?:\b{re.escape(name)}\b\s*[-+*/%]|[-+*/%]\s*\b{re.escape(name)}\b)",
                    )
                    if number and not self._value_guarded(prefix, name):
                        add(number, "typescript-optional-operand",
                            f"Optional parameter '{name}' is used without a defined fallback.",
                            f"Provide a default value or narrow '{name}' before using it.")

                if type_text.strip() == "unknown":
                    number = self._first_body_line(
                        body, start_line,
                        rf"\b{re.escape(name)}\s+as\s+[A-Za-z_$][\w$<>,.\[\] |]*",
                    )
                    if number:
                        add(number, "unsafe-type-assertion",
                            f"Unknown value '{name}' is asserted to a concrete type without validation.",
                            "Use a type guard, schema validation, or a proven discriminant before conversion.")

                assertion_chain = self._first_body_line(
                    body, start_line,
                    rf"\b{re.escape(name)}\s+as\s+unknown\s+as\s+[A-Za-z_$][\w$<>,.\[\] |]*",
                )
                if assertion_chain:
                    add(assertion_chain, "unsafe-type-assertion",
                        f"Value '{name}' is forced through an unknown assertion without runtime validation.",
                        "Validate the value with a type guard or schema before converting it.")

                if type_text.strip() in {"object", "Object"}:
                    number = self._first_body_line(
                        body, start_line,
                        rf"\b{re.escape(name)}\s*\[[^\]]+\]",
                    )
                    if number:
                        add(number, "unsafe-indexed-access",
                            f"Value '{name}' has no index signature for dynamic property access.",
                            "Use Record<string, unknown>, keyof-based access, or narrow the object type.")

                if type_text.strip() == "Function":
                    signature_line = content.count("\n", 0, match.start()) + 1
                    add(signature_line, "broad-function-type",
                        f"Parameter '{name}' uses the non-specific Function type.",
                        "Declare the callback's parameter and return types explicitly.")

            for prop in optional_properties:
                property_match = re.search(
                    rf"\b(?P<owner>[A-Za-z_$][\w$]*)\s*\.\s*{re.escape(prop)}\s*\.(?!\?)",
                    body,
                )
                if not property_match:
                    continue
                owner = property_match.group("owner")
                if self._property_guarded(prefix, owner, prop):
                    continue
                number = start_line + body.count("\n", 0, property_match.start())
                add(number, "typescript-optional-property",
                    f"Optional property '{owner}.{prop}' is dereferenced without narrowing.",
                    "Check the optional property or provide a fallback before accessing it.")

            find_match = re.search(r"\breturn\s+[^;\n]*\.find\s*\(", body)
            if find_match and not re.search(r"\b(?:undefined|null)\b", return_type):
                number = start_line + body.count("\n", 0, find_match.start())
                add(number, "typescript-possibly-undefined-result",
                    "Array.find can return undefined despite the declared non-optional return type.",
                    "Return an optional type or handle the missing element before returning.")

            index_match = re.search(r"\breturn\s+[^;\n]*\[\s*\d+\s*\]", body)
            indexed_owner = None
            if index_match:
                owner_match = re.search(
                    r"\breturn\s+([A-Za-z_$][\w$]*)[^;\n]*\[\s*\d+\s*\]", index_match.group(0)
                )
                indexed_owner = owner_match.group(1) if owner_match else None
            non_empty_tuple = any(
                name == indexed_owner and re.search(r"^readonly\s*\[|^\[", type_text.strip())
                for name, type_text, _optional in params
            )
            if index_match and not non_empty_tuple and not re.search(r"\b(?:undefined|null)\b", return_type):
                number = start_line + body.count("\n", 0, index_match.start())
                add(number, "typescript-possibly-undefined-result",
                    "An array element is returned without proving that the index exists.",
                    "Handle the empty-array case or return an optional result type.")

            self._add_definite_assignment_findings(
                body, start_line, add
            )

            self._add_unvalidated_response_finding(
                body, return_type, start_line, add
            )
            self._add_sequential_io_finding(body, start_line, add)

        for number, source_line in enumerate(lines, 1):
            stripped = source_line.strip()
            if re.search(r"\bthrow\s+(['\"`]|\d|true\b|false\b|null\b|undefined\b)", stripped):
                add(number, "non-error-throw",
                    "A non-Error value is thrown, losing a reliable stack and error contract.",
                    "Throw an Error instance or a domain-specific Error subclass.")
            promise = re.search(r"\bPromise\.reject\s*\(", source_line)
            if promise:
                before = source_line[:promise.start()]
                if not re.search(r"\b(?:return|await|void)\s*$", before) and ".catch(" not in source_line:
                    add(number, "unobserved-promise-rejection",
                        "A rejected Promise is created without being returned, awaited, or observed.",
                        "Return or await the Promise, or attach an intentional rejection handler.")

        for match in re.finditer(
            r"\bthis\s*\.\s*(?P<name>[A-Za-z_$][\w$]*)\s*=\s*setInterval\s*\(",
            content,
        ):
            name = match.group("name")
            owner = self._containing_class(content, match.start())
            ownership_scope = owner[2] if owner else content
            if re.search(rf"\bclearInterval\s*\(\s*this\s*\.\s*{re.escape(name)}\s*\)", ownership_scope):
                continue
            number = content.count("\n", 0, match.start()) + 1
            add(number, "timer-without-cleanup",
                f"Timer handle 'this.{name}' is retained but never cleared.",
                f"Add an ownership cleanup path that calls clearInterval(this.{name}).")

        self._add_observer_cleanup_findings(content, add)
        self._add_prototype_pollution_findings(content, function_spans, add)
        self._add_always_truthy_findings(lines, add)
        self._add_non_exhaustive_union_findings(content, function_spans, add)

        return findings

    @staticmethod
    def _parameters(text: str) -> list[tuple[str, str, bool]]:
        result: list[tuple[str, str, bool]] = []
        for raw in TypeScriptStaticAnalyzer._split_top_level(text):
            match = re.search(
                r"\b([A-Za-z_$][\w$]*)(\?)?\s*:\s*(.+?)\s*$", raw.strip()
            )
            if match:
                result.append((match.group(1), match.group(3).strip(), bool(match.group(2))))
        return result

    @staticmethod
    def _split_top_level(text: str) -> list[str]:
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

    @staticmethod
    def _add_unvalidated_response_finding(body: str, return_type: str, start_line: int, add) -> None:
        declared = return_type.strip()
        promise = re.fullmatch(r"Promise\s*<\s*(.+)\s*>", declared)
        declared = promise.group(1).strip() if promise else declared
        declared = re.sub(r"\s*\|\s*(?:undefined|null)\b", "", declared).strip()
        if declared in {"unknown", "any", "void", "never", "string", "number", "boolean", "Response"}:
            return
        response = re.search(
            r"\breturn\s+\(?\s*(?:await\s+)?([A-Za-z_$][\w$]*)\.json\s*\(\s*\)"
            r"(?:\s*\)?\s+as\s+[A-Za-z_$][\w$<>,.\[\] |]*)?",
            body,
        )
        if not response:
            return
        name = response.group(1)
        if re.search(r"\b(?:Array\.isArray|safeParse|parse|validate|is[A-Z]\w*)\s*\(", body):
            return
        number = start_line + body.count("\n", 0, response.start())
        add(number, "unvalidated-external-data",
            f"The JSON body from '{name}' is returned as a typed value without runtime validation.",
            "Parse the response as unknown and validate its shape before returning it.")

    @staticmethod
    def _add_sequential_io_finding(body: str, start_line: int, add) -> None:
        for loop in re.finditer(r"\b(?:for\s*\([^)]*\)|for\s+await\s*\([^)]*\))\s*\{", body):
            opening = body.find("{", loop.start(), loop.end())
            closing = TypeScriptStaticAnalyzer._matching_brace(body, opening)
            if closing is None:
                continue
            loop_body = body[opening + 1:closing]
            awaited = re.search(r"\bawait\s+(?:fetch\s*\(|[A-Za-z_$][\w$]*\s*\.)", loop_body)
            if not awaited:
                continue
            number = start_line + body.count("\n", 0, opening + 1 + awaited.start())
            add(number, "sequential-await-in-loop",
                "Independent asynchronous work is awaited serially inside a loop.",
                "When iterations are independent and bounded, collect the tasks and await them together.")

    @staticmethod
    def _add_observer_cleanup_findings(content: str, add) -> None:
        for creation in re.finditer(
            r"\b(?:const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)\s*=\s*new\s+"
            r"(?P<kind>MutationObserver|ResizeObserver|IntersectionObserver)\s*\(", content
        ):
            name = creation.group("name")
            observe = re.search(rf"\b{re.escape(name)}\.observe\s*\(", content[creation.end():])
            if not observe:
                continue
            function_start = content.rfind("function", 0, creation.start())
            opening = content.find("{", function_start, creation.start()) if function_start >= 0 else -1
            closing = TypeScriptStaticAnalyzer._matching_brace(content, opening)
            scope = content[function_start:closing + 1] if closing is not None and closing >= creation.end() else content
            if re.search(rf"\b{re.escape(name)}\.disconnect\s*\(", scope):
                continue
            number = content.count("\n", 0, creation.start()) + 1
            add(number, "observer-without-cleanup",
                f"{creation.group('kind')} '{name}' is activated without an owned disconnect path.",
                f"Return or register cleanup that calls {name}.disconnect().")

    @staticmethod
    def _add_prototype_pollution_findings(content: str, functions, add) -> None:
        for _start, _end, body, _return_type, start_line in functions:
            write = re.search(
                r"\b(?P<object>[A-Za-z_$][\w$]*)\s*\[\s*(?P<key>[A-Za-z_$][\w$]*)\s*\]\s*=", body
            )
            if not write:
                continue
            key = write.group("key")
            if "Object.create(null)" in body or re.search(
                rf"{re.escape(key)}\s*===?\s*['\"](?:__proto__|prototype|constructor)['\"]", body
            ):
                continue
            number = start_line + body.count("\n", 0, write.start())
            add(number, "prototype-pollution",
                f"Caller-controlled key '{key}' is written to a normal object without blocking prototype keys.",
                "Reject __proto__, prototype, and constructor keys or use a null-prototype dictionary.")

    @staticmethod
    def _add_always_truthy_findings(lines: list[str], add) -> None:
        pattern = re.compile(r"\b(?:if|while)\s*\([^\n)]*\|\|\s*(['\"])[^'\"]+\1")
        for number, line in enumerate(lines, 1):
            if pattern.search(line):
                add(number, "always-truthy-condition",
                    "A non-empty string literal makes this condition always truthy.",
                    "Repeat the comparison variable on both sides of the logical operator.")

    @staticmethod
    def _add_non_exhaustive_union_findings(content: str, functions, add) -> None:
        aliases: dict[str, set[str]] = {}
        for match in re.finditer(r"\btype\s+(\w+)\s*=\s*((?:['\"][^'\"]+['\"]\s*\|?\s*)+);", content):
            aliases[match.group(1)] = set(re.findall(r"['\"]([^'\"]+)['\"]", match.group(2)))
        if not aliases:
            return
        for start, _end, body, _return_type, start_line in functions:
            signature = content[start:content.find("{", start)]
            for parameter, alias in re.findall(r"\b(\w+)\s*:\s*(\w+)", signature):
                members = aliases.get(alias)
                if not members:
                    continue
                switch = re.search(rf"\bswitch\s*\(\s*{re.escape(parameter)}\s*\)\s*\{{", body)
                if not switch:
                    continue
                opening = body.find("{", switch.start(), switch.end())
                closing = TypeScriptStaticAnalyzer._matching_brace(body, opening)
                if closing is None:
                    continue
                switch_body = body[opening + 1:closing]
                covered = set(re.findall(r"\bcase\s+['\"]([^'\"]+)['\"]\s*:", switch_body))
                if members <= covered or re.search(r"\bassertNever\s*\(", switch_body):
                    continue
                missing = ", ".join(sorted(members - covered))
                number = start_line + body.count("\n", 0, switch.start())
                add(number, "non-exhaustive-union",
                    f"Switch over '{alias}' does not handle: {missing}.",
                    "Handle every union member and use a never assertion in the default branch.")

    @staticmethod
    def _containing_class(content: str, offset: int) -> tuple[int, int, str] | None:
        owner = None
        for match in re.finditer(r"\bclass\s+[A-Za-z_$][\w$]*(?:\s+extends\s+[^\{]+)?\s*\{", content):
            opening = content.find("{", match.start(), match.end())
            closing = TypeScriptStaticAnalyzer._matching_brace(content, opening)
            if closing is not None and opening < offset < closing:
                owner = (match.start(), closing, content[match.start():closing + 1])
        return owner

    @staticmethod
    def _value_guarded(function: str, name: str) -> bool:
        escaped = re.escape(name)
        return bool(re.search(
            rf"(?:if\s*\(\s*!\s*{escaped}\b|{escaped}\s*[!=]==?\s*(?:null|undefined)|"
            rf"{escaped}\s*\?\?|typeof\s+{escaped}\b|{escaped}\s+is\s+)",
            function,
        ))

    @staticmethod
    def _property_guarded(function: str, owner: str, prop: str) -> bool:
        target = rf"{re.escape(owner)}\s*\.\s*{re.escape(prop)}"
        return bool(re.search(
            rf"(?:if\s*\(\s*!\s*{target}\b|{target}\s*[!=]==?\s*(?:null|undefined)|"
            rf"{target}\s*\?\?|{target}\s*\?\.)",
            function,
        ))

    @staticmethod
    def _first_body_line(body: str, start_line: int, pattern: str) -> int | None:
        match = re.search(pattern, body)
        return start_line + body.count("\n", 0, match.start()) if match else None

    @staticmethod
    def _add_definite_assignment_findings(body: str, start_line: int, add) -> None:
        for declaration in re.finditer(
            r"\blet\s+([A-Za-z_$][\w$]*)\s*:\s*[^;=]+;", body
        ):
            name = declaration.group(1)
            remainder = body[declaration.end():]
            increment = re.search(
                rf"(?:\b{re.escape(name)}\s*(?:\+\+|--|[+\-*/%]=)|"
                rf"(?:\+\+|--)\s*\b{re.escape(name)}\b)",
                remainder,
            )
            if increment:
                number = start_line + body.count("\n", 0, declaration.end() + increment.start())
                add(number, "typescript-use-before-assignment",
                    f"Variable '{name}' is read before it has been assigned.",
                    f"Initialize '{name}' before the first read.")
                continue
            returned = re.search(rf"\breturn\s+{re.escape(name)}\s*;", remainder)
            if not returned:
                continue
            before_return = remainder[:returned.start()]
            assignment = re.search(rf"(?m)^\s*{re.escape(name)}\s*=", before_return)
            if assignment and not re.search(r"\b(?:if|switch|for|while|try)\b", before_return[:assignment.start()]):
                continue
            number = start_line + body.count("\n", 0, declaration.end() + returned.start())
            add(number, "typescript-use-before-assignment",
                f"Variable '{name}' is not definitely assigned on every return path.",
                f"Initialize '{name}' or make every control-flow branch assign it.")

    @staticmethod
    def _matching_brace(content: str, opening: int) -> int | None:
        depth = 0
        quote: str | None = None
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
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return index
        return None
