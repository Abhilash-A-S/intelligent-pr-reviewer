from dataclasses import replace

from pr_reviewer.review.models import (
    Finding,
    Severity,
)
from pr_reviewer.review.rules import DEFAULT_RULE_REGISTRY


class FindingPolicy:
    """
    Deterministic product policy for validated findings.

    Responsibilities:
    - Reject low-value review noise.
    - Normalize equivalent rule identifiers.
    - Prevent cosmetic/style preferences from becoming
      PR findings.
    - Reject optional empty-code suggestions that do not
      demonstrate a correctness problem.
    - Cap severity for categories that should not block
      a pull request.
    - Preserve genuine correctness, security,
      accessibility, framework, and reliability issues.
    """

    # --------------------------------------------------
    # Exact rules that should never become PR comments.
    # --------------------------------------------------

    REJECTED_RULES = {
        # --------------------------------------------------
        # Build / deployment noise
        # --------------------------------------------------

        "external-css-not-minified",
        "asset-not-minified",
        "css-not-minified",
        "js-not-minified",

        # --------------------------------------------------
        # Naming preferences
        # --------------------------------------------------

        "naming-preference",
        "variable-naming",
        "function-naming",
        "class-naming",

        # --------------------------------------------------
        # Formatting preferences
        # --------------------------------------------------

        "formatting",
        "code-formatting",

        # --------------------------------------------------
        # Generic cosmetic/style preferences
        # --------------------------------------------------

        "style-preference",
        "cosmetic-cleanup",

        # --------------------------------------------------
        # Repeated CSS values are not automatically defects.
        # --------------------------------------------------

        "consistent-cursor-styles",
        "consistent-border-radius",
        "consistent-font-size",

        # cursor:pointer by itself is not a defect.
        "cursor-pointer-suggestion",

        # --------------------------------------------------
        # Typography / casing preferences
        # --------------------------------------------------

        "unnecessary-uppercase-heading",
        "uppercase-heading",
        "heading-uppercase",
        "text-transform-uppercase",
        "unnecessary-text-transform",

        # --------------------------------------------------
        # Pure visual preferences
        # --------------------------------------------------

        "font-size-preference",
        "font-weight-preference",
        "line-height-preference",
        "letter-spacing-preference",
        "border-radius-preference",
        "padding-preference",
        "margin-preference",
        "color-preference",

        # --------------------------------------------------
        # CSS implementation preferences without
        # demonstrated functional impact.
        # --------------------------------------------------

        "unnecessary-absolute-positioning",
        "unnecessary-relative-positioning",
        "css-selector-preference",
        "css-class-reuse",

        # --------------------------------------------------
        # Low-value typography optimization/duplication.
        #
        # Reordering or deduplicating a font-family stack is
        # not a PR defect unless a concrete rendering or
        # correctness problem is demonstrated.
        # --------------------------------------------------

        "font-family-optimization",
        "font-family-duplication",

        # --------------------------------------------------
        # Optional router cleanup.
        #
        # A router outlet should not be removed merely because
        # the reviewer cannot prove that it is currently used.
        # --------------------------------------------------

        "unnecessary-router-outlet",

        # --------------------------------------------------
        # Empty code suggestions
        #
        # An empty function/block is not automatically a
        # defect. It may intentionally represent:
        #
        # - callback placeholder
        # - interface implementation
        # - lifecycle hook
        # - framework extension point
        # - no-op implementation
        # - intentionally empty branch
        #
        # If an empty block causes a real correctness issue,
        # the LLM should report the actual defect instead.
        # --------------------------------------------------

        "suggestion-empty-block",
        "suggestion-empty-function",
        "empty-block",
        "empty-function",
        "unnecessary-empty-block",
        "unnecessary-empty-function",
        "empty-code-block",
        "empty-method",
        "empty-callback",

        # Generic label-copy/style recommendations are not correctness or
        # accessibility defects by themselves. A concrete association problem
        # must use a specific evidence-backed accessibility rule instead.
        "password-input-label",

        # Optional control-flow cleanup; valid refactor advice but too noisy
        # for a defect-focused PR reviewer without a concrete correctness impact.
        "unnecessary-else",
    }

    # --------------------------------------------------
    # Generic families of low-value rules.
    # --------------------------------------------------

    REJECTED_RULE_PREFIXES = (
        "consistent-",
        "cosmetic-",
        "formatting-",
        "naming-",
        "style-preference-",
        "typography-",
        "visual-preference-",

        # LLM-generated optional empty-code suggestions.
        "suggestion-empty-",
    )

    # --------------------------------------------------
    # Severity ceilings.
    #
    # Even when these findings are legitimate, the LLM
    # must not be able to exaggerate their severity.
    # --------------------------------------------------

    MAX_SEVERITY_BY_RULE = {
        # --------------------------------------------------
        # Simple code-quality findings
        # --------------------------------------------------

        "unused-variable": Severity.LOW,
        "unused-import": Severity.LOW,
        "unused-parameter": Severity.LOW,
        "no-console": Severity.LOW,

        # --------------------------------------------------
        # Debugging
        # --------------------------------------------------

        "debugger": Severity.MEDIUM,

        # --------------------------------------------------
        # General engineering findings
        # --------------------------------------------------

        "duplicate-logic": Severity.MEDIUM,
        "maintainability": Severity.MEDIUM,
        "performance": Severity.MEDIUM,
        "loose-equality": Severity.MEDIUM,
        "unreachable-code": Severity.MEDIUM,
        "empty-catch-block": Severity.MEDIUM,
        "json-parse-without-error-handling": Severity.MEDIUM,
        "unsafe-json-parsing": Severity.MEDIUM,
        "setinterval-without-timer-reference": Severity.MEDIUM,
        "set-interval-without-retaining-timer-reference": Severity.MEDIUM,
        "setinterval-without-retaining-timer-reference": Severity.MEDIUM,
        "global-event-listener-without-removal": Severity.MEDIUM,
        "unhandled-interval": Severity.MEDIUM,
        "unhandled-event-listener": Severity.MEDIUM,
        "no-empty-catch": Severity.MEDIUM,
        "error-handling": Severity.MEDIUM,
        "return-value-handling": Severity.LOW,

        # --------------------------------------------------
        # Accessibility
        #
        # Generic accessibility findings should not
        # automatically become HIGH/CRITICAL.
        #
        # Specific accessibility rules can receive their
        # own policy later when required.
        # --------------------------------------------------

        "accessibility": Severity.MEDIUM,

        # --------------------------------------------------
        # Generic environment-variable hardening.
        #
        # Environment variables can absolutely cause real
        # defects, but a generic recommendation to validate or
        # sanitize one should not become a merge-blocking HIGH
        # severity issue without concrete exploit/correctness
        # evidence. Specific rules can define stricter policy.
        # --------------------------------------------------

        "environment-variable-usage": Severity.LOW,

        # --------------------------------------------------
        # Password strength
        #
        # Password-strength enforcement is normally a
        # product/security-policy decision rather than
        # automatically a merge-blocking vulnerability.
        # --------------------------------------------------

        "missing-password-strength-check": (
            Severity.SUGGESTION
        ),
    }

    # --------------------------------------------------
    # Severity ordering.
    # --------------------------------------------------

    SEVERITY_RANK = {
        Severity.SUGGESTION: 0,
        Severity.LOW: 1,
        Severity.MEDIUM: 2,
        Severity.HIGH: 3,
        Severity.CRITICAL: 4,
    }

    # --------------------------------------------------
    # Normalize equivalent LLM-generated rule IDs.
    #
    # FindingNormalizer is the primary canonicalization
    # layer. These aliases remain as a defensive policy
    # boundary for callers that may invoke FindingPolicy
    # directly.
    # --------------------------------------------------

    RULE_ALIASES = {
        # Unused variables.
        "unnecessary-code": "unused-variable",
        "unused-constant": "unused-variable",
        "unused-var": "unused-variable",
        "unnecessary-variable": "unused-variable",
        "unnecessary-constant": "unused-variable",

        # Console logging.
        "console-log": "no-console",
        "console-statement": "no-console",
        "console-log-statement": "no-console",

        # Debugger.
        "debugger-statement": "debugger",
    }

    def apply(
        self,
        finding: Finding,
    ) -> Finding | None:
        """
        Apply deterministic product policy to one finding.

        Returns:
            Finding:
                Finding is accepted.

            None:
                Finding is rejected as low-value review
                noise.
        """

        rule_id = (
            finding.rule_id
            .strip()
            .lower()
        )

        canonical_rule_id = (
            self.RULE_ALIASES.get(
                rule_id,
                rule_id,
            )
        )

        finding = replace(
            finding,
            rule_id=canonical_rule_id,
        )

        # ----------------------------------------------
        # Reject exact low-value rules.
        # ----------------------------------------------

        if (
            canonical_rule_id
            in self.REJECTED_RULES
        ):
            return None

        # ----------------------------------------------
        # Reject known low-value rule families.
        # ----------------------------------------------

        if self._has_rejected_prefix(
            canonical_rule_id
        ):
            return None

        # ----------------------------------------------
        # Apply severity ceiling.
        # ----------------------------------------------

        definition = DEFAULT_RULE_REGISTRY.get(canonical_rule_id)
        maximum_severity = (
            definition.max_severity
            if definition is not None and definition.max_severity is not None
            else self.MAX_SEVERITY_BY_RULE.get(canonical_rule_id)
        )

        if maximum_severity is None:
            return finding

        if self._is_more_severe(
            current=finding.severity,
            maximum=maximum_severity,
        ):
            return replace(
                finding,
                severity=maximum_severity,
            )

        return finding

    def apply_all(
        self,
        findings: list[Finding],
    ) -> list[Finding]:
        """
        Apply policy to a collection of findings while
        preserving their original order.
        """

        result: list[Finding] = []

        for finding in findings:
            processed = self.apply(
                finding
            )

            if processed is not None:
                result.append(
                    processed
                )

        return result

    def _has_rejected_prefix(
        self,
        rule_id: str,
    ) -> bool:
        """
        Determine whether the rule belongs to a rejected
        low-value rule family.
        """

        return any(
            rule_id.startswith(prefix)
            for prefix
            in self.REJECTED_RULE_PREFIXES
        )

    def _is_more_severe(
        self,
        current: Severity,
        maximum: Severity,
    ) -> bool:
        """
        Return True when the current severity exceeds the
        maximum severity allowed by policy.
        """

        return (
            self.SEVERITY_RANK[current]
            >
            self.SEVERITY_RANK[maximum]
        )