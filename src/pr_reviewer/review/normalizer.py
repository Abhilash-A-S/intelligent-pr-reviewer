import re

from pr_reviewer.review.models import (
    Finding,
    FindingSource,
    Severity,
)
from pr_reviewer.review.rules import DEFAULT_RULE_REGISTRY


class FindingNormalizer:
    """
    Normalizes findings from AI, static analysis,
    security scanners, or future review sources.

    Responsibilities:
    - Standardize rule IDs.
    - Canonicalize semantically equivalent rule IDs.
    - Strip known framework/language prefixes when the
      remaining rule is a known canonical issue.
    - Enforce minimum severity policies.

    The normalizer is intentionally language-agnostic.
    """

    RULE_ALIASES = {
        # Secrets / credentials
        "security-101": "hardcoded-secret",
        "password-hardcoded": "hardcoded-secret",
        "hardcoded-password": "hardcoded-secret",
        "hardcoded-credential": "hardcoded-secret",
        "hardcoded-credentials": "hardcoded-secret",
        "embedded-secret": "hardcoded-secret",
        "embedded-credential": "hardcoded-secret",
        "security-hardcoded-secret": "hardcoded-secret",
        "exposed-secret": "hardcoded-secret",
        "credential-hardcoded": "hardcoded-secret",
        "hardcoded-token": "hardcoded-secret",
        "hardcoded-api-key": "hardcoded-secret",
        "hardcoded-jwt-secret": "hardcoded-secret",

        # Equality comparisons
        "javascript-loose-equality": "loose-equality",
        "typescript-loose-equality": "loose-equality",
        "non-strict-equality": "loose-equality",
        "non-strict-comparison": "loose-equality",
        "eqeqeq": "loose-equality",
        "loose-equality-check": "loose-equality",
        "loose-equality-operator": "loose-equality",

        # Console / debugging
        "console-log": "no-console",
        "console-statement": "no-console",
        "console-log-statement": "no-console",
        "console-logging": "no-console",
        "debug-console": "no-console",
        "console-debug": "no-console",
        "debug-statement": "debugger",
        "debugger-statement": "debugger",

        # Unused variables / constants
        "unused-var": "unused-variable",
        "unused-constant": "unused-variable",
        "unused-variable-declaration": "unused-variable",
        "unused-local-variable": "unused-variable",
        "unused-local": "unused-variable",
        "unnecessary-variable": "unused-variable",
        "unnecessary-constant": "unused-variable",
        "unnecessary-variable-declaration": "unused-variable",
        "dead-variable": "unused-variable",
        "dead-local-variable": "unused-variable",
        "unused-code": "unused-variable",

        # Unused imports
        "unused-import-statement": "unused-import",
        "unnecessary-import": "unused-import",
        "redundant-import": "unused-import",

        # Unused parameters
        "unused-argument": "unused-parameter",
        "unused-function-argument": "unused-parameter",
        "unused-function-parameter": "unused-parameter",
        "unused-method-parameter": "unused-parameter",

        # Error handling
        "missing-error-handling": "error-handling",
        "unhandled-error": "error-handling",
        "unhandled-exception": "error-handling",
        "missing-exception-handling": "error-handling",
        "json-parse": "json-parse-without-error-handling",
        "json-parse-error": "json-parse-without-error-handling",
        "json-parsing-error": "json-parse-without-error-handling",
        # LLMs frequently invent security-flavoured JSON rule names for
        # the same concrete JSON.parse failure-handling issue.  Normalize
        # the entire family before validation/deduplication so wording
        # drift cannot create a second finding.
        "unsafe-json-parse": "json-parse-without-error-handling",
        "unsafe-json-parsing": "json-parse-without-error-handling",
        "insecure-json-parse": "json-parse-without-error-handling",
        "insecure-json-parsing": "json-parse-without-error-handling",
        "json-parse-security": "json-parse-without-error-handling",
        "json-security": "json-parse-without-error-handling",
        "json-injection": "json-parse-without-error-handling",
        "exception-not-handled": "error-handling",
        "fetch-error-handling": "error-handling",
        "missing-fetch-error-handling": "error-handling",
        "no-empty-catch": "empty-catch-block",
        "empty-catch": "empty-catch-block",
        "swallowed-exception": "empty-catch-block",

        # Async
        "unhandled-promise": "async-issue",
        "missing-await": "async-issue",
        "missing-async-await": "async-issue",
        "async-await-issue": "async-issue",
        "async-error": "async-issue",

        # Null safety
        "null-reference": "null-safety",
        "null-dereference": "null-safety",
        "possible-null-reference": "null-safety",
        "none-dereference": "null-safety",
        "nil-dereference": "null-safety",

        # Timer/resource cleanup
        "setinterval": "setinterval-without-timer-reference",
        "set-interval": "setinterval-without-timer-reference",
        "setinterval-without-retaining-timer-reference": "setinterval-without-timer-reference",
        "set-interval-without-retaining-timer-reference": "setinterval-without-timer-reference",
        "setinterval-without-referencing-timer": "setinterval-without-timer-reference",
        "set-interval-without-referencing-timer": "setinterval-without-timer-reference",
        "unhandled-interval": "setinterval-without-timer-reference",
        "interval-not-cleared": "setinterval-without-timer-reference",
        "timer-not-cleared": "setinterval-without-timer-reference",

        # Global listener lifecycle
        "global-event-listener": "global-event-listener-without-removal",
        "global-listener": "global-event-listener-without-removal",
        "window-event-listener": "global-event-listener-without-removal",
        "unhandled-event-listener": "global-event-listener-without-removal",
        "event-listener-without-removal": "global-event-listener-without-removal",

        # Resource cleanup
        "resource-leak": "resource-cleanup",
        "missing-resource-cleanup": "resource-cleanup",
        "resource-not-closed": "resource-cleanup",
        "unclosed-resource": "resource-cleanup",

        # React/effect cleanup
        "missing-effect-cleanup": "effect-cleanup",
        "missing-cleanup": "effect-cleanup",
        "react-use-effect-cleanup": "effect-cleanup",
        "react-missing-effect-cleanup": "effect-cleanup",
        "react-effect-cleanup": "effect-cleanup",
        "hook-cleanup": "effect-cleanup",

        # React/effect dependency
        "react-use-effect-dependency": "effect-dependency",
        "react-hooks-missing-dependency": "effect-dependency",
        "react-empty-dependency-array": "effect-dependency",
        "missing-hook-dependency": "effect-dependency",
        "hook-dependency": "effect-dependency",

        # React DOM
        "react-direct-dom-manipulation": "direct-dom-manipulation",
        "direct-dom-access": "direct-dom-manipulation",

        # HTML / DOM injection
        "xss-vulnerability": "unsafe-inner-html",
        "dom-xss": "unsafe-inner-html",
        "unsafe-html": "unsafe-inner-html",
        "unsanitized-html": "unsafe-inner-html",

        # Subscription/listener cleanup
        "missing-unsubscribe": "subscription-cleanup",
        "subscription-leak": "subscription-cleanup",
        "unclosed-subscription": "subscription-cleanup",
        "event-listener-leak": "listener-cleanup",
        "missing-listener-cleanup": "listener-cleanup",

        # Duplicate logic
        "duplicated-code": "duplicate-logic",
        "duplicate-code": "duplicate-logic",
        "duplicated-logic": "duplicate-logic",
        "code-duplication": "duplicate-logic",

        # Performance
        "performance-issue": "performance",
        "performance-problem": "performance",
        "performance-concern": "performance",

        # Maintainability
        "code-maintainability": "maintainability",
        "maintainability-issue": "maintainability",
        "maintainability-problem": "maintainability",

        # Accessibility
        "accessibility-issue": "accessibility",
        "accessibility-problem": "accessibility",
        "a11y": "accessibility",
        "a11y-issue": "accessibility",
    }

    # Prefixes commonly invented by LLMs. We strip one or
    # more only when the remaining rule is already known.
    CONTEXT_PREFIXES = (
        "react",
        "angular",
        "vue",
        "nextjs",
        "next",
        "javascript",
        "typescript",
        "js",
        "ts",
        "security",
        "frontend",
        "backend",
        "vite",
    )

    CANONICAL_RULES = {
        "hardcoded-secret",
        "no-console",
        "debugger",
        "unused-variable",
        "unused-import",
        "unused-parameter",
        "error-handling",
        "async-issue",
        "null-safety",
        "resource-cleanup",
        "subscription-cleanup",
        "listener-cleanup",
        "duplicate-logic",
        "performance",
        "maintainability",
        "accessibility",
        "effect-cleanup",
        "effect-dependency",
        "direct-dom-manipulation",
        "unsafe-inner-html",
        "loose-equality",
        "empty-catch-block",
        "json-parse-without-error-handling",
        "setinterval-without-timer-reference",
        "global-event-listener-without-removal",
    }

    MINIMUM_SEVERITY = {
        "hardcoded-secret": Severity.CRITICAL,
    }

    SEVERITY_ORDER = {
        Severity.SUGGESTION: 0,
        Severity.LOW: 1,
        Severity.MEDIUM: 2,
        Severity.HIGH: 3,
        Severity.CRITICAL: 4,
    }

    def normalize(
        self,
        finding: Finding,
    ) -> Finding:
        rule_id = self.normalize_rule_id(
            finding.rule_id
        )

        # Free-form LLM rule IDs are not authoritative. Canonicalize the
        # rule from the actual semantic claim before policy/deduplication.
        # This keeps wording drift from creating parallel findings when the
        # same concrete issue is described under a generic rule such as
        # `error-handling` or an internally inconsistent listener/timer label.
        # Authoritative analyzers already selected a canonical rule from the
        # registry. Message-based inference must never relabel that rule.
        if finding.source not in {
            FindingSource.STATIC,
            FindingSource.FRAMEWORK,
            FindingSource.COMPILER,
        }:
            rule_id = self._normalize_by_claim(
                rule_id=rule_id,
                message=finding.message,
                suggestion=finding.suggestion,
            )
            rule_id = self._normalize_universal_semantic_claim(
                rule_id=rule_id,
                message=finding.message,
                suggestion=finding.suggestion,
            )

        severity = self.normalize_severity(
            rule_id=rule_id,
            severity=finding.severity,
        )

        return Finding(
            file_path=finding.file_path.strip(),
            line_number=finding.line_number,
            severity=severity,
            rule_id=rule_id,
            message=finding.message.strip(),
            suggestion=(
                finding.suggestion.strip()
                if finding.suggestion
                else None
            ),
            diff_position=finding.diff_position,
            source=finding.source,
            category=finding.category,
            issue=finding.issue,
            impact=finding.impact,
            evidence=finding.evidence,
            confidence=finding.confidence,
        )


    @classmethod
    def _normalize_by_claim(
        cls,
        rule_id: str,
        message: str,
        suggestion: str | None,
    ) -> str:
        text = f"{message or ''} {suggestion or ''}".lower()

        # Semantic ownership boundary for deterministic issue families.
        # Free-form LLM rule IDs are only labels; the concrete source claim
        # decides the canonical family.  This prevents wording drift from
        # creating parallel findings after unrelated framework changes.

        # Empty/swallowed catch blocks.
        if (
            "empty catch" in text
            or "empty catch block" in text
            or ("catch block" in text and ("silently" in text or "ignored" in text))
        ):
            return "empty-catch-block"

        # JSON.parse failure handling.
        if (
            "json.parse" in text
            or "parsing json" in text
            or "parse json" in text
            or "json parsing" in text
        ) and any(token in text for token in (
            "error", "exception", "throw", "invalid", "failure", "fail", "handling"
        )):
            return "json-parse-without-error-handling"

        # Interval/timer lifecycle.  Timer semantics take precedence over a
        # misleading listener rule ID when the claim explicitly talks about
        # setInterval/clearInterval or retaining a timer handle.
        timer_claim = any(
            token in text
            for token in (
                "setinterval",
                "clearinterval",
                "timer reference",
                "timer handle",
                "retain a reference to the timer",
                "retaining a reference to the timer",
                "store the returned timer",
                "timer is not retained",
            )
        )
        if timer_claim and rule_id not in {"effect-cleanup"}:
            return "setinterval-without-timer-reference"

        # Global/window listener lifecycle.
        listener_claim = (
            ("event listener" in text or "listener" in text)
            and any(token in text for token in (
                "remove", "removal", "cleanup", "clean up", "memory leak"
            ))
        )
        if listener_claim:
            return "global-event-listener-without-removal"

        return rule_id

    @classmethod
    def _normalize_universal_semantic_claim(
        cls,
        rule_id: str,
        message: str,
        suggestion: str | None,
    ) -> str:
        """Map unfamiliar labels by defect concept, never by language name."""

        label = rule_id.replace("-", " ")
        text = f"{label} {message or ''} {suggestion or ''}".lower()

        if (
            "cache" in text
            and any(token in text for token in ("key", "stale", "incorrect result", "wrong result"))
            and any(token in text for token in ("missing", "absent", "exclude", "omit", "collision", "stale"))
        ):
            return "cache-consistency"

        if (
            any(token in text for token in ("pagination", "page offset", "page index", "first page"))
            and any(token in text for token in ("skip", "incorrect", "wrong", "offset", "start"))
        ):
            return "logic-error"

        if (
            any(token in text for token in ("always report", "always return success", "reports success", "return value ignored", "result ignored"))
            or ("return" in text and "none" in text and any(token in text for token in ("declared", "expected", "non-null")))
        ):
            return "incorrect-result-handling"

        if "blocking" in text and any(token in text for token in ("async", "event loop", "non-blocking")):
            return "async-blocking-operation"

        if "timeout" in text and any(token in text for token in ("request", "external", "network", "http", "client")):
            return "missing-timeout"

        if any(token in text for token in ("authorization", "authorisation", "required role", "permission check")):
            return "authorization"

        if any(token in text for token in ("command injection", "shell injection", "shell=true", "shell true")):
            return "command-injection"

        if any(token in text for token in ("unsafe code execution", "dynamic evaluation", "untrusted eval", "arbitrary code")):
            return "unsafe-code-execution"

        if (
            any(token in text for token in ("weak test", "weak assertion", "insufficient assertion", "only checks status", "does not verify"))
            and any(token in text for token in ("test", "assert", "response", "result", "behavior", "behaviour"))
        ):
            return "insufficient-test-assertion"

        return rule_id

    @classmethod
    def normalize_rule_id(
        cls,
        rule_id: str,
    ) -> str:
        normalized = (
            rule_id
            .strip()
            .lower()
        )

        normalized = re.sub(
            r"[\s_]+",
            "-",
            normalized,
        )
        normalized = re.sub(
            r"-+",
            "-",
            normalized,
        )
        normalized = normalized.strip("-")

        # Universal registry is the primary canonical vocabulary. Legacy
        # aliases below remain for backwards compatibility while the older
        # policy/validator layers are migrated incrementally.
        registered = DEFAULT_RULE_REGISTRY.resolve(normalized)
        if registered != normalized:
            return registered

        # First resolve exact aliases.
        aliased = cls.RULE_ALIASES.get(
            normalized
        )
        if aliased is not None:
            return aliased

        # Then conservatively remove context prefixes.
        # Example:
        #   react-hardcoded-secret -> hardcoded-secret
        #   security-hardcoded-secret -> hardcoded-secret
        candidate = normalized
        changed = True

        while changed:
            changed = False
            for prefix in cls.CONTEXT_PREFIXES:
                token = f"{prefix}-"
                if candidate.startswith(token):
                    remainder = candidate[len(token):]

                    if remainder in cls.RULE_ALIASES:
                        return cls.RULE_ALIASES[
                            remainder
                        ]

                    registered_remainder = DEFAULT_RULE_REGISTRY.resolve(remainder)
                    if registered_remainder != remainder:
                        return registered_remainder

                    if (
                        remainder in cls.CANONICAL_RULES
                        or DEFAULT_RULE_REGISTRY.is_registered(remainder)
                    ):
                        return remainder

                    candidate = remainder
                    changed = True
                    break

        return cls.RULE_ALIASES.get(
            candidate,
            normalized,
        )

    @classmethod
    def normalize_severity(
        cls,
        rule_id: str,
        severity: Severity,
    ) -> Severity:
        definition = DEFAULT_RULE_REGISTRY.get(rule_id)
        minimum = (
            definition.minimum_severity
            if definition is not None and definition.minimum_severity is not None
            else cls.MINIMUM_SEVERITY.get(rule_id)
        )

        if minimum is None:
            return severity

        if (
            cls.SEVERITY_ORDER[severity]
            < cls.SEVERITY_ORDER[minimum]
        ):
            return minimum

        return severity
