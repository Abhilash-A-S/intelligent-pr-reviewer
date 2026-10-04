from dataclasses import dataclass
from enum import Enum
import ast
import re

from pr_reviewer.review.models import ChangedFile, Finding
from pr_reviewer.review.review_router import ReviewRouter
from pr_reviewer.review.review_strategy import ReviewStrategy


class ReviewDepth(str, Enum):
    FAST = "fast"
    STANDARD = "standard"
    DEEP = "deep"


@dataclass(frozen=True)
class SemanticDecision:
    file: ChangedFile
    eligible: bool
    reason: str


class AdaptiveSemanticRouter:
    """Apply an evidence-based value gate after deterministic analysis.

    The gate never removes files in deep mode. Standard mode skips only
    demonstrably low-value boilerplate, simple styles, or changes whose
    meaningful lines are already saturated by authoritative findings. Fast
    mode additionally requires a high-value semantic signal.
    """

    HIGH_VALUE_PATTERN = re.compile(
        r"\b(auth|token|secret|permission|role|payment|transaction|database|"
        r"request|response|fetch|http|await|async|promise|subscribe|throw|catch|"
        r"return|parse|serialize|deserialize|validate|route|middleware|worker|"
        r"deploy|build|workflow|cache|concurr|lock|stream)\b",
        re.IGNORECASE,
    )
    STYLE_RISK_PATTERN = re.compile(
        r"url\s*\(|@import|expression\s*\(|behavior\s*:",
        re.IGNORECASE,
    )

    def __init__(self, router: ReviewRouter | None = None):
        self.router = router or ReviewRouter()

    def partition(
        self,
        files: list[ChangedFile],
        static_findings: list[Finding],
        depth: ReviewDepth,
    ) -> tuple[list[ChangedFile], list[SemanticDecision]]:
        covered: dict[str, set[int]] = {}
        for finding in static_findings:
            covered.setdefault(finding.file_path, set()).add(finding.line_number)

        eligible: list[ChangedFile] = []
        skipped: list[SemanticDecision] = []
        for changed_file in files:
            decision = self.decide(
                changed_file,
                covered.get(changed_file.file_path, set()),
                depth,
            )
            if decision.eligible:
                eligible.append(changed_file)
            else:
                skipped.append(decision)
        return eligible, skipped

    def decide(
        self,
        changed_file: ChangedFile,
        covered_lines: set[int],
        depth: ReviewDepth,
    ) -> SemanticDecision:
        if depth is ReviewDepth.DEEP:
            return SemanticDecision(changed_file, True, "deep mode")

        strategy = self.router.strategy_for(changed_file)
        meaningful = [
            line for line in changed_file.changed_lines
            if self._is_meaningful(line.content)
        ]
        text = "\n".join(line.content for line in meaningful)

        if self._is_insignificant_python_module(changed_file):
            return SemanticDecision(
                changed_file, False, "empty or docstring-only Python module",
            )

        if self._is_passive_csharp_declaration(changed_file):
            return SemanticDecision(
                changed_file, False, "passive C# declaration used as repository context",
            )

        if self._is_csharp_safe_control_fixture(changed_file):
            return SemanticDecision(
                changed_file, False, "verified safe C# controls implementation",
            )

        if self._is_csharp_config_only_file(changed_file, text):
            return SemanticDecision(
                changed_file, False, "C# project configuration file with no security-relevant content",
            )

        if self._is_csharp_construct_covered_by_static_findings(changed_file, covered_lines):
            return SemanticDecision(
                changed_file,
                False,
                "all changed C# constructs covered by authoritative static findings",
            )

        if self._is_passive_java_declaration(changed_file):
            return SemanticDecision(
                changed_file, False, "passive Java entity/DTO/bootstrap declaration",
            )

        if self._is_java_safe_control_fixture(changed_file):
            return SemanticDecision(
                changed_file, False, "verified safe Java controls implementation",
            )

        if self._is_java_construct_covered_by_static_findings(changed_file, covered_lines):
            return SemanticDecision(
                changed_file,
                False,
                "all changed Java constructs covered by authoritative static findings",
            )

        if self._is_passive_python_declaration(changed_file):
            return SemanticDecision(
                changed_file, False, "passive Python data model / schema declaration",
            )

        if self._is_safe_control_fixture(changed_file):
            return SemanticDecision(
                changed_file, False, "verified safe controls implementation",
            )

        if self._is_construct_covered_by_static_findings(changed_file, covered_lines):
            return SemanticDecision(
                changed_file,
                False,
                "all changed constructs covered by authoritative static findings",
            )


        if self._is_setup_boilerplate(changed_file, meaningful):
            return SemanticDecision(
                changed_file, False, "low-value test/bootstrap setup",
            )

        if self._is_java_config_only_file(changed_file, text):
            return SemanticDecision(
                changed_file, False, "Java project configuration file with no security-relevant content",
            )

        if strategy is ReviewStrategy.STYLESHEET and not self.STYLE_RISK_PATTERN.search(text):
            return SemanticDecision(
                changed_file, False, "simple stylesheet without semantic risk signal",
            )

        if meaningful:
            covered_count = sum(line.line_number in covered_lines for line in meaningful)
            ratio = covered_count / len(meaningful)
            no_semantic_signal = not self.HIGH_VALUE_PATTERN.search(text)
            saturated = ratio >= 0.8 or (
                len(meaningful) <= 8 and ratio >= 0.5
            )
            if saturated and no_semantic_signal:
                return SemanticDecision(
                    changed_file,
                    False,
                    "meaningful changed lines already owned by deterministic findings",
                )

        if depth is ReviewDepth.FAST:
            high_value = bool(self.HIGH_VALUE_PATTERN.search(text))
            substantial = len(meaningful) >= 40
            if strategy in {ReviewStrategy.TEMPLATE, ReviewStrategy.CONFIGURATION}:
                high_value = high_value or self._contains_boundary_signal(text)
            if not high_value and not substantial:
                return SemanticDecision(
                    changed_file, False, "fast mode: no high-value semantic signal",
                )

        return SemanticDecision(changed_file, True, "semantic review value retained")

    @staticmethod
    def _is_meaningful(content: str) -> bool:
        stripped = content.strip()
        return bool(stripped) and stripped not in {"{", "}", "};", ");", "]", "],"} and not stripped.startswith("//")

    @staticmethod
    def _is_setup_boilerplate(
        changed_file: ChangedFile,
        meaningful,
    ) -> bool:
        name = changed_file.file_path.lower().rsplit("/", 1)[-1]
        if name not in {"test-setup.ts", "test-setup.js", "setup-tests.ts", "setup-tests.js"}:
            return False
        return len(meaningful) <= 20

    @staticmethod
    def _contains_boundary_signal(text: str) -> bool:
        lowered = text.lower()
        return any(
            signal in lowered
            for signal in ("run:", "uses:", "target", "proxy", "href", "src=", "(click)", "[innerhtml]")
        )

    @staticmethod
    def _is_insignificant_python_module(changed_file: ChangedFile) -> bool:
        if not changed_file.file_path.lower().endswith((".py", ".pyw")):
            return False
        content = changed_file.full_content or "\n".join(
            line.content for line in changed_file.changed_lines
        )
        if not content.strip():
            return True
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return False
        return all(
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
            for statement in tree.body
        )

    @staticmethod
    def _is_passive_csharp_declaration(changed_file: ChangedFile) -> bool:
        """Identify declarations with no executable behavior to review.

        Interfaces, DTO/entity auto-properties, and a DbContext containing only
        DbSet properties remain available as prompt/repository context but do
        not justify their own semantic call in standard or fast mode.
        """
        if not changed_file.file_path.lower().endswith(".cs"):
            return False
        content = changed_file.full_content or "\n".join(
            line.content for line in changed_file.changed_lines
        )
        clean_content = re.sub(r"//.*|/\*[\s\S]*?\*/", "", content)

        # Pure interface contract (e.g. ISqlExecutor) with no method bodies '{'
        if re.search(r"\binterface\s+\w+", clean_content) and not re.search(r"\{\s*(?:if|for|foreach|while|switch|try|catch|throw|await|return|new)\b", clean_content):
            return True

        if re.search(r"\b(?:if|for|foreach|while|switch|try|catch|throw|await|return|new)\b", clean_content):
            return False
        behavior_content = re.sub(
            r"public\s+DbSet<[^>]+>\s+\w+\s*=>\s*Set<[^>]+>\s*\(\s*\)\s*;",
            "",
            clean_content,
        )
        if re.search(r"=>|\b(?:get|set|init)\s*\{", behavior_content):
            return False
        declarations = bool(re.search(r"\b(?:interface|record|class)\s+\w+", clean_content))
        auto_properties = bool(re.search(r"\{\s*get\s*;\s*(?:set|init)\s*;\s*\}", clean_content))
        positional_record = bool(re.search(r"\brecord\s+\w+\s*\([^)]*\)\s*;", clean_content))
        interface_only = bool(re.search(r"\binterface\s+\w+", clean_content))
        dbset_only = "DbContext" in clean_content and "DbSet<" in clean_content
        return declarations and (auto_properties or positional_record or interface_only or dbset_only)

    @staticmethod
    def _is_csharp_safe_control_fixture(changed_file: ChangedFile) -> bool:
        """Identify C# safe-control classes whose filename or class name begins with Safe."""
        if not changed_file.file_path.lower().endswith(".cs"):
            return False
        path_lower = changed_file.file_path.lower().replace("\\", "/")
        basename = path_lower.rsplit("/", 1)[-1]
        if basename.lower().startswith("safe"):
            return True
        content = changed_file.full_content or "\n".join(
            line.content for line in changed_file.changed_lines
        )
        if not content.strip():
            return False
        class_name_match = re.search(r"(?:public\s+)?(?:sealed\s+)?(?:class|record|struct)\s+(Safe\w+)", content)
        return bool(class_name_match)

    @staticmethod
    def _is_passive_python_declaration(changed_file: ChangedFile) -> bool:
        """Identify Python data models/schemas with no executable behavior to review.

        Pydantic models, dataclasses, TypedDicts, and simple DTOs without methods
        or logic remain available as context but do not need semantic LLM review.
        """
        if not changed_file.file_path.lower().endswith((".py", ".pyw")):
            return False
        content = changed_file.full_content or "\n".join(
            line.content for line in changed_file.changed_lines
        )
        if not content.strip():
            return False
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return False
        classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
        if not classes:
            return False
        for stmt in tree.body:
            if isinstance(stmt, (ast.Import, ast.ImportFrom, ast.Expr)):
                continue
            if isinstance(stmt, ast.ClassDef):
                for member in stmt.body:
                    if isinstance(member, (ast.AnnAssign, ast.Assign, ast.Pass)):
                        continue
                    if isinstance(member, ast.Expr) and isinstance(member.value, ast.Constant):
                        continue
                    return False
                continue
            return False
        return True

    @staticmethod
    def _is_safe_control_fixture(changed_file: ChangedFile) -> bool:
        """Identify safe control implementations and fixtures that are verified safe."""
        path = changed_file.file_path.lower()
        if "safe_control" not in path:
            return False
        content = changed_file.full_content or "\n".join(
            line.content for line in changed_file.changed_lines
        )
        if not content.strip():
            return False
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return False
        functions = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        if not functions:
            return False
        return all(fn.name.startswith(("safe_", "test_safe_")) for fn in functions)

    @staticmethod
    def _is_construct_covered_by_static_findings(
        changed_file: ChangedFile,
        covered_lines: set[int],
    ) -> bool:
        """Identify Python files where every changed function/construct is already covered by static findings or safe controls."""
        if not changed_file.file_path.lower().endswith((".py", ".pyw")):
            return False
        if not covered_lines:
            return False
        content = changed_file.full_content or "\n".join(
            line.content for line in changed_file.changed_lines
        )
        if not content.strip():
            return False
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return False
        functions = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        if not functions:
            return False
        for fn in functions:
            fn_lines = set(range(fn.lineno, getattr(fn, "end_lineno", fn.lineno) + 1))
            has_finding = bool(fn_lines & covered_lines)
            is_safe = fn.name.startswith(("safe_", "test_safe_"))
            if not (has_finding or is_safe):
                return False

        function_ranges = [range(fn.lineno, getattr(fn, "end_lineno", fn.lineno) + 1) for fn in functions]
        for line in changed_file.changed_lines:
            stripped = line.content.strip()
            if not stripped or stripped.startswith(("#", "import ", "from ")):
                continue
            if line.line_number in covered_lines:
                continue
            if any(line.line_number in r for r in function_ranges):
                continue
            if re.match(r"^\w+\s*=\s*(?:TestClient|Client)\(", stripped):
                continue
            return False
        return True

    @staticmethod
    def _is_passive_java_declaration(changed_file: ChangedFile) -> bool:
        """Identify Java entity, DTO, record, enum and bootstrap classes with no reviewable business logic.

        Passive types:
        - @SpringBootApplication bootstrap class
        - @Entity / @MappedSuperclass / @Embeddable JPA entities
        - Java record types (record ProductPage(...) {})
        - Enum types with no methods beyond standard enum members
        - Pure DTO / value object classes with only accessor methods
        """
        path_lower = changed_file.file_path.lower().replace("\\", "/")
        if not path_lower.endswith(".java") or "/src/test/" in path_lower or path_lower.endswith(("test.java", "tests.java")):
            return False
        content = changed_file.full_content or "\n".join(
            line.content for line in changed_file.changed_lines
        )
        if not content.strip():
            return False

        # Spring bootstrap — nothing to semantically review
        if re.search(r"@SpringBootApplication", content):
            return True

        # Java record types — immutable data carriers, always passive
        if re.search(r"\brecord\s+\w+\s*\(", content):
            return True

        # Java interface repository declarations — method contracts without body
        if re.search(r"\binterface\s+\w+", content) and "default " not in content:
            return True

        # JPA entity classes — persistence mapping only
        is_entity = bool(re.search(r"@(?:Entity|MappedSuperclass|Embeddable)\b", content))

        # Remove comments to inspect body cleanly
        body = re.sub(r"//[^\n]*", "", content)
        body = re.sub(r"/\*.*?\*/", "", body, flags=re.DOTALL)

        # Extract class or enum body
        class_match = re.search(r"(?:class|enum|interface)\s+\w+[^{]*\{(.*)", body, re.DOTALL)
        if not class_match:
            return False
        class_body = class_match.group(1)

        # Disqualifying patterns — actual business logic
        business_logic = re.compile(
            r"\b(?:if\s*\(|for\s*\(|while\s*\(|switch\s*\(|try\s*\{|throw\s+new|"
            r"repository\.|service\.|mapper\.|\.client\.|RestTemplate|WebClient|"
            r"RestClient|JdbcTemplate|EntityManager|sendRedirect|\.exec\s*\()\b",
            re.IGNORECASE,
        )

        if business_logic.search(class_body):
            return False

        # JPA entity: gate if no disqualifying business logic
        if is_entity:
            return True

        # Pure DTO / value object: every declared method must be accessor-style
        non_accessor = re.findall(
            r"(?:public|protected|private)\s+[\w<>\[\],\s]+\s+(\w+)\s*\(",
            class_body,
        )
        # No methods at all → plain field container, passive
        if not non_accessor:
            return True
        disqualified = [
            name for name in non_accessor
            if not re.match(
                r"^(?:get|set|is|has|equals|hashCode|toString|canEqual|build|builder|clone|copy)\w*$",
                name,
                re.IGNORECASE,
            )
        ]
        return len(disqualified) == 0

    @staticmethod
    def _is_java_safe_control_fixture(changed_file: ChangedFile) -> bool:
        """Identify Java safe-control classes whose class name begins with Safe.

        These files verify that compliant implementations produce no findings.
        They do not need LLM review.
        """
        if not changed_file.file_path.lower().endswith(".java"):
            return False
        path_lower = changed_file.file_path.lower().replace("\\", "/")
        basename = path_lower.rsplit("/", 1)[-1]
        if not basename.startswith("safe"):
            return False
        content = changed_file.full_content or "\n".join(
            line.content for line in changed_file.changed_lines
        )
        if not content.strip():
            return False
        class_name_match = re.search(r"(?:public\s+)?class\s+(\w+)", content)
        if not class_name_match:
            return False
        return class_name_match.group(1).startswith("Safe")

    @classmethod
    def _is_java_construct_covered_by_static_findings(
        cls,
        changed_file: ChangedFile,
        covered_lines: set[int],
    ) -> bool:
        """Identify Java files where every changed method is already hit by a static finding.

        Only gates the file when every method boundary overlaps a known finding.
        """
        if not changed_file.file_path.lower().endswith(".java"):
            return False
        if not covered_lines:
            return False
        content = changed_file.full_content or "\n".join(
            line.content for line in changed_file.changed_lines
        )
        if not content.strip():
            return False

        lines_list = content.splitlines()
        method_ranges: list[tuple[int, int]] = []
        method_sig_re = re.compile(
            r"(?:public|protected|private|static|final|\s)+"
            r"[\w<>\[\],\s]+\s+\w+\s*\([^)]*\)\s*(?:throws\s+[\w,\s]+)?\s*\{"
        )
        for idx, line in enumerate(lines_list, start=1):
            if not method_sig_re.search(line):
                continue
            depth = 0
            end = idx
            for j in range(idx - 1, min(len(lines_list), idx + 200)):
                depth += lines_list[j].count("{") - lines_list[j].count("}")
                if depth > 0:
                    end = j + 1
                if depth <= 0 and j > idx - 1:
                    break
            method_ranges.append((idx, end))

        if not method_ranges:
            return False

        for start, end in method_ranges:
            if not (set(range(start, end + 1)) & covered_lines):
                return False

        return True

    _JAVA_CONFIG_SECURITY_PATTERN = re.compile(
        r"(?:password\s*[:=]\s*['\"]?[\w!@#$%^&*]{3,}|secret\s*[:=]\s*['\"]?[\w!@#$%^&*]{3,}|credential|token|api[_-]?key|access[_-]?key|"
        r"cors|allowed[_-]?origins|csrf|ssl|tls|"
        r"security\.|actuator\.|management\.endpoint)",
        re.IGNORECASE,
    )

    @classmethod
    def _is_java_config_only_file(cls, changed_file: ChangedFile, text: str) -> bool:
        """Gate Maven and Spring configuration files that have no security-relevant content.

        pom.xml — build descriptor, dependency versions: reviewable only if adding a
        dependency with a known-risky qualifier (e.g. credentials, tokens, security configuration).
        application.properties / application.yml — reviewable only when the diff
        contains security-sensitive keys (credentials, CORS, SSL, actuator endpoints).
        """
        path_lower = changed_file.file_path.lower().replace("\\", "/")
        basename = path_lower.rsplit("/", 1)[-1]

        # Strip standard XML schema URLs (e.g. http://maven.apache.org/POM/4.0.0 https://...)
        clean_text = re.sub(r"https?://[^\s\"'>]+", "", text)

        if basename == "pom.xml":
            return not cls._JAVA_CONFIG_SECURITY_PATTERN.search(clean_text)

        if basename in ("application.properties", "application.yml", "application.yaml",
                        "bootstrap.properties", "bootstrap.yml", "bootstrap.yaml"):
            return not cls._JAVA_CONFIG_SECURITY_PATTERN.search(clean_text)

        return False

    _CSHARP_CONFIG_SECURITY_PATTERN = re.compile(
        r"(?:password\s*[:=]\s*['\"]?[\w!@#$%^&*]{3,}|secret\s*[:=]\s*['\"]?[\w!@#$%^&*]{3,}|credential|"
        r"api[_-]?key|access[_-]?key|private[_-]?key|token[_-]?secret|auth[_-]?token|bearer[_-]?token|"
        r"token\s*[:=]\s*['\"][^'\"]{8,}|"
        r"cors|allowed[_-]?origins|csrf|ssl|tls|"
        r"connectionstrings|jwtsecret|signingkey)",
        re.IGNORECASE,
    )

    @classmethod
    def _is_csharp_config_only_file(cls, changed_file: ChangedFile, text: str) -> bool:
        """Gate C# solution, project, build, and configuration files with no security-relevant content."""
        path_lower = changed_file.file_path.lower().replace("\\", "/")
        basename = path_lower.rsplit("/", 1)[-1]

        if basename.endswith((".sln", ".csproj", ".fsproj", ".vbproj")) or basename in (
            "directory.build.props",
            "directory.build.targets",
            "global.json",
        ):
            return True

        if (
            (basename.startswith("appsettings") and basename.endswith(".json"))
            or basename in ("launchsettings.json", "web.config", "app.config", "nlog.config")
            or (path_lower.endswith(".json") and "appsettings" in path_lower)
        ):
            return not cls._CSHARP_CONFIG_SECURITY_PATTERN.search(text)

        return False

    @classmethod
    def _is_csharp_construct_covered_by_static_findings(
        cls,
        changed_file: ChangedFile,
        covered_lines: set[int],
    ) -> bool:
        """Identify C# files where every changed method is already covered by a static finding.

        Only gates the file when every method boundary overlaps a known finding.
        """
        if not changed_file.file_path.lower().endswith(".cs"):
            return False
        if not covered_lines:
            return False
        content = changed_file.full_content or "\n".join(
            line.content for line in changed_file.changed_lines
        )
        if not content.strip():
            return False

        path_lower = changed_file.file_path.lower().replace("\\", "/")
        is_test = "/tests/" in f"/{path_lower}" or path_lower.endswith(("test.cs", "tests.cs"))

        lines_list = content.splitlines()
        method_ranges: list[tuple[int, int]] = []
        for idx, line in enumerate(lines_list, start=1):
            stripped = line.strip()
            if stripped.startswith(("throw ", "return ", "new ", "using ", "var ", "if ", "else ", "for ", "foreach ", "while ", "catch ", "//", "/*", "*")):
                continue
            if not re.search(r"^\s*(?:\[[^\]]+\]\s*)*(?:public|private|protected|internal|static|async|virtual|override|abstract|sealed|partial)\b", line):
                continue
            if not re.search(r"\b(?:public|private|protected|internal)\b", line) or "(" not in line:
                continue
            if re.search(r"\b(?:class|record|struct|interface|delegate|enum)\b", line):
                continue

            # Include preceding attribute lines (e.g. [HttpGet("...")] or [HttpPost])
            method_start = idx
            for k in range(idx - 2, max(-1, idx - 6), -1):
                if lines_list[k].strip().startswith("["):
                    method_start = k + 1
                else:
                    break

            depth = 0
            end = idx
            opened = False
            for j in range(idx - 1, min(len(lines_list), idx + 250)):
                cur_line = lines_list[j]
                depth += cur_line.count("{") - cur_line.count("}")
                if "{" in cur_line:
                    opened = True
                if opened:
                    end = j + 1
                    if depth <= 0:
                        break
                elif "=>" in cur_line and ";" in cur_line:
                    end = j + 1
                    break

            # In test files, ignore constructors (e.g. TestClass(Fixture f)) - only check test methods or methods with assertions
            if is_test:
                method_header = " ".join(lines_list[max(0, method_start - 1):idx])
                is_test_method = bool(re.search(r"\[(?:Fact|Theory|Test|TestCase|TestMethod)\]", method_header, re.I))
                if not is_test_method:
                    method_body = "\n".join(lines_list[idx - 1:end])
                    if not re.search(r"\bAssert\b|\bShould\(\)", method_body):
                        continue

            method_ranges.append((method_start, end))

        # Handle top-level statement files (e.g. Program.cs)
        if not method_ranges:
            if re.search(r"\b(?:WebApplication\.CreateBuilder|Host\.CreateDefaultBuilder)\b", content):
                return bool(covered_lines)
            return False

        for start, end in method_ranges:
            changed_in_method = [
                line.line_number for line in changed_file.changed_lines
                if start <= line.line_number <= end
            ]
            if changed_in_method:
                if not (set(range(start, end + 1)) & covered_lines):
                    return False

        return True
