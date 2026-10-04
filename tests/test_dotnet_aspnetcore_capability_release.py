from dataclasses import replace
from textwrap import dedent

from pr_reviewer.context.file_context import FileContextResolver
from pr_reviewer.review.dotnet_static_analyzer import DotNetStaticAnalyzer
from pr_reviewer.review.framework_facts.dotnet import DotNetRuntimeFactValidator
from pr_reviewer.review.models import ChangedFile, ChangedLine, Finding, Severity
from pr_reviewer.review.review_router import ReviewRouter
from pr_reviewer.review.semantic_routing import AdaptiveSemanticRouter, ReviewDepth


def source_file(source: str, path: str = "src/App/Service.cs", changed_numbers=None) -> ChangedFile:
    content = dedent(source).strip()
    lines = content.splitlines()
    numbers = set(changed_numbers or range(1, len(lines) + 1))
    return ChangedFile(
        file_path=path,
        status="modified",
        full_content=content,
        changed_lines=[ChangedLine(path, number, line, number) for number, line in enumerate(lines, 1) if number in numbers],
    )


def rules(source: str, path: str = "src/App/Service.cs") -> list[str]:
    return [finding.rule_id for finding in DotNetStaticAnalyzer().analyze(source_file(source, path))]


def test_csharp_async_pagination_cache_and_error_contracts():
    source = """
        class Service(IRepo repository) {
          public Product Get(long id) => repository.FindAsync(id).Result!;
          public async void Refresh() => await Task.Delay(1);
          public void Audit() => Task.Run(() => WorkAsync());
          public Task<Product?> Find(long id, CancellationToken cancellationToken) =>
            repository.FindAsync(id);
          public Page Page(List<Product> rows, int page, int pageSize) {
            var items = rows.Skip(page * pageSize).Take(pageSize).ToList();
            return new Page(items);
          }
          public async Task<List<Product>> SearchAsync(string tenantId, string query) {
            var key = query.ToLowerInvariant();
            return await repository.SearchAsync(tenantId, query);
          }
          public decimal Parse(string raw) {
            try { return decimal.Parse(raw); }
            catch (FormatException) { }
            return 0;
          }
        }
    """
    assert set(rules(source)) == {
        "sync-over-async", "null-forgiving-nullable", "async-void",
        "unowned-background-task", "missing-cancellation-propagation",
        "pagination-offset", "cache-consistency", "empty-catch-block",
    }
    assert rules(source).count("missing-cancellation-propagation") == 3


def test_dotnet_cryptography_capabilities():
    source = """
        class Security {
          public string ResetToken(string value) { using var md5 = MD5.Create(); return value; }
          public string VerificationCode() => Random.Shared.Next().ToString();
          public void Encrypt(Aes aes) { aes.Mode = CipherMode.ECB; }
        }
    """
    assert set(rules(source)) == {"weak-cryptography", "predictable-random-token", "weak-encryption"}


def test_dotnet_resource_capabilities_and_using_controls():
    unsafe = """
        class Resource {
          public string Read(string path) { var reader = new StreamReader(path); return reader.ReadToEnd(); }
          public async Task<string> Fetch(string url) { var client = new HttpClient(); var response = await client.GetAsync(url); return await response.Content.ReadAsStringAsync(); }
        }
    """
    assert rules(unsafe).count("resource-cleanup") == 2
    assert "httpclient-lifetime" in rules(unsafe)
    safe = """
        class Resource(HttpClient client) {
          public async Task<string> Read(string path) { using var reader = new StreamReader(path); return await reader.ReadToEndAsync(); }
          public async Task<string> Fetch(Uri uri, CancellationToken token) { using var response = await client.GetAsync(uri, token); return await response.Content.ReadAsStringAsync(token); }
        }
    """
    assert rules(safe) == []


def test_ef_core_query_state_and_concurrency_capabilities():
    source = """
        class Repo(Db db) {
          public Task<List<Product>> SearchAsync(string tenantId, string query, CancellationToken token) => db.Products.Where(x => x.Name.Contains(query)).ToListAsync(token);
          public Task<List<Product>> Raw(string name) => db.Products.FromSqlRaw("SELECT * FROM P WHERE Name='" + name + "'").ToListAsync();
          public Task<int> Delete(string tenant) => db.Database.ExecuteSqlRawAsync("DELETE FROM P WHERE Tenant='" + tenant + "'");
          public Task<List<Product>> ReadAllAsync() => db.Products.ToListAsync();
          public async Task Counts() { var products = await db.Products.ToListAsync(); foreach (var product in products) await db.Reviews.CountAsync(x => x.ProductId == product.Id); }
          public async Task<string> Required() { var product = await db.Products.FirstOrDefaultAsync(); return product.Name; }
          public async Task Add(Product product) { await db.Products.AddAsync(product); }
          public Task<List<Product>> Page(int page, int size) => db.Products.Skip(page * size).Take(size).ToListAsync();
          public async Task Parallel() { await Task.WhenAll(db.Products.CountAsync(), db.Users.CountAsync()); }
          public async Task Save(Product product, CancellationToken cancellationToken) { db.Products.Update(product); await db.SaveChangesAsync(); }
        }
    """
    found = rules(source, "src/Infrastructure/ProductRepository.cs")
    assert set(found) == {
        "tenant-isolation", "sql-injection", "ef-tracking-read", "n-plus-one-query",
        "null-safety", "missing-save-changes", "pagination-offset",
        "unstable-pagination", "dbcontext-concurrency", "missing-cancellation-propagation",
    }
    assert found.count("sql-injection") == 2


def test_aspnet_hosting_and_background_service_capabilities():
    program = """
        builder.Services.AddSingleton<MutableTenantState>();
        policy.SetIsOriginAllowed(_ => true).AllowAnyHeader().AllowCredentials();
        app.UseDeveloperExceptionPage();
    """
    assert set(rules(program, "src/Api/Program.cs")) == {
        "singleton-mutable-state", "cors-misconfiguration", "developer-exception-page"
    }
    worker = """
        public sealed class Worker(AppDbContext db) : BackgroundService {
          protected override async Task ExecuteAsync(CancellationToken stoppingToken) {
            while (true) {
              await db.Products.CountAsync();
              await Task.Delay(1000);
            }
          }
        }
    """
    found = rules(worker, "src/Api/Worker.cs")
    assert set(found) == {"dependency-lifetime", "background-cancellation", "missing-cancellation-propagation"}
    assert found.count("missing-cancellation-propagation") == 2


def test_aspnet_controller_security_capabilities():
    source = """
        class Controller(HttpClient client) {
          public IActionResult Admin([FromHeader(Name = "X-Role")] string role) { if (string.IsNullOrWhiteSpace(role)) return Unauthorized(); try { Work(); } catch (Exception error) { return Problem(error.Message); } }
          public IActionResult Download([FromQuery] string name) => PhysicalFile(Path.Combine(root, name), "x");
          public async Task<IActionResult> Upload(IFormFile file) { await using var output = File.Create(Path.Combine(root, file.FileName)); await file.CopyToAsync(output); return Ok(); }
          public Task<string> Proxy([FromQuery] string url) => client.GetStringAsync(url);
          public IActionResult Go([FromQuery] string next) => Redirect(next);
          public IActionResult Ping([FromQuery] string host) { Process.Start("cmd", "/c ping " + host); return Ok(); }
          public IActionResult Update(long id, [FromBody] UserAccount account) { logger.LogInformation("password {Password}", account.Password); return Ok(account); }
          [HttpPost("reindex")]
          public IActionResult Reindex() => Accepted();
        }
    """
    assert set(rules(source, "src/Api/Controller.cs")) == {
        "authorization", "exception-detail-exposure", "path-traversal",
        "unrestricted-file-upload", "ssrf", "open-redirect", "command-injection",
        "mass-assignment", "sensitive-data-logging", "missing-endpoint-authorization",
    }
    assert rules(source, "src/Api/Controller.cs").count("path-traversal") == 2


def test_appsettings_security_and_logging_capabilities():
    content = """
        {
          "Default": "Data Source=x;Password=production-password",
          "JwtSecret": "production-signing-secret",
          "Default": "Debug"
        }
    """
    assert rules(content, "src/Api/appsettings.json") == ["hardcoded-secret", "hardcoded-secret", "debug-logging"]


def test_xunit_weak_assertion_capabilities():
    source = """
        class Tests {
          public void PageTest() { var result = service.Page(rows, 1, 20); Assert.Equal(1, result.Page); }
          public void ParseTest() { Assert.Equal(0, service.ParsePrice("invalid")); }
          public void UpdateTest() { Assert.IsType<OkObjectResult>(controller.Update(1, account)); }
          public void AdminTest() { Assert.NotNull(controller.Clear("anything")); }
          public void RedirectTest() { var result = controller.Continue("https://attacker.example"); Assert.NotNull(result); }
        }
    """
    assert rules(source, "tests/AppTests.cs") == ["insufficient-test-assertion"] * 5


def test_http_client_field_with_existence_only_assertion_is_reported():
    source = """
        public sealed class UnsafeApiTests {
          private readonly HttpClient _client;
          [Fact]
          public async Task ExternalRedirect_ReturnsAResponse() {
            using var response = await _client.GetAsync(
              "/api/unsafe/users/redirect?returnUrl=https%3A%2F%2Fevil.example");
            Assert.NotNull(response);
          }
        }
    """
    assert rules(source, "tests/UnsafeApiTests.cs") == ["insufficient-test-assertion"]


def test_reading_response_properties_does_not_count_as_a_test_verification():
    source = """
        public sealed class Tests {
          public async Task ReadOnly() {
            using var response = await apiClient.GetAsync("/users");
            var body = await response.Content.ReadAsStringAsync();
            var status = response.StatusCode;
            Assert.NotNull(response);
          }
        }
    """
    assert rules(source, "tests/ApiTests.cs") == ["insufficient-test-assertion"]


def test_nunit_mstest_and_fluent_existence_only_assertions_are_reported():
    source = """
        public sealed class Tests {
          public async Task NUnitTest() { using var response = await _client.GetAsync("/nunit"); Assert.That(response, Is.Not.Null); }
          public async Task MsTest() { using var response = await httpClient.GetAsync("/mstest"); Assert.IsNotNull(response); }
          public async Task MsTrueTest() { using var response = await testClient.GetAsync("/true"); Assert.IsTrue(response is not null); }
          public async Task FluentTest() { using var response = await apiClient.GetAsync("/fluent"); response.Should().NotBeNull(); }
        }
    """
    assert rules(source, "tests/FrameworkTests.cs") == ["insufficient-test-assertion"] * 4


def test_meaningful_http_assertions_and_smoke_construction_remain_clean():
    source = """
        public sealed class Tests {
          public async Task StatusAndBody() {
            using var response = await _client.GetAsync("/users");
            Assert.Equal(HttpStatusCode.OK, response.StatusCode);
            var payload = await response.Content.ReadFromJsonAsync<User>();
            Assert.NotNull(payload);
            Assert.Equal("active", payload.Status);
          }
          public async Task FluentStatus() {
            using var response = await apiClient.GetAsync("/users");
            response.StatusCode.Should().Be(HttpStatusCode.OK);
            response.Should().NotBeNull();
          }
          public void ConstructorSmokeTest() {
            var controller = new UsersController();
            Assert.NotNull(controller);
          }
        }
    """
    assert rules(source, "tests/SafeApiTests.cs") == []


def test_unchanged_existence_assertion_cannot_create_a_pr_finding():
    source = """
        public sealed class Tests {
          public async Task ApiTest() {
            using var response = await _client.GetAsync("/users");
            Assert.NotNull(response);
          }
        }
    """
    changed_file = source_file(source, "tests/ApiTests.cs", changed_numbers={3})
    assert DotNetStaticAnalyzer().analyze(changed_file) == []


def test_only_changed_lines_can_create_dotnet_findings():
    changed_file = source_file(
        "class X {\n public string Token() { using var md5 = MD5.Create(); return \"x\"; }\n}",
        changed_numbers={1},
    )
    assert DotNetStaticAnalyzer().analyze(changed_file) == []


def test_dotnet_safe_controls_do_not_create_findings():
    source = """
        class Safe(HttpClient client) {
          public string Token() => Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
          public async Task<string> Fetch(Uri uri, CancellationToken token) { using var response = await client.GetAsync(uri, token); response.EnsureSuccessStatusCode(); return await response.Content.ReadAsStringAsync(token); }
          public async Task Query(SqliteConnection connection, string name) { await using var command = connection.CreateCommand(); command.CommandText = "SELECT * FROM P WHERE Name=$name"; command.Parameters.AddWithValue("$name", name); await command.ExecuteScalarAsync(); }
          public string Path(string root, string name) { var candidate = System.IO.Path.GetFullPath(System.IO.Path.Combine(root, name)); if (!candidate.StartsWith(System.IO.Path.GetFullPath(root))) throw new Exception(); return candidate; }
        }
    """
    assert rules(source) == []


def test_dotnet_workspace_selectors_and_global_usings_are_context_only():
    router = ReviewRouter()
    assert not router.should_review_with_llm(source_file("Microsoft Visual Studio Solution File", "App.sln"))
    assert not router.should_review_with_llm(source_file('{"sdk":{"version":"8.0.100"}}', "global.json"))
    assert not router.should_review_with_llm(source_file("global using Xunit;", "tests/Usings.cs"))


def test_passive_csharp_declarations_are_value_gated_but_behavior_is_retained():
    passive = source_file("public sealed record Product(long Id, string Name);", "src/Product.cs")
    interface = source_file("public interface IRepo { Task SaveAsync(); }", "src/IRepo.cs")
    behavior = source_file("public class Service { public int Read() { return 1; } }", "src/Service.cs")
    router = AdaptiveSemanticRouter()
    assert not router.decide(passive, set(), ReviewDepth.STANDARD).eligible
    assert not router.decide(interface, set(), ReviewDepth.STANDARD).eligible
    assert router.decide(behavior, set(), ReviewDepth.STANDARD).eligible


def test_dotnet_fact_validator_rejects_constructed_local_null_claim():
    changed = source_file("""
        class Tests {
          public void Test() {
            var service = new Service();
            Assert.Equal(0, service.Parse("x"));
          }
        }
    """)
    finding = Finding(changed.file_path, 4, Severity.MEDIUM, "logic-error", "The service might be null.")
    assert DotNetRuntimeFactValidator().validate(finding, changed)


def test_dotnet_fact_validator_rejects_tolist_collection_null_claim():
    changed = source_file("""
        class Repo {
          public async Task Work() {
            var products = await db.Products.ToListAsync();
            foreach (var product in products) { }
          }
        }
    """)
    finding = Finding(changed.file_path, 4, Severity.MEDIUM, "logic-error", "`products` may be null.")
    assert DotNetRuntimeFactValidator().validate(finding, changed)


def test_dotnet_fact_validator_rejects_cross_method_evidence():
    changed = source_file("""
        class Service {
          public void StartAudit() { Task.Run(Work); }
          public Task FindAsync() => Task.CompletedTask;
        }
    """)
    finding = Finding(changed.file_path, 3, Severity.MEDIUM, "logic-error", "The StartAudit method loses task ownership.")
    assert DotNetRuntimeFactValidator().validate(finding, changed)


def test_aspnet_file_context_is_backend():
    assert FileContextResolver._project_type("aspnet-core") == "backend"


def test_csharp_rule_deduplication_in_single_method():
    source = """
        class TestController : ControllerBase {
            [HttpPost("upload")]
            public async Task<IActionResult> Upload(IFormFile file) {
                var path = Path.Combine(root, file.FileName);
                await using var stream = File.Create(path);
                await file.CopyToAsync(stream);
                return Ok();
            }

            [HttpPost("cmd")]
            public IActionResult Exec([FromQuery] string host) {
                var cmd = $"ping {host}";
                Process.Start("cmd.exe", $"/c {cmd}");
                return Ok();
            }

            public void ConfigureCors(IApplicationBuilder app) {
                app.UseCors(policy => {
                    policy.SetIsOriginAllowed(_ => true)
                          .AllowAnyHeader()
                          .AllowCredentials();
                });
            }
        }
    """
    analyzer = DotNetStaticAnalyzer()
    file = source_file(source, "src/Api/TestController.cs")
    findings = analyzer.analyze(file)

    cors_findings = [f for f in findings if f.rule_id == "cors-misconfiguration"]
    upload_findings = [f for f in findings if f.rule_id == "unrestricted-file-upload"]
    path_findings = [f for f in findings if f.rule_id == "path-traversal"]
    cmd_findings = [f for f in findings if f.rule_id == "command-injection"]

    assert len(cors_findings) == 1
    assert len(upload_findings) == 1
    assert len(path_findings) == 1
    assert len(cmd_findings) == 1

    lines = file.full_content.splitlines()
    assert "SetIsOriginAllowed" in lines[cors_findings[0].line_number - 1]
    assert "CopyToAsync" in lines[upload_findings[0].line_number - 1]
    assert "Path.Combine" in lines[path_findings[0].line_number - 1]
    assert "Process.Start" in lines[cmd_findings[0].line_number - 1]


def test_csharp_routing_gates_covered_methods():
    source = """
        class Controller {
            public IActionResult Ping([FromQuery] string host) {
                Process.Start("cmd.exe", $"/c {host}");
                return Ok();
            }
        }
    """
    file = source_file(source, "src/Api/Controller.cs")
    analyzer = DotNetStaticAnalyzer()
    static_findings = analyzer.analyze(file)
    covered_lines = {f.line_number for f in static_findings}

    router = AdaptiveSemanticRouter()
    decision = router.decide(file, covered_lines, ReviewDepth.STANDARD)
    assert not decision.eligible
    assert "covered by authoritative static findings" in decision.reason


def test_command_injection_anchors_strictly_to_process_start():
    source = """
        class Controller : ControllerBase {
            [HttpGet("ping")]
            public IActionResult Ping([FromQuery] string host) {
                var cmd = $"ping {host}";
                Process.Start("cmd.exe", $"/c {cmd}");
                return Ok();
            }
        }
    """
    file = source_file(source, "src/Api/Controller.cs")
    analyzer = DotNetStaticAnalyzer()
    findings = analyzer.analyze(file)
    cmd_findings = [f for f in findings if f.rule_id == "command-injection"]
    assert len(cmd_findings) == 1
    lines = file.full_content.splitlines()
    matched_line = lines[cmd_findings[0].line_number - 1]
    assert "[HttpGet(" not in matched_line
    assert "Process.Start" in matched_line


def test_weak_assertion_finding_classified_as_test_quality():
    source = """
        class ControllerTest {
            public void TestUpdate() {
                Assert.IsType<OkObjectResult>(controller.Update(1, account));
            }
        }
    """
    file = source_file(source, "tests/ControllerTest.cs")
    analyzer = DotNetStaticAnalyzer()
    findings = analyzer.analyze(file)
    assert len(findings) == 1
    assert findings[0].rule_id == "insufficient-test-assertion"
    assert findings[0].severity == Severity.LOW

    from pr_reviewer.review.normalizer import FindingNormalizer
    normalized = FindingNormalizer().normalize(findings[0])
    assert normalized.category == "test-quality"
    assert normalized.severity == Severity.LOW


def test_isqlexecutor_and_safe_controllers_gated_by_router():
    isql = source_file("""
        public interface ISqlExecutor {
            /// <returns>The number of affected rows</returns>
            Task<int> ExecuteAsync(string sql, CancellationToken cancellationToken);
        }
    """, "src/Data/ISqlExecutor.cs")

    safe_controller = source_file("""
        public class SafeUserController : ControllerBase {
            public IActionResult GetUser(int id) => Ok(id);
        }
    """, "src/Controllers/SafeUserController.cs")

    clean_config = source_file("""
        {
          "Logging": { "LogLevel": { "Default": "Information" } }
        }
    """, "src/appsettings.json")

    router = AdaptiveSemanticRouter()
    assert not router.decide(isql, set(), ReviewDepth.STANDARD).eligible
    assert not router.decide(safe_controller, set(), ReviewDepth.STANDARD).eligible
    assert not router.decide(clean_config, set(), ReviewDepth.STANDARD).eligible


def test_ai_weak_test_finding_survives_and_is_not_deduplicated_against_production_finding(capsys):
    from pr_reviewer.review.processor import FindingProcessor
    from pr_reviewer.review.models import FindingSource, Severity, Finding

    test_file = source_file("""
        public class UnsafeApiTests {
            public void RedirectTest() {
                var result = controller.Continue("https://attacker.example");
                Assert.NotNull(result);
            }
        }
    """, "tests/ReviewFixture.Api.Tests/UnsafeApiTests.cs")

    controller_file = source_file("""
        public class UnsafeUserController {
            public IActionResult Continue(string url) => Redirect(url);
        }
    """, "src/ReviewFixture.Api/Controllers/UnsafeUserController.cs")

    # Authoritative production finding
    prod_finding = Finding(
        file_path=controller_file.file_path,
        line_number=3,
        severity=Severity.HIGH,
        rule_id="open-redirect",
        message="Unvalidated redirect allows open redirection.",
        source=FindingSource.STATIC,
    )

    # Raw AI finding 1: Open redirect erroneously placed on test file
    ai_prod_finding = Finding(
        file_path=test_file.file_path,
        line_number=3,
        severity=Severity.HIGH,
        rule_id="open-redirect",
        message="Open redirect vulnerability in test setup.",
        source=FindingSource.LLM,
    )

    # Raw AI finding 2: Weak assertion on test file
    ai_test_finding = Finding(
        file_path=test_file.file_path,
        line_number=4,
        severity=Severity.LOW,
        rule_id="weak-assertion",
        message="The test accepts an external redirect without verifying destination safety.",
        source=FindingSource.LLM,
    )

    processor = FindingProcessor()
    processed = processor.process(
        findings=[prod_finding, ai_prod_finding, ai_test_finding],
        changed_files=[test_file, controller_file],
    )

    captured = capsys.readouterr().out

    # Verify AI production finding on test file was rejected by Ownership
    assert "Stage : Ownership" in captured
    assert "Production vulnerability or defect 'open-redirect' belongs to production source code" in captured

    # Verify AI test finding survived as LOW | test-quality | insufficient-test-assertion
    test_findings = [f for f in processed if f.file_path == test_file.file_path]
    assert len(test_findings) == 1
    assert test_findings[0].rule_id == "insufficient-test-assertion"
    assert test_findings[0].category == "test-quality"
    assert test_findings[0].severity == Severity.LOW

    # Verify total findings count (1 prod + 1 test = 2)
    assert len(processed) == 2


def test_deduplication_prints_detailed_rejection_output(capsys):
    from pr_reviewer.review.processor import FindingProcessor
    from pr_reviewer.review.models import FindingSource, Severity, Finding

    file = source_file("""
        public class UnsafeApiTests {
            public void RedirectTest() {
                var result = controller.Continue("https://attacker.example");
                Assert.NotNull(result);
            }
        }
    """, "tests/ReviewFixture.Api.Tests/UnsafeApiTests.cs")

    ai_finding1 = Finding(
        file_path=file.file_path,
        line_number=4,
        severity=Severity.LOW,
        rule_id="insufficient-test-assertion",
        message="The test accepts an external redirect without verifying destination safety.",
        source=FindingSource.LLM,
    )

    ai_finding2 = Finding(
        file_path=file.file_path,
        line_number=4,
        severity=Severity.LOW,
        rule_id="insufficient-test-assertion",
        message="Test assertion does not check response destination.",
        source=FindingSource.LLM,
    )

    processor = FindingProcessor()
    processed = processor.process(
        findings=[ai_finding1, ai_finding2],
        changed_files=[file],
    )

    captured = capsys.readouterr().out

    assert "Stage : Deduplication" in captured
    assert "Reason: Duplicate of finding at tests/ReviewFixture.Api.Tests/UnsafeApiTests.cs:4 [insufficient-test-assertion]" in captured
    assert "Equivalent to: tests/ReviewFixture.Api.Tests/UnsafeApiTests.cs:4 [insufficient-test-assertion]" in captured
    assert len(processed) == 1


def test_unsafe_profile_client_sequential_io_and_cancellation_propagation():
    unsafe_client = """
        public class UnsafeProfileClient(HttpClient client) {
            public async Task<UserProfile> GetProfileAsync(long userId) {
                var details = await client.GetAsync($"/users/{userId}");
                var preferences = await client.GetAsync($"/preferences/{userId}");
                var activity = await client.GetAsync($"/activity/{userId}");
                return new UserProfile(details, preferences, activity);
            }
        }
    """
    found = rules(unsafe_client, "src/Clients/UnsafeProfileClient.cs")
    assert "sequential-io-operations" in found
    assert "missing-cancellation-propagation" in found

    safe_client = """
        public class SafeProfileClient(HttpClient client) {
            public async Task<UserProfile> GetProfileAsync(long userId, CancellationToken cancellationToken) {
                var detailsTask = client.GetAsync($"/users/{userId}", cancellationToken);
                var prefTask = client.GetAsync($"/preferences/{userId}", cancellationToken);
                await Task.WhenAll(detailsTask, prefTask);
                return new UserProfile(await detailsTask, await prefTask);
            }
        }
    """
    safe_found = rules(safe_client, "src/Clients/SafeProfileClient.cs")
    assert "sequential-io-operations" not in safe_found
    assert "missing-cancellation-propagation" not in safe_found


def test_nested_and_multiline_cancellation_propagation_safe():
    safe_profile = """
        public sealed class SafeProfileClient(HttpClient httpClient)
        {
            private static readonly Uri ProfileBaseUri = new("https://profiles.example/");

            public async Task<string> DownloadUserAsync(string userId, CancellationToken cancellationToken)
            {
                using var response = await httpClient.GetAsync(
                    new Uri(ProfileBaseUri, $"users/{userId}"),
                    cancellationToken);
                return await response.Content.ReadAsStringAsync(cancellationToken);
            }

            public async Task<(string Users, string Roles)> LoadDashboardAsync(
                CancellationToken cancellationToken)
            {
                var usersTask = httpClient.GetStringAsync(new Uri(ProfileBaseUri, "users"), cancellationToken);
                var rolesTask = httpClient.GetStringAsync(new Uri(ProfileBaseUri, "roles"), cancellationToken);
                await Task.WhenAll(usersTask, rolesTask);
                return (await usersTask, await rolesTask);
            }

            public async Task<string> NamedTokenAsync(Uri uri, CancellationToken ct)
            {
                return await httpClient.GetStringAsync(uri, cancellationToken: ct);
            }
        }
    """
    found = rules(safe_profile, "src/ReviewFixture.Api/Integrations/SafeProfileClient.cs")
    assert "missing-cancellation-propagation" not in found
    assert "sequential-io-operations" not in found
    assert len(found) == 0


def test_unsafe_profile_client_deduplicated_method_findings():
    unsafe_profile = """
        public sealed class UnsafeProfileClient(HttpClient httpClient)
        {
            public Task<string> DownloadAsync(string url) => httpClient.GetStringAsync(url);

            public async Task<(string Users, string Roles, string Permissions)> LoadDashboardAsync()
            {
                var users = await httpClient.GetStringAsync("https://profiles.example/users");
                var roles = await httpClient.GetStringAsync("https://profiles.example/roles");
                var permissions = await httpClient.GetStringAsync("https://profiles.example/permissions");
                return (users, roles, permissions);
            }
        }
    """
    file = source_file(unsafe_profile, "src/ReviewFixture.Api/Integrations/UnsafeProfileClient.cs")
    findings = DotNetStaticAnalyzer().analyze(file)

    rule_counts = {}
    for f in findings:
        rule_counts[f.rule_id] = rule_counts.get(f.rule_id, 0) + 1

    assert rule_counts.get("sequential-io-operations") == 1
    assert rule_counts.get("missing-cancellation-propagation") == 2
    assert rule_counts.get("ssrf") == 1
    assert len(findings) == 4


def test_changed_line_ownership_does_not_report_unchanged_lines():
    code = """
        public class UnsafeService(HttpClient httpClient)
        {
            public async Task<string> UnchangedMethod()
            {
                var u = await httpClient.GetStringAsync("https://api/1");
                var r = await httpClient.GetStringAsync("https://api/2");
                return u + r;
            }

            public async Task<string> ChangedMethod()
            {
                var a = await httpClient.GetStringAsync("https://api/a");
                var b = await httpClient.GetStringAsync("https://api/b");
                return a + b;
            }
        }
    """
    # Only lines in ChangedMethod are changed (lines 12-17)
    file = source_file(code, "src/Services/UnsafeService.cs", changed_numbers={12, 13, 14, 15, 16, 17})
    findings = DotNetStaticAnalyzer().analyze(file)
    for f in findings:
        assert 12 <= f.line_number <= 17


def test_semantic_router_gates_covered_csharp_bootstrap_and_tests():
    router = AdaptiveSemanticRouter()

    # Program.cs top-level statements
    program_code = """
        var builder = WebApplication.CreateBuilder(args);
        builder.Services.AddCors(options => {
            options.AddPolicy("unsafe", p => p.SetIsOriginAllowed(_ => true).AllowCredentials());
        });
        var app = builder.Build();
        app.Run();
        public partial class Program {}
    """
    program_file = source_file(program_code, "src/Api/Program.cs")
    decision = router.decide(program_file, covered_lines={3}, depth=ReviewDepth.STANDARD)
    assert not decision.eligible
    assert "static findings" in decision.reason

    # appsettings.json with TokenIssuer
    appsettings_code = '{"Security": {"TokenIssuer": "review-fixture"}}'
    appsettings_file = source_file(appsettings_code, "src/Api/appsettings.json")
    decision = router.decide(appsettings_file, covered_lines=set(), depth=ReviewDepth.STANDARD)
    assert not decision.eligible
    assert "no security-relevant content" in decision.reason

    # UnsafeApiTests.cs with constructor
    tests_code = """
        public sealed class UnsafeApiTests : IClassFixture<WebApplicationFactory<Program>>
        {
            private readonly HttpClient _client;
            public UnsafeApiTests(WebApplicationFactory<Program> factory) {
                _client = factory.CreateClient();
            }
            [Fact]
            public async Task TestRedirect() {
                var res = await _client.GetAsync("/redirect");
                Assert.NotNull(res);
            }
        }
    """
    tests_file = source_file(tests_code, "tests/Api.Tests/UnsafeApiTests.cs")
    decision = router.decide(tests_file, covered_lines={11}, depth=ReviewDepth.STANDARD)
    assert not decision.eligible
    assert "static findings" in decision.reason

