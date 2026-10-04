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
        seen_methods: set[tuple[int, str]] = set()
        DEDUP_METHOD_RULES = {
            "unrestricted-file-upload",
            "path-traversal",
            "command-injection",
            "cors-misconfiguration",
            "sequential-io-operations",
        }
        path = changed_file.file_path.replace("\\", "/").lower()
        is_test = "/tests/" in f"/{path}" or path.endswith(("test.cs", "tests.cs"))

        def add(number: int, severity: Severity, rule: str, message: str, suggestion: str) -> None:
            changed_line = changed.get(number)
            if changed_line is None or (number, rule) in seen:
                return
            if rule in DEDUP_METHOD_RULES:
                start = self._method_start(lines, number)
                method_key = start if start is not None else number
                if (method_key, rule) in seen_methods:
                    return
                seen_methods.add((method_key, rule))
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

            if re.search(r"\bTask\.(?:Run|Factory\.StartNew)\s*\(", line):
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
                line_body = line.split("{", 1)[-1]
                if re.search(r"\btenant(?:Id)?\b", signature, re.I) and not re.search(r"tenant", line_body, re.I):
                    add(number, Severity.MEDIUM, "cache-consistency",
                        "Tenant identity is omitted from a tenant-scoped cache key.",
                        "Include the tenant and every result-shaping input in the cache key.")

            if "async Task" in signature and "SearchAsync" in signature and "CancellationToken" not in signature:
                anchor = self._signature_line(lines, number)
                if anchor == number:
                    add(number, Severity.MEDIUM, "missing-cancellation-propagation",
                        "A request-facing asynchronous search operation offers no cancellation contract.",
                        "Accept a CancellationToken and propagate it to database and network calls.")

            if re.search(r"\b(?:catch)\b", line) and self._block_is_empty(lines, number):
                add(number, Severity.MEDIUM, "empty-catch-block",
                    "A failure is swallowed in an empty catch block.",
                    "Return an explicit failure result or handle and propagate the exception.")

            if re.search(r"\b(?:MD5|SHA1)\.(?:Create|HashData|ComputeHash)\b|HashAlgorithmName\.(?:MD5|SHA1)\b", line):
                add(number, Severity.HIGH, "weak-cryptography",
                    "A weak hash algorithm (MD5 or SHA-1) is used for a security-sensitive value.",
                    "Use a cryptographically secure token generator or an appropriate modern KDF.")

            if re.search(r"(?:const|readonly|var|string)\s+(?:[A-Za-z0-9_]*)(?:Secret|SigningKey|PrivateKey|ApiKey|Password|ClientSecret)\s*=\s*\"[^\"]{8,}\"", line, re.I):
                if not re.search(r"\$\{|%\w+%|__|YOUR_|CHANGE_ME|EXAMPLE", line, re.I):
                    add(number, Severity.CRITICAL, "hardcoded-secret",
                        "A cryptographic or signing secret is hardcoded in source code.",
                        "Load secret values from a protected configuration provider or environment variable.")

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

            # Outbound HTTP sequential I/O check
            if not is_test:
                http_awaits = re.findall(
                    r"\bawait\s+\w+\.(?:GetAsync|GetStringAsync|PostAsync|PutAsync|DeleteAsync|SendAsync|GetByteArrayAsync|GetStreamAsync)\s*\(",
                    method,
                )
                if len(http_awaits) >= 2 and "Task.WhenAll" not in method:
                    if re.search(r"\bawait\s+\w+\.(?:GetAsync|GetStringAsync|PostAsync|PutAsync|DeleteAsync|SendAsync|GetByteArrayAsync|GetStreamAsync)\s*\(", line):
                        add(
                            number,
                            Severity.MEDIUM,
                            "sequential-io-operations",
                            "Independent outbound HTTP requests are executed sequentially.",
                            "Execute independent asynchronous network operations concurrently with Task.WhenAll.",
                        )

            # Outbound HTTP cancellation propagation check (applies to client/service methods, not tests or controller endpoints)
            if not is_test and not re.search(r"\[From(?:Query|Header|Body|Route)", signature):
                http_call = re.search(r"\b\w+\.(?:GetAsync|GetStringAsync|PostAsync|PutAsync|DeleteAsync|SendAsync|GetByteArrayAsync|GetStreamAsync)\s*\(", line)
                if http_call:
                    call_args = self._extract_call_arguments(lines, number - 1, http_call.end() - 1)
                    start = self._method_start(lines, number)
                    method_key = start if start is not None else number
                    if (method_key, "outbound-cancellation") not in seen_methods:
                        if "CancellationToken" not in signature:
                            seen_methods.add((method_key, "outbound-cancellation"))
                            add(
                                number,
                                Severity.MEDIUM,
                                "missing-cancellation-propagation",
                                "Outbound HTTP operation does not accept or propagate a CancellationToken.",
                                "Accept a CancellationToken in the method signature and forward it to outbound HTTP calls.",
                            )
                        else:
                            param = self._cancellation_parameter(signature)
                            if param and not self._has_cancellation_token_argument(call_args, param):
                                seen_methods.add((method_key, "outbound-cancellation"))
                                add(
                                    number,
                                    Severity.MEDIUM,
                                    "missing-cancellation-propagation",
                                    "Outbound HTTP call ignores the cancellation token supplied in the method signature.",
                                    "Forward the CancellationToken parameter to the outbound HTTP call.",
                                )

            response = re.search(r"\bvar\s+(\w+)\s*=\s*await\s+\w+\.GetAsync\s*\(", line)
            if response and not re.search(r"\busing\b", line) and not self._disposed_later(method, response.group(1)):
                add(number, Severity.MEDIUM, "resource-cleanup",
                    "HttpResponseMessage is not disposed after its content is consumed.",
                    "Use a using declaration for the response and validate its status before reading content.")

            if re.search(r"\.Where\s*\([^)]*\.Name\.Contains\s*\(", line) and "tenantId" in signature and "TenantId" not in line:
                add(number, Severity.HIGH, "tenant-isolation",
                    "A tenant-scoped repository query ignores the supplied tenant identifier.",
                    "Include the tenant predicate in the database query.")

            context_5 = "\n".join(lines[max(0, number - 3):min(len(lines), number + 3)])

            if re.search(r"\.(?:FromSqlRaw|ExecuteSqlRawAsync|ExecuteSqlRaw)\s*\([^;]*\+", context_5) or \
               re.search(r"\$\"[^\"]*(?:SELECT|INSERT|UPDATE|DELETE)[^\"]*\{", context_5, re.I) or \
               re.search(r"\"[^\"]*(?:SELECT|INSERT|UPDATE|DELETE)[^\"]*\"\s*\+", context_5, re.I) or \
               (re.search(r"\b(?:ExecuteAsync|QueryAsync|Execute|Query)\s*\(\s*(?:\$\"[^\"]*|(?:\"[^\"]*\")?\s*\+)", context_5) and re.search(r"SELECT|INSERT|UPDATE|DELETE", context_5, re.I)):
                if not re.search(r"FromSqlInterpolated|FromSql\b|AddWithValue|@\w+", line):
                    if re.search(r"\b(?:SELECT|INSERT|UPDATE|DELETE)\b|FromSqlRaw|ExecuteSqlRaw", line, re.I) or re.search(r"\bvar\s+sql\s*=\s*\$\"[^\"]*(?:SELECT|INSERT|UPDATE|DELETE)", line, re.I):
                        add(number, Severity.HIGH, "sql-injection",
                            "Raw SQL is constructed by concatenating or interpolating runtime data.",
                            "Use interpolated/parameterized queries and bind external values.")

            if re.search(r"=>\s*db\.\w+\.ToListAsync\s*\(", line) and self._read_method(signature):
                if ".AsNoTracking(" not in line:
                    add(number, Severity.LOW, "ef-tracking-read",
                        "A read-only EF Core query tracks every returned entity.",
                        "Use AsNoTracking for read-only query results.")

            if re.search(r"\bforeach\s*\(", line) and self._loop_contains_ef_query(lines, number):
                add(number, Severity.MEDIUM, "n-plus-one-query",
                    "A database query is executed once for every item in the loop.",
                    "Project or aggregate the related values in one database query.")

            nullable_assignment = re.search(r"var\s+(\w+)\s*=\s*(?:await\s+)?[^;]*\b(?:FirstOrDefaultAsync|FirstOrDefault|SingleOrDefaultAsync|SingleOrDefault|LastOrDefaultAsync|LastOrDefault|FindAsync|Find)\b", method)
            if nullable_assignment:
                var_name = nullable_assignment.group(1)
                if re.search(rf"\b{re.escape(var_name)}\.[A-Za-z_]", line):
                    if not re.search(rf"\b{re.escape(var_name)}\s*(?:==|!=|is)\s*null|\?\.", method):
                        add(number, Severity.MEDIUM, "null-safety",
                            f"The nullable result '{var_name}' is dereferenced without a null check.",
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

            if ("SetIsOriginAllowed(_ => true)" in line or "AllowAnyOrigin()" in line or "SetIsOriginAllowed" in context_5) and ("AllowCredentials()" in line or "AllowCredentials" in context_5):
                if "SetIsOriginAllowed" in line or "AllowAnyOrigin" in line or ("AllowCredentials" in line and "SetIsOriginAllowed" not in context_5 and "AllowAnyOrigin" not in context_5):
                    add(number, Severity.HIGH, "cors-misconfiguration",
                        "Credentialed CORS accepts every requesting origin.",
                        "Allow-list trusted origins when credentials are enabled.")

            if re.search(r"Response\.Cookies\.Append\s*\(", line) or re.search(r"Response\.Cookies\.Append\s*\(", context_5):
                if not (re.search(r"HttpOnly\s*=\s*true", method, re.I) and re.search(r"Secure\s*=\s*true", method, re.I)):
                    if "CookieOptions" not in line or not (re.search(r"HttpOnly\s*=\s*true", line, re.I) and re.search(r"Secure\s*=\s*true", line, re.I)):
                        if "Append" in line:
                            add(number, Severity.HIGH, "insecure-cookie",
                                "A cookie is appended without HttpOnly or Secure protection.",
                                "Set HttpOnly = true, Secure = true, and appropriate SameSite policy in CookieOptions.")

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

            if re.search(r"(?:Problem|BadRequest|StatusCode|Json)\s*\(", context_5):
                if re.search(r"\b(?:ex|error|exception)\.(?:Message|ToString|StackTrace)\b", context_5):
                    if re.search(r"Problem|BadRequest|StatusCode|Json", line) or re.search(r"\b(?:ex|error|exception)\.(?:Message|ToString)", line):
                        add(number, Severity.MEDIUM, "exception-detail-exposure",
                            "An internal exception message is returned to the HTTP client.",
                            "Return a stable public error and log internal details server-side.")

            if re.search(r"(?:PhysicalFile|File)\s*\([^;]*Path\.Combine\s*\([^;]*(?:name|fileName)", context_5, re.I) or \
               re.search(r"Path\.Combine\s*\([^;]*(?:name|fileName|file\.FileName)", context_5, re.I):
                if not self._has_path_containment(method):
                    if re.search(r"Path\.Combine", line) or ("Path.Combine" not in method and re.search(r"PhysicalFile|File\.Create", line)):
                        add(number, Severity.HIGH, "path-traversal",
                            "Caller-controlled file input is combined with a server directory without containment validation.",
                            "Resolve the canonical path and verify it remains under the allowed root.")

            if re.search(r"File\.Create\s*\([^;]*(?:\.FileName|fileName)", context_5, re.I) and not self._has_path_containment(method):
                if re.search(r"Path\.Combine", line) or ("Path.Combine" not in method and re.search(r"File\.Create", line)):
                    add(number, Severity.HIGH, "path-traversal",
                        "The client-supplied upload filename controls the server filesystem path.",
                        "Generate a server-owned name and enforce canonical destination containment.")

            if "IFormFile" in signature and (re.search(r"CopyToAsync\s*\(", method) or re.search(r"File\.Create", method)):
                if not re.search(r"ContentType|Length|extension|GetExtension|allowed", method, re.I):
                    if re.search(r"CopyToAsync", line) or ("CopyToAsync" not in method and re.search(r"CopyToAsync|File\.Create|IFormFile", line)):
                        add(number, Severity.HIGH, "unrestricted-file-upload",
                            "The upload is stored without size, type, or extension restrictions.",
                            "Enforce size limits, validate content and extension allow-lists, and store outside executable paths.")

            if re.search(r"\b(?:GetStringAsync|GetAsync|SendAsync|DownloadString|DownloadData)\s*\(", context_5, re.I) or \
               re.search(r"httpClient\.(?:GetStringAsync|GetAsync|SendAsync)", context_5, re.I):
                if not re.search(r"\bUri\s+\w+", signature):
                    if re.search(r"\b(url|target|destination|address|endpoint)\b", context_5, re.I) or \
                       re.search(r"\bstring\s+(url|target|uri|destination|address|endpoint)\b", signature, re.I):
                        if not re.search(r"https?://|Url\.IsLocalUrl|AllowList", method, re.I):
                            if re.search(r"GetStringAsync|GetAsync|SendAsync|DownloadString|DownloadAsync", line, re.I):
                                add(number, Severity.HIGH, "ssrf",
                                    "A request-controlled URL reaches an outbound HTTP request.",
                                    "Resolve destinations from an allow-list and block private, loopback, and metadata-network addresses.")

            if re.search(r"\b(?:Redirect|RedirectPermanent|RedirectPreserveMethod)\s*\(", line, re.I) or \
               re.search(r"Response\.Redirect\s*\(", line, re.I):
                if not re.search(r"Url\.IsLocalUrl|LocalRedirect", method):
                    if re.search(r"\b(returnUrl|redirectUrl|next|url|destination|target)\b", context_5, re.I) or \
                       re.search(r"\bstring\s+(returnUrl|redirectUrl|next|url|destination|target)\b", signature, re.I):
                        add(number, Severity.MEDIUM, "open-redirect",
                            "A request-controlled destination is used directly for an HTTP redirect.",
                            "Allow only local URLs or map stable identifiers to server-owned destinations.")

            if re.search(r"Process\.Start\s*\(", context_5) or re.search(r"new\s+ProcessStartInfo\s*\(", context_5):
                if re.search(r"cmd\.exe|powershell|bash|/c\s+|\$\"[^\"]*\{|\+\s*\w+", context_5, re.I):
                    if re.search(r"\b(host|cmd|args|command|input|url)\b", method, re.I) or \
                       re.search(r"\bstring\s+(host|cmd|args|command|input|url)\b", signature, re.I):
                        if not re.search(r"ArgumentList", method):
                            if re.search(r"Process\.Start|new\s+ProcessStartInfo|ProcessStartInfo", line):
                                add(number, Severity.HIGH, "command-injection",
                                    "Request input is concatenated into an operating-system command.",
                                    "Avoid shell execution or use a fixed executable with validated ArgumentList entries.")
                            elif not re.search(r"Process\.Start|ProcessStartInfo", method) and not line.strip().startswith("[") and re.search(r"cmd\.exe|powershell|bash|/c\s+", line, re.I):
                                add(number, Severity.HIGH, "command-injection",
                                    "Request input is concatenated into an operating-system command.",
                                    "Avoid shell execution or use a fixed executable with validated ArgumentList entries.")

            if re.search(r"\b(?:IsAdministrator|IsAdmin|Role|Roles|Permissions|TenantId|OwnerId|AccountStatus|IsSuperuser)\s*=\s*(?:request|input)\.(?:IsAdministrator|IsAdmin|Role|Roles|Permissions|TenantId|OwnerId|AccountStatus|IsSuperuser)\b", line, re.I) or \
               re.search(r"\b(?:\w+\.)?(?:IsAdministrator|IsAdmin|Role|Roles|Permissions|TenantId|OwnerId|AccountStatus|IsSuperuser)\s*=\s*(?:request|input)\.", line, re.I):
                add(number, Severity.HIGH, "mass-assignment",
                    "Client-controlled request properties are copied directly into privileged domain fields.",
                    "Use explicit DTO mapping and enforce authorization checks before modifying privileged domain fields.")

            if "[FromBody]" in signature and re.search(r"\b(?:UserAccount|UserRecord|\w*Entity)\s+\w+", signature):
                anchor = self._signature_line(lines, number)
                if anchor == number:
                    add(number, Severity.HIGH, "mass-assignment",
                        "A domain or persistence model is bound directly from the request body.",
                        "Bind a dedicated request DTO and explicitly map only allowed fields.")

            if re.search(r"Log(?:Trace|Debug|Information|Warning|Error)\s*\([^;]*password", line, re.I):
                add(number, Severity.HIGH, "sensitive-data-logging",
                    "A password value is written to application logs.",
                    "Never log credentials or secret values.")

            if re.search(r"\[Http(?:Put|Post|Delete|Patch)\s*\([^)]*(?:admin|reindex|refresh|manage|update|delete)", line, re.I) or \
               (re.search(r"\[Http(?:Put|Post|Delete|Patch)", line) and re.search(r"admin|administrator|manage", signature, re.I)):
                controller = "\n".join(lines)
                if "[Authorize" not in controller and "[AllowAnonymous]" not in line and "[AllowAnonymous]" not in context_5:
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
            stripped = line.strip()
            if stripped.startswith(("throw ", "return ", "new ", "using ", "var ", "if ", "else ", "for ", "foreach ", "while ", "catch ", "//", "/*", "*")):
                continue
            if not re.search(r"^\s*(?:\[[^\]]+\]\s*)*(?:public|private|protected|internal|static|async|virtual|override|abstract|sealed|partial)\b", line):
                continue
            if re.search(r"\b(?:public|private|protected|internal)\b", line) and "(" in line:
                if not re.search(r"\b(?:class|record|struct|interface|delegate|enum)\b", line):
                    return index
        return None

    @staticmethod
    def _signature_line(lines: list[str], number: int) -> int:
        start = DotNetStaticAnalyzer._method_start(lines, number)
        return start + 1 if start is not None else number

    @staticmethod
    def _cancellation_parameter(signature: str) -> str | None:
        match = re.search(r"CancellationToken(?:\s*\?)?\s+(\w+)", signature)
        return match.group(1) if match else None

    @staticmethod
    def _extract_call_arguments(lines: list[str], line_idx: int, open_paren_idx: int) -> str:
        """Extract full argument text starting after open_paren_idx using balanced delimiter parsing."""
        cur_line = line_idx
        cur_char = open_paren_idx + 1
        depth = 1
        chars: list[str] = []

        in_string = False
        in_verbatim = False
        in_char = False

        while cur_line < len(lines):
            line = lines[cur_line]
            while cur_char < len(line):
                ch = line[cur_char]

                if in_string:
                    chars.append(ch)
                    if in_verbatim:
                        if ch == '"':
                            if cur_char + 1 < len(line) and line[cur_char + 1] == '"':
                                chars.append('"')
                                cur_char += 1
                            else:
                                in_string = False
                                in_verbatim = False
                    else:
                        if ch == '\\':
                            if cur_char + 1 < len(line):
                                chars.append(line[cur_char + 1])
                                cur_char += 1
                        elif ch == '"':
                            in_string = False
                elif in_char:
                    chars.append(ch)
                    if ch == '\\':
                        if cur_char + 1 < len(line):
                            chars.append(line[cur_char + 1])
                            cur_char += 1
                    elif ch == "'":
                        in_char = False
                else:
                    if ch == '@' and cur_char + 1 < len(line) and line[cur_char + 1] == '"':
                        in_string = True
                        in_verbatim = True
                        chars.append('@"')
                        cur_char += 1
                    elif ch == '$' and cur_char + 2 < len(line) and line[cur_char + 1:cur_char + 3] in ('@"', '"{'):
                        if line[cur_char + 1] == '@':
                            in_string = True
                            in_verbatim = True
                            chars.append('$@"')
                            cur_char += 2
                        else:
                            in_string = True
                            chars.append('$"')
                            cur_char += 1
                    elif ch == '"':
                        in_string = True
                        chars.append(ch)
                    elif ch == "'":
                        in_char = True
                        chars.append(ch)
                    elif ch in '([{':
                        depth += 1
                        chars.append(ch)
                    elif ch in ')]}':
                        depth -= 1
                        if depth == 0:
                            return "".join(chars)
                        chars.append(ch)
                    else:
                        chars.append(ch)
                cur_char += 1

            chars.append("\n")
            cur_line += 1
            cur_char = 0

        return "".join(chars)

    @staticmethod
    def _has_cancellation_token_argument(args_str: str, param: str | None) -> bool:
        """Check whether the call arguments pass the expected cancellation token."""
        if not args_str.strip():
            return False
        if param and re.search(rf"\b{re.escape(param)}\b", args_str):
            return True
        return False

    @staticmethod
    def _has_task_failure_observer(method: str) -> bool:
        return any(token in method for token in ("await ", ".ContinueWith(", "Observe", "return Task"))

    @staticmethod
    def _block_is_empty(lines: list[str], number: int) -> bool:
        block = "\n".join(lines[number - 1:min(len(lines), number + 6)])
        match = re.search(r"catch\s*(?:\([^)]*\))?\s*\{([^}]*)\}", block, re.DOTALL)
        if not match:
            return False
        body = match.group(1).strip()
        return not bool(re.search(r"\S", body))

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
            add(number, Severity.LOW, "insufficient-test-assertion",
                "The pagination test checks metadata without verifying returned records.",
                "Assert item boundaries and page contents.")
        if re.search(r"Assert\.Equal\s*\(\s*0\s*,[^;]*Parse", line):
            add(number, Severity.LOW, "insufficient-test-assertion",
                "The test accepts a valid zero value when parsing invalid input.",
                "Assert the explicit failure contract or expected parsing exception.")
        if "Assert.IsType<OkObjectResult>" in line and ".Update(" in line:
            add(number, Severity.LOW, "insufficient-test-assertion",
                "The update test checks only the action-result type.",
                "Verify that protected fields cannot be changed and that persistence receives only allowed values.")
        if "Assert.NotNull(" in line and ".Clear(" in line:
            add(number, Severity.LOW, "insufficient-test-assertion",
                "The administrative endpoint test does not verify its authorization policy.",
                "Assert unauthorized and forbidden outcomes for unauthenticated and unprivileged callers.")
        # High-confidence C# test capability for xUnit, NUnit, MSTest, FluentAssertions.
        # Existence checks are intentionally not treated as meaningful behavioural
        # verification when an API call is the subject under test.
        is_existence_assertion = cls._is_existence_assertion(line)
        if is_existence_assertion:
            executes_api = bool(re.search(
                r"\b(?:client|controller|[A-Za-z_]\w*(?:client|controller))\.\w+\s*\(",
                method,
                re.IGNORECASE,
            ))
            meaningful_verifications = cls._has_meaningful_test_verification(method)
            sig = cls._method_signature(lines, number)
            is_smoke_test = bool(re.search(
                r"\b(?:smoke|constructor|createinstance|factory|instantiate)\b",
                sig,
                re.IGNORECASE,
            ))
            if executes_api and not meaningful_verifications and not is_smoke_test:
                add(
                    number,
                    Severity.LOW,
                    "insufficient-test-assertion",
                    "The test executes an HTTP/API operation but only asserts object existence (NotNull), failing to verify response status, payload content, or security policy.",
                    "Assert specific response status codes, returned body fields, or security outcome behavior.",
                )

    @staticmethod
    def _is_existence_assertion(text: str) -> bool:
        return bool(re.search(
            r"(?:\bAssert\.(?:NotNull|IsNotNull)\s*\(|"
            r"\bAssert\.That\s*\([^;]*,\s*Is\.Not\.Null\b|"
            r"\.Should\(\)\.NotBeNull\s*\(|"
            r"\bAssert\.(?:True|IsTrue)\s*\([^;]*(?:!=\s*null|is\s+not\s+null))",
            text,
            re.IGNORECASE | re.DOTALL,
        ))

    @classmethod
    def _has_meaningful_test_verification(cls, method: str) -> bool:
        verification = re.compile(
            r"(?:\bAssert\.(?:Equal|NotEqual|AreEqual|AreNotEqual|Same|NotSame|"
            r"Equivalent|Contains|DoesNotContain|True|False|IsTrue|IsFalse|"
            r"Empty|NotEmpty|Single|Collection|All|Throws|ThrowsAsync|"
            r"ThrowsException|ThrowsExceptionAsync|IsType|IsAssignableFrom|"
            r"Matches|InRange)\b|"
            r"\bAssert\.That\s*\([^;]*,\s*(?:Is|Does|Has)\.|"
            r"\.Should\(\)\.(?:Be|NotBe|BeEquivalentTo|Contain|NotContain|"
            r"Match|Throw|NotThrow|HaveCount|BeEmpty|NotBeEmpty)\w*\s*\(|"
            r"\bEnsureSuccessStatusCode\s*\(|"
            r"\b[A-Za-z_]\w*\.Verify\w*\s*\()",
            re.IGNORECASE | re.DOTALL,
        )
        statements = re.findall(r"[^;]+;", method, re.DOTALL)
        for statement in statements:
            if cls._is_existence_assertion(statement):
                continue
            if verification.search(statement):
                return True
        return False
