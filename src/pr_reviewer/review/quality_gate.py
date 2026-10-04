from dataclasses import dataclass
from enum import Enum

from pr_reviewer.review.models import Finding, Severity


class QualityGateDecision(str, Enum):
    BLOCK = "block"
    REQUEST_CHANGES = "request_changes"
    REVIEW_RECOMMENDED = "review_recommended"
    NON_BLOCKING = "non_blocking"
    OPTIONAL = "optional"
    PASS = "pass"


@dataclass(frozen=True)
class QualityGateResult:
    decision: QualityGateDecision

    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    suggestion_count: int = 0

    @property
    def total_findings(self) -> int:
        return (
            self.critical_count
            + self.high_count
            + self.medium_count
            + self.low_count
            + self.suggestion_count
        )

    @property
    def should_block_merge(self) -> bool:
        return self.decision == QualityGateDecision.BLOCK

    @property
    def should_request_changes(self) -> bool:
        return self.decision in {
            QualityGateDecision.BLOCK,
            QualityGateDecision.REQUEST_CHANGES,
        }


class QualityGate:
    """
    Evaluates review findings and determines the overall
    Pull Request quality decision.

    Decision priority:

    Critical   -> BLOCK
    High       -> REQUEST_CHANGES
    Medium     -> REVIEW_RECOMMENDED
    Low        -> NON_BLOCKING
    Suggestion -> OPTIONAL
    No issues  -> PASS
    """

    def evaluate(
        self,
        findings: list[Finding],
    ) -> QualityGateResult:

        counts = {
            Severity.CRITICAL: 0,
            Severity.HIGH: 0,
            Severity.MEDIUM: 0,
            Severity.LOW: 0,
            Severity.SUGGESTION: 0,
        }

        for finding in findings:
            counts[finding.severity] += 1

        decision = self._determine_decision(
            critical_count=counts[Severity.CRITICAL],
            high_count=counts[Severity.HIGH],
            medium_count=counts[Severity.MEDIUM],
            low_count=counts[Severity.LOW],
            suggestion_count=counts[Severity.SUGGESTION],
        )

        return QualityGateResult(
            decision=decision,
            critical_count=counts[Severity.CRITICAL],
            high_count=counts[Severity.HIGH],
            medium_count=counts[Severity.MEDIUM],
            low_count=counts[Severity.LOW],
            suggestion_count=counts[Severity.SUGGESTION],
        )

    @staticmethod
    def _determine_decision(
        critical_count: int,
        high_count: int,
        medium_count: int,
        low_count: int,
        suggestion_count: int,
    ) -> QualityGateDecision:

        if critical_count > 0:
            return QualityGateDecision.BLOCK

        if high_count > 0:
            return QualityGateDecision.REQUEST_CHANGES

        if medium_count > 0:
            return QualityGateDecision.REVIEW_RECOMMENDED

        if low_count > 0:
            return QualityGateDecision.NON_BLOCKING

        if suggestion_count > 0:
            return QualityGateDecision.OPTIONAL

        return QualityGateDecision.PASS