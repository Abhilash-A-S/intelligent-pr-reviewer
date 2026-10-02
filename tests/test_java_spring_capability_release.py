import pytest

from pr_reviewer.review.java_static_analyzer import JavaStaticAnalyzer
from pr_reviewer.review.models import ChangedFile, ChangedLine
from pr_reviewer.context.file_context import FileContextResolver


def inline_java(content: str, path: str = "src/main/java/example/Sample.java") -> ChangedFile:
    return ChangedFile(
        file_path=path,
        status="modified",
        full_content=content,
        changed_lines=[
            ChangedLine(path, number, line, number)
            for number, line in enumerate(content.splitlines(), start=1)
        ],
    )


@pytest.mark.parametrize(("source", "rule"), [
    ("class X { boolean same(String a, String b) { return a == b; } }", "identity-comparison-literal"),
    ("class X {\npublic Product get(long id) {\nreturn repository.findById(id).orElse(null);\n}\n}", "null-safety"),
    ("class X { Page list(int page, int pageSize) { int start = page * pageSize; return null; } }", "logic-error"),
    ("class X {\nList find(String query, String tenantId) {\nString cacheKey = query.toLowerCase();\nreturn null;\n}\n}", "cache-consistency"),
    ("class X { void parse() { try { work(); } catch (Exception error) {\n} } }", "empty-catch-block"),
    ("class X { @Async\nvoid work() throws Exception { Thread.sleep(10); } }", "async-blocking-operation"),
    ("class X { void run(String host) throws Exception { Runtime.getRuntime().exec(\"ping \" + host); } }", "command-injection"),
    ("class X { byte[] read(Path root, String name) throws Exception { return Files.readAllBytes(root.resolve(name)); } }", "path-traversal"),
    ("class X { Object find(JdbcTemplate jdbc, String name) { String sql = \"SELECT * FROM p WHERE name='\" + name; return jdbc.queryForList(sql); } }", "sql-injection"),
    ("class X { Object find(EntityManager em, String name) { return em.createNativeQuery(\n\"SELECT * FROM p WHERE name='\" + name).getResultList(); } }", "sql-injection"),
    ("class X { void unzip(ZipInputStream zip, Path root, ZipEntry entry) throws Exception { Files.copy(zip, root.resolve(entry.getName())); } }", "path-traversal"),
    ("class X { Object load(ObjectInputStream input) throws Exception { return input.readObject(); } }", "unsafe-deserialization"),
    ("class X { String token() throws Exception { return MessageDigest.getInstance(\"MD5\").toString(); } }", "weak-cryptography"),
    ("class X { String verificationCode() { return Integer.toString(new Random().nextInt()); } }", "weak-cryptography"),
    ("class X { Object report(Path path) throws Exception { Stream<String> lines = Files.lines(path); return lines.toList(); } }", "resource-cleanup"),
    ("class X { Object parse(String xml) throws Exception { DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance(); return factory.newDocumentBuilder().parse(xml); } }", "security"),
    ("class X { ResponseEntity fail(Exception error) { return ResponseEntity.internalServerError().body(error.getMessage()); } }", "exception-detail-exposure"),
    # SSRF via RestClient — specific rule ID
    ("class X { RestClient client = RestClient.create(); String proxy(@RequestParam String url) { return client.get().uri(url).retrieve().body(String.class); } }", "ssrf"),
    # Open redirect — specific rule ID
    ("class X { void go(@RequestParam String next) throws Exception { response.sendRedirect(next); } }", "open-redirect"),
    ("class X { Object update(Object request, Object account) { BeanUtils.copyProperties(request, account); return account; } }", "data-validation"),
    ("class X {\nvoid audit() {\nCompletableFuture.runAsync(() -> work());\n}\n}", "unowned-background-task"),
    # Sensitive data logging — specific rule ID
    ("class X { void update(Request request) { LOGGER.info(\"password {}\", request.getPassword()); } }", "sensitive-data-logging"),
    # SSRF via RestTemplate
    ("class X { String fetch(@RequestParam String url) { return restTemplate.getForObject(url, String.class); } }", "ssrf"),
    # Missing @Valid on @RequestBody
    ("class X { @PostMapping void create(@RequestBody CreateRequest req) { service.save(req); } }", "missing-input-validation"),
    # Sequential outbound HTTP calls
    ("class X { String combine(@RequestParam String a, @RequestParam String b) {\n  String r1 = restTemplate.getForObject(a, String.class);\n  String r2 = restTemplate.getForObject(b, String.class);\n  return r1 + r2;\n} }", "sequential-io-operations"),
    # Unsafe multipart upload (no content-type check)
    ("class X { void upload(MultipartFile file) throws Exception { Files.copy(file.getInputStream(), Path.of(file.getOriginalFilename())); } }", "unrestricted-file-upload"),
])

def test_java_high_confidence_capabilities(source, rule):
    assert rule in {finding.rule_id for finding in JavaStaticAnalyzer().analyze(inline_java(source))}


def test_java_findings_are_limited_to_changed_lines():
    content = """class Sample {
  String compare(String left, String right) {
    return left == right ? left : right;
  }
}
"""
    changed_file = ChangedFile(
        file_path="Sample.java",
        status="modified",
        full_content=content,
        changed_lines=[ChangedLine("Sample.java", 1, "class Sample {")],
    )

    assert JavaStaticAnalyzer().analyze(changed_file) == []


def test_parameterized_sql_and_path_containment_are_clean():
    source = """class Safe {
  Object find(JdbcTemplate jdbc, String name) {
    return jdbc.queryForList("SELECT * FROM product WHERE name = ?", name);
  }
  byte[] read(Path root, String name) throws Exception {
    Path normalizedRoot = root.toAbsolutePath().normalize();
    Path candidate = normalizedRoot.resolve(name).normalize();
    if (!candidate.startsWith(normalizedRoot)) throw new IllegalArgumentException();
    return Files.readAllBytes(candidate);
  }
}
"""
    assert JavaStaticAnalyzer().analyze(inline_java(source)) == []


def test_try_with_resources_hardened_xml_and_owned_future_are_clean():
    source = """class Safe {
  List<String> report(Path path) throws Exception {
    try (Stream<String> lines = Files.lines(path)) { return lines.toList(); }
  }
  DocumentBuilderFactory xml() throws Exception {
    DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
    factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
    factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
    return factory;
  }
  CompletableFuture<Void> audit(Runnable work) {
    return CompletableFuture.runAsync(work).exceptionally(error -> null);
  }
}
"""
    assert JavaStaticAnalyzer().analyze(inline_java(source)) == []


def test_secure_random_and_value_equality_are_clean():
    source = """class Safe {
  boolean same(String left, String right) { return Objects.equals(left, right); }
  String token() { return Long.toString(new SecureRandom().nextLong()); }
}
"""
    assert JavaStaticAnalyzer().analyze(inline_java(source)) == []


def test_java_command_injection_is_high_severity():
    source = """class Controller {
  String ping(String host) throws Exception {
    return new String(Runtime.getRuntime().exec("ping " + host).getInputStream().readAllBytes());
  }
}
"""
    findings = JavaStaticAnalyzer().analyze(inline_java(source))
    assert [(finding.rule_id, finding.severity.value) for finding in findings] == [
        ("command-injection", "high")
    ]


@pytest.mark.parametrize(("framework", "expected"), [
    ("spring", "backend"),
    ("spring-boot", "backend"),
])
def test_spring_file_context_is_backend(framework, expected):
    assert FileContextResolver._project_type(framework) == expected


def test_valid_requestbody_is_clean():
    """@Valid + @RequestBody must not produce a missing-input-validation finding."""
    source = """class X {
  @PostMapping
  void create(@Valid @RequestBody CreateRequest req) { service.save(req); }
}
"""
    findings = JavaStaticAnalyzer().analyze(inline_java(source))
    rule_ids = {f.rule_id for f in findings}
    assert "missing-input-validation" not in rule_ids


def test_single_outbound_call_is_clean():
    """A single outbound HTTP call must not trigger sequential-io-operations."""
    source = """class X {
  String fetch(@RequestParam String url) {
    return restTemplate.getForObject("https://api.example.com/data", String.class);
  }
}
"""
    findings = JavaStaticAnalyzer().analyze(inline_java(source))
    rule_ids = {f.rule_id for f in findings}
    assert "sequential-io-operations" not in rule_ids


def test_upload_with_content_type_check_is_clean():
    """An upload handler that validates MIME type and size must not trigger upload-security."""
    source = """class X {
  void upload(MultipartFile file) throws Exception {
    String ct = file.getContentType();
    long size = file.getSize();
    if (!List.of("image/jpeg", "image/png").contains(ct)) throw new IllegalArgumentException();
    Files.copy(file.getInputStream(), Path.of("safe.jpg"));
  }
}
"""
    findings = JavaStaticAnalyzer().analyze(inline_java(source))
    rule_ids = {f.rule_id for f in findings}
    assert "unrestricted-file-upload" not in rule_ids
