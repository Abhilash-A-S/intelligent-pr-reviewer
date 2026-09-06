import re

from pr_reviewer.context.models import (
    RepositoryContext,
)
from pr_reviewer.review.models import (
    ChangedFile,
    Finding,
)


class ExpressFactValidator:
    """
    Validates AI findings against deterministic Express
    framework semantics.

    This validator is intentionally evidence-driven.

    Repository-level framework detection is not enough
    for Express validation because repositories can contain
    more than one runtime/framework.

    Example:

    An Angular SSR application may have:

        Angular frontend
        +
        Express server.ts

    Therefore Express validation uses evidence from the
    actual changed file rather than requiring the repository
    framework itself to be "express".

    Current validation:

    - Promise .catch(next) is valid Express error
      propagation.

    The validator does not attempt to implement a complete
    Express static analyzer.
    """

    # ======================================================
    # .catch(next) findings
    # ======================================================

    CATCH_NEXT_RULE_TERMS = (
        "catch-next",
        "async-catch",
        "catch-all-error",
        "async-catch-all-error",
        "express-error-handling",
        "express-next-error",
        "error-propagation",
    )

    CATCH_NEXT_MESSAGE_PATTERNS = (
        r"""
        \.
        catch
        \s*
        \(
        \s*
        next
        \s*
        \)
        .*?
        \bmask
        """,

        r"""
        \bcatch
        \s*
        \(
        \s*
        next
        \s*
        \)
        .*?
        \bincorrect
        """,

        r"""
        \bcatch
        \s*
        \(
        \s*
        next
        \s*
        \)
        .*?
        \bnot\s+recommended
        """,

        r"""
        \bcatch
        \s*
        \(
        \s*
        next
        \s*
        \)
        .*?
        \bhide
        """,

        r"""
        \bcatch
        \s*
        \(
        \s*
        next
        \s*
        \)
        .*?
        \bdebug
        """,
    )

    # ======================================================
    # Express evidence
    # ======================================================

    EXPRESS_EVIDENCE_PATTERNS = (
        # ES module import
        r"""
        \bfrom
        \s+
        ["']
        express
        ["']
        """,

        # CommonJS
        r"""
        \brequire
        \s*
        \(
        \s*
        ["']
        express
        ["']
        \s*
        \)
        """,

        # express()
        r"""
        \bexpress
        \s*
        \(
        """,

        # Express types
        r"""
        \bNextFunction\b
        """,

        r"""
        \bRequestHandler\b
        """,

        r"""
        \bRequest\b
        \s*
        ,
        \s*
        \bResponse\b
        """,
    )

    CATCH_NEXT_PATTERN = re.compile(
        r"""
        \.
        catch
        \s*
        \(
        \s*
        next
        \s*
        \)
        """,
        re.IGNORECASE
        | re.VERBOSE,
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
        Validate a finding against known Express facts.

        Returns:

            []

        when the validator has no deterministic reason
        to reject the finding.

        Returns one or more rejection reasons when the
        finding contradicts known Express semantics.

        changed_files and repository_context are part of
        the common framework-validator interface. They are
        intentionally accepted even though the current
        Express checks need only the current file.
        """

        del changed_files
        del repository_context

        reasons: list[str] = []

        self._validate_catch_next(
            finding=finding,
            changed_file=changed_file,
            reasons=reasons,
        )

        return reasons

    # ======================================================
    # .catch(next)
    # ======================================================

    def _validate_catch_next(
        self,
        finding: Finding,
        changed_file: ChangedFile,
        reasons: list[str],
    ) -> None:
        """
        Reject findings claiming that .catch(next) itself
        masks, hides, or incorrectly handles errors in an
        Express request path.

        In Express, forwarding an error through next(error)
        is the normal mechanism for handing the error to
        error-handling middleware.

        Therefore:

            promise.catch(next)

        is not automatically an error-handling defect.

        We reject only when:

        1. The finding is actually about catch(next).
        2. The current file has Express evidence.
        3. The current source actually contains catch(next).
        """

        if not self._looks_like_catch_next_claim(
            finding
        ):
            return

        content = changed_file.full_content

        if not content:
            return

        if not self._has_express_evidence(
            content
        ):
            return

        if (
            self.CATCH_NEXT_PATTERN.search(
                content
            )
            is None
        ):
            return

        reasons.append(
            (
                "Finding contradicts Express error "
                "propagation semantics: .catch(next) "
                "forwards a rejected promise to Express "
                "error-handling middleware and does not "
                "by itself mask or swallow the error."
            )
        )

    # ======================================================
    # Finding recognition
    # ======================================================

    def _looks_like_catch_next_claim(
        self,
        finding: Finding,
    ) -> bool:
        """
        Recognize the semantic family of Express
        catch(next) findings.

        We intentionally do not depend on one exact LLM
        rule ID because model-generated identifiers can
        change between runs.
        """

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

        # --------------------------------------------------
        # Strongest signal:
        #
        # The finding literally discusses .catch(next).
        # --------------------------------------------------

        compact_text = re.sub(
            r"\s+",
            "",
            normalized_text,
        )

        if (
            ".catch(next)" in compact_text
            or "catch(next)" in compact_text
        ):
            return True

        # --------------------------------------------------
        # Rule-family signal
        # --------------------------------------------------

        if any(
            term in rule_id
            for term
            in self.CATCH_NEXT_RULE_TERMS
        ):
            return True

        # --------------------------------------------------
        # Natural-language signal
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
            in self.CATCH_NEXT_MESSAGE_PATTERNS
        )

    # ======================================================
    # Express source evidence
    # ======================================================

    def _has_express_evidence(
        self,
        content: str,
    ) -> bool:
        """
        Determine whether the current source provides
        reasonable evidence that Express APIs are being
        used.

        This avoids treating every JavaScript/TypeScript
        function named "next" as Express middleware.
        """

        if not content:
            return False

        return any(
            re.search(
                pattern,
                content,
                flags=(
                    re.IGNORECASE
                    | re.MULTILINE
                    | re.VERBOSE
                ),
            )
            is not None
            for pattern
            in self.EXPRESS_EVIDENCE_PATTERNS
        )

    # ======================================================
    # Helpers
    # ======================================================

    @staticmethod
    def _finding_text(
        finding: Finding,
    ) -> str:
        """
        Combine finding message and suggestion for
        semantic-family recognition.
        """

        return " ".join(
            part
            for part in (
                finding.message,
                finding.suggestion or "",
            )
            if part
        )