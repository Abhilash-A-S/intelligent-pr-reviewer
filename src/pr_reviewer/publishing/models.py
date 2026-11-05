from dataclasses import dataclass, field
from enum import Enum


@dataclass
class PublishingResult:
    published_comments: list[dict] = field(
        default_factory=list
    )

    skipped_duplicates: int = 0
    failed_comments: list[dict] = field(default_factory=list)
    summary_only_findings: int = 0
    grouped_findings: int = 0
    rate_limited: bool = False

    @property
    def published_count(self) -> int:
        return len(self.published_comments)

    @property
    def total_processed(self) -> int:
        return (
            self.published_count
            + self.skipped_duplicates
            + self.failed_count
            + self.summary_only_findings
        )

    @property
    def failed_count(self) -> int:
        return len(self.failed_comments)


class SummaryPublishingAction(str, Enum):
    CREATED = "created"
    UPDATED = "updated"


@dataclass
class SummaryPublishingResult:
    action: SummaryPublishingAction
    comment: dict

    @property
    def comment_id(self) -> int | None:
        return self.comment.get("id")
