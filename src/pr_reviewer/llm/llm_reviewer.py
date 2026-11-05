from dataclasses import dataclass
from threading import Lock

from pr_reviewer.context.models import RepositoryContext
from pr_reviewer.llm.base import LLMProvider
from pr_reviewer.llm.parser import LLMResponseParser
from pr_reviewer.llm.review_planner import (
    FileReviewPlanner,
)
from pr_reviewer.review.models import (
    ChangedFile,
    Finding,
)


@dataclass(frozen=True)
class LLMExecutionStats:
    actual_calls: int = 0
    retries: int = 0
    failed_parts: int = 0


class LLMReviewer:
    """
    Coordinates LLM-based semantic review.

    Responsibilities:
    - Build a file review plan.
    - Call the configured LLM provider.
    - Retry recoverable malformed responses.
    - Parse and validate LLM responses.
    - Restrict findings to changed/commentable lines.
    - Convert validated LLM findings into domain Findings.

    Finding normalization is intentionally NOT performed
    here. Canonical rule IDs and severity policies belong
    to FindingNormalizer / FindingProcessor.
    """

    DEFAULT_MAX_ATTEMPTS = 2

    def __init__(
        self,
        llm_provider: LLMProvider,
        response_parser: LLMResponseParser | None = None,
        review_planner: FileReviewPlanner | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ):
        if max_attempts <= 0:
            raise ValueError(
                "max_attempts must be greater than 0."
            )

        self.llm_provider = llm_provider

        self.response_parser = (
            response_parser
            or LLMResponseParser()
        )

        self.review_planner = (
            review_planner
            or FileReviewPlanner()
        )

        self.max_attempts = max_attempts
        self._stats_lock = Lock()
        self._actual_calls = 0
        self._retries = 0
        self._failed_parts = 0

    def reset_execution_stats(self) -> None:
        with self._stats_lock:
            self._actual_calls = 0
            self._retries = 0
            self._failed_parts = 0

    def execution_stats(self) -> LLMExecutionStats:
        with self._stats_lock:
            return LLMExecutionStats(
                actual_calls=self._actual_calls,
                retries=self._retries,
                failed_parts=self._failed_parts,
            )

    def review(
        self,
        changed_file: ChangedFile,
        repository_context: RepositoryContext,
    ) -> list[Finding]:

        if not changed_file.changed_lines:
            return []

        # --------------------------------------------------
        # Build file-first review plan.
        # --------------------------------------------------

        plan = self.review_planner.plan(
            changed_file
        )

        all_findings: list[Finding] = []

        print()
        print(
            f"📄 Reviewing "
            f"{changed_file.file_path}"
        )

        print(
            f"   Changed lines : "
            f"{len(changed_file.changed_lines)}"
        )

        print(
            f"   Review mode   : "
            f"{plan.mode.value.upper()}"
        )

        print(
            f"   LLM calls     : "
            f"{plan.llm_call_count}"
        )

        if changed_file.full_content:
            print(
                "   File context  : available"
            )
        else:
            print(
                "   File context  : unavailable"
            )

        # --------------------------------------------------
        # Review each planned part.
        # --------------------------------------------------

        for part in plan.parts:

            print()
            print(
                f"   🧠 Reviewing part "
                f"{part.index}/{part.total}..."
            )

            part_file = ChangedFile(
                file_path=changed_file.file_path,
                status=changed_file.status,
                language=changed_file.language,
                patch=changed_file.patch,
                changed_lines=part.changed_lines,
                full_content=changed_file.full_content,
            )

            mapped_findings = (
                self._review_part(
                    changed_file=part_file,
                    repository_context=(
                        repository_context
                    ),
                    part_index=part.index,
                )
            )

            all_findings.extend(
                mapped_findings
            )

            print(
                f"   ✅ Part complete — "
                f"{len(mapped_findings)} "
                f"finding(s)"
            )

        return all_findings

    def review_batch(
        self,
        changed_files: list[ChangedFile],
        repository_context: RepositoryContext,
    ) -> list[Finding]:
        """Review a compatible small-file batch with strict file/line mapping."""

        if not changed_files:
            return []
        if len(changed_files) == 1:
            return self.review(changed_files[0], repository_context)

        for attempt in range(1, self.max_attempts + 1):
            with self._stats_lock:
                self._actual_calls += 1
                if attempt > 1:
                    self._retries += 1
            try:
                raw_response = self.llm_provider.review_batch(
                    changed_files=changed_files,
                    repository_context=repository_context,
                )
                response = self.response_parser.parse(raw_response)
                return self._map_batch_findings(changed_files, response.findings)
            except Exception as exc:
                if attempt < self.max_attempts:
                    print(
                        f"   ⚠️ Batch attempt {attempt}/{self.max_attempts} "
                        f"failed: {type(exc).__name__}: {exc}"
                    )
                    continue
                print(
                    f"   ⚠️ Batch failed after {self.max_attempts} "
                    f"attempt(s): {type(exc).__name__}: {exc}"
                )

        with self._stats_lock:
            self._failed_parts += 1
        return []

    @staticmethod
    def _map_batch_findings(
        changed_files: list[ChangedFile],
        llm_findings,
    ) -> list[Finding]:
        files_by_path = {file.file_path: file for file in changed_files}
        mapped: list[Finding] = []
        for llm_finding in llm_findings:
            if not llm_finding.file_path:
                print("   🛡️ Rejected batch finding: missing file_path")
                continue
            changed_file = files_by_path.get(llm_finding.file_path)
            if changed_file is None:
                print(
                    "   🛡️ Rejected batch finding: file is outside this batch "
                    f"[{llm_finding.file_path}]"
                )
                continue
            mapped.extend(
                LLMReviewer._map_findings(changed_file, [llm_finding])
            )
        return mapped

    def _review_part(
        self,
        changed_file: ChangedFile,
        repository_context: RepositoryContext,
        part_index: int,
    ) -> list[Finding]:
        """
        Review one planned part.

        Invalid JSON or invalid response schema is treated
        as a recoverable LLM response failure and retried.

        Provider/runtime failures are also retried because
        local and remote LLM backends can fail transiently.

        If every attempt fails, the part is skipped without
        crashing the complete PR review.
        """

        last_exception: Exception | None = None

        for attempt in range(
            1,
            self.max_attempts + 1,
        ):

            with self._stats_lock:
                self._actual_calls += 1
                if attempt > 1:
                    self._retries += 1

            try:
                if attempt > 1:
                    print(
                        f"   🔄 Retry "
                        f"{attempt}/"
                        f"{self.max_attempts}..."
                    )

                raw_response = (
                    self.llm_provider.review(
                        changed_file=changed_file,
                        repository_context=(
                            repository_context
                        ),
                    )
                )

                response = (
                    self.response_parser.parse(
                        raw_response
                    )
                )

                return self._map_findings(
                    changed_file=changed_file,
                    llm_findings=(
                        response.findings
                    ),
                )

            except Exception as exc:
                last_exception = exc

                if attempt < self.max_attempts:
                    print(
                        f"   ⚠️ Attempt "
                        f"{attempt}/"
                        f"{self.max_attempts} "
                        f"failed: "
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    )

                    continue

                print(
                    f"   ⚠️ Part "
                    f"{part_index} failed after "
                    f"{self.max_attempts} "
                    f"attempt(s): "
                    f"{type(exc).__name__}: "
                    f"{exc}"
                )

        # Defensive fallback.
        #
        # The loop above always returns or reaches this
        # point after exhausting all attempts.
        if last_exception is not None:
            with self._stats_lock:
                self._failed_parts += 1
            return []

        return []

    @staticmethod
    def _map_findings(
        changed_file: ChangedFile,
        llm_findings,
    ) -> list[Finding]:

        mapped_findings: list[Finding] = []

        # --------------------------------------------------
        # Real source line -> changed line.
        #
        # This is a critical safety boundary.
        #
        # The LLM cannot create an inline finding for a
        # source line that is not part of the PR diff.
        # --------------------------------------------------

        changed_line_map = {
            line.line_number: line
            for line in changed_file.changed_lines
        }

        for llm_finding in llm_findings:

            source_line_number = (
                llm_finding.line_number
            )

            changed_line = (
                changed_line_map.get(
                    source_line_number
                )
            )

            if changed_line is None:
                print(
                    f"   🛡️ Rejected finding "
                    f"on non-commentable line "
                    f"{source_line_number}"
                )

                continue

            # --------------------------------------------------
            # IMPORTANT:
            #
            # Do not normalize rule IDs or severity here.
            #
            # FindingNormalizer is the single normalization
            # boundary for findings coming from:
            #
            # - LLM review
            # - static analysis
            # - security scanners
            # - future analyzers
            # --------------------------------------------------

            mapped_findings.append(
                Finding(
                    file_path=(
                        changed_line.file_path
                    ),
                    line_number=(
                        changed_line.line_number
                    ),
                    severity=(
                        llm_finding.severity
                    ),
                    rule_id=(
                        llm_finding.rule_id
                    ),
                    message=(
                        llm_finding
                        .message
                        .strip()
                    ),
                    suggestion=(
                        llm_finding
                        .suggestion
                        .strip()
                        if (
                            llm_finding
                            .suggestion
                        )
                        else None
                    ),
                    diff_position=(
                        changed_line
                        .diff_position
                    ),
                )
            )

        return mapped_findings
