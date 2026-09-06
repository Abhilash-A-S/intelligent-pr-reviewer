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
    ("class X { RestClient client = RestClient.create(); String proxy(@RequestParam String url) { return client.get().uri(url).retrieve().body(String.class); } }", "security"),
    ("class X { void go(@RequestParam String next) throws Exception { response.sendRedirect(next); } }", "security"),
    ("class X { Object update(Object request, Object account) { BeanUtils.copyProperties(request, account); return account; } }", "data-validation"),
    ("class X {\nvoid audit() {\nCompletableFuture.runAsync(() -> work());\n}\n}", "unowned-background-task"),
    ("class X { void update(Request request) { LOGGER.info(\"password {}\", request.getPassword()); } }", "security"),
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


@pytest.mark.parametrize("framework", ["spring", "spring-boot"])
def test_spring_file_context_is_backend(framework):
    assert FileContextResolver._project_type(framework) == "backend"
