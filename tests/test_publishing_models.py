from pr_reviewer.publishing.models import (
    PublishingResult,
)


def test_empty_publishing_result():
    result = PublishingResult()

    assert result.published_count == 0
    assert result.skipped_duplicates == 0
    assert result.total_processed == 0


def test_publishing_result_counts():
    result = PublishingResult(
        published_comments=[
            {"id": 1},
            {"id": 2},
        ],
        skipped_duplicates=3,
    )

    assert result.published_count == 2
    assert result.skipped_duplicates == 3
    assert result.total_processed == 5