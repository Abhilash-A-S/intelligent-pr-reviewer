import re

from pr_reviewer.review.models import ChangedFile, Finding, Severity


class DotNetStaticAnalyzer:
    """High-confidence C# and ASP.NET Core capability adapter.

    The adapter recognizes concrete language/runtime/framework constructs.  It
    never reports an unchanged line and deliberately exempts safe equivalents
    such as using declarations, parameterized SQL, cancellation propagation,
    canonical path containment, and cryptographic random generators.
    """

    def analyze(self, changed_file: ChangedFile) -> list[Finding]:
        path = changed_file.file_path.replace("\\", "/").lower()
        if path.endswith(".cs"):
            return self._analyze_csharp(changed_file)
        if path.endswith("appsettings.json"):
            return self._analyze_appsettings(changed_file)
        return []

    def _analyze_csharp(self, changed_file: ChangedFile) -> list[Finding]:
        content = changed_file.full_content or "\n".join(
            line.content for line in changed_file.changed_lines
        )
        lines = content.splitlines()
        changed = {line.line_number: line for line in changed_file.changed_lines}
        findings: list[Finding] = []
        seen: set[tuple[int, str]] = set()
        path = changed_file.file_path.replace("\\", "/").lower()
        is_test = "/tests/" in f"/{path}" or path.endswith(("test.cs", "tests.cs"))

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

        for number, line in enumerate(lines, start=1):
            stripped = line.strip()
            method = self._method_text(lines, number)
            signature = self._method_signature(lines, number)

            if re.search(r"\.(?:Result|Wait\s*\(\s*\))\b", line):
                add(number, Severity.MEDIUM, "sync-over-async",
                    "Asynchronous work is synchronously blocked.",
                    "Make the caller asynchronous and await the operation.")

            if re.search(r"(?:\.Result|await\s+[^;]+)!\s*(?:;|\.|$)", line):
                add(number, Severity.MEDIUM, "null-forgiving-nullable",
                    "The null-forgiving operator suppresses a nullable result without proving it exists.",
                    "Handle the missing-result case explicitly or return a nullable/optional contract.")

            if re.search(r"\basync\s+void\s+\w+\s*\(", line):
                add(number, Severity.MEDIUM, "async-void",
                    "An async void method hides completion and exceptions from its caller.",
                    "Return Task so callers can await completion and observe failures.")

            if re.search(r"=>\s*Task\.(?:Run|Factory\.StartNew)\s*\(", line) or re.match(
                r"^(?:_\s*=\s*)?Task\.(?:Run|Factory\.StartNew)\s*\(", stripped
            ):
                if "_ =" not in stripped or not self._has_task_failure_observer(method):
                    add(number, Severity.MEDIUM, "unowned-background-task",
                        "A background task is started without lifecycle or exception ownership.",
                        "Return or await the task, or supervise it through an application-owned task service.")

            if "CancellationToken" in signature:
                parameter = self._cancellation_parameter(signature)
                if parameter and re.search(r"repository\.\w+Async\s*\([^)]*\)", line):
                    arguments = re.search(r"repository\.\w+Async\s*\(([^)]*)\)", line)
                    if arguments and parameter not in arguments.group(1):
                        add(number, Severity.MEDIUM, "missing-cancellation-propagation",
                            "The supplied cancellation token is not forwarded to asynchronous repository work.",
                            "Pass the cancellation token through every cancellable asynchronous boundary.")
                if parameter and "SaveChangesAsync()" in line:
                    add(number, Severity.MEDIUM, "missing-cancellation-propagation",
                        "SaveChangesAsync ignores the cancellation token supplied by the caller.",
                        "Pass the caller's cancellation token to SaveChangesAsync.")

            if re.search(r"\.Skip\s*\(\s*page\s*\*\s*(?:pageSize|size)\s*\)", line):
                add(number, Severity.MEDIUM, "pagination-offset",
                    "A one-based page number is used directly as a zero-based offset.",
                    "Use (page - 1) * pageSize for one-based APIs, or make the API explicitly zero-based.")

            if re.search(r"\b(?:key|cacheKey)\s*=.*\bquery\b", line, re.I):
                if re.search(r"\btenant(?:Id)?\b", signature, re.I) and not re.search(r"tenant", line, re.I):
                    add(number, Severity.MEDIUM, "cache-consistency",
                        "Tenant identity is omitted from a tenant-scoped cache key.",
                        "Include the tenant and every result-shaping input in the cache key.")

            if "async Task" in signature and "SearchAsync" in signature and "CancellationToken" not in signature:
                anchor = self._signature_line(lines, number)
                if anchor == number:
                    add(number, Severity.MEDIUM, "missing-cancellation-propagation",
                        "A request-facing asynchronous search operation offers no cancellation contract.",
                        "Accept a CancellationToken and propagate it to database and network calls.")

            if re.search(r"\bcatch\s*\([^)]*\)\s*\{\s*\}", line) or (
                re.search(r"\bcatch\s*\([^)]*\)\s*\{\s*$", line) and self._block_is_empty(lines, number)
            ):
                add(number, Severity.MEDIUM, "empty-catch-block",
                    "A parsing failure is swallowed and execution continues with a valid-looking fallback.",
                    "Return an explicit failure result or handle and propagate the parsing error.")

            if re.search(r"\bMD5\.Create\s*\(", line) or re.search(r"HashAlgorithmName\.MD5", line):
                add(number, Severity.HIGH, "weak-cryptography",
                    "MD5 is used for a security-sensitive value.",
                    "Use a cryptographically secure token generator or an appropriate modern KDF.")

            if re.search(r"(?:Random\.Shared|new\s+Random\s*\()", line) and re.search(
                r"token|verification|otp|code|reset", signature, re.I
            ):
                add(number, Severity.HIGH, "predictable-random-token",
                    "A predictable pseudo-random generator creates a security code or token.",
                    "Use RandomNumberGenerator or another cryptographically secure generator.")

            if re.search(r"\.Mode\s*=\s*CipherMode\.ECB\b", line):
                add(number, Severity.HIGH, "weak-encryption",
                    "AES ECB mode reveals equality patterns in encrypted plaintext.",
                    "Use an authenticated mode such as AES-GCM with a unique nonce.")

            resource = re.search(r"\bvar\s+(\w+)\s*=\s*new\s+(StreamReader|StreamWriter|FileStream)\s*\(", line)
            if resource and not re.search(r"\b(?:await\s+)?using\b", line) and not self._disposed_later(method, resource.group(1)):
                add(number, Severity.MEDIUM, "resource-cleanup",
                    f"{resource.group(2)} is created without deterministic disposal.",
                    "Use a using declaration/statement or dispose the resource in a finally block.")

            if re.search(r"\bnew\s+HttpClient\s*\(", line) and not re.search(r"\b(?:using|static)\b", line):
                add(number, Severity.MEDIUM, "httpclient-lifetime",
                    "A new HttpClient is created for each operation.",
                    "Inject a reusable HttpClient from IHttpClientFactory.")

            response = re.search(r"\bvar\s+(\w+)\s*=\s*await\s+\w+\.GetAsync\s*\(", line)
            if response and not re.search(r"\busing\b", line) and not self._disposed_later(method, response.group(1)):
                add(number, Severity.MEDIUM, "resource-cleanup",
                    "HttpResponseMessage is not disposed after its content is consumed.",
                    "Use a using declaration for the response and validate its status before reading content.")

            if re.search(r"\.Where\s*\([^)]*\.Name\.Contains\s*\(", line) and "tenantId" in signature and "TenantId" not in line:
                add(number, Severity.HIGH, "tenant-isolation",
                    "A tenant-scoped repository query ignores the supplied tenant identifier.",
                    "Include the tenant predicate in the database query.")

            if re.search(r"\.(?:FromSqlRaw|ExecuteSqlRawAsync|ExecuteSqlRaw)\s*\([^;]*\+", line):
                add(number, Severity.HIGH, "sql-injection",
                    "Raw SQL is constructed by concatenating runtime data.",
                    "Use interpolated/parameterized EF Core APIs and bind external values.")

            if re.search(r"=>\s*db\.\w+\.ToListAsync\s*\(", line) and self._read_method(signature):
                if ".AsNoTracking(" not in line:
                    add(number, Severity.LOW, "ef-tracking-read",
                        "A read-only EF Core query tracks every returned entity.",
                        "Use AsNoTracking for read-only query results.")

            if re.search(r"\bforeach\s*\(", line) and self._loop_contains_ef_query(lines, number):
                add(number, Severity.MEDIUM, "n-plus-one-query",
                    "A database query is executed once for every item in the loop.",
                    "Project or aggregate the related values in one database query.")

            nullable_assignment = re.search(r"var\s+(\w+)\s*=\s*await\s+[^;]*FirstOrDefaultAsync", line)
            if nullable_assignment and self._dereferenced_later(method, nullable_assignment.group(1)):
                add(number, Severity.MEDIUM, "null-safety",
                    "A nullable FirstOrDefaultAsync result is later dereferenced without a check.",
                    "Handle the not-found case before accessing the entity.")

            if re.search(r"\.AddAsync\s*\(", line) and "SaveChanges" not in method:
                add(number, Severity.MEDIUM, "missing-save-changes",
                    "An entity is added to the DbContext but the method never persists the change.",
                    "Call and await SaveChangesAsync before reporting completion.")

            if re.search(r"db\.\w+\.Skip\s*\(", line) and ".OrderBy(" not in line and ".OrderByDescending(" not in line:
                add(number, Severity.MEDIUM, "unstable-pagination",
                    "Database pagination is applied without deterministic ordering.",
                    "Apply a stable OrderBy before Skip and Take.")

            if "Task.WhenAll(" in line and len(re.findall(r"db\.\w+\.", line)) >= 2:
                add(number, Severity.HIGH, "dbcontext-concurrency",
                    "Multiple operations run concurrently on the same DbContext instance.",
                    "Await operations sequentially or create an independent scope/DbContext for each concurrent operation.")

            if re.search(r"AddSingleton<\s*Mutable\w*(?:Tenant|Request|User)\w*\s*>", line):
                add(number, Severity.HIGH, "singleton-mutable-state",
                    "Mutable request or tenant state is registered as a singleton.",
                    "Use scoped state or pass tenant identity explicitly through request-owned services.")

            if "SetIsOriginAllowed(_ => true)" in line and "AllowCredentials()" in line:
                add(number, Severity.HIGH, "cors-misconfiguration",
                    "Credentialed CORS accepts every requesting origin.",
                    "Allow-list trusted origins when credentials are enabled.")

            if "UseDeveloperExceptionPage(" in line and not self._inside_development_guard(lines, number):
                add(number, Severity.MEDIUM, "developer-exception-page",
                    "Developer exception details are enabled without an environment guard.",
                    "Enable the developer exception page only in Development.")

            if re.search(r"class\s+\w+\s*\([^)]*AppDbContext\s+\w+[^)]*\)\s*:\s*BackgroundService", line):
                add(number, Severity.HIGH, "dependency-lifetime",
                    "A singleton hosted service captures a scoped DbContext.",
                    "Inject IServiceScopeFactory or IDbContextFactory and create a scope per unit of work.")

            if re.search(r"while\s*\(\s*true\s*\)", line) and "stoppingToken" in signature:
                add(number, Severity.MEDIUM, "background-cancellation",
                    "The background loop does not stop when application shutdown is requested.",
                    "Loop while the stopping token is not cancelled.")

            if "stoppingToken" in signature and re.search(r"await\s+(?:db\.[^;]+Async|Task\.Delay)\s*\([^;]*\)", line):
                call_args = re.search(r"Async\s*\(([^)]*)\)|Task\.Delay\s*\(([^)]*)\)", line)
                args = next((group for group in call_args.groups() if group is not None), "") if call_args else ""
                if "stoppingToken" not in args:
                    add(number, Severity.MEDIUM, "missing-cancellation-propagation",
                        "Background work ignores the host shutdown cancellation token.",
                        "Pass stoppingToken to the asynchronous operation.")

            if re.search(r"string\.IsNullOrWhiteSpace\s*\(\s*role\s*\)", line) and "[FromHeader" in signature:
                if not re.search(r"\[Authorize|User\.IsInRole|RequireAuthorization", method):
                    add(number, Severity.HIGH, "authorization",
                        "Any non-empty caller-controlled role header authorizes an administrative operation.",
                        "Use authenticated claims and an ASP.NET Core authorization policy.")

            if re.search(r"(?:Problem|BadRequest|StatusCode)\s*\([^;]*error\.Message", line):
                add(number, Severity.MEDIUM, "exception-detail-exposure",
                    "An internal exception message is returned to the HTTP client.",
                    "Return a stable public error and log internal details server-side.")

            if re.search(r"(?:PhysicalFile|File)\s*\([^;]*Path\.Combine\s*\([^;]*(?:name|fileName)", line, re.I):
                if not self._has_path_containment(method):
                    add(number, Severity.HIGH, "path-traversal",
                        "Caller-controlled file input is combined with a server directory without containment validation.",
                        "Resolve the canonical path and verify it remains under the allowed root.")

            if re.search(r"File\.Create\s*\([^;]*\.FileName", line) and not self._has_path_containment(method):
                add(number, Severity.HIGH, "path-traversal",
                    "The client-supplied upload filename controls the server filesystem path.",
                    "Generate a server-owned name and enforce canonical destination containment.")

            if "IFormFile" in signature and re.search(r"CopyToAsync\s*\(", line):
                if not re.search(r"ContentType|Length|extension|GetExtension|allowed", method, re.I):
                    add(number, Severity.HIGH, "unrestricted-file-upload",
                        "The upload is stored without size, type, or extension restrictions.",
                        "Enforce size limits, validate content and extension allow-lists, and store outside executable paths.")

            if re.search(r"GetStringAsync\s*\(\s*url\s*\)", line) and "[FromQuery]" in signature:
                add(number, Severity.HIGH, "ssrf",
                    "A request-controlled URL reaches an outbound HTTP request.",
                    "Resolve destinations from an allow-list and block private, loopback, and metadata-network addresses.")

            if re.search(r"\bRedirect\s*\(\s*next\s*\)", line) and "[FromQuery]" in signature:
                add(number, Severity.MEDIUM, "open-redirect",
                    "A request-controlled destination is used directly for an HTTP redirect.",
                    "Allow only local URLs or map stable identifiers to server-owned destinations.")

            if re.search(r"Process\.Start\s*\([^;]*\+\s*\w+", line) and "[FromQuery]" in signature:
                add(number, Severity.HIGH, "command-injection",
                    "Request input is concatenated into an operating-system command.",
                    "Avoid shell execution or use a fixed executable with validated ArgumentList entries.")

            if "[FromBody]" in signature and re.search(r"\b(?:UserAccount|\w*Entity)\s+\w+", signature):
                anchor = self._signature_line(lines, number)
                if anchor == number:
                    add(number, Severity.HIGH, "mass-assignment",
                        "A domain or persistence model is bound directly from the request body.",
                        "Bind a dedicated request DTO and explicitly map only allowed fields.")

            if re.search(r"Log(?:Trace|Debug|Information|Warning|Error)\s*\([^;]*password", line, re.I):
                add(number, Severity.HIGH, "sensitive-data-logging",
                    "A password value is written to application logs.",
                    "Never log credentials or secret values.")

            if "[HttpPost(\"reindex\")]" in line or "[HttpPost(\"refresh\")]" in line:
                controller = "\n".join(lines)
                if "[Authorize" not in controller:
                    add(number, Severity.HIGH, "missing-endpoint-authorization",
                        "A state-changing administrative endpoint has no authorization requirement.",
                        "Require an authenticated policy or administrative role for this endpoint.")

            if is_test:
                self._analyze_test_line(lines, number, add)

        return findings

    def _analyze_appsettings(self, changed_file: ChangedFile) -> list[Finding]:
        findings: list[Finding] = []
        for line in changed_file.changed_lines:
            text = line.content
            lowered = text.lower()
            if "password=" in lowered and not re.search(r"\$\{|%\w+%|__", text):
                findings.append(self._finding(changed_file, line, Severity.CRITICAL, "hardcoded-secret",
                    "A database credential is embedded in application configuration.",
                    "Load the connection secret from a protected configuration provider."))
            if re.search(r'"(?:JwtSecret|SigningKey|ClientSecret)"\s*:\s*"[^"$%]+"', text, re.I):
                findings.append(self._finding(changed_file, line, Severity.CRITICAL, "hardcoded-secret",
                    "A signing or authentication secret is embedded in application configuration.",
                    "Store the secret in a protected environment or secret-management provider."))
            if re.search(r'"Default"\s*:\s*"(?:Trace|Debug)"', text, re.I):
                findings.append(self._finding(changed_file, line, Severity.LOW, "debug-logging",
                    "Debug-level logging is enabled by default.",
                    "Use Information or a stricter production default and override it only in development."))
        return findings

    @staticmethod
    def _finding(changed_file, line, severity, rule, message, suggestion):
        return Finding(changed_file.file_path, line.line_number, severity, rule, message,
                       suggestion, line.diff_position)

    @staticmethod
    def _method_signature(lines: list[str], number: int) -> str:
        start = DotNetStaticAnalyzer._method_start(lines, number)
        if start is None:
            return ""
        collected: list[str] = []
        for index in range(start, min(len(lines), start + 12)):
            collected.append(lines[index].strip())
            joined = " ".join(collected)
            if re.search(r"\)\s*(?:=>|\{)\s*", joined):
                annotations = " ".join(lines[max(0, start - 5):start])
                return annotations + " " + joined
        return " ".join(collected)

    @classmethod
    def _method_text(cls, lines: list[str], number: int) -> str:
        start = cls._method_start(lines, number)
        if start is None:
            return lines[number - 1]
        signature = cls._method_signature(lines, number)
        declaration = " ".join(lines[start:min(len(lines), start + 12)])
        declaration = declaration.split("{", 1)[0]
        if re.search(r"\)\s*=>", declaration):
            return "\n".join(lines[start:min(len(lines), start + 4)])
        depth = 0
        opened = False
        for end in range(start, len(lines)):
            depth += lines[end].count("{") - lines[end].count("}")
            opened = opened or "{" in lines[end]
            if opened and depth <= 0:
                return "\n".join(lines[start:end + 1])
        return "\n".join(lines[start:min(len(lines), start + 30)])

    @staticmethod
    def _method_start(lines: list[str], number: int) -> int | None:
        for index in range(number - 1, max(-1, number - 40), -1):
            line = lines[index]
            if re.search(r"\b(?:public|private|protected|internal)\b", line) and "(" in line:
                if not re.search(r"\b(?:class|record|struct|interface)\b", line):
                    return index
        return None

    @staticmethod
    def _signature_line(lines: list[str], number: int) -> int:
        start = DotNetStaticAnalyzer._method_start(lines, number)
        return start + 1 if start is not None else number

    @staticmethod
    def _cancellation_parameter(signature: str) -> str | None:
        match = re.search(r"CancellationToken\s+(\w+)", signature)
        return match.group(1) if match else None

    @staticmethod
    def _has_task_failure_observer(method: str) -> bool:
        return any(token in method for token in ("await ", ".ContinueWith(", "Observe", "return Task"))

    @staticmethod
    def _block_is_empty(lines: list[str], number: int) -> bool:
        return bool(re.search(r"catch\s*\([^)]*\)\s*\{\s*\}", " ".join(lines[number - 1:number + 3])))

    @staticmethod
    def _disposed_later(method: str, name: str) -> bool:
        return bool(re.search(rf"\b{re.escape(name)}\.(?:Dispose|DisposeAsync)\s*\(", method))

    @staticmethod
    def _read_method(signature: str) -> bool:
        return bool(re.search(r"\b(?:Read|Get|Find|List|Search|Load)\w*Async\b", signature))

    @staticmethod
    def _loop_contains_ef_query(lines: list[str], number: int) -> bool:
        tail = "\n".join(lines[number - 1:min(len(lines), number + 8)])
        return bool(re.search(r"await\s+db\.\w+\.(?:Count|Any|First|Single|ToList)Async", tail))

    @staticmethod
    def _dereferenced_later(method: str, name: str) -> bool:
        assignment_end = method.find("FirstOrDefaultAsync")
        return bool(re.search(rf"\b{re.escape(name)}\.[A-Za-z_]", method[assignment_end + 1:]))

    @staticmethod
    def _inside_development_guard(lines: list[str], number: int) -> bool:
        return any("IsDevelopment()" in line for line in lines[max(0, number - 8):number])

    @staticmethod
    def _has_path_containment(method: str) -> bool:
        return "GetFullPath(" in method and "StartsWith(" in method

    @classmethod
    def _analyze_test_line(cls, lines, number, add) -> None:
        line = lines[number - 1]
        method = cls._method_text(lines, number)
        if re.search(r"Assert\.Equal\s*\([^;]*\.Page\s*\)", line) and not re.search(r"\.Items\b", method):
            add(number, Severity.MEDIUM, "insufficient-test-assertion",
                "The pagination test checks metadata without verifying returned records.",
                "Assert item boundaries and page contents.")
        if re.search(r"Assert\.Equal\s*\(\s*0\s*,[^;]*Parse", line):
            add(number, Severity.MEDIUM, "insufficient-test-assertion",
                "The test accepts a valid zero value when parsing invalid input.",
                "Assert the explicit failure contract or expected parsing exception.")
        if "Assert.IsType<OkObjectResult>" in line and ".Update(" in line:
            add(number, Severity.MEDIUM, "insufficient-test-assertion",
                "The update test checks only the action-result type.",
                "Verify that protected fields cannot be changed and that persistence receives only allowed values.")
        if "Assert.NotNull(" in line and ".Clear(" in line:
            add(number, Severity.MEDIUM, "insufficient-test-assertion",
                "The administrative endpoint test does not verify its authorization policy.",
                "Assert unauthorized and forbidden outcomes for unauthenticated and unprivileged callers.")
        if "Assert.NotNull(result)" in line and "attacker.example" in method:
            add(number, Severity.MEDIUM, "insufficient-test-assertion",
                "The redirect test accepts an external destination.",
                "Assert that external redirects are rejected or converted to a safe local destination.")
