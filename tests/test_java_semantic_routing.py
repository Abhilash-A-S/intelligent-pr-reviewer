"""Tests for Java semantic routing helpers in AdaptiveSemanticRouter."""
import pytest

from pr_reviewer.review.models import ChangedFile, ChangedLine
from pr_reviewer.review.semantic_routing import AdaptiveSemanticRouter, ReviewDepth


def java_file(content: str, path: str = "src/main/java/example/Sample.java") -> ChangedFile:
    return ChangedFile(
        file_path=path,
        status="modified",
        full_content=content,
        changed_lines=[
            ChangedLine(path, number, line, number)
            for number, line in enumerate(content.splitlines(), start=1)
        ],
    )


router = AdaptiveSemanticRouter()


# ---------------------------------------------------------------------------
# _is_passive_java_declaration
# ---------------------------------------------------------------------------

class TestIsPassiveJavaDeclaration:
    def test_spring_boot_application_is_passive(self):
        content = """
@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
"""
        assert router._is_passive_java_declaration(java_file(content))

    def test_jpa_entity_is_passive(self):
        content = """
@Entity
@Table(name = "users")
public class User {
    @Id
    private Long id;
    private String name;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
}
"""
        assert router._is_passive_java_declaration(java_file(content))

    def test_pure_dto_with_only_accessors_is_passive(self):
        content = """
public class CreateUserRequest {
    private String username;
    private String email;

    public String getUsername() { return username; }
    public void setUsername(String username) { this.username = username; }
    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
}
"""
        assert router._is_passive_java_declaration(java_file(content))

    def test_rest_controller_with_business_logic_is_not_passive(self):
        content = """
@RestController
public class UserController {
    public ResponseEntity<String> getUser(@RequestParam String id) {
        if (id == null) return ResponseEntity.badRequest().build();
        return ResponseEntity.ok(service.find(id));
    }
}
"""
        assert not router._is_passive_java_declaration(java_file(content))

    def test_service_with_repository_call_is_not_passive(self):
        content = """
@Service
public class UserService {
    public User findById(Long id) {
        return repository.findById(id).orElseThrow();
    }
}
"""
        assert not router._is_passive_java_declaration(java_file(content))

    def test_non_java_file_returns_false(self):
        cf = java_file("public class X {}", path="src/main/resources/Sample.py")
        assert not router._is_passive_java_declaration(cf)


# ---------------------------------------------------------------------------
# _is_java_safe_control_fixture
# ---------------------------------------------------------------------------

class TestIsJavaSafeControlFixture:
    def test_safe_prefixed_class_is_gated(self):
        content = """
public class SafeController {
    public ResponseEntity<String> create(@Valid @RequestBody CreateRequest req) {
        return ResponseEntity.ok(service.save(req));
    }
}
"""
        assert router._is_java_safe_control_fixture(
            java_file(content, path="src/main/java/example/SafeController.java")
        )

    def test_unsafe_prefixed_class_is_not_gated(self):
        content = """
public class UnsafeController {
    public ResponseEntity<String> create(@RequestBody CreateRequest req) {
        return ResponseEntity.ok(service.save(req));
    }
}
"""
        assert not router._is_java_safe_control_fixture(
            java_file(content, path="src/main/java/example/UnsafeController.java")
        )

    def test_non_java_file_returns_false(self):
        content = "class SafeStuff {}"
        cf = java_file(content, path="src/SafeStuff.py")
        assert not router._is_java_safe_control_fixture(cf)


# ---------------------------------------------------------------------------
# _is_java_construct_covered_by_static_findings
# ---------------------------------------------------------------------------

class TestIsJavaConstructCoveredByStaticFindings:
    def test_all_methods_covered_is_gated(self):
        content = """public class X {
    public String method1(String a, String b) {
        return a == b ? a : b;
    }
    public void method2(String host) throws Exception {
        Runtime.getRuntime().exec("ping " + host);
    }
}
"""
        covered = {2, 5}
        assert router._is_java_construct_covered_by_static_findings(java_file(content), covered)

    def test_uncovered_method_is_not_gated(self):
        content = """public class X {
    public String covered(String a) { return a; }
    public String uncovered(String b) { return b; }
}
"""
        covered = {2}
        assert not router._is_java_construct_covered_by_static_findings(java_file(content), covered)

    def test_no_covered_lines_is_not_gated(self):
        content = """public class X {
    public String fetch(String url) { return url; }
}
"""
        assert not router._is_java_construct_covered_by_static_findings(java_file(content), set())

    def test_non_java_file_returns_false(self):
        content = "def foo(): pass"
        cf = java_file(content, path="src/foo.py")
        assert not router._is_java_construct_covered_by_static_findings(cf, {1})


# ---------------------------------------------------------------------------
# decide() integration — Java files routed correctly
# ---------------------------------------------------------------------------

class TestDecideJavaIntegration:
    def test_entity_is_value_gated_in_standard_mode(self):
        content = """
@Entity
public class Product {
    @Id private Long id;
    private String name;
    public Long getId() { return id; }
    public String getName() { return name; }
}
"""
        cf = java_file(content)
        decision = router.decide(cf, set(), ReviewDepth.STANDARD)
        assert not decision.eligible

    def test_safe_fixture_is_value_gated(self):
        content = """
public class SafeAuthController {
    public ResponseEntity<String> login(@Valid @RequestBody LoginRequest req) {
        return ResponseEntity.ok(service.authenticate(req));
    }
}
"""
        cf = java_file(content, path="src/main/java/SafeAuthController.java")
        decision = router.decide(cf, set(), ReviewDepth.STANDARD)
        assert not decision.eligible

    def test_controller_with_business_logic_is_eligible(self):
        content = """
@RestController
public class UnsafeController {
    public ResponseEntity<String> create(@RequestBody CreateRequest req) {
        return ResponseEntity.ok(service.save(req));
    }
}
"""
        cf = java_file(content, path="src/main/java/UnsafeController.java")
        decision = router.decide(cf, set(), ReviewDepth.STANDARD)
        assert decision.eligible

    def test_deep_mode_never_gates(self):
        content = """
@Entity
public class Item {
    @Id private Long id;
    public Long getId() { return id; }
}
"""
        cf = java_file(content)
        decision = router.decide(cf, set(), ReviewDepth.DEEP)
        assert decision.eligible
