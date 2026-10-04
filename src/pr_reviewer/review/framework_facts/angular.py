import json
import re

from pr_reviewer.context.models import (
    RepositoryContext,
)
from pr_reviewer.review.models import (
    ChangedFile,
    Finding,
)


class AngularFactValidator:
    """
    Validates AI findings against deterministic Angular
    framework evidence and known Angular semantics.

    This validator is intentionally conservative.

    It rejects a finding only when available repository
    evidence proves that the finding contradicts Angular
    behavior.

    Current checks:

    1. Angular TestBed / standalone component imports.
    2. Angular 19+ standalone-by-default behavior.
    3. Angular / TypeScript compatibility.
    4. provideRouter(...) inside ApplicationConfig.providers.
    5. Empty Angular Routes arrays.
    6. Invalid project/package-name vs folder-name claims.
    7. Optional withComponentInputBinding router feature claims.
    8. Valid Angular bootstrap host element claims.

    It does NOT attempt to replace Angular ESLint,
    TypeScript compiler checks, or the LLM semantic review.
    """

    # ======================================================
    # Angular TestBed / standalone import claims
    # ======================================================

    ANGULAR_TEST_IMPORT_RULE_TERMS = (
        "testbed",
        "standalone-component-import",
        "standalone-import",
        "component-import",
        "module-import",
        "incorrect-import",
        "test-import",
        "incorrect-testbed",
        "testbed-configuration",
        "standalone-component-configuration",
        "component-test-configuration",
    )

    ANGULAR_TEST_IMPORT_MESSAGE_PATTERNS = (
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

        # --------------------------------------------------
        # Selector-vs-class misconception.
        #
        # A standalone Angular component is imported into
        # TestBed using its TypeScript class reference.
        #
        # Example:
        #
        #     imports: [App]
        #
        # The component selector is used in templates and
        # is not a replacement for the class reference.
        # --------------------------------------------------

        r"""
        \bcomponent\b
        .*?
        \b(?:should|must)\s+be\s+imported\b
        .*?
        \busing\b
        .*?
        \bselector\b
        .*?
        \binstead\s+of\b
        .*?
        \bclass(?:\s+name)?\b
        """,

        r"""
        \b(?:use|using)\b
        .*?
        \bcomponent(?:'s)?\s+selector\b
        .*?
        \binstead\s+of\b
        .*?
        \bcomponent(?:'s)?\s+class(?:\s+name)?\b
        """,

        r"""
        \bselector\b
        .*?
        \binstead\s+of\b
        .*?
        \bclass(?:\s+name)?\b
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

    # ======================================================
    # Angular / TypeScript compatibility
    # ======================================================

    TYPESCRIPT_COMPATIBILITY_RULE_TERMS = (
        "typescript-version",
        "typescript-compatibility",
        "typescript-incompatibility",
        "typescript-version-incompatibility",
        "angular-typescript",
        "angular-version-compatibility",
    )

    TYPESCRIPT_COMPATIBILITY_MESSAGE_PATTERNS = (
        r"\btypescript\b.*\bnot\s+compatible\b",
        r"\btypescript\b.*\bincompatible\b",
        r"\bangular\b.*\brequires\b.*\btypescript\b",
        r"\btypescript\b.*\bunsupported\b",
        r"\btypescript\s+version\b.*\bangular\b",
    )

    # Conservative compatibility ranges.
    #
    # The validator rejects only when the current versions
    # are clearly known to be compatible.
    #
    # Format:
    #
    # Angular major:
    #     minimum TypeScript inclusive
    #     maximum TypeScript exclusive

    TYPESCRIPT_SAFE_RANGES = {
        18: (
            (5, 4, 0),
            (5, 6, 0),
        ),
        19: (
            (5, 5, 0),
            (5, 9, 0),
        ),
        20: (
            (5, 8, 0),
            (6, 0, 0),
        ),
    }

    # ======================================================
    # provideRouter
    # ======================================================

    PROVIDE_ROUTER_RULE_TERMS = (
        "provide-router",
        "provider-router",
        "router-provider",
        "provide-router-misuse",
        "provide-router-incorrect",
        "angular-router-provide-router",
    )

    PROVIDE_ROUTER_MESSAGE_PATTERNS = (
        r"\bproviderouter\b.*\boutside\b.*\bproviders\b",
        r"\bproviderouter\b.*\bshould\s+not\b.*\bproviders\b",
        r"\bproviderouter\b.*\bincorrect\b",
        r"\bproviderouter\b.*\bmisuse\b",
        r"\bmove\b.*\bproviderouter\b.*\boutside\b",
    )

    PROVIDE_ROUTER_IN_PROVIDERS_PATTERN = re.compile(
        r"""
        providers
        \s*:
        \s*
        \[
        (?P<body>.*?)
        provideRouter
        \s*
        \(
        """,
        re.IGNORECASE
        | re.DOTALL
        | re.VERBOSE,
    )

    # ======================================================
    # Empty Angular routes
    # ======================================================

    EMPTY_ROUTES_RULE_TERMS = (
        "empty-routes",
        "empty-route",
        "missing-routes",
        "routes-empty",
        "no-routes",
    )

    EMPTY_ROUTES_MESSAGE_PATTERNS = (
        r"\broutes\s+array\s+is\s+empty\b",
        r"\broutes\s+are\s+empty\b",
        r"\bno\s+routes\s+(?:are\s+)?defined\b",
        r"\badd\s+at\s+least\s+one\s+route\b",
        r"\bempty\s+routing\s+configuration\b",
    )

    EMPTY_ROUTES_PATTERN = re.compile(
        r"""
        (?:
            export
            \s+
        )?
        const
        \s+
        [A-Za-z_$][A-Za-z0-9_$]*
        \s*
        :
        \s*
        Routes
        \s*
        =
        \s*
        \[
        \s*
        \]
        \s*
        ;?
        """,
        re.IGNORECASE
        | re.MULTILINE
        | re.VERBOSE,
    )

    # ======================================================
    # Project/package name vs folder name
    # ======================================================

    PROJECT_NAME_FOLDER_RULE_TERMS = (
        "project-name-must-match-folder",
        "project-name-folder-mismatch",
        "project-folder-name",
        "package-name-folder",
        "package-name-must-match-folder",
        "angular-project-name-must-match-folder",
        "angular-project-name-must-match-folder-name",
    )

    PROJECT_NAME_FOLDER_MESSAGE_PATTERNS = (
        r"""
        \bproject\s+name\b
        .*?
        \bdoes\s+not\s+match\b
        .*?
        \bfolder\s+name\b
        """,

        r"""
        \bproject\s+name\b
        .*?
        \bmust\s+match\b
        .*?
        \bfolder\s+name\b
        """,

        r"""
        \bproject\s+name\b
        .*?
        \bshould\s+match\b
        .*?
        \bfolder\s+name\b
        """,

        r"""
        \bpackage\s+name\b
        .*?
        \bdoes\s+not\s+match\b
        .*?
        \bfolder\s+name\b
        """,

        r"""
        \bpackage\s+name\b
        .*?
        \bmust\s+match\b
        .*?
        \bfolder\s+name\b
        """,

        r"""
        \bpackage\s+name\b
        .*?
        \bshould\s+match\b
        .*?
        \bfolder\s+name\b
        """,
    )

    # ======================================================
    # Optional withComponentInputBinding router feature
    # ======================================================

    COMPONENT_INPUT_BINDING_RULE_TERMS = (
        "with-component-input-binding",
        "component-input-binding",
        "withcomponentinputbinding",
        "missing-dependency-injection",
    )

    COMPONENT_INPUT_BINDING_MESSAGE_PATTERNS = (
        r"\bwithcomponentinputbindings?\b.*?\b(?:missing|required|recommended|must|should)\b",
        r"\b(?:missing|required|recommended|must|should)\b.*?\bwithcomponentinputbindings?\b",
    )

    # ======================================================
    # Angular bootstrap host elements
    # ======================================================

    BOOTSTRAP_HOST_RULE_TERMS = (
        "angular-template-syntax",
        "angular-root-component",
        "bootstrap-host",
        "root-component-host",
    )

    BOOTSTRAP_HOST_MESSAGE_PATTERNS = (
        r"\bwithout\s+proper\s+angular\s+component\s+interaction\b",
        r"\bnot\s+properly\s+defined\b",
        r"\bensure\b.*?\bproperly\s+defined\b",
        r"\bhost\s+element\b.*?\b(?:invalid|incorrect|unsupported)\b",
    )

    HTML_TAG_PATTERN = re.compile(
        r"<\s*(?P<tag>[a-z][a-z0-9-]*)\b",
        re.IGNORECASE,
    )

    COMPONENT_SELECTOR_PATTERN = re.compile(
        r"\bselector\s*:\s*['\"](?P<selector>[a-z][a-z0-9-]*)['\"]",
        re.IGNORECASE,
    )

    # ======================================================
    # Public API
    # ======================================================

    def validate(
        self,
        finding: Finding,
        changed_file: ChangedFile,
        changed_files: list[ChangedFile],
        repository_context: RepositoryContext | None,
    ) -> list[str]:
        """
        Validate an AI finding against deterministic
        Angular evidence.

        Returns an empty list when no deterministic reason
        exists to reject the finding.
        """

        if repository_context is None:
            return []

        # Resolve the framework for the file's owning project
        # first. This prevents Angular facts from leaking into
        # React/Vue/Express/etc. projects inside a monorepo.
        framework = repository_context.resolve_file_context(
            changed_file.file_path
        ).framework.strip().lower()

        if framework != "angular":
            return []

        reasons: list[str] = []

        self._validate_testbed_import(
            finding=finding,
            changed_file=changed_file,
            changed_files=changed_files,
            reasons=reasons,
        )

        self._validate_typescript_compatibility(
            finding=finding,
            changed_files=changed_files,
            reasons=reasons,
        )

        self._validate_provide_router(
            finding=finding,
            changed_file=changed_file,
            reasons=reasons,
        )

        self._validate_empty_routes(
            finding=finding,
            changed_file=changed_file,
            reasons=reasons,
        )

        self._validate_project_name_folder_claim(
            finding=finding,
            changed_file=changed_file,
            reasons=reasons,
        )

        self._validate_component_input_binding_claim(
            finding=finding,
            changed_file=changed_file,
            reasons=reasons,
        )

        self._validate_bootstrap_host_claim(
            finding=finding,
            changed_file=changed_file,
            changed_files=changed_files,
            reasons=reasons,
        )

        self._validate_application_config_claim(
            finding=finding, changed_file=changed_file, reasons=reasons,
        )

        self._validate_httpclient_subscription_cleanup_claim(
            finding=finding, changed_file=changed_file, reasons=reasons,
        )

        return reasons


    def _validate_httpclient_subscription_cleanup_claim(
        self,
        finding: Finding,
        changed_file: ChangedFile,
        reasons: list[str],
    ) -> None:
        """Reject generic unsubscribe claims for finite Angular HttpClient requests.

        HttpClient request Observables complete after the response/error. A plain
        `http.get/post/...().subscribe()` is therefore not, by itself, evidence of
        a component-lifetime subscription leak. Long-lived sources such as
        interval(), Subjects, router/event streams, sockets, etc. remain eligible
        for lifecycle analysis.
        """
        rule_id = (finding.rule_id or "").strip().lower()
        if rule_id not in {
            "subscription-cleanup",
            "resource-cleanup",
            "rxjs-subscription-without-cleanup",
        }:
            return

        path = changed_file.file_path.replace("\\", "/").lower()
        if not path.endswith(".ts"):
            return

        content = changed_file.full_content or ""
        if not content or "HttpClient" not in content:
            return

        # Resolve class-member names that are actually HttpClient instances.
        member_names = set(
            re.findall(
                r"(?:(?:private|public|protected|readonly|override)\s+)+"
                r"([A-Za-z_$][A-Za-z0-9_$]*)\s*:\s*HttpClient\b",
                content,
            )
        )
        member_names.update(
            re.findall(
                r"(?:this\.)?([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*inject\(\s*HttpClient\s*\)",
                content,
            )
        )
        if not member_names:
            return

        lines = content.splitlines()
        if not (1 <= finding.line_number <= len(lines)):
            return

        start = max(0, finding.line_number - 1 - 8)
        end = min(len(lines), finding.line_number + 3)
        window = "\n".join(lines[start:end])
        http_methods = r"(?:get|post|put|patch|delete|head|options|request)"
        finite_http_call = any(
            re.search(
                rf"\bthis\s*\.\s*{re.escape(name)}\s*\.\s*{http_methods}\s*\(",
                window,
                flags=re.IGNORECASE,
            )
            for name in member_names
        )
        if finite_http_call and re.search(r"\.\s*subscribe\s*\(", window):
            reasons.append(
                "Angular HttpClient request Observables are finite and complete after the response/error; this source does not prove a subscription-lifecycle leak."
            )

    def _validate_application_config_claim(
        self, finding: Finding, changed_file: ChangedFile, reasons: list[str]
    ) -> None:
        path = changed_file.file_path.replace("\\", "/").lower()
        if not path.endswith("app.config.ts"):
            return
        content = changed_file.full_content or ""
        if "ApplicationConfig" not in content:
            return
        text = " ".join(
            part for part in (finding.rule_id, finding.message, finding.suggestion or "") if part
        ).lower()
        generic_error_claim = (
            "error-handling" in text
            or "exception-handling" in text
            or ("applicationconfig" in text and "error" in text)
        )
        if generic_error_claim and not re.search(r"\b(?:throw|catch|promise|subscribe|http)\b", content, re.I):
            reasons.append(
                "ApplicationConfig is declarative provider configuration; this file contains no fallible operation requiring generic runtime error handling."
            )

    # ======================================================
    # TestBed / standalone component
    # ======================================================

    def _validate_testbed_import(
        self,
        finding: Finding,
        changed_file: ChangedFile,
        changed_files: list[ChangedFile],
        reasons: list[str],
    ) -> None:

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

    def _looks_like_invalid_testbed_import_claim(
        self,
        finding: Finding,
    ) -> bool:

        rule_id = (
            finding.rule_id
            .strip()
            .lower()
        )

        text = self._finding_text(
            finding
        )

        normalized_text = (
            text
            .strip()
            .lower()
        )

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

        # --------------------------------------------------
        # Explicit TestBed import claim
        # --------------------------------------------------

        if (
            has_testbed_signal
            and has_import_signal
            and has_component_or_module_signal
        ):
            return True

        # --------------------------------------------------
        # Known Angular/TestBed rule terminology
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
        # Standalone class-import misconception independent of rule ID.
        # Example hallucination: "Using App directly in imports is incorrect;
        # standalone components should be imported using their names, not the
        # component class." In TestBed, the TypeScript class reference is exactly
        # what belongs in `imports`.
        # --------------------------------------------------

        standalone_class_import_misconception = (
            "standalone" in normalized_text
            and has_import_signal
            and ("class" in normalized_text or "component class" in normalized_text)
            and any(
                term in normalized_text
                for term in (
                    "incorrect",
                    "should be imported",
                    "not the component class",
                    "using their names",
                    "using its name",
                )
            )
        )
        if standalone_class_import_misconception:
            return True

        # Broad semantic contradiction: when the evidence is a TestBed
        # imports entry and the component is proven standalone, wording such as
        # "imported directly is not the correct usage" is still the same false
        # framework claim even if the LLM labels it duplicate-logic/api-misuse.
        standalone_direct_import_wrong_claim = (
            "standalone" in normalized_text
            and has_import_signal
            and any(
                phrase in normalized_text
                for phrase in (
                    "not correct",
                    "incorrect",
                    "invalid",
                    "not valid",
                    "not recommended",
                    "imported directly",
                    "correct usage",
                    "correct syntax",
                    "should be imported as a standalone",
                )
            )
        )
        if standalone_direct_import_wrong_claim:
            return True

        # TestBed is a test harness, not component metadata. A component class
        # listed once in TestBed imports is therefore not "importing itself".
        # Match the semantic contradiction rather than a specific rule ID so
        # duplicate-logic/api-misuse/maintainability wording is handled equally.
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
        # Selector-vs-class misconception
        # --------------------------------------------------
        #
        # A standalone Angular component belongs in
        # TestBed imports as its TypeScript class:
        #
        #     imports: [App]
        #
        # A selector such as "app-root" belongs in a
        # template and is not a replacement for App.
        #
        # Rule IDs generated by an LLM are unstable.
        # Therefore this detects the underlying semantic
        # claim instead of depending on one exact ID.
        # --------------------------------------------------

        has_selector_signal = (
            "selector" in normalized_text
        )

        has_class_signal = (
            "class" in normalized_text
            or "class name" in normalized_text
        )

        has_instead_signal = (
            "instead" in normalized_text
            or "rather than" in normalized_text
            or "replace" in normalized_text
        )

        if (
            has_import_signal
            and has_component_or_module_signal
            and has_selector_signal
            and has_class_signal
            and has_instead_signal
        ):
            return True

        # --------------------------------------------------
        # Regex-based semantic recognition
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

    def _extract_testbed_import_identifiers(
        self,
        changed_file: ChangedFile,
    ) -> list[str]:

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

        # Component-level imports are standalone-component
        # configuration evidence.
        if re.search(
            r"\bimports\s*:",
            decorator_body,
            flags=re.IGNORECASE,
        ):
            return True

        # Angular 19+ components are standalone by default
        # unless explicitly marked standalone: false.
        if (
            angular_major is not None
            and angular_major >= 19
        ):
            return True

        return False

    # ======================================================
    # Angular / TypeScript compatibility
    # ======================================================

    def _validate_typescript_compatibility(
        self,
        finding: Finding,
        changed_files: list[ChangedFile],
        reasons: list[str],
    ) -> None:

        if not self._looks_like_typescript_compatibility_claim(
            finding
        ):
            return

        package_data = (
            self._load_package_json(
                changed_files
            )
        )

        if package_data is None:
            return

        angular_version = (
            self._get_dependency_version(
                package_data=package_data,
                dependency_name="@angular/core",
            )
        )

        typescript_version = (
            self._get_dependency_version(
                package_data=package_data,
                dependency_name="typescript",
            )
        )

        if not angular_version:
            return

        if not typescript_version:
            return

        angular_tuple = (
            self._extract_version_tuple(
                angular_version
            )
        )

        typescript_tuple = (
            self._extract_version_tuple(
                typescript_version
            )
        )

        if angular_tuple is None:
            return

        if typescript_tuple is None:
            return

        angular_major = angular_tuple[0]

        supported_range = (
            self.TYPESCRIPT_SAFE_RANGES.get(
                angular_major
            )
        )

        if supported_range is None:
            return

        minimum, maximum = supported_range

        if (
            typescript_tuple >= minimum
            and typescript_tuple < maximum
        ):
            reasons.append(
                (
                    "Finding contradicts Angular/TypeScript "
                    "compatibility evidence: "
                    f"Angular {angular_version} and "
                    f"TypeScript {typescript_version} are "
                    "within a supported compatibility range."
                )
            )

    def _looks_like_typescript_compatibility_claim(
        self,
        finding: Finding,
    ) -> bool:

        rule_id = (
            finding.rule_id
            .strip()
            .lower()
        )

        if any(
            term in rule_id
            for term
            in self.TYPESCRIPT_COMPATIBILITY_RULE_TERMS
        ):
            return True

        text = self._finding_text(
            finding
        )

        return any(
            re.search(
                pattern,
                text,
                flags=re.IGNORECASE,
            )
            is not None
            for pattern
            in self.TYPESCRIPT_COMPATIBILITY_MESSAGE_PATTERNS
        )

    # ======================================================
    # provideRouter
    # ======================================================

    def _validate_provide_router(
        self,
        finding: Finding,
        changed_file: ChangedFile,
        reasons: list[str],
    ) -> None:

        if not self._looks_like_provide_router_claim(
            finding
        ):
            return

        content = changed_file.full_content

        if not content:
            return

        if "provideRouter" not in content:
            return

        if not re.search(
            r"\bApplicationConfig\b",
            content,
        ):
            return

        if (
            self.PROVIDE_ROUTER_IN_PROVIDERS_PATTERN.search(
                content
            )
            is None
        ):
            return

        reasons.append(
            (
                "Finding contradicts Angular provider "
                "configuration semantics: "
                "provideRouter(...) is valid inside "
                "ApplicationConfig.providers."
            )
        )

    def _looks_like_provide_router_claim(
        self,
        finding: Finding,
    ) -> bool:

        rule_id = (
            finding.rule_id
            .strip()
            .lower()
        )

        if any(
            term in rule_id
            for term
            in self.PROVIDE_ROUTER_RULE_TERMS
        ):
            return True

        text = self._finding_text(
            finding
        )

        return any(
            re.search(
                pattern,
                text,
                flags=re.IGNORECASE,
            )
            is not None
            for pattern
            in self.PROVIDE_ROUTER_MESSAGE_PATTERNS
        )

    # ======================================================
    # Empty Angular routes
    # ======================================================

    def _validate_empty_routes(
        self,
        finding: Finding,
        changed_file: ChangedFile,
        reasons: list[str],
    ) -> None:

        if not self._looks_like_empty_routes_claim(
            finding
        ):
            return

        content = changed_file.full_content

        if not content:
            return

        if (
            self.EMPTY_ROUTES_PATTERN.search(
                content
            )
            is None
        ):
            return

        reasons.append(
            (
                "Finding treats an empty Angular Routes "
                "array as a defect, but an empty route "
                "configuration is valid and does not by "
                "itself prove broken navigation."
            )
        )

    def _looks_like_empty_routes_claim(
        self,
        finding: Finding,
    ) -> bool:

        rule_id = (
            finding.rule_id
            .strip()
            .lower()
        )

        if any(
            term in rule_id
            for term
            in self.EMPTY_ROUTES_RULE_TERMS
        ):
            return True

        text = self._finding_text(
            finding
        )

        return any(
            re.search(
                pattern,
                text,
                flags=re.IGNORECASE,
            )
            is not None
            for pattern
            in self.EMPTY_ROUTES_MESSAGE_PATTERNS
        )

    # ======================================================
    # Angular project/package name vs folder name
    # ======================================================

    def _validate_project_name_folder_claim(
        self,
        finding: Finding,
        changed_file: ChangedFile,
        reasons: list[str],
    ) -> None:
        """
        Reject claims that an Angular project/package name
        must match the containing directory name.

        Angular does not impose a general requirement that
        package.json "name" match the repository directory
        name.

        This also protects against incorrect reasoning where
        the LLM interprets "package.json" itself as a folder
        name.
        """

        if not self._looks_like_project_name_folder_claim(
            finding
        ):
            return

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

        # Keep this Angular fact validator conservative.
        #
        # Reject only when the claim targets Angular/package
        # metadata. Do not suppress unrelated naming findings
        # against application source files.
        if file_name not in {
            "package.json",
            "angular.json",
        }:
            return

        reasons.append(
            (
                "Finding assumes that an Angular project "
                "or package name must match its containing "
                "folder name, but Angular does not impose "
                "that requirement."
            )
        )

    def _looks_like_project_name_folder_claim(
        self,
        finding: Finding,
    ) -> bool:

        rule_id = (
            finding.rule_id
            .strip()
            .lower()
        )

        if any(
            term in rule_id
            for term
            in self.PROJECT_NAME_FOLDER_RULE_TERMS
        ):
            return True

        text = self._finding_text(
            finding
        )

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
            in self.PROJECT_NAME_FOLDER_MESSAGE_PATTERNS
        )

    # ======================================================
    # Optional withComponentInputBinding router feature
    # ======================================================

    def _validate_component_input_binding_claim(
        self,
        finding: Finding,
        changed_file: ChangedFile,
        reasons: list[str],
    ) -> None:
        """
        Reject claims that withComponentInputBinding() is a
        mandatory companion to provideRouter().

        withComponentInputBinding() enables an optional router
        feature. Standalone components do not require it merely
        because provideRouter(routes) is used.
        """

        if not self._looks_like_component_input_binding_claim(
            finding
        ):
            return

        content = changed_file.full_content or ""

        if not content:
            return

        if "provideRouter" not in content:
            return

        reasons.append(
            (
                "Finding treats withComponentInputBinding() "
                "as required by provideRouter() or standalone "
                "components, but it is an optional Angular "
                "Router feature."
            )
        )

    def _looks_like_component_input_binding_claim(
        self,
        finding: Finding,
    ) -> bool:

        rule_id = (
            finding.rule_id
            .strip()
            .lower()
        )

        text = self._finding_text(
            finding
        )

        normalized_text = (
            text
            .strip()
            .lower()
        )

        # Require the optional Angular API itself to be named.
        # This prevents a generic rule such as
        # "missing-dependency-injection" from being rejected
        # unless the finding actually makes this misconception.
        has_api_signal = (
            "withcomponentinputbinding" in normalized_text
            or "withcomponentinputbindings" in normalized_text
            or "withcomponentinputbinding" in rule_id
        )

        if not has_api_signal:
            return False

        if any(
            term in rule_id
            for term
            in self.COMPONENT_INPUT_BINDING_RULE_TERMS
        ):
            return True

        return any(
            re.search(
                pattern,
                text,
                flags=re.IGNORECASE | re.DOTALL,
            )
            is not None
            for pattern
            in self.COMPONENT_INPUT_BINDING_MESSAGE_PATTERNS
        )

    # ======================================================
    # Angular bootstrap host elements
    # ======================================================

    def _validate_bootstrap_host_claim(
        self,
        finding: Finding,
        changed_file: ChangedFile,
        changed_files: list[ChangedFile],
        reasons: list[str],
    ) -> None:
        """
        Reject vague claims that a valid Angular component host
        element in index.html is inherently incorrect.

        Rejection requires concrete cross-file evidence:

        - the finding targets an HTML file,
        - the finding names a concrete custom element,
        - that element exists in the HTML, and
        - an Angular @Component declares the same selector.

        This keeps the rule narrow and evidence-based.
        """

        normalized_path = (
            changed_file.file_path
            .strip()
            .lower()
            .replace("\\", "/")
        )

        if not normalized_path.endswith((".html", ".htm")):
            return

        if not self._looks_like_bootstrap_host_claim(
            finding
        ):
            return

        content = changed_file.full_content or ""

        if not content:
            return

        finding_text = self._finding_text(
            finding
        )

        mentioned_tags = {
            match.group("tag").lower()
            for match in self.HTML_TAG_PATTERN.finditer(
                finding_text
            )
        }

        if not mentioned_tags:
            return

        component_selectors = (
            self._find_angular_component_selectors(
                changed_files
            )
        )

        for tag in sorted(mentioned_tags):
            if tag not in component_selectors:
                continue

            if re.search(
                rf"<\s*{re.escape(tag)}\b",
                content,
                flags=re.IGNORECASE,
            ) is None:
                continue

            reasons.append(
                (
                    "Finding contradicts Angular bootstrap-host "
                    "evidence: "
                    f"<{tag}> matches a declared Angular "
                    "component selector and is a valid host "
                    "element."
                )
            )
            return

    def _looks_like_bootstrap_host_claim(
        self,
        finding: Finding,
    ) -> bool:

        rule_id = (
            finding.rule_id
            .strip()
            .lower()
        )

        text = self._finding_text(
            finding
        )

        has_rule_signal = any(
            term in rule_id
            for term
            in self.BOOTSTRAP_HOST_RULE_TERMS
        )

        has_message_signal = any(
            re.search(
                pattern,
                text,
                flags=re.IGNORECASE | re.DOTALL,
            )
            is not None
            for pattern
            in self.BOOTSTRAP_HOST_MESSAGE_PATTERNS
        )

        return (
            has_rule_signal
            and has_message_signal
        )

    def _find_angular_component_selectors(
        self,
        changed_files: list[ChangedFile],
    ) -> set[str]:

        selectors: set[str] = set()

        for changed_file in changed_files:
            content = changed_file.full_content or ""

            if "@Component" not in content:
                continue

            for component_match in (
                self.ANGULAR_COMPONENT_DECORATOR.finditer(
                    content
                )
            ):
                decorator_body = (
                    component_match.group("body")
                )

                selector_match = (
                    self.COMPONENT_SELECTOR_PATTERN.search(
                        decorator_body
                    )
                )

                if selector_match is None:
                    continue

                selectors.add(
                    selector_match.group("selector").lower()
                )

        return selectors

    # ======================================================
    # package.json / version helpers
    # ======================================================

    @staticmethod
    def _load_package_json(
        changed_files: list[ChangedFile],
    ) -> dict | None:

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
                return None

            try:
                data = json.loads(
                    content
                )

            except (
                json.JSONDecodeError,
                TypeError,
            ):
                return None

            if isinstance(
                data,
                dict,
            ):
                return data

            return None

        return None

    @staticmethod
    def _get_dependency_version(
        package_data: dict,
        dependency_name: str,
    ) -> str | None:

        sections = (
            "dependencies",
            "devDependencies",
            "peerDependencies",
            "optionalDependencies",
        )

        for section_name in sections:

            section = package_data.get(
                section_name
            )

            if not isinstance(
                section,
                dict,
            ):
                continue

            value = section.get(
                dependency_name
            )

            if isinstance(
                value,
                str,
            ):
                return value

        return None

    @staticmethod
    def _extract_version_tuple(
        version: str,
    ) -> tuple[int, int, int] | None:

        match = re.search(
            r"""
            (?<!\d)
            (?P<major>\d+)
            \.
            (?P<minor>\d+)
            (?:
                \.
                (?P<patch>\d+)
            )?
            """,
            version,
            flags=re.VERBOSE,
        )

        if match is None:
            return None

        try:
            major = int(
                match.group(
                    "major"
                )
            )

            minor = int(
                match.group(
                    "minor"
                )
            )

            patch_text = (
                match.group(
                    "patch"
                )
            )

            patch = (
                int(patch_text)
                if patch_text is not None
                else 0
            )

        except ValueError:
            return None

        return (
            major,
            minor,
            patch,
        )

    def _detect_angular_major_version(
        self,
        changed_files: list[ChangedFile],
    ) -> int | None:

        package_data = (
            self._load_package_json(
                changed_files
            )
        )

        if package_data is None:
            return None

        angular_version = (
            self._get_dependency_version(
                package_data=package_data,
                dependency_name="@angular/core",
            )
        )

        if not angular_version:
            return None

        version_tuple = (
            self._extract_version_tuple(
                angular_version
            )
        )

        if version_tuple is None:
            return None

        return version_tuple[0]

    # ======================================================
    # Test file detection
    # ======================================================

    @classmethod
    def _is_test_file(
        cls,
        file_path: str,
    ) -> bool:

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

    # ======================================================
    # Common helper
    # ======================================================

    @staticmethod
    def _finding_text(
        finding: Finding,
    ) -> str:

        return " ".join(
            part
            for part in (
                finding.message,
                finding.suggestion or "",
            )
            if part
        )
