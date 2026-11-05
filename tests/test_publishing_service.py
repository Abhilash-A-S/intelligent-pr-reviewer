from unittest.mock import Mock

from pr_reviewer.publishing.service import (
    PublishingService,
)
from pr_reviewer.review.models import (
    Finding,
    Severity,
)


def create_finding(
    *,
    file_path: str = "src/app.js",
    line_number: int = 10,
    rule_id: str = "no-console",
    severity: Severity = Severity.LOW,
) -> Finding:

    return Finding(
        file_path=file_path,
        line_number=line_number,
        severity=severity,
        rule_id=rule_id,
        message="Test finding.",
        suggestion="Fix the issue.",
        diff_position=20,
    )


def test_publishes_new_finding():
    provider = Mock()

    provider.get_existing_comments.return_value = []

    provider.publish_inline_comment.return_value = {
        "id": 123,
    }

    service = PublishingService(
        provider=provider
    )

    finding = create_finding()

    result = service.publish_findings(
        repository="example/repository",
        pull_number=10,
        commit_id="abc123",
        findings=[finding],
    )

    assert result.published_count == 1
    assert result.skipped_duplicates == 0

    provider.publish_inline_comment.assert_called_once()

    call = (
        provider
        .publish_inline_comment
        .call_args
    )

    assert (
        call.kwargs["repository"]
        == "example/repository"
    )

    assert call.kwargs["pull_number"] == 10
    assert call.kwargs["commit_id"] == "abc123"

    assert (
        call.kwargs["file_path"]
        == "src/app.js"
    )

    assert call.kwargs["line_number"] == 10
    assert call.kwargs["diff_position"] == 20

    assert (
        "🔵 **Low**"
        in call.kwargs["body"]
    )


def test_skips_existing_duplicate():
    provider = Mock()

    provider.get_existing_comments.return_value = [
        {
            "id": 1,
            "body": (
                "<!-- intelligent-pr-reviewer:"
                "no-console:src/app.js:10 -->\n\n"
                "Existing review comment."
            ),
        }
    ]

    service = PublishingService(
        provider=provider
    )

    result = service.publish_findings(
        repository="example/repository",
        pull_number=10,
        commit_id="abc123",
        findings=[
            create_finding(),
        ],
    )

    assert result.published_count == 0
    assert result.skipped_duplicates == 1

    provider.publish_inline_comment.assert_not_called()


def test_different_line_is_not_duplicate():
    provider = Mock()

    provider.get_existing_comments.return_value = [
        {
            "body": (
                "<!-- intelligent-pr-reviewer:"
                "no-console:src/app.js:10 -->"
            )
        }
    ]

    provider.publish_inline_comment.return_value = {
        "id": 2,
    }

    service = PublishingService(
        provider=provider
    )

    result = service.publish_findings(
        repository="example/repository",
        pull_number=10,
        commit_id="abc123",
        findings=[
            create_finding(
                line_number=11
            ),
        ],
    )

    assert result.published_count == 1
    assert result.skipped_duplicates == 0


def test_different_rule_is_not_duplicate():
    provider = Mock()

    provider.get_existing_comments.return_value = [
        {
            "body": (
                "<!-- intelligent-pr-reviewer:"
                "no-console:src/app.js:10 -->"
            )
        }
    ]

    provider.publish_inline_comment.return_value = {
        "id": 2,
    }

    service = PublishingService(
        provider=provider
    )

    result = service.publish_findings(
        repository="example/repository",
        pull_number=10,
        commit_id="abc123",
        findings=[
            create_finding(
                rule_id="unused-variable"
            ),
        ],
    )

    assert result.published_count == 1


def test_duplicate_inside_same_run_is_skipped():
    provider = Mock()

    provider.get_existing_comments.return_value = []

    provider.publish_inline_comment.return_value = {
        "id": 123,
    }

    service = PublishingService(
        provider=provider
    )

    finding = create_finding()

    result = service.publish_findings(
        repository="example/repository",
        pull_number=10,
        commit_id="abc123",
        findings=[
            finding,
            finding,
        ],
    )

    assert result.published_count == 1
    assert result.skipped_duplicates == 1

    assert (
        provider
        .publish_inline_comment
        .call_count
        == 1
    )


def test_unplaceable_comment_does_not_abort_remaining_findings():
    provider = Mock()
    provider.get_existing_comments.return_value = []
    provider.publish_inline_comment.side_effect = [
        ValueError("line is not part of the diff"),
        {"id": 123},
    ]
    service = PublishingService(provider=provider)

    result = service.publish_findings(
        repository="example/repository",
        pull_number=10,
        commit_id="abc123",
        findings=[
            create_finding(line_number=10),
            create_finding(line_number=11),
        ],
    )

    assert result.published_count == 1
    assert result.failed_count == 1
    assert result.total_processed == 2
    assert result.failed_comments[0]["line_number"] == 10
    assert provider.publish_inline_comment.call_count == 2


def test_same_line_findings_are_grouped_into_one_inline_comment():
    provider = Mock()
    provider.supports_batch_inline_comments = False
    provider.get_existing_comments.return_value = []
    provider.publish_inline_comment.return_value = {"id": 1}
    service = PublishingService(provider=provider)

    result = service.publish_findings(
        repository="example/repository", pull_number=10, commit_id="abc123",
        findings=[
            create_finding(line_number=10, rule_id="hardcoded-secret", severity=Severity.HIGH),
            create_finding(line_number=10, rule_id="unused-variable", severity=Severity.LOW),
        ],
    )

    assert result.published_count == 1
    assert result.grouped_findings == 1
    assert provider.publish_inline_comment.call_count == 1
    body = provider.publish_inline_comment.call_args.kwargs["body"]
    assert "2 findings on this line" in body
    assert "hardcoded-secret" in body
    assert "unused-variable" in body


def test_inline_cap_counts_existing_comments_and_defers_remainder_to_summary():
    provider = Mock()
    provider.supports_batch_inline_comments = False
    provider.get_existing_comments.return_value = [
        {"body": "<!-- intelligent-pr-reviewer:no-console:old.js:1 -->"},
        {"body": "<!-- intelligent-pr-reviewer:no-console:old.js:2 -->"},
    ]
    provider.publish_inline_comment.return_value = {"id": 1}
    service = PublishingService(provider=provider, max_inline_comments=3)

    result = service.publish_findings(
        repository="example/repository", pull_number=10, commit_id="abc123",
        findings=[create_finding(line_number=10), create_finding(line_number=11)],
    )

    assert result.published_count == 1
    assert result.summary_only_findings == 1
    assert provider.publish_inline_comment.call_count == 1


def test_batch_provider_receives_one_review_request_for_multiple_lines():
    provider = Mock()
    provider.supports_batch_inline_comments = True
    provider.get_existing_comments.return_value = []
    provider.publish_inline_comments_batch.return_value = {"id": 99}
    service = PublishingService(provider=provider)

    result = service.publish_findings(
        repository="example/repository", pull_number=10, commit_id="abc123",
        findings=[create_finding(line_number=10), create_finding(line_number=11)],
    )

    assert result.published_count == 2
    provider.publish_inline_comments_batch.assert_called_once()
    assert len(provider.publish_inline_comments_batch.call_args.kwargs["comments"]) == 2
    provider.publish_inline_comment.assert_not_called()


def test_existing_forty_comments_prevent_more_inline_noise_but_keep_summary_count():
    provider = Mock()
    provider.supports_batch_inline_comments = True
    provider.get_existing_comments.return_value = [
        {"body": f"<!-- intelligent-pr-reviewer:rule-{number}:old.ts:{number} -->"}
        for number in range(40)
    ]
    service = PublishingService(provider=provider, max_inline_comments=40)

    result = service.publish_findings(
        repository="example/repository", pull_number=10, commit_id="abc123",
        findings=[create_finding(line_number=50), create_finding(line_number=51)],
    )

    assert result.published_count == 0
    assert result.summary_only_findings == 2
    provider.publish_inline_comments_batch.assert_not_called()


def test_batch_throttle_is_recorded_without_falling_back_to_request_flood():
    provider = Mock()
    provider.supports_batch_inline_comments = True
    provider.get_existing_comments.return_value = []
    error = RuntimeError("GitHub secondary rate limit: submitted too quickly")
    provider.publish_inline_comments_batch.side_effect = error
    service = PublishingService(provider=provider)

    result = service.publish_findings(
        repository="example/repository", pull_number=10, commit_id="abc123",
        findings=[create_finding(line_number=10), create_finding(line_number=11)],
    )

    assert result.published_count == 0
    assert result.failed_count == 2
    assert result.rate_limited
    provider.publish_inline_comments_batch.assert_called_once()
    provider.publish_inline_comment.assert_not_called()
