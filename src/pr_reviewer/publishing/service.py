from pr_reviewer.providers.base import PullRequestProvider
from pr_reviewer.publishing.comment import (
    InlineCommentFormatter,
)
from pr_reviewer.publishing.models import (
    PublishingResult,
)
from pr_reviewer.review.models import Finding, Severity


class PublishingService:
    """
    Provider-independent Pull Request publishing service.

    Responsibilities:
    - Prevent duplicate AI review comments.
    - Format inline comments.
    - Publish comments through PullRequestProvider.

    This class does not know whether the provider is:
    - GitHub
    - Azure DevOps
    - GitLab
    - Bitbucket
    """

    def __init__(
        self,
        provider: PullRequestProvider,
        comment_formatter: type[
            InlineCommentFormatter
        ] = InlineCommentFormatter,
        max_inline_comments: int = 40,
    ):
        self.provider = provider
        self.comment_formatter = comment_formatter
        self.max_inline_comments = max(0, max_inline_comments)

    def publish_findings(
        self,
        repository: str,
        pull_number: int,
        commit_id: str,
        findings: list[Finding],
    ) -> PublishingResult:

        existing_comments = (
            self.provider.get_existing_comments(
                repository=repository,
                pull_number=pull_number,
            )
        )

        result = PublishingResult()

        existing_markers = (
            self._extract_existing_markers(
                existing_comments
            )
        )

        new_findings: list[Finding] = []
        run_markers: set[str] = set()
        for finding in findings:
            marker = self._build_marker(
                finding
            )

            if marker in existing_markers or marker in run_markers:
                result.skipped_duplicates += 1
                continue
            run_markers.add(marker)
            new_findings.append(finding)

        groups = self._group_findings(new_findings)
        result.grouped_findings = len(new_findings) - len(groups)

        existing_review_comments = sum(
            1 for comment in existing_comments
            if "<!-- intelligent-pr-reviewer:" in comment.get("body", "")
        )
        available = max(0, self.max_inline_comments - existing_review_comments)
        selected = groups[:available]
        deferred = groups[available:]
        result.summary_only_findings = sum(len(group) for group in deferred)

        if not selected:
            return result

        if getattr(self.provider, "supports_batch_inline_comments", False) is True:
            return self._publish_batch(
                repository, pull_number, commit_id, selected, result
            )

        for group in selected:
            finding = group[0]
            body = self.comment_formatter.format_group(group)

            try:
                comment = self.provider.publish_inline_comment(
                    repository=repository,
                    pull_number=pull_number,
                    body=body,
                    commit_id=commit_id,
                    file_path=finding.file_path,
                    line_number=finding.line_number,
                    diff_position=finding.diff_position,
                )
            except Exception as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status in {401, 403}:
                    raise
                result.failed_comments.append({
                    "file_path": finding.file_path,
                    "line_number": finding.line_number,
                    "rule_id": finding.rule_id,
                    "error": f"{type(exc).__name__}: {exc}",
                })
                print(
                    f"   ⚠️ Inline comment skipped: {finding.file_path}:"
                    f"{finding.line_number} [{finding.rule_id}] — {exc}"
                )
                continue

            result.published_comments.append(
                comment
            )

        return result

    def _publish_batch(
        self,
        repository: str,
        pull_number: int,
        commit_id: str,
        groups: list[list[Finding]],
        result: PublishingResult,
    ) -> PublishingResult:
        comments = [{
            "file_path": group[0].file_path,
            "line_number": group[0].line_number,
            "diff_position": group[0].diff_position,
            "body": self.comment_formatter.format_group(group),
        } for group in groups]
        try:
            review = self.provider.publish_inline_comments_batch(
                repository=repository,
                pull_number=pull_number,
                commit_id=commit_id,
                comments=comments,
            )
        except Exception as exc:
            result.rate_limited = self._is_rate_limited(exc)
            for group in groups:
                for finding in group:
                    result.failed_comments.append({
                        "file_path": finding.file_path,
                        "line_number": finding.line_number,
                        "rule_id": finding.rule_id,
                        "error": f"{type(exc).__name__}: {exc}",
                    })
            print(f"   ⚠️ Batched inline review was not published — {exc}")
            return result

        review_id = review.get("id") if isinstance(review, dict) else None
        for group in groups:
            result.published_comments.append({
                "review_id": review_id,
                "file_path": group[0].file_path,
                "line_number": group[0].line_number,
                "finding_count": len(group),
            })
        return result

    @staticmethod
    def _group_findings(findings: list[Finding]) -> list[list[Finding]]:
        severity_rank = {
            Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2,
            Severity.LOW: 3, Severity.SUGGESTION: 4,
        }
        ordered = sorted(
            enumerate(findings),
            key=lambda item: (severity_rank[item[1].severity], item[0]),
        )
        grouped: dict[tuple[str, int], list[Finding]] = {}
        for _index, finding in ordered:
            grouped.setdefault((finding.file_path, finding.line_number), []).append(finding)
        return list(grouped.values())

    @staticmethod
    def _is_rate_limited(exc: Exception) -> bool:
        text = str(exc).lower()
        status = getattr(getattr(exc, "response", None), "status_code", None)
        return status in {403, 429} or any(marker in text for marker in (
            "submitted too quickly", "secondary rate limit", "abuse detection",
        ))

    @staticmethod
    def _build_marker(
        finding: Finding,
    ) -> str:
        return (
            f"<!-- intelligent-pr-reviewer:"
            f"{finding.rule_id}:"
            f"{finding.file_path}:"
            f"{finding.line_number} -->"
        )

    @staticmethod
    def _extract_existing_markers(
        comments: list[dict],
    ) -> set[str]:

        markers: set[str] = set()

        marker_prefix = (
            "<!-- intelligent-pr-reviewer:"
        )

        for comment in comments:
            body = comment.get(
                "body",
                "",
            )

            for line in body.splitlines():
                stripped = line.strip()

                if (
                    stripped.startswith(marker_prefix)
                    and stripped.endswith("-->")
                ):
                    markers.add(stripped)

        return markers
