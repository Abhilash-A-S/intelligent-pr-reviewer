import re
from dataclasses import dataclass, field

from pr_reviewer.review.models import Finding, FindingSource
from pr_reviewer.review.rules import DEFAULT_RULE_REGISTRY, AIPolicy, RuleRegistry
from pr_reviewer.review.root_cause_matcher import RootCauseMatcher


@dataclass
class OwnershipValidationResult:
    accepted: bool
    reasons: list[str] = field(default_factory=list)


class FindingOwnershipValidator:
    """
    Enforces the universal rule ownership boundary.

    Deterministic/framework/compiler-owned rule families cannot be invented by
    the LLM. An LLM instance of such a rule is admitted only when an
    authoritative finding for the same concrete issue already exists; the
    deduplicator then keeps the authoritative finding.

    Unknown LLM rule IDs are rejected. This is intentional: the LLM must use a
    registered universal semantic category instead of silently expanding the
    product's rule vocabulary on every run.
    """

    SUBJECT_SENSITIVE_RULES = {
        "hardcoded-secret",
        "unused-variable",
        "unused-import",
        "unused-parameter",
    }

    def __init__(self, registry: RuleRegistry | None = None):
        self.registry = registry or DEFAULT_RULE_REGISTRY
        self.root_cause_matcher = RootCauseMatcher(self.registry)

    def validate(
        self,
        finding: Finding,
        authoritative_findings: list[Finding],
        changed_file_map: dict | None = None,
    ) -> OwnershipValidationResult:
        if finding.source != FindingSource.LLM:
            return OwnershipValidationResult(True)

        definition = self.registry.get(finding.rule_id)
        if definition is None:
            return OwnershipValidationResult(
                False,
                [
                    "AI rule is not registered in the universal rule registry. "
                    "Use a registered semantic category instead of inventing a new rule ID."
                ],
            )

        # Even AI-owned semantic categories cannot create a second finding for
        # a root cause that deterministic/framework/compiler analysis has already
        # proven. Match by defect semantics + nearby source location, not merely
        # by the LLM's chosen rule ID.
        if self._duplicates_authoritative_root_cause(finding, authoritative_findings, changed_file_map):
            return OwnershipValidationResult(
                False,
                [
                    "AI finding describes the same root cause as an authoritative "
                    "finding already produced for this changed code."
                ],
            )

        if definition.ai_policy == AIPolicy.VALIDATE:
            return OwnershipValidationResult(True)

        if self._has_authoritative_match(finding, authoritative_findings):
            return OwnershipValidationResult(True)

        return OwnershipValidationResult(
            False,
            [
                "This rule family is owned by deterministic/framework analysis; "
                "AI cannot create it independently without authoritative evidence."
            ],
        )

    def _duplicates_authoritative_root_cause(
        self,
        finding: Finding,
        authoritative_findings: list[Finding],
        changed_file_map: dict | None = None,
    ) -> bool:
        for candidate in authoritative_findings:
            if candidate.source == FindingSource.LLM:
                continue
            if self.root_cause_matcher.same_root_cause(finding, candidate, changed_file_map):
                return True
        return False

    def _has_authoritative_match(
        self,
        finding: Finding,
        authoritative_findings: list[Finding],
    ) -> bool:
        for candidate in authoritative_findings:
            if candidate.source == FindingSource.LLM:
                continue
            if candidate.file_path != finding.file_path:
                continue
            if self.registry.resolve(candidate.rule_id) != self.registry.resolve(finding.rule_id):
                continue

            if finding.rule_id in self.SUBJECT_SENSITIVE_RULES:
                finding_subject = self._subject(finding)
                candidate_subject = self._subject(candidate)
                if finding_subject and candidate_subject:
                    if finding_subject != candidate_subject:
                        continue
                    if abs(candidate.line_number - finding.line_number) <= 10:
                        return True
                    continue

            if abs(candidate.line_number - finding.line_number) <= 5:
                return True

        return False

    @staticmethod
    def _subject(finding: Finding) -> str | None:
        text = f"{finding.message} {finding.suggestion or ''}"
        quoted = re.findall(r"['\"]([A-Za-z_$][\w$.-]*)['\"]", text)
        if quoted:
            return quoted[0].lower()
        return None
