import re
from dataclasses import dataclass, field

from pr_reviewer.review.models import (
    ChangedFile,
    Finding,
    FindingSource,
)


@dataclass
class ValidationResult:
    accepted: bool
    reasons: list[str] = field(
        default_factory=list
    )


class FindingValidator:
    """
    Deterministic validation layer for AI findings.

    This layer does not call an LLM.

    It rejects findings that are:
    - malformed
    - speculative
    - targeted at unchanged lines
    - incompatible with the file type
    - based on placeholder/generic rule identifiers
    - copied from prompt/example templates
    - unsupported by available source evidence
    - cross-file behavioural claims that cannot be
      proven from the current file

    Structural HTML findings are preserved when the
    markup itself is sufficient evidence.
    """

    SPECULATIVE_PATTERNS = (
        r"\bmight\b",
        r"\bmay be\b",
        r"\bmay potentially\b",
        r"\bcould potentially\b",
        r"\bpossibly\b",
        r"\bperhaps\b",
        r"\bpotentially\b",
        r"\bmay not\b",
        r"\bmight not\b",
        r"\bcould be\b",
        r"\bappears to\b",
        r"\bseems to\b",
        r"\bconsider\b",
        r"\bmay\s+(?:throw|fail|cause|lead\s+to|result\s+in)\b",
        r"\bnot\s+clear\s+(?:if|whether)\b",
        r"\bunclear\s+(?:if|whether)\b",
        r"\bnot\s+obvious\s+(?:if|whether)\b",
    )

    INVALID_RULE_IDS = {
        "descriptive-kebab-case-id",
        "descriptive-rule-id",
        "rule-id",
        "rule-id-1",
        "issue",
        "issue-1",
        "code-101",
        "security-101",
        "example-rule",
        "example-rule-id",
    }

    TEMPLATE_RULE_IDS = {
        "specific-kebab-case-rule",
    }

    TEMPLATE_MESSAGES = {
        "concrete explanation supported by the code.",
        "concrete explanation of the issue.",
    }

    TEMPLATE_SUGGESTIONS = {
        "practical fix.",
    }

    CSS_ONLY_RULES = {
        "css-syntax",
        "color-contrast",
        "invalid-css",
        "css-layout",
    }

    HTML_ONLY_RULES = {
        "html-structure",
        "checkbox-label",
        "missing-alt-text",
        "missing-form-label",
        "missing-aria-label",
        "missing-required-attribute",
    }

    JAVASCRIPT_STYLE_RULES = {
        "no-console",
        "debugger",
    }

    CSS_EXTENSIONS = {
        ".css",
        ".scss",
        ".sass",
        ".less",
    }

    HTML_EXTENSIONS = {
        ".html",
        ".htm",
    }

    JAVASCRIPT_EXTENSIONS = {
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".mjs",
        ".cjs",
    }

    INITIALIZATION_RULES = {
        "missing-variable-initialization",
        "uninitialized-variable",
        "variable-not-initialized",
        "missing-initial-value",
        "variable-used-before-assignment",
        "potential-uninitialized-variable",
    }

    HTML_STRUCTURAL_RULES = {
        "missing-alt-text",
        "missing-form-label",
        "missing-aria-label",
        "missing-required-attribute",
        "missing-input-label",
        "missing-button-type",
        "missing-lang-attribute",
        "missing-title",
    }

    HTML_BEHAVIOR_RULE_TERMS = (
        "functionality",
        "validation",
        "authentication",
        "authorization",
        "submission",
        "submit-handler",
        "event-handler",
        "event-handling",
        "click-handler",
        "toggle-behavior",
        "toggle-functionality",
        "business-logic",
        "api-call",
        "api-request",
        "password-match",
        "confirm-password",
        "password-strength",
        "strength-meter",
    )

    HTML_BEHAVIOR_MESSAGE_PATTERNS = (
        r"\bdoes not validate\b",
        r"\bdoesn't validate\b",
        r"\bnot validated\b",
        r"\bvalidation is missing\b",
        r"\bvalidation is not\b",
        r"\bdoes not handle\b",
        r"\bdoesn't handle\b",
        r"\bnot handled\b",
        r"\bdoes not check\b",
        r"\bdoesn't check\b",
        r"\bno check\b",
        r"\bdoes not ensure\b",
        r"\bdoesn't ensure\b",
        r"\bdoes not prevent\b",
        r"\bdoesn't prevent\b",
        r"\bdoes not enforce\b",
        r"\bdoesn't enforce\b",
        r"\bdoes not submit\b",
        r"\bdoesn't submit\b",
        r"\bdoes not call\b",
        r"\bdoesn't call\b",
        r"\bdoes not trigger\b",
        r"\bdoesn't trigger\b",
        r"\bdoes not update\b",
        r"\bdoesn't update\b",
        r"\bdoes not toggle\b",
        r"\bdoesn't toggle\b",
        r"\bfunctionality is missing\b",
        r"\bhandler is missing\b",
        r"\bevent handler is missing\b",
        r"\bpasswords? do not match\b",
        r"\bdoes not match the original password\b",
        # HTML/template text can name or invoke implementation methods, but it
        # cannot prove what those methods do internally. Direct-DOM/security
        # behavior must be anchored to the executable component/service source.
        r"\b(?:method|function)\b.*\b(?:performs?|uses?)\b.*\bdirect\s+dom\b",
        r"\bdirect\s+dom\s+manipulation\b",
        r"\bbypass(?:es|ing)?\b.*\b(?:angular|framework)[’'s]*\s+security\b",
        r"\b(?:method|function)\b.*\b(?:unsafe|insecure|security)\b",
    )

    # ==================================================
    # Source-construct evidence
    # ==================================================
    #
    # These are not "framework rules". They are concrete
    # source constructs whose presence can be checked
    # deterministically.
    #
    # If an AI finding claims that a construct is misused,
    # missing cleanup, missing dependencies, etc., but the
    # construct does not occur anywhere in the reviewed
    # source file, the finding is unsupported.
    #
    # This protects against hallucinations such as:
    #
    # - useEffect dependency findings on JSON config files
    # - useEffect cleanup findings on a React bootstrap file
    #   that contains no useEffect at all
    #
    # The mapping is intentionally extensible.
    # ==================================================

    SOURCE_CONSTRUCT_PATTERNS = {
        "useEffect": re.compile(
            r"\buseEffect\s*\(",
            re.IGNORECASE,
        ),
        "useState": re.compile(
            r"\buseState\s*\(",
            re.IGNORECASE,
        ),
        "useMemo": re.compile(
            r"\buseMemo\s*\(",
            re.IGNORECASE,
        ),
        "useCallback": re.compile(
            r"\buseCallback\s*\(",
            re.IGNORECASE,
        ),
        "useRef": re.compile(
            r"\buseRef\s*\(",
            re.IGNORECASE,
        ),
        "useLayoutEffect": re.compile(
            r"\buseLayoutEffect\s*\(",
            re.IGNORECASE,
        ),
        "setInterval": re.compile(
            r"\bsetInterval\s*\(",
            re.IGNORECASE,
        ),
        "setTimeout": re.compile(
            r"\bsetTimeout\s*\(",
            re.IGNORECASE,
        ),
        "addEventListener": re.compile(
            r"\baddEventListener\s*\(",
            re.IGNORECASE,
        ),
    }

    REACT_HOOK_RULE_TERMS = (
        "react-hook",
        "react-hooks",
        "hook-dependency",
        "hook-cleanup",
        "useeffect",
        "usestate",
        "usememo",
        "usecallback",
        "useref",
    )

    def validate(
        self,
        finding: Finding,
        changed_file: ChangedFile,
    ) -> ValidationResult:

        reasons: list[str] = []

        self._validate_required_fields(
            finding=finding,
            reasons=reasons,
        )

        self._validate_rule_id(
            finding=finding,
            reasons=reasons,
        )

        self._validate_template_output(
            finding=finding,
            reasons=reasons,
        )

        self._validate_changed_line(
            finding=finding,
            changed_file=changed_file,
            reasons=reasons,
        )

        # Static/framework/compiler findings are authoritative source facts.
        # Retain structural safety (required fields and changed-line ownership)
        # but never apply AI speculation or hallucination filters to them.
        if finding.source in {
            FindingSource.STATIC,
            FindingSource.FRAMEWORK,
            FindingSource.COMPILER,
        }:
            return ValidationResult(
                accepted=not reasons,
                reasons=reasons,
            )

        self._validate_speculation(
            finding=finding,
            reasons=reasons,
        )

        self._validate_file_type(
            finding=finding,
            changed_file=changed_file,
            reasons=reasons,
        )

        self._validate_source_construct_evidence(
            finding=finding,
            changed_file=changed_file,
            reasons=reasons,
        )

        self._validate_llm_grounding(
            finding=finding,
            changed_file=changed_file,
            reasons=reasons,
        )

        self._validate_semantic_evidence_location(
            finding=finding,
            changed_file=changed_file,
            reasons=reasons,
        )

        self._validate_framework_and_sink_claims(
            finding=finding,
            changed_file=changed_file,
            reasons=reasons,
        )

        self._validate_duplicate_evidence(
            finding=finding,
            changed_file=changed_file,
            reasons=reasons,
        )

        self._validate_configuration_and_style_evidence(
            finding=finding,
            changed_file=changed_file,
            reasons=reasons,
        )

        self._validate_low_value_comment_noise(
            finding=finding,
            changed_file=changed_file,
            reasons=reasons,
        )

        self._validate_evidence(
            finding=finding,
            changed_file=changed_file,
            reasons=reasons,
        )

        return ValidationResult(
            accepted=not reasons,
            reasons=reasons,
        )

    def filter_findings(
        self,
        findings: list[Finding],
        changed_file: ChangedFile,
    ) -> list[Finding]:

        accepted: list[Finding] = []

        for finding in findings:
            result = self.validate(
                finding=finding,
                changed_file=changed_file,
            )

            if result.accepted:
                accepted.append(
                    finding
                )

        return accepted

    @staticmethod
    def _validate_required_fields(
        finding: Finding,
        reasons: list[str],
    ) -> None:

        if not finding.file_path.strip():
            reasons.append(
                "Finding has no file path."
            )

        if finding.line_number <= 0:
            reasons.append(
                "Finding has an invalid line number."
            )

        if not finding.rule_id.strip():
            reasons.append(
                "Finding has no rule ID."
            )

        if not finding.message.strip():
            reasons.append(
                "Finding has no message."
            )

    def _validate_rule_id(
        self,
        finding: Finding,
        reasons: list[str],
    ) -> None:

        rule_id = (
            finding.rule_id
            .strip()
            .lower()
        )

        if rule_id in self.INVALID_RULE_IDS:
            reasons.append(
                "Finding uses an invalid placeholder rule ID."
            )

    def _validate_template_output(
        self,
        finding: Finding,
        reasons: list[str],
    ) -> None:

        rule_id = (
            finding.rule_id
            .strip()
            .lower()
        )

        message = (
            finding.message
            .strip()
            .lower()
        )

        suggestion = (
            finding.suggestion
            .strip()
            .lower()
            if finding.suggestion
            else ""
        )

        if rule_id in self.TEMPLATE_RULE_IDS:
            reasons.append(
                "Finding uses a template rule ID."
            )

        if message in self.TEMPLATE_MESSAGES:
            reasons.append(
                "Finding uses a template message."
            )

        if suggestion in self.TEMPLATE_SUGGESTIONS:
            reasons.append(
                "Finding uses a template suggestion."
            )

    @staticmethod
    def _validate_changed_line(
        finding: Finding,
        changed_file: ChangedFile,
        reasons: list[str],
    ) -> None:

        changed_line_numbers = {
            line.line_number
            for line in changed_file.changed_lines
        }

        if (
            finding.line_number
            not in changed_line_numbers
        ):
            reasons.append(
                "Finding targets a non-commentable line."
            )

    def _validate_speculation(
        self,
        finding: Finding,
        reasons: list[str],
    ) -> None:

        text = " ".join(
            part
            for part in (
                finding.message,
                finding.suggestion or "",
            )
            if part
        )

        for pattern in self.SPECULATIVE_PATTERNS:
            if re.search(
                pattern,
                text,
                flags=re.IGNORECASE,
            ):
                reasons.append(
                    "Finding is speculative."
                )
                return

    def _validate_file_type(
        self,
        finding: Finding,
        changed_file: ChangedFile,
        reasons: list[str],
    ) -> None:

        extension = self._get_extension(
            changed_file.file_path
        )

        rule_id = (
            finding.rule_id
            .strip()
            .lower()
        )

        if (
            rule_id in self.CSS_ONLY_RULES
            and extension
            not in self.CSS_EXTENSIONS
        ):
            reasons.append(
                "CSS-specific finding reported "
                "for a non-CSS file."
            )

        if (
            rule_id in self.HTML_ONLY_RULES
            and extension
            not in self.HTML_EXTENSIONS
        ):
            reasons.append(
                "HTML-specific finding reported "
                "for a non-HTML file."
            )

        if (
            rule_id
            in self.JAVASCRIPT_STYLE_RULES
            and extension
            not in self.JAVASCRIPT_EXTENSIONS
        ):
            reasons.append(
                "JavaScript-specific finding reported "
                "for a non-JavaScript file."
            )

    def _validate_source_construct_evidence(
        self,
        finding: Finding,
        changed_file: ChangedFile,
        reasons: list[str],
    ) -> None:
        """
        Reject findings that discuss concrete source
        constructs which do not exist in the reviewed file.

        This is deliberately evidence-based:

        - We do NOT reject every React finding.
        - We do NOT reject every hook finding.
        - We reject only when the finding references a
          concrete construct and the file proves that the
          construct is absent.
        """

        extension = self._get_extension(
            changed_file.file_path
        )

        rule_id = (
            finding.rule_id
            .strip()
            .lower()
        )

        text = " ".join(
            part
            for part in (
                finding.rule_id,
                finding.message,
                finding.suggestion or "",
            )
            if part
        )

        text_lower = text.lower()

        # --------------------------------------------------
        # React hook claims on non-JS/TS source
        # --------------------------------------------------

        has_react_hook_rule_signal = any(
            term in rule_id
            for term
            in self.REACT_HOOK_RULE_TERMS
        )

        mentioned_hooks = [
            construct_name
            for construct_name
            in (
                "useEffect",
                "useState",
                "useMemo",
                "useCallback",
                "useRef",
                "useLayoutEffect",
            )
            if construct_name.lower()
            in text_lower
        ]

        if (
            (
                has_react_hook_rule_signal
                or mentioned_hooks
            )
            and extension
            not in self.JAVASCRIPT_EXTENSIONS
        ):
            reasons.append(
                "React hook finding reported for a file "
                "that is not JavaScript/TypeScript source."
            )
            return

        # --------------------------------------------------
        # Construct-presence proof
        # --------------------------------------------------

        if extension not in self.JAVASCRIPT_EXTENSIONS:
            return

        full_content = (
            changed_file.full_content
            or "\n".join(
                line.content
                for line
                in changed_file.changed_lines
            )
        )

        if not full_content:
            return

        for (
            construct_name,
            construct_pattern,
        ) in self.SOURCE_CONSTRUCT_PATTERNS.items():

            if (
                construct_name.lower()
                not in text_lower
            ):
                continue

            if not construct_pattern.search(
                full_content
            ):
                reasons.append(
                    (
                        "Finding is not supported by source "
                        "evidence: it references "
                        f"`{construct_name}`, but that "
                        "construct is absent from the file."
                    )
                )
                return

        # --------------------------------------------------
        # Cleanup/dependency claims with an implied useEffect
        #
        # Some LLM rule IDs do not include the literal hook
        # name even though the message/suggestion clearly
        # claims a React effect lifecycle problem.
        # --------------------------------------------------

        lifecycle_claim = (
            (
                "cleanup" in rule_id
                or "dependency" in rule_id
                or "dependencies" in rule_id
            )
            and (
                "react" in rule_id
                or "hook" in rule_id
                or "effect" in rule_id
            )
        )

        if (
            lifecycle_claim
            and not self.SOURCE_CONSTRUCT_PATTERNS[
                "useEffect"
            ].search(full_content)
            and not self.SOURCE_CONSTRUCT_PATTERNS[
                "useLayoutEffect"
            ].search(full_content)
        ):
            reasons.append(
                "React effect lifecycle finding is not "
                "supported by source evidence because the "
                "file contains no effect hook."
            )

    def _validate_llm_grounding(
        self,
        finding: Finding,
        changed_file: ChangedFile,
        reasons: list[str],
    ) -> None:
        """Reject recurring LLM claims that contradict source or misuse a rule ID."""

        rule_id = finding.rule_id.strip().lower()
        message = finding.message.strip().lower()
        suggestion = (finding.suggestion or "").strip().lower()
        full_content = changed_file.full_content or "\n".join(
            line.content for line in changed_file.changed_lines
        )

        # A label's visible text is not required to equal an input id.  A real
        # accessibility issue is a broken/missing label association (for/id), not
        # a text-vs-id mismatch.
        if rule_id == "password-input-label-mismatch":
            if "match" in message and "id" in message:
                reasons.append(
                    "Label text does not need to match the input ID; this accessibility claim is invalid."
                )
                return

        # Password-order claims require concrete control-flow evidence.  When the
        # file visibly contains password/confirm-password comparison before the
        # submission helper, reject the contradictory LLM finding.
        if rule_id == "password-matching-check-order" and full_content:
            submit = full_content.find("handleFormSubmit")
            match_patterns = (
                r"password\s*!==?\s*confirm",
                r"password\s*===?\s*confirm",
                r"confirm\w*\s*!==?\s*password",
                r"confirm\w*\s*===?\s*password",
                r"passwords?\s+match",
            )
            match_positions = [
                m.start() for pattern in match_patterns
                for m in re.finditer(pattern, full_content, flags=re.IGNORECASE)
            ]
            if submit >= 0 and match_positions and min(match_positions) < submit:
                reasons.append(
                    "Password matching is already checked before submission in the reviewed source."
                )
                return

        # Hallucinated "implementation not provided" findings are easy to disprove
        # when the same file contains the named function/method definition.
        missing_impl_phrases = (
            "implementation is not provided",
            "implementation is missing",
            "not implemented",
            "not defined",
        )
        if any(phrase in message for phrase in missing_impl_phrases):
            symbol = self._extract_quoted_identifier(finding.message)
            if symbol and full_content and self._has_symbol_definition(full_content, symbol):
                reasons.append(
                    f"Finding contradicts source evidence: '{symbol}' is implemented in this file."
                )
                return

        # Reject rule/message mismatches instead of letting plausible-sounding but
        # semantically unrelated LLM comments through.
        if rule_id == "duplicate-calculation":
            duplicate_terms = (
                "duplicate calculation", "duplicated calculation",
                "repeated calculation", "same calculation",
                "calculation is duplicated", "calculation is repeated",
            )
            if not any(term in message for term in duplicate_terms):
                reasons.append("Finding message does not support the duplicate-calculation rule.")
                return

        if rule_id == "variable-scope" and ("unused" in message or "not used" in message):
            reasons.append("Finding message describes an unused value, not a variable-scope defect.")
            return

        if rule_id == "return-value" and (
            "without any specific logic" in message
            or "ensure that the function logic is clear" in suggestion
        ):
            reasons.append("Finding does not identify a concrete return-value defect.")
            return

        # Generic accessibility findings must identify a concrete, source-proven
        # accessibility defect.  Broad statements such as "this button/container
        # needs an aria-label or role" are not valid by themselves: native controls
        # already expose semantics, and live-region requirements depend on how a
        # message is actually used.  Specific structural rules (missing-form-label,
        # missing-alt-text, etc.) remain eligible elsewhere in the validator.
        if rule_id == "accessibility":
            generic_aria_claim = any(
                phrase in message
                for phrase in (
                    "does not have an aria-label or role",
                    "doesn't have an aria-label or role",
                    "add an aria-label or role",
                    "needs an aria-label or role",
                    "should have an aria-label or role",
                )
            ) or any(
                phrase in suggestion
                for phrase in (
                    "add an aria-label or role",
                    "add aria-label or role",
                )
            )
            if generic_aria_claim:
                reasons.append(
                    "Generic accessibility claim is not supported by a specific structural defect."
                )
                return

        # Do not invent a return-value contract for a function whose result is not
        # consumed by the reviewed source.  A helper may intentionally perform side
        # effects and return nothing.  Keep a return-contract finding only when the
        # source itself demonstrates that callers consume the returned value.
        if rule_id in {"return-value", "return-value-handling"}:
            if any(
                phrase in message
                for phrase in (
                    "should return",
                    "does not handle the return value",
                    "doesn't handle the return value",
                    "return the result",
                    "all paths return",
                )
            ) or "return" in suggestion:
                symbol = self._extract_quoted_identifier(finding.message)
                if symbol and full_content and not self._symbol_return_value_is_consumed(
                    full_content, symbol
                ):
                    reasons.append(
                        "Return-value requirement is not supported by how the function is used in the reviewed source."
                    )
                    return

        # When an AI emits a vague generic error-handling finding on an empty catch,
        # the deterministic analyzer already reports the concrete empty-catch-block
        # root cause.  Reject the vague duplicate here instead of allowing severity
        # inflation (for example to CRITICAL because of generic security wording).
        if rule_id == "error-handling":
            if self._has_nearby_empty_catch(changed_file, finding.line_number, distance=3):
                reasons.append(
                    "Generic error-handling finding duplicates the concrete empty-catch-block issue."
                )
                return

        # A frontend LLM may restate an already-proven hardcoded secret as a
        # separate "unsafe-api" exposure issue merely because the value is rendered
        # in the UI. When the same file already contains a literal hardcoded
        # credential assignment, keep the concrete hardcoded-secret root cause and
        # reject this redundant severity-inflating narrative.
        if rule_id == "unsafe-api" and any(
            token in message for token in ("api key", "secret", "token", "credential")
        ) and any(
            token in message for token in ("display", "expos", "render", "ui")
        ):
            if re.search(
                r"\b(?:api[_-]?key|password|secret|token|client[_-]?secret|jwt[_-]?secret)\b"
                r"\s*=\s*['\"][^'\"]{6,}['\"]",
                full_content,
                flags=re.IGNORECASE,
            ):
                reasons.append(
                    "Secret-exposure finding duplicates the concrete hardcoded-secret root cause already proven by source."
                )
                return

        # Canonical JSON.parse findings must be grounded in an actual parse call on
        # the target/nearby source and should describe failure handling, not invent
        # generic security claims about JSON validation.
        if rule_id == "json-parse-without-error-handling":
            if not self._has_nearby_source_pattern(
                changed_file, finding.line_number, r"\bJSON\s*\.\s*parse\s*\(", distance=3
            ):
                reasons.append("JSON.parse finding is not supported by nearby source evidence.")
                return
            # JSON.parse is a data parser, not an execution sink.  LLMs often
            # turn ordinary parse-failure handling into an invented injection or
            # generic security vulnerability.  Those claims are only meaningful
            # when the reviewed code also feeds the parsed value into an actual
            # dangerous execution/rendering sink.  Without such evidence, keep
            # the concrete parse-error finding and reject the security narrative.
            json_security_claim = any(
                phrase in message
                for phrase in (
                    "security vulnerab",
                    "injection attack",
                    "code injection",
                    "command injection",
                    "sql injection",
                    "cross-site scripting",
                    " xss",
                    "arbitrary code execution",
                    "remote code execution",
                )
            )
            if json_security_claim and not self._has_nearby_dangerous_sink(
                changed_file, finding.line_number, distance=8
            ):
                reasons.append(
                    "JSON.parse security/injection claim is not supported by a concrete dangerous sink."
                )
                return

        # Generic LLM setInterval findings are normalized to the canonical timer
        # reference rule.  Keep them only when nearby source actually starts an
        # interval without retaining the returned handle.  This prevents false
        # positives for patterns such as `this.timer = setInterval(...)`.
        if rule_id == "setinterval-without-timer-reference":
            if not self._has_nearby_source_pattern(
                changed_file, finding.line_number, r"\bsetInterval\s*\(", distance=3
            ):
                reasons.append("setInterval finding is not supported by nearby source evidence.")
                return
            if self._nearby_setinterval_result_is_retained(changed_file, finding.line_number, distance=3):
                reasons.append("The setInterval return value is retained in nearby source code.")
                return

        # Global-listener findings must be owned by an actual nearby listener
        # construct.  Do not let a generic cleanup/memory-leak sentence anchored
        # on a timer line masquerade as an event-listener issue.
        if rule_id == "global-event-listener-without-removal":
            if not self._has_nearby_source_pattern(
                changed_file, finding.line_number,
                r"\b(?:window|document)\s*\.\s*addEventListener\s*\(", distance=3
            ):
                reasons.append("Global event-listener finding is not supported by nearby source evidence.")
                return

        # Function-specific rule IDs at call sites are often duplicate symptoms of a
        # root cause already present in the implementation. Reject the recurring
        # parseUserData call-site variant when the function itself contains JSON.parse.
        if rule_id == "parse-user-data" and "will throw" in message and full_content:
            if re.search(
                r"function\s+parseUserData\s*\([^)]*\)\s*(?::[^\{]+)?\{[^}]*JSON\s*\.\s*parse\s*\(",
                full_content, flags=re.IGNORECASE | re.DOTALL,
            ):
                reasons.append("Call-site finding duplicates the JSON.parse root cause in parseUserData.")
                return



    def _validate_low_value_comment_noise(
        self,
        finding: Finding,
        changed_file: ChangedFile,
        reasons: list[str],
    ) -> None:
        """Reject cosmetic findings whose only evidence is a comment marker.

        Professional PR review should not create findings merely because a file
        contains framework starter separators, decorative comments, boilerplate
        markers, or placeholder comments. This is intentionally technology-
        agnostic: Angular, React, Java, Python, C#, configuration files, and
        templates can all contain such comments.

        The boundary is deliberately narrow. We only reject when the target line
        is comment-only and either:

        * the comment body is purely decorative punctuation; or
        * the finding itself is explicitly asking to remove/replace placeholder,
          boilerplate, sample, separator, or decorative comment content.

        Comments that carry actionable semantics (for example TODO/FIXME notes,
        security warnings, disabled code, or a concrete correctness claim) are not
        rejected by this helper merely because they are comments.
        """
        line = self._source_line(changed_file, finding.line_number)
        stripped = line.strip()
        if not stripped:
            return

        comment_body = self._comment_only_body(stripped)
        if comment_body is None:
            return

        normalized_body = comment_body.strip()
        message = finding.message.strip().lower()
        suggestion = (finding.suggestion or "").strip().lower()
        combined = f"{message} {suggestion}"
        rule_id = finding.rule_id.strip().lower()

        # Pure punctuation separators such as:
        # <!-- * * * * * -->, // ----, /* ===== */
        # have no defect semantics on their own. Limit the automatic rejection
        # to broad maintainability/cosmetic rule families so a concrete rule is
        # never hidden solely because it happens to target a comment.
        decorative_only = bool(normalized_body) and re.fullmatch(
            r"[\s*#=\-_/\\.|:~+<>]+", normalized_body
        ) is not None
        broad_comment_rule = rule_id in {
            "duplicate-logic",
            "maintainability",
            "suggestion",
            "cosmetic-cleanup",
            "style-preference",
        }
        if decorative_only and broad_comment_rule:
            reasons.append(
                "Finding is low-value review noise anchored only to a decorative comment."
            )
            return

        placeholder_terms = (
            "placeholder",
            "boilerplate",
            "starter content",
            "sample content",
            "decorative comment",
            "separator comment",
            "replace with actual content",
            "replace with real content",
            "remove the placeholder",
            "remove this comment",
        )
        if any(term in combined for term in placeholder_terms):
            reasons.append(
                "Finding is low-value placeholder/decorative-comment cleanup rather than a code defect."
            )

    @staticmethod
    def _comment_only_body(stripped_line: str) -> str | None:
        """Return the body when a source line contains only a comment."""
        if stripped_line.startswith("<!--") and stripped_line.endswith("-->"):
            return stripped_line[4:-3]
        if stripped_line.startswith("//"):
            return stripped_line[2:]
        if stripped_line.startswith("#"):
            return stripped_line[1:]
        if stripped_line.startswith("/*") and stripped_line.endswith("*/"):
            return stripped_line[2:-2]
        return None

    def _validate_semantic_evidence_location(
        self,
        finding: Finding,
        changed_file: ChangedFile,
        reasons: list[str],
    ) -> None:
        """Reject duplicate findings whose cited line does not prove the claim.

        Duplicate/redundancy findings are especially prone to plausible wording
        with an unrelated source location. This validator keeps the rule generic:
        named methods must be anchored inside that callable, while named values or
        calculations must be anchored to a line that actually contains the named
        construct rather than a method signature, brace, or unrelated statement.
        """
        message = finding.message.strip()
        lowered = message.lower()
        symbol = (
            self._extract_quoted_identifier(message)
            or self._extract_backticked_identifier(message)
        )
        full_content = changed_file.full_content or ""

        # Any AI claim explicitly scoped inside a named function/method must be
        # anchored inside that callable. This prevents evidence transfer from a
        # real defect in one function to an unrelated changed line in another.
        callable_scope_claim = bool(re.search(
            r"\b(?:function|method)\b.{0,100}\b(?:contains?|inside|within|has)\b",
            lowered,
        ))
        if callable_scope_claim and symbol and full_content:
            span = self._javascript_typescript_callable_span(full_content, symbol)
            if span is not None and not (span[0] <= finding.line_number <= span[1]):
                reasons.append(
                    "Finding evidence line does not belong to the named "
                    f"method/function '{symbol}' described by the issue."
                )
                return

        rule_id = finding.rule_id.strip().lower()
        if rule_id != "duplicate-logic":
            return

        scoped_claim = any(
            phrase in lowered
            for phrase in (
                "method contains duplicate",
                "method contains duplicated",
                "function contains duplicate",
                "function contains duplicated",
                "duplicate logic in the method",
                "duplicate logic in the function",
                "same calculation is performed twice",
                "calculation is performed twice",
                "calculated twice",
                "duplicate calculation",
                "duplicated calculation",
                "same values",
            )
        )
        if not scoped_claim:
            return

        if not symbol or not full_content:
            return

        evidence_line = ""
        for changed_line in changed_file.changed_lines:
            if changed_line.line_number == finding.line_number:
                evidence_line = changed_line.content or ""
                break
        if not evidence_line:
            lines = full_content.splitlines()
            if 1 <= finding.line_number <= len(lines):
                evidence_line = lines[finding.line_number - 1]
        evidence_line = evidence_line.strip()

        span = self._javascript_typescript_callable_span(full_content, symbol)
        if span is not None:
            start_line, end_line = span
            if not (start_line <= finding.line_number <= end_line):
                reasons.append(
                    "Finding evidence line does not belong to the named "
                    f"method/function '{symbol}' described by the issue."
                )
                return

            # The symbol names a callable. A changed statement inside that method
            # is acceptable evidence; do not require the method name itself on
            # every statement line.
            return

        # Otherwise the quoted/backticked symbol is a value/expression target
        # (for example `total`). The cited line must contain that construct.
        if symbol not in evidence_line:
            reasons.append(
                "Duplicate-logic finding is not anchored to the source "
                f"construct '{symbol}' that the issue claims is duplicated."
            )

    def _validate_duplicate_evidence(
        self,
        finding: Finding,
        changed_file: ChangedFile,
        reasons: list[str],
    ) -> None:
        """Require concrete multiplicity evidence for explicit duplicate claims.

        This is a language/framework-neutral evidence check.  It deliberately
        handles only claims whose scope is concrete enough to prove
        deterministically (currently array/list duplication).  Broader duplicate
        calculations/blocks continue through the existing semantic-location and
        source-evidence checks instead of being guessed from wording.
        """
        rule_id = finding.rule_id.strip().lower()
        if rule_id != "duplicate-logic":
            return

        message = finding.message.strip()
        lowered = message.lower()
        duplicate_claim = any(
            term in lowered
            for term in (
                "duplicate",
                "duplicated",
                "appears twice",
                "listed twice",
                "included twice",
                "repeated in",
            )
        )
        if not duplicate_claim:
            return

        # Array/list claims are high-confidence to validate because membership is
        # syntactically bounded.  This protects any JS/TS/JSON-style construct,
        # not just Angular TestBed imports.
        array_claim = any(
            term in lowered
            for term in (
                " array",
                "array ",
                " list",
                "list ",
            )
        )
        if not array_claim:
            return

        symbol = (
            self._extract_quoted_identifier(message)
            or self._extract_backticked_identifier(message)
        )
        if not symbol:
            return

        array_text = self._array_scope_at_line(
            changed_file,
            finding.line_number,
        )
        if array_text is None:
            return

        occurrences = len(
            re.findall(
                rf"(?<![A-Za-z0-9_$]){re.escape(symbol)}(?![A-Za-z0-9_$])",
                array_text,
            )
        )
        if occurrences < 2:
            reasons.append(
                "Duplicate array/list claim is not supported by a second "
                f"occurrence of '{symbol}' in the relevant collection."
            )

    def _validate_framework_and_sink_claims(
        self,
        finding: Finding,
        changed_file: ChangedFile,
        reasons: list[str],
    ) -> None:
        content = changed_file.full_content or ""
        evidence_line = self._source_line(
            changed_file,
            finding.line_number,
        )
        text = " ".join(
            part
            for part in (
                finding.rule_id,
                finding.message,
                finding.suggestion or "",
            )
            if part
        ).lower()

        if (
            "bootstrapapplication" in content.lower()
            and "express" not in content.lower()
            and any(term in text for term in ("express", "middleware", "next(err)"))
        ):
            reasons.append(
                "Finding applies Express error-middleware semantics to an Angular bootstrap file."
            )
            return

        if finding.rule_id == "security" and re.search(
            r"\bdocument\s*\.\s*(?:querySelector|querySelectorAll|getElementById)\s*\(",
            evidence_line,
        ):
            if not re.search(
                r"\b(?:innerHTML|outerHTML|insertAdjacentHTML|eval|Function)\b",
                evidence_line,
            ):
                reasons.append(
                    "DOM element lookup is not itself an injection sink; the finding must target the concrete dangerous write or execution sink."
                )
                return

        if finding.rule_id in {"subscription-cleanup", "resource-cleanup"}:
            if not self._has_nearby_source_pattern(
                changed_file,
                finding.line_number,
                r"\.\s*subscribe\s*\(|\b(?:interval|timer|fromEvent|Subject|WebSocket)\s*\(",
                distance=4,
            ):
                reasons.append(
                    "Subscription cleanup claim is not anchored to a nearby subscription or long-lived source."
                )

    @staticmethod
    def _array_scope_at_line(
        changed_file: ChangedFile,
        line_number: int,
    ) -> str | None:
        """Return the balanced [] collection containing the evidence line."""
        content = changed_file.full_content or ""
        if not content or line_number <= 0:
            return None

        lines = content.splitlines(keepends=True)
        if line_number > len(lines):
            return None

        line_start = sum(len(line) for line in lines[: line_number - 1])
        line_end = line_start + len(lines[line_number - 1])

        # Prefer an array whose bounds actually contain the cited line. Search
        # backward for candidate '[' tokens and balance forward while ignoring
        # quoted strings sufficiently for config/source evidence validation.
        for open_index in range(max(line_start, line_end - 1), -1, -1):
            if content[open_index] != "[":
                continue

            depth = 0
            quote: str | None = None
            escaped = False
            for pos in range(open_index, len(content)):
                ch = content[pos]
                if quote is not None:
                    if escaped:
                        escaped = False
                    elif ch == "\\":
                        escaped = True
                    elif ch == quote:
                        quote = None
                    continue
                if ch in {'"', "'", "`"}:
                    quote = ch
                    continue
                if ch == "[":
                    depth += 1
                elif ch == "]":
                    depth -= 1
                    if depth == 0:
                        close_index = pos
                        if open_index <= line_end and close_index >= line_start:
                            return content[open_index : close_index + 1]
                        break

        return None

    @staticmethod
    def _javascript_typescript_callable_span(
        full_content: str,
        symbol: str,
    ) -> tuple[int, int] | None:
        """Return the brace-delimited line span of a JS/TS method/function."""
        escaped = re.escape(symbol)
        patterns = (
            rf"(?:^|\n)\s*(?:public\s+|private\s+|protected\s+|static\s+|async\s+|readonly\s+)*{escaped}\s*\([^)]*\)\s*(?::[^{{=]+)?\s*{{",
            rf"\bfunction\s+{escaped}\s*\([^)]*\)\s*(?::[^{{=]+)?\s*{{",
        )
        match = next(
            (
                found
                for pattern in patterns
                if (found := re.search(pattern, full_content, flags=re.MULTILINE))
            ),
            None,
        )
        if match is None:
            return None

        brace_start = full_content.find("{", match.start(), match.end() + 1)
        if brace_start < 0:
            return None

        depth = 0
        quote: str | None = None
        escaped_char = False
        for pos in range(brace_start, len(full_content)):
            ch = full_content[pos]
            if quote is not None:
                if escaped_char:
                    escaped_char = False
                elif ch == "\\":
                    escaped_char = True
                elif ch == quote:
                    quote = None
                continue

            if ch in "'\"`":
                quote = ch
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    start_line = full_content.count("\n", 0, match.start()) + 1
                    end_line = full_content.count("\n", 0, pos) + 1
                    return start_line, end_line

        return None

    def _validate_configuration_and_style_evidence(
        self,
        finding: Finding,
        changed_file: ChangedFile,
        reasons: list[str],
    ) -> None:
        """Reject source/config/style claims that are contradicted by syntax evidence.

        This validator is deliberately technology-agnostic. It does not encode
        Vite or ESLint product rules. Instead it verifies three generic claim
        families that require concrete source evidence:

        * a line claimed to be invalid comment syntax must actually be code,
          not a valid line/block comment;
        * a glob-pattern criticism must identify an invalid glob, not merely a
          valid brace-expansion form;
        * a duplicate CSS declaration must be proven by a second declaration of
          the same property inside the same declaration block.
        """
        rule_id = finding.rule_id.strip().lower()
        message = finding.message.strip().lower()
        suggestion = (finding.suggestion or "").strip().lower()
        line = self._source_line(changed_file, finding.line_number)
        stripped = line.strip()

        # Valid JavaScript/TypeScript comments are never syntax/API misuse.
        # This catches hallucinations such as claiming that
        # `// https://example.dev/config/` is "not a comment".
        if rule_id in {"api-misuse", "correctness"}:
            comment_claim = (
                "not a comment" in message
                or "invalid comment" in message
                or "not valid javascript comment" in message
                or "invalid javascript comment" in message
            )
            if comment_claim and (
                stripped.startswith("//")
                or stripped.startswith("/*")
                or stripped.startswith("*")
                or stripped.endswith("*/")
            ):
                reasons.append(
                    "Comment-syntax claim is contradicted by a valid source comment."
                )
                return

        # Brace expansion such as **/*.{js,jsx} is a standard glob form.
        # A preference for splitting it into two patterns is not a correctness
        # or data-validation defect.
        if rule_id == "data-validation":
            glob_claim = any(
                term in message or term in suggestion
                for term in (
                    "file pattern",
                    "file patterns",
                    "glob",
                    "linting unintended files",
                )
            )
            valid_brace_glob = re.search(
                r"(?:\*\*/)?\*?\.\{[^{}]+(?:,[^{}]+)+\}",
                line,
            ) is not None
            if glob_claim and valid_brace_glob:
                reasons.append(
                    "Configuration claim treats a valid brace-expansion glob as an error."
                )
                return

        extension = self._get_extension(changed_file.file_path)

        # Declarative JSON/configuration values do not prove runtime lifecycle,
        # subscription, or application data-validation defects. Require source
        # evidence compatible with the semantic claim instead of accepting a
        # generic LLM recommendation anchored to a scalar config property.
        config_extensions = {".json", ".jsonc"}
        if extension in config_extensions:
            runtime_only_rules = {
                "resource-cleanup",
                "subscription-cleanup",
                "listener-cleanup",
                "async-issue",
                "error-handling",
                "concurrency",
            }
            if rule_id in runtime_only_rules:
                reasons.append(
                    "Declarative configuration does not provide executable runtime evidence for this lifecycle/async claim."
                )
                return

            # Rule IDs/categories produced by the LLM are not stable. A runtime
            # implementation claim must therefore also be recognized from its
            # semantics, not only from the rule ID. This blocks claims such as
            # "missing error handling in the RxJS subscription" when the only
            # evidence is a JSON property like `"type": "initial"`, while
            # preserving legitimate configuration findings (for example an
            # exposed secret, insecure URL, or an actually invalid build option).
            runtime_claim_text = " ".join(
                part for part in (message, suggestion) if part
            )
            runtime_construct_terms = (
                "rxjs",
                "subscription",
                "observable",
                "unsubscribe",
                "takeuntildestroyed",
                "event listener",
                "addeventlistener",
                "removeeventlistener",
                "memory leak",
                "resource cleanup",
                "cleanup",
                "error handler",
                "error handling",
                "unhandled error",
                "promise rejection",
                "async function",
                "await ",
                "setinterval",
                "settimeout",
            )
            executable_runtime_claim = any(
                term in runtime_claim_text
                for term in runtime_construct_terms
            )
            if executable_runtime_claim:
                reasons.append(
                    "Declarative configuration cannot prove the claimed executable runtime behavior; anchor the finding to source code that contains the runtime construct."
                )
                return

            if rule_id == "data-validation":
                generic_validation_claim = any(
                    phrase in message or phrase in suggestion
                    for phrase in (
                        "validation logic is missing",
                        "missing validation",
                        "add validation logic",
                        "validate the data",
                        "ensure the data is correct",
                    )
                )
                scalar_property = re.match(
                    r'^\s*"[^"\n]+"\s*:\s*(?:true|false|null|-?\d+(?:\.\d+)?|"[^"\n]*")\s*,?\s*$',
                    line,
                    flags=re.IGNORECASE,
                ) is not None
                if generic_validation_claim and scalar_property:
                    reasons.append(
                        "Generic data-validation claim is not supported by a declarative scalar configuration property."
                    )
                    return

        # Generic business-rule validation claims need an observable constraint,
        # schema, parser, boundary, or concrete invalid-value path. A plain object
        # property assignment (for example `username: this.username`) does not by
        # itself prove that validation is required at that location.
        if rule_id == "data-validation" and extension in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
            vague_validation_claim = any(
                phrase in message or phrase in suggestion
                for phrase in (
                    "without validation",
                    "missing validation",
                    "add validation",
                    "ensure the",
                    "meets the required criteria",
                )
            )
            concrete_constraint_terms = (
                "length", "range", "minimum", "maximum", "regex", "pattern",
                "format", "schema", "required field", "null", "undefined", "empty",
                "email", "uuid", "enum", "whitelist", "allowlist", "sanitize",
            )
            combined_validation_text = f"{message} {suggestion}"
            has_concrete_constraint = any(
                term in combined_validation_text for term in concrete_constraint_terms
            )
            plain_property_assignment = re.match(
                r"^\s*[A-Za-z_$][A-Za-z0-9_$]*\s*:\s*(?:this\.)?[A-Za-z_$][A-Za-z0-9_$]*(?:[,.]?)\s*$",
                line,
            ) is not None
            if vague_validation_claim and plain_property_assignment and not has_concrete_constraint:
                reasons.append(
                    "Generic business-rule validation claim is not proven by this property assignment; no concrete constraint is evidenced."
                )
                return

        # Duplicate CSS-property claims need two declarations of the same
        # property in the same declaration block. One property occurrence is
        # insufficient evidence.
        if rule_id == "duplicate-logic" and extension in self.CSS_EXTENSIONS:
            duplicate_property_claim = (
                "defined twice" in message
                or "declared twice" in message
                or "duplicate" in message and "property" in message
                or "duplicate" in message and "margin" in message
            )
            if duplicate_property_claim:
                property_name = self._extract_css_property_from_line(line)
                if property_name and not self._css_property_duplicated_in_same_block(
                    changed_file, finding.line_number, property_name
                ):
                    reasons.append(
                        "Duplicate CSS-property claim is not supported by a second declaration in the same block."
                    )
                    return

    @staticmethod
    def _source_line(changed_file: ChangedFile, line_number: int) -> str:
        full_content = changed_file.full_content or ""
        if full_content:
            lines = full_content.splitlines()
            if 1 <= line_number <= len(lines):
                return lines[line_number - 1]
        for changed_line in changed_file.changed_lines:
            if changed_line.line_number == line_number:
                return changed_line.content
        return ""

    @staticmethod
    def _extract_css_property_from_line(line: str) -> str | None:
        match = re.match(r"\s*([A-Za-z-]+)\s*:\s*[^;{}]+;?\s*$", line)
        return match.group(1).lower() if match else None

    @staticmethod
    def _css_property_duplicated_in_same_block(
        changed_file: ChangedFile,
        line_number: int,
        property_name: str,
    ) -> bool:
        full_content = changed_file.full_content or ""
        if not full_content:
            return False
        lines = full_content.splitlines()
        if not (1 <= line_number <= len(lines)):
            return False

        # Find the nearest opening brace that owns the target declaration while
        # respecting nested blocks such as @media { selector { ... } }.
        depth = 0
        block_start = None
        for i in range(line_number - 1, -1, -1):
            text = lines[i]
            # Scan backwards within the line so close/open braces are balanced.
            for ch in reversed(text):
                if ch == "}":
                    depth += 1
                elif ch == "{":
                    if depth == 0:
                        block_start = i
                        break
                    depth -= 1
            if block_start is not None:
                break
        if block_start is None:
            return False

        depth = 0
        block_end = None
        for i in range(block_start, len(lines)):
            for ch in lines[i]:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        block_end = i
                        break
            if block_end is not None:
                break
        if block_end is None:
            block_end = len(lines) - 1

        pattern = re.compile(rf"^\s*{re.escape(property_name)}\s*:", re.IGNORECASE)
        count = sum(1 for line in lines[block_start + 1:block_end] if pattern.search(line))
        return count >= 2

    @staticmethod
    def _has_nearby_dangerous_sink(
        changed_file: ChangedFile,
        line_number: int,
        distance: int = 8,
    ) -> bool:
        """Return True only for concrete execution/rendering sinks near a claim.

        This is deliberately cross-language and evidence based.  It is not a
        vulnerability detector by itself; it merely prevents an LLM from
        upgrading a benign parser/API call into an injection/RCE claim when no
        compatible sink exists in the reviewed source.
        """
        sink_pattern = re.compile(
            r"(?:"
            r"\b(?:eval|exec|system)\s*\("
            r"|\bFunction\s*\("
            r"|\bProcessBuilder\s*\("
            r"|\bRuntime\.getRuntime\(\)\.exec\s*\("
            r"|\bsubprocess\.(?:run|call|Popen|check_output|check_call)\s*\("
            r"|\b(?:innerHTML|outerHTML)\s*="
            r"|\binsertAdjacentHTML\s*\("
            r"|\bdocument\.write\s*\("
            r"|\b(?:executeQuery|executeUpdate|execute)\s*\("
            r")",
            re.IGNORECASE,
        )
        return FindingValidator._has_nearby_source_pattern(
            changed_file, line_number, sink_pattern.pattern, distance=distance
        )

    @staticmethod
    def _symbol_return_value_is_consumed(full_content: str, symbol: str) -> bool:
        escaped = re.escape(symbol)
        usage_patterns = (
            rf"\bif\s*\([^\n)]*\b{escaped}\s*\(",
            rf"\bwhile\s*\([^\n)]*\b{escaped}\s*\(",
            rf"\breturn\s+{escaped}\s*\(",
            rf"(?:=|\?|:|&&|\|\|)\s*{escaped}\s*\(",
            rf"\b(?:const|let|var)\s+[A-Za-z_$][A-Za-z0-9_$]*\s*=\s*{escaped}\s*\(",
        )
        return any(
            re.search(pattern, full_content, flags=re.IGNORECASE | re.MULTILINE)
            for pattern in usage_patterns
        )

    @staticmethod
    def _has_nearby_empty_catch(
        changed_file: ChangedFile,
        line_number: int,
        distance: int = 3,
    ) -> bool:
        full_content = changed_file.full_content or ""
        if not full_content:
            return False

        lines = full_content.splitlines()
        start = max(0, line_number - 1 - distance)
        end = min(len(lines), line_number + distance)
        window = "\n".join(lines[start:end])

        # Allow whitespace and comments only inside the catch body.
        pattern = (
            r"\bcatch\s*(?:\([^)]*\))?\s*\{"
            r"(?:\s|//[^\n]*\n|/\*.*?\*/)*\}"
        )
        return re.search(
            pattern,
            window,
            flags=re.IGNORECASE | re.DOTALL,
        ) is not None

    @staticmethod
    def _nearby_setinterval_result_is_retained(
        changed_file: ChangedFile,
        line_number: int,
        distance: int = 3,
    ) -> bool:
        full_content = changed_file.full_content or ""
        if not full_content:
            return False

        lines = full_content.splitlines()
        start = max(0, line_number - 1 - distance)
        end = min(len(lines), line_number + distance)
        window = "\n".join(lines[start:end])

        assignment_patterns = (
            r"\b(?:const|let|var)\s+[A-Za-z_$][A-Za-z0-9_$]*\s*=\s*setInterval\s*\(",
            r"\b(?:this\.)?[A-Za-z_$][A-Za-z0-9_$]*\s*=\s*setInterval\s*\(",
        )
        return any(
            re.search(pattern, window, flags=re.IGNORECASE)
            for pattern in assignment_patterns
        )

    @staticmethod
    def _has_symbol_definition(full_content: str, symbol: str) -> bool:
        escaped = re.escape(symbol)
        patterns = (
            rf"\bfunction\s+{escaped}\s*\(",
            rf"\b(?:const|let|var)\s+{escaped}\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][A-Za-z0-9_$]*)\s*=>",
            rf"(?:^|\n)\s*(?:public\s+|private\s+|protected\s+|static\s+|async\s+)*{escaped}\s*\(",
        )
        return any(re.search(pattern, full_content, flags=re.IGNORECASE | re.MULTILINE) for pattern in patterns)

    @staticmethod
    def _has_nearby_source_pattern(
        changed_file: ChangedFile,
        line_number: int,
        pattern: str,
        distance: int = 2,
    ) -> bool:
        full_content = changed_file.full_content or ""
        if not full_content:
            return False
        lines = full_content.splitlines()
        start = max(0, line_number - 1 - distance)
        end = min(len(lines), line_number + distance)
        return re.search(pattern, "\n".join(lines[start:end]), flags=re.IGNORECASE) is not None

    def _validate_evidence(
        self,
        finding: Finding,
        changed_file: ChangedFile,
        reasons: list[str],
    ) -> None:

        rule_id = (
            finding.rule_id
            .strip()
            .lower()
        )

        extension = self._get_extension(
            changed_file.file_path
        )

        if rule_id in self.INITIALIZATION_RULES:
            if (
                extension
                not in self.JAVASCRIPT_EXTENSIONS
            ):
                reasons.append(
                    "Variable-initialization finding reported "
                    "for an unsupported file type."
                )
                return

            if not self._has_read_before_assignment_evidence(
                finding=finding,
                changed_file=changed_file,
            ):
                reasons.append(
                    "Variable initialization issue is not "
                    "supported by read-before-assignment evidence."
                )

        if extension in self.HTML_EXTENSIONS:

            if rule_id in self.HTML_STRUCTURAL_RULES:
                return

            if self._looks_like_html_behavior_claim(
                finding=finding,
            ):
                reasons.append(
                    "Behavioral functionality cannot be "
                    "proven from HTML alone."
                )

    def _has_read_before_assignment_evidence(
        self,
        finding: Finding,
        changed_file: ChangedFile,
    ) -> bool:

        variable_name = (
            self._extract_backticked_identifier(
                finding.message
            )
        )

        if variable_name is None:
            variable_name = (
                self._extract_quoted_identifier(
                    finding.message
                )
            )

        if variable_name is None:
            return False

        full_content = changed_file.full_content

        if not full_content:
            return False

        lines = full_content.splitlines()

        assignment_pattern = re.compile(
            rf"""
            (?:
                \b(?:const|let|var)\s+
                {re.escape(variable_name)}
                \s*=
            )
            |
            (?:
                \b{re.escape(variable_name)}
                \s*=
            )
            """,
            re.VERBOSE,
        )

        identifier_pattern = re.compile(
            rf"\b{re.escape(variable_name)}\b"
        )

        first_assignment_index: int | None = None
        first_usage_index: int | None = None

        for index, line in enumerate(
            lines,
            start=1,
        ):
            if (
                first_assignment_index is None
                and assignment_pattern.search(line)
            ):
                first_assignment_index = index

            if identifier_pattern.search(line):

                declaration_without_value = re.search(
                    rf"""
                    \b(?:let|var)\s+
                    {re.escape(variable_name)}
                    \s*;
                    """,
                    line,
                    flags=re.VERBOSE,
                )

                if declaration_without_value:
                    continue

                if assignment_pattern.search(line):
                    continue

                first_usage_index = index
                break

        if first_usage_index is None:
            return False

        if first_assignment_index is None:
            return True

        return (
            first_usage_index
            < first_assignment_index
        )

    def _looks_like_html_behavior_claim(
        self,
        finding: Finding,
    ) -> bool:

        rule_id = (
            finding.rule_id
            .strip()
            .lower()
        )

        if (
            rule_id.startswith("missing-")
            and rule_id
            not in self.HTML_STRUCTURAL_RULES
        ):
            return True

        if any(
            term in rule_id
            for term in self.HTML_BEHAVIOR_RULE_TERMS
        ):
            return True

        text = " ".join(
            part
            for part in (
                finding.message,
                finding.suggestion or "",
            )
            if part
        )

        return any(
            re.search(
                pattern,
                text,
                flags=re.IGNORECASE,
            )
            is not None
            for pattern
            in self.HTML_BEHAVIOR_MESSAGE_PATTERNS
        )

    @staticmethod
    def _extract_backticked_identifier(
        text: str,
    ) -> str | None:

        match = re.search(
            r"`([A-Za-z_$][A-Za-z0-9_$]*)`",
            text,
        )

        if match:
            return match.group(1)

        return None

    @staticmethod
    def _extract_quoted_identifier(
        text: str,
    ) -> str | None:

        match = re.search(
            r"'([A-Za-z_$][A-Za-z0-9_$]*)'",
            text,
        )

        if match:
            return match.group(1)

        return None

    @staticmethod
    def _get_extension(
        file_path: str,
    ) -> str:

        normalized = file_path.lower()

        for extension in (
            ".scss",
            ".sass",
            ".less",
            ".html",
            ".htm",
            ".jsx",
            ".tsx",
            ".mjs",
            ".cjs",
            ".css",
            ".jsonc",
            ".json",
            ".js",
            ".ts",
        ):
            if normalized.endswith(
                extension
            ):
                return extension

        return ""
