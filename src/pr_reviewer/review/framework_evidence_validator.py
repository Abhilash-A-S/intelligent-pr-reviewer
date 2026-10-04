import re
from dataclasses import dataclass, field

from pr_reviewer.context.models import RepositoryContext
from pr_reviewer.review.models import (
    ChangedFile,
    Finding,
)


@dataclass
class FrameworkEvidenceValidationResult:
    """
    Result returned by framework-specific deterministic
    evidence validation.

    accepted:
        True when no deterministic framework-specific
        evidence contradicts the finding.

    reasons:
        Human-readable explanations for rejection.
    """

    accepted: bool

    reasons: list[str] = field(
        default_factory=list
    )


class FrameworkEvidenceValidator:
    """
    Deterministic validation for framework-specific
    AI findings.

    This validator runs after the generic
    FindingValidator.

    Its responsibility is different from ordinary
    validation:

    - generic validation checks structure, changed lines,
      speculation, file type, etc.

    - framework evidence validation checks whether a
      framework-specific claim contradicts repository
      evidence.

    The implementation is intentionally conservative.

    If a finding cannot be disproved using available
    repository evidence, it is preserved.

    Current framework validation:

    Angular
    -------
    - TestBed import claims.
    - Standalone-component evidence.
    - Protection against hallucinated AppModule/module
      requirements for valid standalone components.

    Future frameworks can be added without expanding the
    generic FindingValidator.
    """

    # ======================================================
    # Angular TestBed import finding detection
    # ======================================================

    ANGULAR_TEST_IMPORT_RULE_TERMS = (
        "testbed",
        "standalone-component-import",
        "standalone-import",
        "component-import",
        "module-import",
        "incorrect-import",
        "test-import",
    )

    ANGULAR_TEST_IMPORT_MESSAGE_PATTERNS = (
        # --------------------------------------------------
        # Direct component imports claimed to be invalid.
        # --------------------------------------------------

        r"""
        \bcomponent\b
        .*?
        \bshould\s+not\s+be\s+imported\b
        .*?
        \btestbed\b
        """,

        r"""
        \bshould\s+not\s+be\s+imported\s+directly\b
        .*?
        \btestbed\b
        """,

        r"""
        \bshould\s+not\s+be\s+imported\s+directly\b
        """,

        # A standalone component imported through TestBed imports is valid.
        # LLMs sometimes disguise the contrary claim as maintainability or
        # duplicate-logic instead of using an Angular-specific rule ID.
        r"""
        \bcomponent\b
        .*?
        \bimported\s+directly\b
        .*?
        \bimports?\s+array\b
        .*?
        \bunnecessary\b
        """,

        r"""
        \busing\s+the\s+component\s+itself\b
        .*?
        \bimport\b
        """,

        r"""
        \bcomponent\s+itself\b
        .*?
        \btestbed\b
        """,

        # --------------------------------------------------
        # Claims that an NgModule/module is required.
        # --------------------------------------------------

        r"""
        \buse\s+(?:an?\s+)?
        (?:ngmodule|module)
        \s+instead\b
        """,

        r"""
        \brequire(?:s|d)?\s+(?:an?\s+)?
        (?:ngmodule|module)\b
        """,

        r"""
        \bshould\s+use\s+(?:an?\s+)?
        (?:ngmodule|module)\b
        """,

        r"""
        \bshould\s+be\s+declared\s+in\s+
        (?:an?\s+)?
        (?:ngmodule|module)\b
        """,

        r"""
        \bimports\s*:\s*\[[^\]]+\]
        .*?
        \bnot\s+(?:valid|recommended|correct)\b
        """,

        # --------------------------------------------------
        # Hallucinated replacement-component claims.
        # --------------------------------------------------

        r"""
        \breplace\b
        .*?
        \bimports\s*:\s*\[
        .*?
        \]
        .*?
        \bstandalone\b
        """,

        r"""
        \breplace\b
        .*?
        \bappcomponent\b
        """,
    )

    TEST_FILE_MARKERS = (
        ".spec.",
        ".test.",
        "_test.",
        "_tests.",
    )

    # ======================================================
    # Angular source parsing
    # ======================================================

    ANGULAR_COMPONENT_DECORATOR = re.compile(
        r"""
        @Component
        \s*
        \(
        \s*
        \{
        (?P<body>.*?)
        \}
        \s*
        \)
        \s*
        (?:export\s+)?
        (?:default\s+)?
        class
        \s+
        (?P<class_name>
            [A-Za-z_$][A-Za-z0-9_$]*
        )
        \b
        """,
        re.IGNORECASE
        | re.DOTALL
        | re.VERBOSE,
    )

    TESTBED_IMPORTS_PATTERN = re.compile(
        r"""
        imports
        \s*:
        \s*
        \[
        (?P<imports>.*?)
        \]
        """,
        re.IGNORECASE
        | re.DOTALL
        | re.VERBOSE,
    )

    IDENTIFIER_PATTERN = re.compile(
        r"\b[A-Za-z_$][A-Za-z0-9_$]*\b"
    )

    ANGULAR_CORE_VERSION_PATTERN = re.compile(
        r"""
        ["']
        @angular/core
        ["']
        \s*
        :
        \s*
        ["']
        [^0-9]*
        (?P<major>\d+)
        """,
        re.IGNORECASE
        | re.VERBOSE,
    )

    # ======================================================
    # Public validation API
    # ======================================================

    def validate(
        self,
        finding: Finding,
        changed_file: ChangedFile,
        changed_files: list[ChangedFile],
        repository_context: RepositoryContext | None,
    ) -> FrameworkEvidenceValidationResult:
        """
        Validate one finding against available
        framework-specific repository evidence.

        Unknown frameworks and unsupported finding types
        are preserved.
        """

        reasons: list[str] = []

        if repository_context is None:
            return FrameworkEvidenceValidationResult(
                accepted=True,
                reasons=[],
            )

        framework = (
            repository_context.framework
            or ""
        ).strip().lower()

        if framework == "angular":
            self._validate_angular(
                finding=finding,
                changed_file=changed_file,
                changed_files=changed_files,
                reasons=reasons,
            )

        return FrameworkEvidenceValidationResult(
            accepted=not reasons,
            reasons=reasons,
        )

    # ======================================================
    # Angular
    # ======================================================

    def _validate_angular(
        self,
        finding: Finding,
        changed_file: ChangedFile,
        changed_files: list[ChangedFile],
        reasons: list[str],
    ) -> None:
        """
        Apply deterministic Angular evidence checks.
        """

        # --------------------------------------------------
        # Angular template event bindings are framework-owned.
        # A template `(event)="handler()"` binding is not a native
        # addEventListener registration and does not require manual removal.
        # --------------------------------------------------

        if self._is_angular_template(changed_file.file_path):
            evidence_line = self._changed_line_content(
                changed_file,
                finding.line_number,
            )

            if (
                self._is_angular_event_binding(evidence_line)
                and self._looks_like_listener_cleanup_claim(finding)
            ):
                reasons.append(
                    "Angular template event bindings are managed by Angular "
                    "and are not manual global listener registrations."
                )
                return

            # A template method invocation can prove that a method is called,
            # but it cannot prove implementation defects such as missing error
            # handling or resource cleanup. Those findings must be anchored to
            # executable component/service source evidence.
            if (
                self._is_angular_event_binding(evidence_line)
                and self._looks_like_implementation_behavior_claim(finding)
            ):
                reasons.append(
                    "Angular template invocation does not provide source "
                    "evidence for the claimed implementation defect; anchor "
                    "the finding to the component/service implementation."
                )
                return

        # --------------------------------------------------
        # Angular TestBed / standalone import validation
        # --------------------------------------------------

        if not self._is_test_file(
            changed_file.file_path
        ):
            return

        if not self._looks_like_invalid_testbed_import_claim(
            finding
        ):
            return

        imported_identifiers = (
            self._extract_testbed_import_identifiers(
                changed_file
            )
        )

        if not imported_identifiers:
            return

        angular_major = (
            self._detect_angular_major_version(
                changed_files
            )
        )

        for identifier in imported_identifiers:

            component_evidence = (
                self._find_angular_component(
                    class_name=identifier,
                    changed_files=changed_files,
                )
            )

            if component_evidence is None:
                continue

            if self._component_is_proven_standalone(
                decorator_body=component_evidence,
                angular_major=angular_major,
            ):
                reasons.append(
                    (
                        "Finding contradicts Angular "
                        "standalone-component evidence: "
                        f"'{identifier}' is valid in "
                        "TestBed imports."
                    )
                )

                return

    @staticmethod
    def _is_angular_template(file_path: str) -> bool:
        return file_path.lower().endswith(".html")

    @staticmethod
    def _changed_line_content(
        changed_file: ChangedFile,
        line_number: int,
    ) -> str:
        for changed_line in changed_file.changed_lines:
            if changed_line.line_number == line_number:
                return changed_line.content or ""

        full_content = changed_file.full_content or ""
        lines = full_content.splitlines()
        if 1 <= line_number <= len(lines):
            return lines[line_number - 1]

        return ""

    @staticmethod
    def _is_angular_event_binding(content: str) -> bool:
        return bool(
            re.search(
                r"\(\s*[A-Za-z_][A-Za-z0-9_.:-]*\s*\)\s*=",
                content or "",
            )
        )

    @staticmethod
    def _looks_like_listener_cleanup_claim(finding: Finding) -> bool:
        rule_id = (finding.rule_id or "").strip().lower()
        text = " ".join(
            part
            for part in (
                finding.message,
                finding.suggestion,
            )
            if part
        ).lower()

        return (
            rule_id in {
                "listener-cleanup",
                "global-event-listener-without-removal",
                "resource-cleanup",
            }
            and any(
                term in text
                for term in (
                    "listener",
                    "event",
                    "detach",
                    "remove",
                    "cleanup",
                    "memory leak",
                )
            )
        )

    @staticmethod
    def _looks_like_implementation_behavior_claim(
        finding: Finding,
    ) -> bool:
        rule_id = (finding.rule_id or "").strip().lower()
        return rule_id in {
            "error-handling",
            "resource-cleanup",
            "subscription-cleanup",
            "listener-cleanup",
            "async-issue",
            "null-safety",
            "logic-error",
            "security",
        }

    # ======================================================
    # Finding classification
    # ======================================================

    def _looks_like_invalid_testbed_import_claim(
        self,
        finding: Finding,
    ) -> bool:
        """
        Determine whether the finding belongs to the
        Angular TestBed/component-import problem family.

        The LLM may generate different rule IDs between
        runs, so validation must not depend on one exact
        rule ID.

        We therefore combine:

        - rule-ID terms
        - message evidence
        - suggestion evidence
        """

        rule_id = (
            finding.rule_id
            .strip()
            .lower()
        )

        text = " ".join(
            part
            for part in (
                finding.message,
                finding.suggestion or "",
            )
            if part
        )

        normalized_text = (
            text
            .strip()
            .lower()
        )

        # --------------------------------------------------
        # Strong signal:
        #
        # TestBed appears either in the rule ID or text,
        # together with import/component/module concepts.
        # --------------------------------------------------

        has_testbed_signal = (
            "testbed" in rule_id
            or "testbed" in normalized_text
        )

        has_import_signal = (
            "import" in rule_id
            or "import" in normalized_text
        )

        has_component_or_module_signal = (
            "component" in rule_id
            or "component" in normalized_text
            or "module" in rule_id
            or "module" in normalized_text
        )

        if (
            has_testbed_signal
            and has_import_signal
            and has_component_or_module_signal
        ):
            return True

        # --------------------------------------------------
        # Semantic standalone-import contradiction.
        #
        # LLMs often omit the word "TestBed" even when the evidence line is
        # inside TestBed.configureTestingModule(...).  In that context, a
        # claim that a standalone component must not/cannot be imported
        # directly is still the same framework-fact family regardless of the
        # generated rule ID (api-misuse, duplicate-logic, etc.).
        # --------------------------------------------------

        standalone_import_contradiction = (
            "standalone" in normalized_text
            and has_import_signal
            and (
                "should not be imported" in normalized_text
                or "shouldn't be imported" in normalized_text
                or "cannot be imported" in normalized_text
                or "can't be imported" in normalized_text
                or "incorrect" in normalized_text
                or "not correct" in normalized_text
                or "invalid" in normalized_text
                or "not valid" in normalized_text
                or "not recommended" in normalized_text
                or "do not import" in normalized_text
                or "don't import" in normalized_text
                or "imported directly" in normalized_text
                or "correct usage" in normalized_text
                or "correct syntax" in normalized_text
                or "should be imported as a standalone" in normalized_text
            )
        )
        if standalone_import_contradiction:
            return True

        # Another recurring hallucination treats a component listed once in
        # TestBed.configureTestingModule({ imports: [...] }) as though the
        # component were importing itself or were inherently redundant. That is
        # a semantic TestBed misconception, independent of generated rule ID.
        testbed_self_import_misconception = (
            has_import_signal
            and (
                "imported into itself" in normalized_text
                or "imports itself" in normalized_text
                or "component is importing itself" in normalized_text
                or (
                    "remove" in normalized_text
                    and "component" in normalized_text
                    and "imports array" in normalized_text
                )
            )
        )
        if testbed_self_import_misconception:
            return True

        # --------------------------------------------------
        # Rule family signal
        # --------------------------------------------------

        matching_rule_terms = sum(
            1
            for term
            in self.ANGULAR_TEST_IMPORT_RULE_TERMS
            if term in rule_id
        )

        if (
            matching_rule_terms >= 2
            and has_import_signal
        ):
            return True

        # --------------------------------------------------
        # Natural-language patterns
        # --------------------------------------------------

        return any(
            re.search(
                pattern,
                text,
                flags=(
                    re.IGNORECASE
                    | re.DOTALL
                    | re.VERBOSE
                ),
            )
            is not None
            for pattern
            in self.ANGULAR_TEST_IMPORT_MESSAGE_PATTERNS
        )

    # ======================================================
    # TestBed parsing
    # ======================================================

    def _extract_testbed_import_identifiers(
        self,
        changed_file: ChangedFile,
    ) -> list[str]:
        """
        Extract identifiers from TestBed imports.

        Example:

            TestBed.configureTestingModule({
                imports: [
                    App,
                    RouterTestingModule
                ]
            })

        Returns:

            [
                "App",
                "RouterTestingModule"
            ]
        """

        content = (
            changed_file.full_content
            or "\n".join(
                line.content
                for line
                in changed_file.changed_lines
            )
        )

        if not content:
            return []

        # Do not treat arbitrary imports arrays as TestBed
        # evidence unless the file actually contains
        # TestBed configuration.
        if "TestBed" not in content:
            return []

        identifiers: list[str] = []

        for match in (
            self.TESTBED_IMPORTS_PATTERN.finditer(
                content
            )
        ):

            imports_content = (
                match.group(
                    "imports"
                )
            )

            for identifier in (
                self.IDENTIFIER_PATTERN.findall(
                    imports_content
                )
            ):

                if identifier not in identifiers:
                    identifiers.append(
                        identifier
                    )

        return identifiers

    # ======================================================
    # Angular component evidence
    # ======================================================

    def _find_angular_component(
        self,
        class_name: str,
        changed_files: list[ChangedFile],
    ) -> str | None:
        """
        Find the @Component decorator body belonging to
        a named Angular component.

        Only currently available repository evidence is
        used.
        """

        for changed_file in changed_files:

            content = changed_file.full_content

            if not content:
                continue

            if "@Component" not in content:
                continue

            for match in (
                self.ANGULAR_COMPONENT_DECORATOR.finditer(
                    content
                )
            ):

                detected_class = (
                    match.group(
                        "class_name"
                    )
                )

                if detected_class != class_name:
                    continue

                return (
                    match.group(
                        "body"
                    )
                )

        return None

    @staticmethod
    def _component_is_proven_standalone(
        decorator_body: str,
        angular_major: int | None,
    ) -> bool:
        """
        Determine whether repository evidence proves that
        an Angular component is standalone.

        Evidence:

        1. standalone: true
           Explicit standalone component.

        2. standalone: false
           Explicit non-standalone component.

        3. Component-level imports: [...]
           Strong standalone-component evidence.

        4. Angular 19+
           Components are standalone by default unless
           explicitly marked standalone: false.

        If standalone status cannot be proven, return
        False and preserve the finding.
        """

        if re.search(
            r"\bstandalone\s*:\s*true\b",
            decorator_body,
            flags=re.IGNORECASE,
        ):
            return True

        if re.search(
            r"\bstandalone\s*:\s*false\b",
            decorator_body,
            flags=re.IGNORECASE,
        ):
            return False

        if re.search(
            r"\bimports\s*:",
            decorator_body,
            flags=re.IGNORECASE,
        ):
            return True

        if (
            angular_major is not None
            and angular_major >= 19
        ):
            return True

        return False

    # ======================================================
    # Angular version evidence
    # ======================================================

    def _detect_angular_major_version(
        self,
        changed_files: list[ChangedFile],
    ) -> int | None:
        """
        Detect @angular/core major version from
        package.json when available.
        """

        for changed_file in changed_files:

            normalized_path = (
                changed_file.file_path
                .strip()
                .lower()
                .replace("\\", "/")
            )

            file_name = (
                normalized_path
                .split("/")[-1]
            )

            if file_name != "package.json":
                continue

            content = changed_file.full_content

            if not content:
                continue

            match = (
                self.ANGULAR_CORE_VERSION_PATTERN.search(
                    content
                )
            )

            if match is None:
                continue

            try:
                return int(
                    match.group(
                        "major"
                    )
                )

            except ValueError:
                return None

        return None

    # ======================================================
    # Test file detection
    # ======================================================

    @classmethod
    def _is_test_file(
        cls,
        file_path: str,
    ) -> bool:
        """
        Return True for common test/spec naming
        conventions.
        """

        normalized = (
            file_path
            .strip()
            .lower()
            .replace("\\", "/")
        )

        path_parts = set(
            normalized.split("/")[:-1]
        )

        if (
            "test" in path_parts
            or "tests" in path_parts
            or "__tests__" in path_parts
            or "spec" in path_parts
            or "specs" in path_parts
        ):
            return True

        file_name = (
            normalized
            .split("/")[-1]
        )

        return any(
            marker in file_name
            for marker
            in cls.TEST_FILE_MARKERS
        )