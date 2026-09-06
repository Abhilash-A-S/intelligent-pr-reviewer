from pr_reviewer.providers.base import PullRequestProvider
from pr_reviewer.publishing.models import (
    SummaryPublishingAction,
    SummaryPublishingResult,
)


class SummaryPublishingService:
    """
    Publishes exactly one Intelligent PR Reviewer summary
    to a Pull Request.

    If the summary already exists, it is updated instead
    of creating another duplicate comment.
    """

    SUMMARY_MARKER = (
        "<!-- intelligent-pr-reviewer:summary -->"
    )

    def __init__(
        self,
        provider: PullRequestProvider,
    ):
        self.provider = provider

    def publish(
        self,
        repository: str,
        pull_number: int,
        summary: str,
    ) -> SummaryPublishingResult:

        comments = self.provider.get_summary_comments(
            repository=repository,
            pull_number=pull_number,
        )

        existing_summary = (
            self._find_existing_summary(
                comments
            )
        )

        body = self._build_body(
            summary
        )

        if existing_summary is not None:
            comment = (
                self.provider.update_summary_comment(
                    repository=repository,
                    comment_id=existing_summary["id"],
                    body=body,
                )
            )

            return SummaryPublishingResult(
                action=SummaryPublishingAction.UPDATED,
                comment=comment,
            )

        comment = (
            self.provider.publish_summary_comment(
                repository=repository,
                pull_number=pull_number,
                body=body,
            )
        )

        return SummaryPublishingResult(
            action=SummaryPublishingAction.CREATED,
            comment=comment,
        )

    @classmethod
    def _build_body(
        cls,
        summary: str,
    ) -> str:
        return (
            f"{cls.SUMMARY_MARKER}\n\n"
            f"{summary.strip()}"
        )

    @classmethod
    def _find_existing_summary(
        cls,
        comments: list[dict],
    ) -> dict | None:

        for comment in comments:
            body = comment.get(
                "body",
                "",
            )

            if cls.SUMMARY_MARKER in body:
                return comment

        return None