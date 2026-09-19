import ast
import re
from dataclasses import dataclass

from pr_reviewer.review.models import ChangedFile, Finding, Severity


@dataclass(frozen=True)
class _Context:
    changed: dict[int, object]
    file_path: str


class PythonStaticAnalyzer:
    """Conservative Python AST capability adapter.

    The adapter emits findings only for AST nodes whose evidence line is part
    of the PR diff. Syntax errors safely fall back to generic/LLM review.
    """

    def analyze(self, changed_file: ChangedFile) -> list[Finding]:
        if not changed_file.file_path.lower().endswith((".py", ".pyw")):
            return []
        content = changed_file.full_content or "\n".join(
            line.content for line in changed_file.changed_lines
        )
        if not content.strip():
            return []
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return []

        ctx = _Context(
            changed={line.line_number: line for line in changed_file.changed_lines},
            file_path=changed_file.file_path,
        )
        findings: list[Finding] = []
        seen: set[tuple[int, str]] = set()
        source_lines = content.splitlines()
        response_models = self._pydantic_model_fields(tree)

        def add(node, severity, rule, message, suggestion, evidence=None):
            line_number = getattr(node, "lineno", 0)
            changed_line = ctx.changed.get(line_number)
            if changed_line is None or (line_number, rule) in seen:
                return
            seen.add((line_number, rule))
            findings.append(Finding(
                file_path=ctx.file_path,
                line_number=line_number,
                severity=severity,
                rule_id=rule,
                message=message,
                suggestion=suggestion,
                diff_position=getattr(changed_line, "diff_position", None),
                evidence=evidence,
            ))

        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign):
                self._typed_secret(node, add)

            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._mutable_defaults(node, add)
                self._unreachable_statements(node.body, add)
                self._typed_identity_comparisons(node, add)
                self._nullable_return_suppressions(node, source_lines, add)
                self._ignored_result_followed_by_success(node, add)
                self._one_based_pagination(node, add)
                self._incomplete_cache_key(node, add)
                self._resource_lifecycle(node, add)
                self._exception_detail_exposure(node, add)
                self._weak_header_authorization(node, add)
                self._untrusted_identity_headers(node, add, source_lines)
                self._python_http_contracts(node, add, content)
                self._sequential_async_io(node, add)
                self._failure_reported_as_success(node, add)
                self._fastapi_upload_contract(node, add)
                self._fastapi_response_model_contract(node, response_models, add)
                self._open_redirects(node, add)
                if self._is_test_file(changed_file.file_path):
                    self._weak_test_assertions(node, add)
                if isinstance(node, ast.AsyncFunctionDef):
                    for child in ast.walk(node):
                        if isinstance(child, ast.Call) and self._call_name(child.func) == "time.sleep":
                            add(child, Severity.MEDIUM, "async-blocking-operation",
                                "A blocking sleep is executed inside an async function.",
                                "Use an asynchronous delay such as asyncio.sleep and await it.")
                self._weak_role_guard(node, add)

            if isinstance(node, ast.Compare) and any(
                isinstance(operator, (ast.Is, ast.IsNot)) for operator in node.ops
            ):
                values = [node.left, *node.comparators]
                if any(self._is_non_singleton_literal(value) for value in values):
                    add(node, Severity.MEDIUM, "identity-comparison-literal",
                        "Identity comparison is used with a value literal.",
                        "Use == or != for value comparison; reserve is/is not for identity and singleton checks.")

            if isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    add(node, Severity.MEDIUM, "bare-except",
                        "A bare exception handler silently catches system-exiting and unrelated failures.",
                        "Catch specific exception types and handle, record, or propagate the failure.")
                if not node.body or all(isinstance(statement, ast.Pass) for statement in node.body):
                    # A bare-and-empty handler is one root cause. Emit only the
                    # stronger bare-except finding; deduplication also protects
                    # equivalent findings from other analyzers.
                    if node.type is not None:
                        add(node, Severity.MEDIUM, "empty-catch-block",
                            "An empty exception handler silently ignores a failure.",
                            "Handle, propagate, or explicitly record the exception.")
                if self._returns_success(node.body):
                    anchor = next(
                        (statement for statement in node.body if isinstance(statement, ast.Return)),
                        node,
                    )
                    add(anchor, Severity.MEDIUM, "incorrect-result-handling",
                        "An exception path returns a successful result.",
                        "Return an error result or propagate an appropriate exception/status.")

            if isinstance(node, ast.Call):
                call_name = self._call_name(node.func)
                if call_name in {"eval", "exec"}:
                    add(node, Severity.HIGH, "unsafe-code-execution",
                        "Dynamic code execution is performed on a runtime value.",
                        "Replace dynamic execution with an explicit parser or allow-listed operation.")
                if self._uses_shell_true(node):
                    shell_kw = next((k for k in node.keywords if k.arg == "shell"), None)
                    anchor_node = shell_kw if shell_kw is not None else node
                    # Build evidence that shows the call, shell=True, and the
                    # first argument (the caller-controlled command string).
                    call_line = source_lines[node.lineno - 1].strip() if node.lineno <= len(source_lines) else ""
                    end_line = getattr(node, "end_lineno", node.lineno)
                    if end_line > node.lineno and end_line <= len(source_lines):
                        call_snippet = " ".join(
                            source_lines[i].strip()
                            for i in range(node.lineno - 1, min(end_line, node.lineno + 3))
                        )
                    else:
                        call_snippet = call_line
                    cmd_evidence = (
                        f"Line {anchor_node.lineno}: {call_snippet}"
                        if call_snippet
                        else None
                    )
                    add(anchor_node, Severity.HIGH, "command-injection",
                        "A command is executed through a shell-enabled API with shell=True; "
                        "caller-controlled input reaches the shell interpreter.",
                        "Pass a fixed argument list without a shell and validate any external input.",
                        evidence=cmd_evidence)
                if call_name == "print" and not self._logs_sensitive_header(node):
                    add(node, Severity.LOW, "debug-print",
                        "A direct print statement was added to application code.",
                        "Use the application's structured logger or remove the debug output.")
                if call_name in {"pickle.load", "pickle.loads", "dill.load", "dill.loads"}:
                    add(node, Severity.HIGH, "unsafe-deserialization",
                        "Untrusted binary data is deserialized with an object-construction API.",
                        "Use a non-executable data format and validate the decoded schema.")
                if call_name == "yaml.load" and not self._uses_safe_yaml_loader(node):
                    add(node, Severity.HIGH, "unsafe-deserialization",
                        "YAML is loaded with an unsafe object-construction loader.",
                        "Use yaml.safe_load or SafeLoader and validate the resulting data.")
                if call_name in {"hashlib.md5", "hashlib.sha1", "md5", "sha1"}:
                    add(node, Severity.MEDIUM, "weak-cryptography",
                        "A cryptographically broken hash is used to construct a security-sensitive value.",
                        "Use the secrets module for tokens or a modern password/KDF primitive for credentials.")
                if self._is_interpolated_sql_sink(node):
                    add(node, Severity.HIGH, "sql-injection",
                        "A SQL execution boundary receives a query containing interpolated runtime data.",
                        "Use parameterized SQL and pass external values separately from the statement text.")
                if self._is_unvalidated_path_read(node):
                    add(node, Severity.HIGH, "path-traversal",
                        "A caller-controlled path segment reaches a file-read boundary without containment validation.",
                        "Resolve the candidate path and verify it remains inside the configured root before reading.")
                if self._jwt_verification_disabled(node):
                    opt_kw = next((k for k in node.keywords if k.arg in {"options", "verify"}), None)
                    anchor_node = opt_kw if opt_kw is not None else node
                    add(anchor_node, Severity.HIGH, "jwt-signature-verification-disabled",
                        "JWT decoding explicitly disables signature verification.",
                        "Verify the signature with an allow-listed algorithm and require expiry and subject claims.")
                if self._is_mass_assignment(node):
                    add(node, Severity.HIGH, "mass-assignment",
                        "Caller-provided fields are applied wholesale to an existing domain object.",
                        "Allow-list editable fields and keep privileged or server-owned fields immutable.")
                if self._logs_sensitive_header(node):
                    add(node, Severity.HIGH, "sensitive-data-logging",
                        "An authentication or authorization header is written to application output.",
                        "Never log credential headers; record only non-sensitive request metadata.")

            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                if self._call_name(node.value.func) in {"asyncio.create_task", "create_task"}:
                    add(node, Severity.MEDIUM, "unowned-background-task",
                        "A background task is created without retaining lifecycle or exception ownership.",
                        "Retain and supervise the task, await it in structured concurrency, or register explicit completion/error handling.")

        self._unreachable_statements(getattr(tree, "body", []), add)
        return findings

    def analyze_project(self, changed_files: list[ChangedFile]) -> list[Finding]:
        """Resolve high-confidence Python contracts that cross changed files."""
        parsed: list[tuple[ChangedFile, ast.AST]] = []
        models: dict[str, set[str]] = {}
        for changed_file in changed_files:
            if not changed_file.file_path.lower().endswith((".py", ".pyw")):
                continue
            content = changed_file.full_content or "\n".join(
                line.content for line in changed_file.changed_lines
            )
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            parsed.append((changed_file, tree))
            models.update(self._pydantic_model_fields(tree))

        findings: list[Finding] = []
        seen: set[tuple[str, int, str]] = set()
        for changed_file, tree in parsed:
            local_models = self._pydantic_model_fields(tree)
            changed = {line.line_number: line for line in changed_file.changed_lines}

            def add(node, severity, rule, message, suggestion):
                number = getattr(node, "lineno", 0)
                source = changed.get(number)
                key = (changed_file.file_path, number, rule)
                if source is None or key in seen:
                    return
                seen.add(key)
                findings.append(Finding(
                    file_path=changed_file.file_path,
                    line_number=number,
                    severity=severity,
                    rule_id=rule,
                    message=message,
                    suggestion=suggestion,
                    diff_position=source.diff_position,
                ))

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    response_model = self._response_model_name(node)
                    if response_model not in local_models:
                        self._fastapi_response_model_contract(node, models, add)
        return findings

    @staticmethod
    def _mutable_defaults(node, add) -> None:
        defaults = [*node.args.defaults, *[value for value in node.args.kw_defaults if value]]
        for default in defaults:
            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                add(default, Severity.MEDIUM, "mutable-default-argument",
                    "A mutable object is used as a function default argument.",
                    "Use None as the default and create a new object inside the function.")

    @staticmethod
    def _typed_secret(node: ast.AnnAssign, add) -> None:
        """Cover Python annotated assignments without broad string scanning."""
        if not isinstance(node.target, ast.Name) or not isinstance(node.value, ast.Constant):
            return
        if not isinstance(node.value.value, str):
            return
        normalized_name = "".join(character for character in node.target.id.lower() if character.isalnum())
        secret_names = (
            "password", "passwd", "pwd", "secret", "secretkey", "apikey",
            "accesskey", "authtoken", "token", "clientsecret", "privatekey",
        )
        value = node.value.value.strip()
        safe_values = {
            "", "changeme", "change-me", "example", "placeholder", "secret",
            "password", "token", "your-secret", "your-token", "todo",
        }
        if any(name in normalized_name for name in secret_names) and len(value) >= 6:
            if value.lower() not in safe_values:
                add(node, Severity.CRITICAL, "hardcoded-secret",
                    f"Hardcoded credential or secret detected in '{node.target.id}'.",
                    "Move the secret to an environment variable or secret-management service.")

    @classmethod
    def _typed_identity_comparisons(cls, node, add) -> None:
        value_typed_names = {
            argument.arg
            for argument in [*node.args.args, *node.args.kwonlyargs]
            if cls._annotation_is_value_type(argument.annotation)
        }
        if not value_typed_names:
            return
        for comparison in ast.walk(node):
            if not isinstance(comparison, ast.Compare):
                continue
            if not any(isinstance(operator, (ast.Is, ast.IsNot)) for operator in comparison.ops):
                continue
            operands = [comparison.left, *comparison.comparators]
            if any(isinstance(operand, ast.Name) and operand.id in value_typed_names for operand in operands):
                other_operands = [
                    operand for operand in operands
                    if not (isinstance(operand, ast.Constant) and operand.value is None)
                ]
                if len(other_operands) >= 2:
                    add(comparison, Severity.MEDIUM, "identity-comparison-literal",
                        "Identity comparison is used for a value-typed operand.",
                        "Use == or != for value comparison; reserve is/is not for object identity and singletons.")

    @staticmethod
    def _annotation_is_value_type(annotation) -> bool:
        if annotation is None:
            return False
        names = {
            child.id.lower()
            for child in ast.walk(annotation)
            if isinstance(child, ast.Name)
        }
        return bool(names & {"int", "str", "float", "complex", "bytes", "bytearray"})

    @classmethod
    def _nullable_return_suppressions(cls, node, source_lines, add) -> None:
        if node.returns is None or cls._annotation_allows_none(node.returns):
            return
        for returned in (child for child in ast.walk(node) if isinstance(child, ast.Return)):
            if not isinstance(returned.value, (ast.Call, ast.Name, ast.Attribute)):
                continue
            line = source_lines[returned.lineno - 1] if returned.lineno <= len(source_lines) else ""
            if "type: ignore" in line and "return-value" in line:
                add(returned, Severity.MEDIUM, "null-safety",
                    "A possibly-null value is returned despite the function's non-null return contract.",
                    "Handle the missing-value case or declare an optional return type and require callers to handle it.")

    @staticmethod
    def _annotation_allows_none(annotation) -> bool:
        return any(
            (isinstance(child, ast.Constant) and child.value is None)
            or (isinstance(child, ast.Name) and child.id in {"None", "Optional"})
            for child in ast.walk(annotation)
        )

    @classmethod
    def _ignored_result_followed_by_success(cls, node, add) -> None:
        for statements in cls._statement_blocks(node):
            for current, following in zip(statements, statements[1:]):
                if not isinstance(current, ast.Expr) or not isinstance(current.value, ast.Call):
                    continue
                if not isinstance(following, ast.Return) or not cls._is_true(following.value):
                    continue
                call_name = cls._call_name(current.value.func)
                operation = call_name.rsplit(".", 1)[-1]
                function_is_mutation = any(
                    token in node.name.lower() for token in ("update", "delete", "save", "write")
                )
                if operation in {"update", "delete"} or (
                    function_is_mutation and operation in {"execute", "executemany"}
                ):
                    add(following, Severity.MEDIUM, "incorrect-result-handling",
                        "The operation result is ignored and the function always reports success.",
                    "Return or validate the operation result and preserve its failure outcome.")

    @classmethod
    def _resource_lifecycle(cls, node, add) -> None:
        assigned_resources: list[tuple[str, ast.Call, str]] = []
        for child in ast.walk(node):
            if not isinstance(child, (ast.Assign, ast.AnnAssign)):
                continue
            value = child.value
            call = value if isinstance(value, ast.Call) else None
            if call is None:
                continue
            targets = child.targets if isinstance(child, ast.Assign) else [child.target]
            names = [target.id for target in targets if isinstance(target, ast.Name)]
            if not names:
                continue
            call_name = cls._call_name(call.func)
            if call_name in {"open", "path.open"} or call_name.endswith(".open"):
                assigned_resources.append((names[0], call, "file"))
            elif call_name in {"aiohttp.clientsession", "clientsession"}:
                assigned_resources.append((names[0], call, "aiohttp session"))
            elif call_name in {"httpx.asyncclient", "httpx.client", "asyncclient"}:
                assigned_resources.append((names[0], call, "HTTP client"))

        all_calls = [child for child in ast.walk(node) if isinstance(child, ast.Call)]
        for name, call, resource_type in assigned_resources:
            closed = any(
                cls._call_name(candidate.func) == f"{name.lower()}.close"
                for candidate in all_calls
            )
            if not closed:
                add(call, Severity.MEDIUM, "resource-cleanup",
                    f"The {resource_type} is created without deterministic closure.",
                    "Use a with/async with context manager or close the resource in a guaranteed cleanup path.")

    @classmethod
    def _exception_detail_exposure(cls, node, add) -> None:
        for handler in (child for child in ast.walk(node) if isinstance(child, ast.ExceptHandler)):
            if not handler.name:
                continue
            for returned in (child for statement in handler.body for child in ast.walk(statement) if isinstance(child, ast.Return)):
                exposes = any(
                    isinstance(call, ast.Call)
                    and cls._call_name(call.func) == "str"
                    and any(isinstance(arg, ast.Name) and arg.id == handler.name for arg in call.args)
                    for call in ast.walk(returned.value)
                ) if returned.value is not None else False
                if exposes:
                    add(returned, Severity.MEDIUM, "exception-detail-exposure",
                        "Internal exception details are returned directly to the client.",
                        "Return a stable public error message and record detailed diagnostics only in protected logs.")

    @classmethod
    def _weak_header_authorization(cls, node, add) -> None:
        for condition in (child for child in ast.walk(node) if isinstance(child, ast.If)):
            calls = [child for child in ast.walk(condition.test) if isinstance(child, ast.Call)]
            role_header = any(
                "headers.get" in cls._call_name(call.func)
                and any(
                    isinstance(arg, ast.Constant)
                    and isinstance(arg.value, str)
                    and any(token in arg.value.lower() for token in ("role", "permission", "scope"))
                    for arg in call.args
                )
                for call in calls
            )
            comparisons = [child for child in ast.walk(condition.test) if isinstance(child, ast.Compare)]
            if role_header and not comparisons:
                add(condition, Severity.HIGH, "authorization",
                    "The authorization check verifies only that a role header exists, not that it grants the required access.",
                    "Validate an explicit allowed role/permission using a trusted authentication context.")

    @classmethod
    def _is_interpolated_sql_sink(cls, node: ast.Call) -> bool:
        terminal = cls._call_name(node.func).rsplit(".", 1)[-1]
        if terminal not in {"execute", "executemany", "raw", "text"} or not node.args:
            return False
        query = node.args[0]
        return isinstance(query, ast.JoinedStr) or (
            isinstance(query, ast.BinOp) and isinstance(query.op, (ast.Add, ast.Mod))
        ) or isinstance(query, ast.Call) and cls._call_name(query.func) == "str.format"

    @classmethod
    def _is_unvalidated_path_read(cls, node: ast.Call) -> bool:
        terminal = cls._call_name(node.func).rsplit(".", 1)[-1]
        if terminal not in {"read_text", "read_bytes"} or not isinstance(node.func, ast.Attribute):
            return False
        value = node.func.value
        return isinstance(value, ast.BinOp) and isinstance(value.op, ast.Div) and any(
            isinstance(child, ast.Name) for child in ast.walk(value.right)
        )

    @classmethod
    def _uses_safe_yaml_loader(cls, node: ast.Call) -> bool:
        for keyword in node.keywords:
            if keyword.arg in {"Loader", "loader"}:
                loader = cls._call_name(keyword.value)
                return loader.endswith("safeloader") or loader.endswith("csafeloader")
        return False

    @staticmethod
    def _is_true(node) -> bool:
        return isinstance(node, ast.Constant) and node.value is True

    @classmethod
    def _one_based_pagination(cls, node, add) -> None:
        parameter_names = {argument.arg for argument in [*node.args.args, *node.args.kwonlyargs]}
        page_names = parameter_names & {"page", "page_number", "page_index"}
        size_names = parameter_names & {"page_size", "pagesize", "limit", "per_page"}
        if not page_names or not size_names:
            return
        candidates: list[tuple[ast.AST, ast.AST]] = [
            (assignment, assignment.value)
            for assignment in ast.walk(node)
            if isinstance(assignment, (ast.Assign, ast.AnnAssign))
        ]
        candidates.extend(
            (expression, expression)
            for subscript in ast.walk(node)
            if isinstance(subscript, ast.Subscript)
            for expression in ast.walk(subscript.slice)
            if isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.Mult)
        )
        for anchor, value in candidates:
            if not isinstance(value, ast.BinOp) or not isinstance(value.op, ast.Mult):
                continue
            direct_page = any(
                isinstance(side, ast.Name) and side.id in page_names
                for side in (value.left, value.right)
            )
            direct_size = any(
                isinstance(side, ast.Name) and side.id in size_names
                for side in (value.left, value.right)
            )
            if direct_page and direct_size:
                add(anchor, Severity.MEDIUM, "logic-error",
                    "The page offset multiplies the one-based page number directly, so the first page skips one page of records.",
                    "Calculate the offset as (page - 1) * page_size, or explicitly use a zero-based page contract.")

    @classmethod
    def _incomplete_cache_key(cls, node, add) -> None:
        parameters = {
            argument.arg for argument in [*node.args.args, *node.args.kwonlyargs]
            if argument.arg not in {"self", "cls"}
        }
        if len(parameters) < 2:
            return
        for assignment in (child for child in ast.walk(node) if isinstance(child, (ast.Assign, ast.AnnAssign))):
            targets = assignment.targets if isinstance(assignment, ast.Assign) else [assignment.target]
            key_names = {
                target.id for target in targets
                if isinstance(target, ast.Name) and "key" in target.id.lower()
            }
            if not key_names:
                continue
            included = {child.id for child in ast.walk(assignment.value) if isinstance(child, ast.Name)} & parameters
            omitted = parameters - included
            if not omitted:
                continue
            function_nodes = list(ast.walk(node))
            key_used_for_cache = any(
                isinstance(child, ast.Subscript)
                and any(isinstance(part, ast.Name) and part.id in key_names for part in ast.walk(child.slice))
                and "cache" in cls._call_name(child.value)
                for child in function_nodes
            )
            omitted_affects_result = any(
                isinstance(child, ast.Name) and child.id in omitted and child.lineno > assignment.lineno
                for child in function_nodes
            )
            if key_used_for_cache and omitted_affects_result:
                names = ", ".join(sorted(omitted))
                add(assignment, Severity.MEDIUM, "cache-consistency",
                    f"The cache key omits result-shaping input(s): {names}.",
                    "Include every input that can change the computed result in the cache key.")

    @classmethod
    def _weak_test_assertions(cls, node, add) -> None:
        assertions = [child for child in ast.walk(node) if isinstance(child, ast.Assert)]
        if not assertions:
            return
        function_name = node.name.lower()
        for assertion in assertions:
            expression = assertion.test
            attributes = {
                child.attr.lower() for child in ast.walk(expression) if isinstance(child, ast.Attribute)
            }
            calls = [child for child in ast.walk(expression) if isinstance(child, ast.Call)]
            if attributes & {"status_code", "status"} and len(assertions) == 1:
                add(assertion, Severity.MEDIUM, "insufficient-test-assertion",
                    "The test verifies only the response status and not the returned behavior or data.",
                    "Assert the relevant response body fields or observable behavior in addition to the status.")
            elif "page" in attributes and not attributes & {"items", "results", "total", "content"} and len(assertions) == 1:
                add(assertion, Severity.MEDIUM, "insufficient-test-assertion",
                    "The pagination test verifies metadata but not the records returned for that page.",
                    "Assert the expected items or boundaries so skipped or duplicated records fail the test.")
            elif "missing" in function_name and calls and isinstance(expression, ast.Compare):
                if any(isinstance(value, ast.Constant) and value.value is True for value in expression.comparators):
                    add(assertion, Severity.MEDIUM, "insufficient-test-assertion",
                        "The missing-record test accepts a successful operation result.",
                        "Assert the failure result or exception required when the target record does not exist.")

    @staticmethod
    def _statement_blocks(node):
        blocks = [node.body]
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try)):
                for attribute in ("body", "orelse", "finalbody"):
                    statements = getattr(child, attribute, None)
                    if statements:
                        blocks.append(statements)
        return blocks

    @staticmethod
    def _is_test_file(file_path: str) -> bool:
        lowered = file_path.lower().replace("\\", "/")
        name = lowered.rsplit("/", 1)[-1]
        return "/tests/" in f"/{lowered}" or name.startswith("test_") or ".test." in name

    @classmethod
    def _unreachable_statements(cls, statements, add) -> None:
        terminated = False
        for statement in statements:
            if terminated:
                add(statement, Severity.MEDIUM, "unreachable-code",
                    "This statement is unreachable because the current block already exits.",
                    "Remove the statement or restructure the control flow.")
                break
            if isinstance(statement, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
                terminated = True

    @classmethod
    def _weak_role_guard(cls, node, add) -> None:
        name = node.name.lower()
        if not any(token in name for token in ("admin", "authoriz", "permission", "role")):
            return
        role_names = {
            argument.arg for argument in [*node.args.args, *node.args.kwonlyargs]
            if any(token in argument.arg.lower() for token in ("role", "permission", "scope"))
        }
        dictionary_role_lookup = any(
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "get"
            and call.args
            and isinstance(call.args[0], ast.Constant)
            and str(call.args[0].value).lower() in {"role", "permission", "scope"}
            for call in ast.walk(node)
        )
        if not role_names and not dictionary_role_lookup:
            return
        comparisons = [child for child in ast.walk(node) if isinstance(child, ast.Compare)]
        has_required_value_check = any(
            any(isinstance(value, ast.Constant) and isinstance(value.value, str)
                for value in [comparison.left, *comparison.comparators])
            for comparison in comparisons
        )
        if has_required_value_check:
            return
        guard = next((child for child in ast.walk(node) if isinstance(child, ast.If)), None)
        if guard is not None:
            add(guard, Severity.HIGH, "authorization",
                "The authorization guard checks only that a role exists, not that it grants the required access.",
                "Compare against an explicit allowed role/permission or use a centralized authorization policy.")

    @staticmethod
    def _returns_success(statements) -> bool:
        for statement in statements:
            if not isinstance(statement, ast.Return):
                continue
            value = statement.value
            if isinstance(value, ast.Constant) and value.value is True:
                return True
            if isinstance(value, ast.Dict):
                for key, item in zip(value.keys, value.values):
                    if isinstance(key, ast.Constant) and str(key.value).lower() in {"success", "ok"}:
                        if isinstance(item, ast.Constant) and item.value is True:
                            return True
            if isinstance(value, ast.Call) and any(
                keyword.arg == "status_code"
                and isinstance(keyword.value, ast.Constant)
                and 200 <= keyword.value.value < 300
                for keyword in value.keywords
            ):
                return True
        return False

    @classmethod
    def _uses_shell_true(cls, node: ast.Call) -> bool:
        call_name = cls._call_name(node.func)
        if not any(token in call_name for token in ("subprocess", "popen", "check_output", "run", "call")):
            return False
        return any(
            keyword.arg == "shell"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is True
            for keyword in node.keywords
        )

    @staticmethod
    def _pydantic_model_fields(tree: ast.AST) -> dict[str, set[str]]:
        models: dict[str, set[str]] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            bases = {PythonStaticAnalyzer._call_name(base).rsplit(".", 1)[-1] for base in node.bases}
            if "basemodel" not in bases:
                continue
            models[node.name] = {
                statement.target.id
                for statement in node.body
                if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name)
            }
        return models

    @classmethod
    def _untrusted_identity_headers(cls, node, add, source_lines: list[str] | None = None) -> None:
        name = node.name.lower()
        if not any(token in name for token in ("current_user", "identity", "authenticate")):
            return
        positional = list(node.args.args)
        positional_defaults = [None] * (len(positional) - len(node.args.defaults)) + list(node.args.defaults)
        arguments_with_defaults = [
            *zip(positional, positional_defaults),
            *zip(node.args.kwonlyargs, node.args.kw_defaults),
        ]
        header_arguments = []
        for argument, default in arguments_with_defaults:
            annotation = argument.annotation
            annotated_header = annotation is not None and any(
                isinstance(child, ast.Name) and child.id == "Header"
                for child in ast.walk(annotation)
            )
            default_header = (
                isinstance(default, ast.Call)
                and cls._call_name(default.func).rsplit(".", 1)[-1] == "header"
            )
            if annotated_header or default_header:
                header_arguments.append(argument.arg)
        if not header_arguments:
            return
        returned_names = {
            child.id
            for returned in ast.walk(node)
            if isinstance(returned, ast.Return) and returned.value is not None
            for child in ast.walk(returned.value)
            if isinstance(child, ast.Name)
        }
        trusted = set(header_arguments) & returned_names
        if trusted:
            trusted_params = ", ".join(sorted(trusted))
            
            # Find the actual return statements that leak the header
            return_lines = []
            for returned in ast.walk(node):
                if isinstance(returned, ast.Return) and returned.value is not None:
                    if any(
                        isinstance(child, ast.Name) and child.id in trusted
                        for child in ast.walk(returned.value)
                    ):
                        ret_lineno = getattr(returned, "lineno", None)
                        if source_lines and ret_lineno and 1 <= ret_lineno <= len(source_lines):
                            return_lines.append(source_lines[ret_lineno - 1].strip())
                        else:
                            try:
                                code = ast.unparse(returned).replace("'", '"')
                                return_lines.append(code)
                            except Exception:
                                pass

            returns_text = "\n".join(return_lines) if return_lines else 'return {"id": x_user_id, "role": x_role}'
            
            identity_evidence = (
                f"def {node.name}(..., {trusted_params}: ... = Header(), ...)\n"
                f"{returns_text}"
            )
            add(node, Severity.HIGH, "untrusted-identity-header",
                f"Caller-controlled request header(s) '{trusted_params}' are returned as "
                "authenticated identity or role evidence.",
                "Derive identity from a verified credential and build authorization context server-side.",
                evidence=identity_evidence)

    @classmethod
    def _python_http_contracts(
        cls,
        node,
        add,
        source_content: str = "",
    ) -> None:
        # aiohttp ClientSession supplies a finite default timeout and its
        # response lifecycle differs from httpx/requests. Keep that adapter's
        # established lifecycle rules authoritative instead of layering
        # generic HTTP contract claims on top.
        if "clientsession" in ast.dump(node).lower():
            return

        # httpx ships with a finite default timeout (5 s connect + 5 s read).
        # Emitting missing-timeout when the caller simply relies on that default
        # is a false positive.  Only report the rule when:
        #   1. httpx is NOT in use (other clients have no finite default), OR
        #   2. httpx IS in use AND timeout=None was explicitly set on the client
        #      (which disables all timeouts and is demonstrably unsafe).
        node_dump = ast.dump(node)
        uses_httpx = (
            "httpx" in node_dump
            or (source_content and "httpx" in source_content)
        )
        httpx_timeout_disabled = bool(
            source_content
            and re.search(
                r"\bhttpx\.(?:AsyncClient|Client)\s*\([^)]*timeout\s*=\s*None",
                source_content,
                re.DOTALL,
            )
        )
        # Suppress missing-timeout entirely when httpx has its finite default.
        suppress_missing_timeout = uses_httpx and not httpx_timeout_disabled

        calls: list[tuple[str, ast.Call]] = []
        for child in ast.walk(node):
            if not isinstance(child, (ast.Assign, ast.AnnAssign)):
                continue
            value = child.value
            if not isinstance(value, ast.Await) or not isinstance(value.value, ast.Call):
                continue
            call = value.value
            if cls._call_name(call.func).rsplit(".", 1)[-1] not in {"get", "post", "put", "patch", "delete", "request"}:
                continue
            targets = child.targets if isinstance(child, ast.Assign) else [child.target]
            target = next((item.id for item in targets if isinstance(item, ast.Name)), None)
            if target:
                calls.append((target, call))
        for response_name, call in calls:
            timeout_kw = next((keyword for keyword in call.keywords if keyword.arg == "timeout"), None)
            timeout_is_none = (
                timeout_kw is not None
                and isinstance(timeout_kw.value, ast.Constant)
                and timeout_kw.value.value is None
            )
            has_valid_timeout = timeout_kw is not None and not timeout_is_none
            suppress = uses_httpx and not httpx_timeout_disabled and not timeout_is_none
            if not has_valid_timeout and not suppress:
                anchor = timeout_kw if timeout_is_none else call
                add(anchor, Severity.MEDIUM, "missing-timeout",
                    "The outbound HTTP request has no explicit timeout boundary.",
                    "Set an explicit connect/read timeout appropriate for the dependency.")
            status_checked = any(
                isinstance(candidate, ast.Call)
                and cls._call_name(candidate.func) == f"{response_name.lower()}.raise_for_status"
                for candidate in ast.walk(node)
            ) or any(
                isinstance(candidate, ast.Attribute)
                and isinstance(candidate.value, ast.Name)
                and candidate.value.id == response_name
                and candidate.attr in {"status", "status_code", "is_success"}
                for candidate in ast.walk(node)
            )
            if not status_checked:
                add(call, Severity.MEDIUM, "http-status-not-checked",
                    "The outbound HTTP response is consumed without validating its status.",
                    "Call raise_for_status() or explicitly validate the accepted status range.")
            json_calls = [
                candidate for candidate in ast.walk(node)
                if isinstance(candidate, ast.Call)
                and cls._call_name(candidate.func) == f"{response_name.lower()}.json"
            ]
            validation_present = any(
                isinstance(candidate, ast.Call)
                and cls._call_name(candidate.func) in {"isinstance", "type_adapter.validate_python", "model_validate"}
                for candidate in ast.walk(node)
            )
            if json_calls and not validation_present:
                add(json_calls[0], Severity.MEDIUM, "unvalidated-external-data",
                    "External JSON data is used without runtime shape validation.",
                    "Validate the decoded value with a schema, model, or explicit type guards before use.")

    @classmethod
    def _sequential_async_io(cls, node, add) -> None:
        if not isinstance(node, ast.AsyncFunctionDef):
            return
        for loop in (child for child in ast.walk(node) if isinstance(child, (ast.For, ast.AsyncFor))):
            for child in ast.walk(loop):
                if not isinstance(child, ast.Await) or not isinstance(child.value, ast.Call):
                    continue
                terminal = cls._call_name(child.value.func).rsplit(".", 1)[-1]
                if terminal in {"get", "post", "put", "patch", "delete", "request"}:
                    add(child, Severity.MEDIUM, "sequential-await-in-loop",
                        "Independent outbound requests are awaited serially inside a loop.",
                        "Use bounded concurrency when iterations are independent.")
                    break

    @classmethod
    def _failure_reported_as_success(cls, node, add) -> None:
        for index, statement in enumerate(node.body):
            if not isinstance(statement, ast.Try):
                continue
            swallowed = any(
                not handler.body or all(isinstance(item, ast.Pass) for item in handler.body)
                for handler in statement.handlers
            )
            if not swallowed:
                continue
            for following in node.body[index + 1:]:
                if isinstance(following, ast.Return) and cls._is_true(following.value):
                    add(following, Severity.MEDIUM, "incorrect-result-handling",
                        "The function reports success after an exception was silently ignored.",
                        "Propagate the failure or return an explicit unsuccessful result.")
                    break

    @classmethod
    def _fastapi_upload_contract(cls, node, add) -> None:
        upload_names = {
            argument.arg
            for argument in [*node.args.args, *node.args.kwonlyargs]
            if argument.annotation is not None and any(
                isinstance(child, ast.Name) and child.id == "UploadFile"
                for child in ast.walk(argument.annotation)
            )
        }
        for name in upload_names:
            filename = next((
                child for child in ast.walk(node)
                if isinstance(child, ast.Attribute)
                and isinstance(child.value, ast.Name)
                and child.value.id == name and child.attr == "filename"
            ), None)
            if filename is None:
                continue
            has_validation = any(
                isinstance(child, ast.Attribute)
                and isinstance(child.value, ast.Name)
                and child.value.id == name
                and child.attr in {"content_type", "size"}
                for child in ast.walk(node)
            )
            if not has_validation:
                add(filename, Severity.HIGH, "unrestricted-file-upload",
                    "The client filename is used without filename, content-type, or size validation.",
                    "Generate a server-owned filename, enforce size/type limits, and keep the resolved path inside the upload root.")

    @classmethod
    def _fastapi_response_model_contract(cls, node, models: dict[str, set[str]], add) -> None:
        response_model = cls._response_model_name(node)
        required = models.get(response_model or "")
        if not required:
            return
        argument_models = {
            argument.arg: argument.annotation.id
            for argument in [*node.args.args, *node.args.kwonlyargs]
            if isinstance(argument.annotation, ast.Name)
        }
        for returned in (child for child in ast.walk(node) if isinstance(child, ast.Return)):
            value = returned.value
            if not isinstance(value, ast.Call) or not isinstance(value.func, ast.Attribute):
                continue
            if value.func.attr != "model_dump" or not isinstance(value.func.value, ast.Name):
                continue
            source_fields = models.get(argument_models.get(value.func.value.id, ""), set())
            missing = required - source_fields
            if missing:
                add(returned, Severity.MEDIUM, "response-contract-mismatch",
                    f"The response model requires fields not supplied by the returned model: {', '.join(sorted(missing))}.",
                    "Construct the declared response model with every required field.")

    @staticmethod
    def _response_model_name(node) -> str | None:
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            for keyword in decorator.keywords:
                if keyword.arg == "response_model" and isinstance(keyword.value, ast.Name):
                    return keyword.value.id
        return None

    @classmethod
    def _jwt_verification_disabled(cls, node: ast.Call) -> bool:
        if cls._call_name(node.func).rsplit(".", 1)[-1] != "decode":
            return False
        for keyword in node.keywords:
            if keyword.arg != "options" or not isinstance(keyword.value, ast.Dict):
                continue
            for key, value in zip(keyword.value.keys, keyword.value.values):
                if isinstance(key, ast.Constant) and key.value == "verify_signature":
                    return isinstance(value, ast.Constant) and value.value is False
        return False

    @classmethod
    def _open_redirects(cls, function, add) -> None:
        parameter_names = {
            argument.arg for argument in [*function.args.args, *function.args.kwonlyargs]
        }
        validation_text = ast.dump(function).lower()
        has_destination_validation = (
            "urlparse" in validation_text
            or "allowed_origins" in validation_text
            or "trusted_origins" in validation_text
            or "startswith" in validation_text
        )
        if has_destination_validation:
            return
        for node in ast.walk(function):
            if not isinstance(node, ast.Call):
                continue
            if cls._call_name(node.func).rsplit(".", 1)[-1] not in {"redirectresponse", "redirect"}:
                continue
            destination = node.args[0] if node.args else next(
                (keyword.value for keyword in node.keywords if keyword.arg in {"url", "location"}),
                None,
            )
            if isinstance(destination, ast.Name) and destination.id in parameter_names:
                add(node, Severity.HIGH, "open-redirect",
                    "A caller-controlled destination is passed directly to a redirect response.",
                    "Allow only local paths or validate the destination against trusted origins.")

    @classmethod
    def _is_mass_assignment(cls, node: ast.Call) -> bool:
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "update" or not node.args:
            return False
        return (
            isinstance(node.func.value, ast.Name)
            and node.func.value.id.lower() in {"user", "account", "profile", "entity", "model"}
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id.lower() in {"updates", "payload", "data", "fields"}
        )

    @classmethod
    def _logs_sensitive_header(cls, node: ast.Call) -> bool:
        if cls._call_name(node.func).rsplit(".", 1)[-1] not in {"print", "debug", "info", "warning", "error", "critical"}:
            return False
        text = ast.dump(node).lower()
        return any(token in text for token in ("authorization", "cookie", "x-api-key", "api_key"))

    @staticmethod
    def _call_name(node) -> str:
        parts: list[str] = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name):
            parts.append(node.id)
        return ".".join(reversed(parts)).lower()

    @staticmethod
    def _is_non_singleton_literal(node) -> bool:
        return isinstance(node, ast.Constant) and node.value not in {None, True, False, Ellipsis}
