from unittest.mock import Mock

from pr_reviewer.publishing.models import (
    SummaryPublishingAction,
)
from pr_reviewer.publishing.summary_service import (
    SummaryPublishingService,
)


def test_creates_summary_when_none_exists():
    provider = Mock()

    provider.get_summary_comments.return_value = []

    provider.publish_summary_comment.return_value = {
        "id": 100,
        "body": "summary",
    }

    service = SummaryPublishingService(
        provider=provider
    )

    result = service.publish(
        repository="example/repository",
        pull_number=10,
        summary="## AI Review\n\nPassed.",
    )

    assert (
        result.action
        == SummaryPublishingAction.CREATED
    )

    assert result.comment_id == 100

    provider.publish_summary_comment.assert_called_once()

    provider.update_summary_comment.assert_not_called()

    body = (
        provider
        .publish_summary_comment
        .call_args
        .kwargs["body"]
    )

    assert (
        "<!-- intelligent-pr-reviewer:summary -->"
        in body
    )

    assert "## AI Review" in body


def test_updates_existing_summary():
    provider = Mock()

    provider.get_summary_comments.return_value = [
        {
            "id": 200,
            "body": (
                "<!-- intelligent-pr-reviewer:summary -->"
                "\n\nOld summary"
            ),
        }
    ]

    provider.update_summary_comment.return_value = {
        "id": 200,
        "body": "updated",
    }

    service = SummaryPublishingService(
        provider=provider
    )

    result = service.publish(
        repository="example/repository",
        pull_number=10,
        summary="New summary",
    )

    assert (
        result.action
        == SummaryPublishingAction.UPDATED
    )

    assert result.comment_id == 200

    provider.update_summary_comment.assert_called_once()

    provider.publish_summary_comment.assert_not_called()

    call = (
        provider
        .update_summary_comment
        .call_args
    )

    assert call.kwargs["comment_id"] == 200

    assert "New summary" in call.kwargs["body"]


def test_ignores_unrelated_comments():
    provider = Mock()

    provider.get_summary_comments.return_value = [
        {
            "id": 1,
            "body": "Normal developer comment.",
        },
        {
            "id": 2,
            "body": "Another unrelated comment.",
        },
    ]

    provider.publish_summary_comment.return_value = {
        "id": 300,
    }

    service = SummaryPublishingService(
        provider=provider
    )

    result = service.publish(
        repository="example/repository",
        pull_number=10,
        summary="Review complete.",
    )

    assert (
        result.action
        == SummaryPublishingAction.CREATED
    )

    assert result.comment_id == 300


def test_summary_marker_is_added_only_once():
    provider = Mock()

    provider.get_summary_comments.return_value = []

    provider.publish_summary_comment.return_value = {
        "id": 400,
    }

    service = SummaryPublishingService(
        provider=provider
    )

    service.publish(
        repository="example/repository",
        pull_number=10,
        summary="Review complete.",
    )

    body = (
        provider
        .publish_summary_comment
        .call_args
        .kwargs["body"]
    )

    assert (
        body.count(
            "<!-- intelligent-pr-reviewer:summary -->"
        )
        == 1
    )