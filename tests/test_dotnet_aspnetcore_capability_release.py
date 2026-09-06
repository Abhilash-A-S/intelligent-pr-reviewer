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
