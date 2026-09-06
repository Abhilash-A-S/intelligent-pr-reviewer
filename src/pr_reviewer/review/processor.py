from pr_reviewer.context.models import (
    RepositoryContext,
)
from pr_reviewer.review.deduplicator import (
    FindingDeduplicator,
)
from pr_reviewer.review.finding_policy import (
    FindingPolicy,
)
from pr_reviewer.review.finding_ownership_validator import (
    FindingOwnershipValidator,
)
from pr_reviewer.review.finding_validator import (
    FindingValidator,
)
from pr_reviewer.review.framework_evidence_validator import (
    FrameworkEvidenceValidator,
)
from pr_reviewer.review.framework_fact_validator import (
    FrameworkFactValidator,
)
from pr_reviewer.review.professionalizer import FindingProfessionalizer
from pr_reviewer.review.models import (
    ChangedFile,
    Finding,
    FindingSource,
)
from pr_reviewer.review.normalizer import (
    FindingNormalizer,
)
from pr_reviewer.review.test_evidence_validator import (
    TestEvidenceValidator,
)
from pr_reviewer.review.semantic_evidence_validator import (
    UniversalSemanticEvidenceValidator,
)


class FindingProcessor:
    """
    Processes findings before they reach the quality gate.

    Pipeline:

    Raw findings
        ↓
    Normalize
        ↓
    Generic validation
        ↓
    Framework evidence validation
        ↓
    Framework fact validation
        ↓
    Test evidence validation
        ↓
    Apply deterministic policy
        ↓
    Deduplicate
        ↓
    Final findings

    Responsibilities:

    FindingValidator
        Generic structural and evidence validation.

    FrameworkEvidenceValidator
        Cross-file framework evidence validation.

    FrameworkFactValidator
        Deterministic framework/runtime facts.

    TestEvidenceValidator
        Protects against speculative or incorrect
        test-specific findings.

    FindingPolicy
        Product-level noise and severity policy.

    FindingDeduplicator
        Removes duplicate findings before the
        quality gate and publishing layers.
    """

    def __init__(
        self,
        normalizer: FindingNormalizer | None = None,
        validator: FindingValidator | None = None,
        framework_evidence_validator: (
            FrameworkEvidenceValidator | None
        ) = None,
        policy: FindingPolicy | None = None,
        deduplicator: FindingDeduplicator | None = None,
        framework_fact_validator: (
            FrameworkFactValidator | None
        ) = None,
        test_evidence_validator: (
            TestEvidenceValidator | None
        ) = None,
        ownership_validator: (
            FindingOwnershipValidator | None
        ) = None,
        semantic_evidence_validator: UniversalSemanticEvidenceValidator | None = None,
    ):
        self.normalizer = (
            normalizer
            or FindingNormalizer()
        )

        self.validator = (
            validator
            or FindingValidator()
        )

        self.framework_evidence_validator = (
            framework_evidence_validator
            or FrameworkEvidenceValidator()
        )

        self.framework_fact_validator = (
            framework_fact_validator
            or FrameworkFactValidator()
        )

        self.test_evidence_validator = (
            test_evidence_validator
            or TestEvidenceValidator()
        )

        self.ownership_validator = (
            ownership_validator
            or FindingOwnershipValidator()
        )
        self.semantic_evidence_validator = (
            semantic_evidence_validator or UniversalSemanticEvidenceValidator()
        )

        self.policy = (
            policy
            or FindingPolicy()
        )

        self.deduplicator = (
            deduplicator
            or FindingDeduplicator()
        )

    def process(
        self,
        findings: list[Finding],
        changed_files: list[ChangedFile],
        repository_context: RepositoryContext | None = None,
    ) -> list[Finding]:

        if not findings:
            return []

        changed_file_map = {
            changed_file.file_path: changed_file
            for changed_file in changed_files
        }

        # --------------------------------------------------
        # 1. Normalize
        # --------------------------------------------------

        normalized_findings = [
            self.normalizer.normalize(
                finding
            )
            for finding in findings
        ]

        # --------------------------------------------------
        # 2. Generic validation
        # --------------------------------------------------

        validated_findings: list[
            Finding
        ] = []

        validation_rejected = 0

        for finding in normalized_findings:

            changed_file = changed_file_map.get(
                finding.file_path
            )

            if changed_file is None:
                self._print_rejection(
                    finding=finding,
                    reasons=[
                        (
                            "Changed file could not "
                            "be resolved."
                        )
                    ],
                )

                validation_rejected += 1
                continue

            validation = (
                self.validator.validate(
                    finding=finding,
                    changed_file=changed_file,
                )
            )

            if not validation.accepted:
                self._print_rejection(
                    finding=finding,
                    reasons=validation.reasons,
                )

                validation_rejected += 1
                continue

            validated_findings.append(
                finding
            )

        semantic_validated_findings: list[Finding] = []
        semantic_rejected = 0
        for finding in validated_findings:
            changed_file = changed_file_map[finding.file_path]
            validation = self.semantic_evidence_validator.validate(finding, changed_file)
            if not validation.accepted:
                self._print_rejection(finding=finding, reasons=validation.reasons)
                semantic_rejected += 1
                continue
            semantic_validated_findings.append(finding)
        validated_findings = semantic_validated_findings

        # --------------------------------------------------
        # 3. Universal rule ownership / AI admission
        # --------------------------------------------------

        authoritative_findings = [
            finding
            for finding in normalized_findings
            if finding.source.value != "llm"
        ]

        ownership_validated_findings: list[Finding] = []
        ownership_rejected = 0

        for finding in validated_findings:
            validation = self.ownership_validator.validate(
                finding=finding,
                authoritative_findings=authoritative_findings,
            )

            if not validation.accepted:
                self._print_rejection(
                    finding=finding,
                    reasons=validation.reasons,
                )
                ownership_rejected += 1
                continue

            ownership_validated_findings.append(finding)

        # --------------------------------------------------
        # 4. Framework evidence validation
        # --------------------------------------------------

        evidence_validated_findings: list[
            Finding
        ] = []

        framework_evidence_rejected = 0

        for finding in ownership_validated_findings:

            changed_file = changed_file_map.get(
                finding.file_path
            )

            if changed_file is None:
                continue

            if finding.source in {
                FindingSource.STATIC,
                FindingSource.FRAMEWORK,
                FindingSource.COMPILER,
            }:
                evidence_validated_findings.append(finding)
                continue

            validation = (
                self.framework_evidence_validator.validate(
                    finding=finding,
                    changed_file=changed_file,
                    changed_files=changed_files,
                    repository_context=(
                        repository_context
                    ),
                )
            )

            if not validation.accepted:
                self._print_rejection(
                    finding=finding,
                    reasons=validation.reasons,
                )

                framework_evidence_rejected += 1
                continue

            evidence_validated_findings.append(
                finding
            )

        # --------------------------------------------------
        # 4. Framework fact validation
        # --------------------------------------------------

        fact_validated_findings: list[
            Finding
        ] = []

        framework_fact_rejected = 0

        for finding in evidence_validated_findings:

            changed_file = changed_file_map.get(
                finding.file_path
            )

            if changed_file is None:
                continue

            if finding.source in {
                FindingSource.STATIC,
                FindingSource.FRAMEWORK,
                FindingSource.COMPILER,
            }:
                fact_validated_findings.append(finding)
                continue

            validation = (
                self.framework_fact_validator.validate(
                    finding=finding,
                    changed_file=changed_file,
                    changed_files=changed_files,
                    repository_context=(
                        repository_context
                    ),
                )
            )

            if not validation.accepted:
                self._print_rejection(
                    finding=finding,
                    reasons=validation.reasons,
                )

                framework_fact_rejected += 1
                continue

            fact_validated_findings.append(
                finding
            )

        # --------------------------------------------------
        # 5. Test evidence validation
        # --------------------------------------------------
        #
        # This stage is intentionally separate from
        # framework validation.
        #
        # Test files have their own semantics regardless
        # of whether the repository uses Angular, React,
        # Vue, Python, Java, .NET, etc.
        #
        # Examples of false positives rejected here:
        #
        # - requiring fixture.whenStable() without
        #   concrete asynchronous behavior
        #
        # - claiming a test is incorrect merely because
        #   an asserted DOM element may not exist
        #
        # Real test defects continue through the pipeline.
        # --------------------------------------------------

        test_validated_findings: list[
            Finding
        ] = []

        test_evidence_rejected = 0

        for finding in fact_validated_findings:

            changed_file = changed_file_map.get(
                finding.file_path
            )

            if changed_file is None:
                continue

            if finding.source in {
                FindingSource.STATIC,
                FindingSource.FRAMEWORK,
                FindingSource.COMPILER,
            }:
                test_validated_findings.append(finding)
                continue

            validation = (
                self.test_evidence_validator.validate(
                    finding=finding,
                    changed_file=changed_file,
                )
            )

            if not validation.accepted:
                self._print_rejection(
                    finding=finding,
                    reasons=validation.reasons,
                )

                test_evidence_rejected += 1
                continue

            test_validated_findings.append(
                finding
            )

        # --------------------------------------------------
        # 6. Apply deterministic finding policy
        # --------------------------------------------------

        policy_findings: list[
            Finding
        ] = []

        policy_rejected = 0
        severity_adjusted = 0

        for finding in test_validated_findings:

            processed = self.policy.apply(
                finding
            )

            if processed is None:
                print(
                    f"🛡️ Policy rejected: "
                    f"{finding.file_path}:"
                    f"{finding.line_number} "
                    f"[{finding.rule_id}]"
                )

                policy_rejected += 1
                continue

            if (
                processed.severity
                != finding.severity
            ):
                print(
                    f"⚖️ Severity adjusted: "
                    f"{finding.file_path}:"
                    f"{finding.line_number} "
                    f"[{finding.rule_id}] "
                    f"{finding.severity.value.upper()} "
                    f"→ "
                    f"{processed.severity.value.upper()}"
                )

                severity_adjusted += 1

            policy_findings.append(
                processed
            )

        # --------------------------------------------------
        # 7. Deduplicate
        # --------------------------------------------------

        final_findings = (
            self.deduplicator.deduplicate(
                policy_findings,
                changed_files=changed_files,
            )
        )

        duplicates_removed = (
            len(policy_findings)
            - len(final_findings)
        )

        # --------------------------------------------------
        # 8. Professional presentation metadata
        # --------------------------------------------------

        final_findings = [
            FindingProfessionalizer.enrich(
                finding=finding,
                changed_file=changed_file_map.get(finding.file_path),
            )
            for finding in final_findings
        ]

        # --------------------------------------------------
        # Processing summary
        # --------------------------------------------------

        print()
        print("🛡️ Finding processing")
        print("-------------------------")

        print(
            f"Raw       : "
            f"{len(findings)}"
        )

        print(
            f"Validated : "
            f"{len(validated_findings)}"
        )

        print(
            f"Rejected  : "
            f"{validation_rejected}"
        )

        print(
            f"Semantic  : "
            f"{semantic_rejected} rejected"
        )

        print(
            f"Ownership : "
            f"{ownership_rejected} rejected"
        )

        print(
            f"Evidence  : "
            f"{framework_evidence_rejected} rejected"
        )

        print(
            f"Facts     : "
            f"{framework_fact_rejected} rejected"
        )

        print(
            f"Tests     : "
            f"{test_evidence_rejected} rejected"
        )

        print(
            f"Policy    : "
            f"{policy_rejected} rejected"
        )

        print(
            f"Adjusted  : "
            f"{severity_adjusted}"
        )

        print(
            f"Duplicates: "
            f"{duplicates_removed}"
        )

        print(
            f"Final     : "
            f"{len(final_findings)}"
        )

        return final_findings

    @staticmethod
    def _print_rejection(
        finding: Finding,
        reasons: list[str],
    ) -> None:

        print(
            f"🛡️ Rejected finding: "
            f"{finding.file_path}:"
            f"{finding.line_number} "
            f"[{finding.rule_id}]"
        )

        for reason in reasons:
            print(
                f"   Reason: {reason}"
            )
