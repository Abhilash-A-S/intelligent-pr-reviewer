from textwrap import dedent

from pr_reviewer.review.dotnet_static_analyzer import DotNetStaticAnalyzer
from pr_reviewer.review.models import ChangedFile, ChangedLine


def create_changed_file(source: str, path: str = "src/Api/Controller.cs") -> ChangedFile:
    content = dedent(source).strip()
    lines = content.splitlines()
    return ChangedFile(
        file_path=path,
        status="modified",
        full_content=content,
        changed_lines=[
            ChangedLine(path, number, line, number)
            for number, line in enumerate(lines, start=1)
        ],
    )


def analyze_rules(source: str, path: str = "src/Api/Controller.cs") -> list[str]:
    changed_file = create_changed_file(source, path)
    findings = DotNetStaticAnalyzer().analyze(changed_file)
    return [finding.rule_id for finding in findings]


def test_multiline_sql_injection():
    unsafe = """
        public class UserRepository(IDbConnection db) {
            public async Task<User?> FindByEmail(string email) {
                var sql = $"SELECT * FROM Users WHERE Email = '{email}'";
                return await db.QueryFirstOrDefaultAsync<User>(sql);
            }
        }
    """
    assert "sql-injection" in analyze_rules(unsafe)

    safe = """
        public class UserRepository(IDbConnection db) {
            public async Task<User?> FindByEmail(string email) {
                var sql = "SELECT * FROM Users WHERE Email = @Email";
                return await db.QueryFirstOrDefaultAsync<User>(sql, new { Email = email });
            }
        }
    """
    assert "sql-injection" not in analyze_rules(safe)


def test_weak_sha1_and_md5_cryptography():
    unsafe_sha1 = """
        public class TokenService {
            public string GenerateToken(byte[] payload) {
                return Convert.ToHexString(SHA1.HashData(payload));
            }
        }
    """
    assert "weak-cryptography" in analyze_rules(unsafe_sha1)

    safe = """
        public class TokenService {
            public string GenerateToken() {
                return Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
            }
        }
    """
    assert "weak-cryptography" not in analyze_rules(safe)


def test_ssrf_download_async():
    unsafe = """
        public class RemoteClient(HttpClient httpClient) {
            public Task<string> DownloadAsync(string url) =>
                httpClient.GetStringAsync(url);
        }
    """
    assert "ssrf" in analyze_rules(unsafe)

    safe = """
        public class RemoteClient(HttpClient httpClient) {
            public Task<string> DownloadAsync(string id) =>
                httpClient.GetStringAsync("https://api.internal.com/items/" + Uri.EscapeDataString(id));
        }
    """
    assert "ssrf" not in analyze_rules(safe)


def test_single_or_default_null_dereference():
    unsafe = """
        public class UserService(List<User> users) {
            public string GetUserEmail(long id) {
                var user = users.SingleOrDefault(x => x.Id == id);
                return user.Email;
            }
        }
    """
    assert "null-safety" in analyze_rules(unsafe)

    safe = """
        public class UserService(List<User> users) {
            public string GetUserEmail(long id) {
                var user = users.SingleOrDefault(x => x.Id == id);
                if (user == null) throw new NotFoundException();
                return user.Email;
            }
        }
    """
    assert "null-safety" not in analyze_rules(safe)


def test_privileged_mass_assignment():
    unsafe = """
        public class UserController : ControllerBase {
            public IActionResult UpdateRole(UpdateUserRequest request, User user) {
                user.IsAdministrator = request.IsAdministrator;
                return Ok();
            }
        }
    """
    assert "mass-assignment" in analyze_rules(unsafe)

    safe = """
        public class UserController : ControllerBase {
            public IActionResult UpdateProfile(UpdateProfileRequest request, User user) {
                user.Bio = request.Bio;
                return Ok();
            }
        }
    """
    assert "mass-assignment" not in analyze_rules(safe)


def test_multiline_empty_catch():
    unsafe = """
        public class SettingsReader {
            public void Read() {
                try { Load(); }
                catch (Exception)
                {
                }
            }
        }
    """
    assert "empty-catch-block" in analyze_rules(unsafe)

    safe = """
        public class SettingsReader {
            public void Read() {
                try { Load(); }
                catch (Exception ex)
                {
                    logger.LogError(ex, "Failed to read settings");
                }
            }
        }
    """
    assert "empty-catch-block" not in analyze_rules(safe)


def test_missing_authorization_on_admin_endpoint():
    unsafe = """
        public class AdminController : ControllerBase {
            [HttpPut("{id:int}/admin")]
            public ActionResult<UserRecord> UpdateAdministrator(int id, [FromBody] UserRecord record) {
                return Ok(record);
            }
        }
    """
    assert "missing-endpoint-authorization" in analyze_rules(unsafe)

    safe = """
        [Authorize(Roles = "Admin")]
        public class AdminController : ControllerBase {
            [HttpPut("{id:int}/admin")]
            public ActionResult<UserRecord> UpdateAdministrator(int id, [FromBody] UserRecord record) {
                return Ok(record);
            }
        }
    """
    assert "missing-endpoint-authorization" not in analyze_rules(safe)


def test_open_redirect_return_url():
    unsafe = """
        public class AccountController : ControllerBase {
            public IActionResult RedirectUser(string returnUrl) =>
                Redirect(returnUrl);
        }
    """
    assert "open-redirect" in analyze_rules(unsafe)

    safe = """
        public class AccountController : ControllerBase {
            public IActionResult RedirectUser(string returnUrl) {
                if (Url.IsLocalUrl(returnUrl)) return Redirect(returnUrl);
                return Redirect("/");
            }
        }
    """
    assert "open-redirect" not in analyze_rules(safe)


def test_upload_filename_path_traversal():
    unsafe = """
        public class UploadController(IHostEnvironment environment) : ControllerBase {
            public async Task<IActionResult> Save(IFormFile file) {
                var path = Path.Combine(
                    environment.ContentRootPath,
                    "uploads",
                    file.FileName);
                await using var stream = File.Create(path);
                await file.CopyToAsync(stream);
                return Ok();
            }
        }
    """
    found = analyze_rules(unsafe)
    assert "path-traversal" in found
    assert "unrestricted-file-upload" in found


def test_command_injection_process_start_info():
    unsafe = """
        public class NetworkController : ControllerBase {
            public IActionResult Ping(string host) {
                Process.Start(
                    new ProcessStartInfo(
                        "cmd.exe",
                        $"/c ping {host}"));
                return Ok();
            }
        }
    """
    assert "command-injection" in analyze_rules(unsafe)


def test_exception_detail_exposure_problem_detail():
    unsafe = """
        public class ApiController : ControllerBase {
            public IActionResult Execute() {
                try { Work(); }
                catch (Exception exception) {
                    return Problem(
                        detail: exception.ToString(),
                        statusCode: 500);
                }
                return Ok();
            }
        }
    """
    assert "exception-detail-exposure" in analyze_rules(unsafe)

    safe = """
        public class ApiController : ControllerBase {
            public IActionResult Execute() {
                try { Work(); }
                catch (Exception exception) {
                    logger.LogError(exception, "Operation failed");
                    return Problem(
                        detail: "An internal error occurred.",
                        statusCode: 500);
                }
                return Ok();
            }
        }
    """
    assert "exception-detail-exposure" not in analyze_rules(safe)


def test_credentialed_permissive_cors_policy():
    unsafe = """
        public class Startup {
            public void Configure(IApplicationBuilder app) {
                app.UseCors(policy =>
                    policy.SetIsOriginAllowed(_ => true)
                          .AllowCredentials());
            }
        }
    """
    assert "cors-misconfiguration" in analyze_rules(unsafe)

    safe = """
        public class Startup {
            public void Configure(IApplicationBuilder app) {
                app.UseCors(policy =>
                    policy.WithOrigins("https://app.example.com")
                          .AllowCredentials());
            }
        }
    """
    assert "cors-misconfiguration" not in analyze_rules(safe)


def test_comprehensive_22_dotnet_authoritative_root_causes():
    source = """
        public class CompleteFixture(HttpClient httpClient, AppDbContext db, IDbConnection dapper, ILogger logger, IHostEnvironment environment) : ControllerBase {
            private const string Secret = "super-secret-signing-key-1234567890";
            public string Token(byte[] payload) => Convert.ToHexString(SHA1.HashData(payload));
            public string OTP() => Random.Shared.Next().ToString();
            public Task<string> Fetch(string url) => httpClient.GetStringAsync(url);
            public async Task<string> Email(long id) { var user = await db.Users.FirstOrDefaultAsync(x => x.Id == id); return user.Email; }
            public User Blocking(long id) => db.Users.FindAsync(id).Result!;
            public async Task<List<Product>> SearchCache(string tenantId, string query) { var key = query; return await db.Products.ToListAsync(); }
            public IActionResult Log(string password) { logger.LogInformation("password {Password}", password); return Ok(); }
            public IActionResult Update(User user, UpdateRequest request) { user.IsAdministrator = request.IsAdministrator; return Ok(); }
            public async void BackgroundWork() { await Task.Delay(100); }
            public void TaskRun() { Task.Run(() => Work()); }
            public void Swallow() { try { Work(); } catch (Exception) { } }
            [HttpPut("{id:int}/admin")]
            public IActionResult AdminUpdate(int id) => Ok();
            public IActionResult Go(string returnUrl) => Redirect(returnUrl);
            public async Task<IActionResult> SaveUpload(IFormFile file) { var path = Path.Combine(environment.ContentRootPath, "uploads", file.FileName); await using var stream = File.Create(path); await file.CopyToAsync(stream); return Ok(); }
            public IActionResult Ping(string host) { Process.Start(new ProcessStartInfo("cmd.exe", $"/c ping {host}")); return Ok(); }
            public IActionResult Error() { try { Work(); } catch (Exception ex) { return Problem(ex.ToString()); } return Ok(); }
            public IActionResult Cookie(string token) { Response.Cookies.Append("session", token); return Ok(); }
            public void Cors(CorsPolicyBuilder builder) { builder.SetIsOriginAllowed(_ => true).AllowCredentials(); }
            public Task<List<User>> RawSql(string email) { var sql = $"SELECT * FROM Users WHERE Email = '{email}'"; return dapper.QueryAsync<User>(sql); }
        }
    """
    found = analyze_rules(source)
    expected_rules = {
        "hardcoded-secret",
        "weak-cryptography",
        "predictable-random-token",
        "ssrf",
        "null-safety",
        "sync-over-async",
        "null-forgiving-nullable",
        "cache-consistency",
        "sensitive-data-logging",
        "mass-assignment",
        "async-void",
        "unowned-background-task",
        "empty-catch-block",
        "missing-endpoint-authorization",
        "open-redirect",
        "path-traversal",
        "unrestricted-file-upload",
        "command-injection",
        "exception-detail-exposure",
        "insecure-cookie",
        "cors-misconfiguration",
        "sql-injection",
    }
    assert expected_rules.issubset(set(found))

