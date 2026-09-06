import re
from dataclasses import dataclass, field

from pr_reviewer.review.models import (
    ChangedFile,
    Finding,
)


@dataclass
class TestEvidenceValidationResult:
    __test__ = False
    """
    Result returned by deterministic test-evidence
    validation.

    accepted:
        True when the finding is not contradicted by
        available test evidence.

    reasons:
        Reasons explaining why the finding should be
        rejected.
    """

    accepted: bool

    reasons: list[str] = field(
        default_factory=list
    )


class TestEvidenceValidator:
    """
    Validates AI-generated findings for test files.

    The goal is not to replace a test framework or
    coverage tool.

    This layer protects against common LLM false positives
    in tests where the model turns normal test behavior
    into a defect.

    Current protections:

    1. Do not require async stabilization when the test
       does not provide evidence that asynchronous work
       must finish before the assertion.

    2. Do not report that a test "assumes" an element
       exists merely because the test intentionally asserts
       against that element.

    3. Preserve findings when concrete async evidence
       exists.

    4. Preserve unrelated test findings.

    The validator is intentionally conservative.
    """

    TEST_FILE_MARKERS = (
        ".spec.",
        ".test.",
        "_test.",
        "_tests.",
    )

    # ======================================================
    # Async-wait findings
    # ======================================================

    ASYNC_WAIT_RULE_TERMS = (
        "async-wait",
        "async-waiting",
        "missing-wait",
        "missing-async-wait",
        "wait-for-stability",
        "when-stable",
        "fixture-when-stable",
        "async-stability",
    )

    ASYNC_WAIT_MESSAGE_PATTERNS = (
        r"\bwait\s+for\b.*\binitial",
        r"\bwait\s+for\b.*\bstable",
        r"\bwhenstable\b",
        r"\bwhenStable\b",
        r"\bcomponent\s+to\s+be\s+initialized\b",
        r"\bshould\s+wait\b.*\bassert",
        r"\bmissing\b.*\bawait\b",
    )

    # Evidence that a test genuinely contains asynchronous
    # behavior which may require stabilization/waiting.
    ASYNC_BEHAVIOR_PATTERNS = (
        r"\bawait\b",
        r"\basync\b",
        r"\bPromise\b",
        r"\bsetTimeout\b",
        r"\bsetInterval\b",
        r"\bfixture\.whenStable\s*\(",
        r"\bfakeAsync\s*\(",
        r"\btick\s*\(",
        r"\bflush\s*\(",
        r"\bflushMicrotasks\s*\(",
        r"\bwaitForAsync\s*\(",
        r"\bfirstValueFrom\s*\(",
        r"\blastValueFrom\s*\(",
        r"\bsubscribe\s*\(",
        r"\bObservable\b",
    )

    # ======================================================
    # Assertion-target findings
    # ======================================================

    ASSERTION_TARGET_RULE_TERMS = (
        "content-selector",
        "selector-assumption",
        "element-assumption",
        "missing-element-check",
        "dom-element-assumption",
        "assertion-selector",
    )

    ASSERTION_TARGET_MESSAGE_PATTERNS = (
        r"\btest\s+assumes\b.*\belement\b",
        r"\bassumes\s+the\s+presence\b",
        r"\bcould\s+fail\s+if\b.*\belement\b",
        r"\bcheck\s+if\b.*\belement\b.*\bbefore\b",
        r"\bqueryselector\b.*\bcould\s+fail\b",
        r"\bensure\b.*\belement\s+exists\b.*\bbefore\b",
    )

    ASSERTION_PATTERNS = (
        r"\bexpect\s*\(",
        r"\bassert\b",
        r"\bshould\b",
        r"\btoContain\s*\(",
        r"\btoBe\s*\(",
        r"\btoEqual\s*\(",
        r"\btoHaveTextContent\s*\(",
        r"\btoBeTruthy\s*\(",
        r"\btoBeFalsy\s*\(",
    )

    SELECTOR_PATTERNS = (
        r"\bquerySelector\s*\(",
        r"\bquerySelectorAll\s*\(",
        r"\bgetByRole\s*\(",
        r"\bgetByText\s*\(",
        r"\bgetByTestId\s*\(",
        r"\bfindByRole\s*\(",
        r"\bfindByText\s*\(",
    )

    # ======================================================
    # Public API
    # ======================================================

    def validate(
        self,
        finding: Finding,
        changed_file: ChangedFile,
    ) -> TestEvidenceValidationResult:
        """
        Validate one test finding.

        Non-test files are accepted unchanged.
        """

        if not self._is_test_file(
            changed_file.file_path
        ):
            return TestEvidenceValidationResult(
                accepted=True,
                reasons=[],
            )

        reasons: list[str] = []

        self._validate_async_wait_claim(
            finding=finding,
            changed_file=changed_file,
            reasons=reasons,
        )

        self._validate_assertion_target_claim(
            finding=finding,
            changed_file=changed_file,
            reasons=reasons,
        )

        self._validate_angular_test_semantics(
            finding=finding,
            changed_file=changed_file,
            reasons=reasons,
        )

        return TestEvidenceValidationResult(
            accepted=not reasons,
            reasons=reasons,
        )

    # ======================================================
    # Async-wait validation
    # ======================================================

    def _validate_async_wait_claim(
        self,
        finding: Finding,
        changed_file: ChangedFile,
        reasons: list[str],
    ) -> None:
        """
        Reject generic "you must wait before asserting"
        findings when the supplied test does not contain
        evidence that asynchronous work is actually pending.

        This intentionally does NOT reject the finding when
        async evidence exists.
        """

        if not self._looks_like_async_wait_claim(
            finding
        ):
            return

        content = self._content(
            changed_file
        )

        if not content:
            return

        if self._contains_async_behavior(
            content
        ):
            return

        reasons.append(
            (
                "Finding requires asynchronous waiting "
                "without concrete async evidence in the "
                "test. A test does not automatically need "
                "fixture.whenStable() or another wait before "
                "making assertions."
            )
        )

    def _looks_like_async_wait_claim(
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
            for term in self.ASYNC_WAIT_RULE_TERMS
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
            for pattern in self.ASYNC_WAIT_MESSAGE_PATTERNS
        )

    def _contains_async_behavior(
        self,
        content: str,
    ) -> bool:

        return any(
            re.search(
                pattern,
                content,
                flags=re.IGNORECASE,
            )
            is not None
            for pattern in self.ASYNC_BEHAVIOR_PATTERNS
        )

    # ======================================================
    # Assertion-target validation
    # ======================================================

    def _validate_assertion_target_claim(
        self,
        finding: Finding,
        changed_file: ChangedFile,
        reasons: list[str],
    ) -> None:
        """
        Reject findings that complain merely because an
        assertion may fail if the expected element/value is
        absent.

        Assertions are allowed to fail when the expected
        behavior is not present. That is the purpose of the
        test.
        """

        if not self._looks_like_assertion_target_claim(
            finding
        ):
            return

        content = self._content(
            changed_file
        )

        if not content:
            return

        if not self._contains_assertion(
            content
        ):
            return

        if not self._contains_selector(
            content
        ):
            return

        reasons.append(
            (
                "Finding treats an intentional test "
                "assertion as a defect. A test may "
                "legitimately query an expected element "
                "and fail when that element or content is "
                "not rendered."
            )
        )

    def _looks_like_assertion_target_claim(
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
            for term in self.ASSERTION_TARGET_RULE_TERMS
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
            in self.ASSERTION_TARGET_MESSAGE_PATTERNS
        )

    def _contains_assertion(
        self,
        content: str,
    ) -> bool:

        return any(
            re.search(
                pattern,
                content,
                flags=re.IGNORECASE,
            )
            is not None
            for pattern in self.ASSERTION_PATTERNS
        )

    def _contains_selector(
        self,
        content: str,
    ) -> bool:

        return any(
            re.search(
                pattern,
                content,
                flags=re.IGNORECASE,
            )
            is not None
            for pattern in self.SELECTOR_PATTERNS
        )

    def _validate_angular_test_semantics(
        self,
        finding: Finding,
        changed_file: ChangedFile,
        reasons: list[str],
    ) -> None:
        content = self._content(changed_file)
        line = self._line_content(changed_file, finding.line_number).strip()
        text = " ".join(
            part
            for part in (
                finding.rule_id,
                finding.message,
                finding.suggestion or "",
            )
            if part
        ).lower()

        if finding.rule_id in {"null-safety", "async-issue", "error-handling"}:
            if re.match(r"^(?:it|test|describe)\s*\(", line):
                reasons.append(
                    "Test declaration text is not evidence for the claimed runtime defect."
                )
                return

        if finding.rule_id == "error-handling" and re.search(
            r"\bexpect\s*\(",
            line,
        ):
            reasons.append(
                "A test assertion line is not evidence for missing production error handling."
            )
            return

        if finding.rule_id == "async-issue":
            exact_async_evidence = re.search(
                r"\b(?:await|async|Promise|subscribe|firstValueFrom|lastValueFrom|"
                r"whenStable|fakeAsync|tick|flush|setTimeout|setInterval|Observable)\b",
                line,
            )
            if exact_async_evidence is None:
                reasons.append(
                    "Async test finding is not anchored to an asynchronous construct on the evidence line."
                )
                return

        if "compilecomponents" in text and re.search(
            r"\bawait\s+TestBed[\s\S]*?\.compileComponents\s*\(",
            content,
        ):
            reasons.append(
                "Angular TestBed compileComponents is already awaited in this test setup."
            )
            return

        if "topromise" in text:
            reasons.append(
                "The suggested RxJS toPromise API is deprecated and is not a valid correction."
            )
            return

        if "await" in text and "flush" in text and "httpMock" in content:
            reasons.append(
                "Angular HttpTestingController request flushing is synchronous and does not require await."
            )
            return

        if finding.rule_id in {"subscription-cleanup", "resource-cleanup"}:
            long_lived = re.search(
                r"\b(?:interval|timer|fromEvent|Subject|BehaviorSubject|ReplaySubject|WebSocket)\s*\(",
                content,
            )
            if not long_lived:
                reasons.append(
                    "A test-local subscription without a proven long-lived source does not establish a lifecycle leak."
                )

    @staticmethod
    def _line_content(changed_file: ChangedFile, line_number: int) -> str:
        lines = (changed_file.full_content or "").splitlines()
        if 1 <= line_number <= len(lines):
            return lines[line_number - 1]
        for line in changed_file.changed_lines:
            if line.line_number == line_number:
                return line.content
        return ""

    # ======================================================
    # Helpers
    # ======================================================

    @staticmethod
    def _content(
        changed_file: ChangedFile,
    ) -> str:

        if changed_file.full_content:
            return changed_file.full_content

        return "\n".join(
            line.content
            for line in changed_file.changed_lines
        )

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

        parts = set(
            normalized.split("/")[:-1]
        )

        if (
            "test" in parts
            or "tests" in parts
            or "__tests__" in parts
            or "spec" in parts
            or "specs" in parts
        ):
            return True

        file_name = (
            normalized
            .split("/")[-1]
        )

        return any(
            marker in file_name
            for marker in cls.TEST_FILE_MARKERS
        )

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
