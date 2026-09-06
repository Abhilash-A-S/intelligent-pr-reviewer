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

        if self._is_setup_boilerplate(changed_file, meaningful):
            return SemanticDecision(
                changed_file, False, "low-value test/bootstrap setup",
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
        if re.search(r"\b(?:if|for|foreach|while|switch|try|catch|throw|await|return|new)\b", content):
            return False
        behavior_content = re.sub(
            r"public\s+DbSet<[^>]+>\s+\w+\s*=>\s*Set<[^>]+>\s*\(\s*\)\s*;",
            "",
            content,
        )
        if re.search(r"=>|\b(?:get|set|init)\s*\{", behavior_content):
            return False
        declarations = bool(re.search(r"\b(?:interface|record|class)\s+\w+", content))
        auto_properties = bool(re.search(r"\{\s*get\s*;\s*(?:set|init)\s*;\s*\}", content))
        positional_record = bool(re.search(r"\brecord\s+\w+\s*\([^)]*\)\s*;", content))
        interface_only = bool(re.search(r"\binterface\s+\w+", content))
        dbset_only = "DbContext" in content and "DbSet<" in content
        return declarations and (auto_properties or positional_record or interface_only or dbset_only)
