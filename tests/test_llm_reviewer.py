from unittest.mock import Mock

import pytest

from pr_reviewer.context.models import (
    RepositoryContext,
)
from pr_reviewer.llm.models import (
    ReviewResponse,
)
from pr_reviewer.llm.llm_reviewer import (
    LLMReviewer,
)
from pr_reviewer.review.models import (
    ChangedFile,
    ChangedLine,
    Severity,
)


def create_changed_file(
    line_count: int = 1,
) -> ChangedFile:

    return ChangedFile(
        file_path="src/app.js",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app.js",
                line_number=index,
                content=f"const value{index} = {index};",
                diff_position=index,
            )
            for index in range(
                1,
                line_count + 1,
            )
        ],
        full_content="\n".join(
            (
                f"const value{index} = {index};"
            )
            for index in range(
                1,
                line_count + 1,
            )
        ),
    )


def create_repository_context():
    return RepositoryContext(
        languages={"javascript"},
    )


def test_empty_changed_file_returns_no_findings():

    llm_provider = Mock()

    reviewer = LLMReviewer(
        llm_provider=llm_provider
    )

    changed_file = ChangedFile(
        file_path="src/app.js",
        status="modified",
        changed_lines=[],
    )

    result = reviewer.review(
        changed_file=changed_file,
        repository_context=(
            create_repository_context()
        ),
    )

    assert result == []

    llm_provider.review.assert_not_called()


def test_valid_response_is_mapped():

    llm_provider = Mock()

    llm_provider.review.return_value = """
    {
      "findings": [
        {
          "line_number": 1,
          "severity": "medium",
          "rule_id": "test-rule",
          "message": "A real issue exists.",
          "suggestion": "Fix the issue."
        }
      ]
    }
    """

    reviewer = LLMReviewer(
        llm_provider=llm_provider
    )

    result = reviewer.review(
        changed_file=create_changed_file(),
        repository_context=(
            create_repository_context()
        ),
    )

    assert len(result) == 1

    finding = result[0]

    assert finding.file_path == "src/app.js"
    assert finding.line_number == 1
    assert finding.severity == Severity.MEDIUM
    assert finding.rule_id == "test-rule"
    assert finding.message == "A real issue exists."
    assert finding.suggestion == "Fix the issue."
    assert finding.diff_position == 1

    assert llm_provider.review.call_count == 1


def test_non_commentable_line_is_rejected():

    llm_provider = Mock()

    llm_provider.review.return_value = """
    {
      "findings": [
        {
          "line_number": 999,
          "severity": "high",
          "rule_id": "test-rule",
          "message": "Invalid target.",
          "suggestion": "Fix it."
        }
      ]
    }
    """

    reviewer = LLMReviewer(
        llm_provider=llm_provider
    )

    result = reviewer.review(
        changed_file=create_changed_file(),
        repository_context=(
            create_repository_context()
        ),
    )

    assert result == []


def test_invalid_json_is_retried():

    llm_provider = Mock()

    llm_provider.review.side_effect = [
        "this is not json",
        """
        {
          "findings": [
            {
              "line_number": 1,
              "severity": "low",
              "rule_id": "unused-variable",
              "message": "Variable is unused.",
              "suggestion": "Remove it."
            }
          ]
        }
        """,
    ]

    reviewer = LLMReviewer(
        llm_provider=llm_provider
    )

    result = reviewer.review(
        changed_file=create_changed_file(),
        repository_context=(
            create_repository_context()
        ),
    )

    assert len(result) == 1

    assert (
        result[0].rule_id
        == "unused-variable"
    )

    assert llm_provider.review.call_count == 2
    stats = reviewer.execution_stats()
    assert stats.actual_calls == 2
    assert stats.retries == 1
    assert stats.failed_parts == 0


def test_invalid_schema_is_retried():

    llm_provider = Mock()

    llm_provider.review.side_effect = [
        """
        {
          "findings": [
            {
              "line_number": 1
            }
          ]
        }
        """,
        """
        {
          "findings": []
        }
        """,
    ]

    reviewer = LLMReviewer(
        llm_provider=llm_provider
    )

    result = reviewer.review(
        changed_file=create_changed_file(),
        repository_context=(
            create_repository_context()
        ),
    )

    assert result == []

    assert llm_provider.review.call_count == 2


def test_provider_failure_is_retried():

    llm_provider = Mock()

    llm_provider.review.side_effect = [
        RuntimeError(
            "Temporary provider failure."
        ),
        """
        {
          "findings": []
        }
        """,
    ]

    reviewer = LLMReviewer(
        llm_provider=llm_provider
    )

    result = reviewer.review(
        changed_file=create_changed_file(),
        repository_context=(
            create_repository_context()
        ),
    )

    assert result == []

    assert llm_provider.review.call_count == 2


def test_all_attempts_can_fail_without_crashing():

    llm_provider = Mock()

    llm_provider.review.side_effect = [
        "invalid response one",
        "invalid response two",
    ]

    reviewer = LLMReviewer(
        llm_provider=llm_provider
    )

    result = reviewer.review(
        changed_file=create_changed_file(),
        repository_context=(
            create_repository_context()
        ),
    )

    assert result == []

    assert llm_provider.review.call_count == 2
    stats = reviewer.execution_stats()
    assert stats.actual_calls == 2
    assert stats.retries == 1
    assert stats.failed_parts == 1


def test_custom_max_attempts_is_respected():

    llm_provider = Mock()

    llm_provider.review.side_effect = [
        "invalid one",
        "invalid two",
        """
        {
          "findings": []
        }
        """,
    ]

    reviewer = LLMReviewer(
        llm_provider=llm_provider,
        max_attempts=3,
    )

    result = reviewer.review(
        changed_file=create_changed_file(),
        repository_context=(
            create_repository_context()
        ),
    )

    assert result == []

    assert llm_provider.review.call_count == 3


def test_invalid_max_attempts_is_rejected():

    llm_provider = Mock()

    with pytest.raises(
        ValueError,
        match=(
            "max_attempts must be greater than 0"
        ),
    ):
        LLMReviewer(
            llm_provider=llm_provider,
            max_attempts=0,
        )


def test_llm_reviewer_does_not_canonicalize_rule_id():
    """
    Canonicalization belongs to FindingNormalizer.

    LLMReviewer should preserve the LLM rule ID so every
    review source goes through the same normalization
    pipeline later.
    """

    llm_provider = Mock()

    llm_provider.review.return_value = """
    {
      "findings": [
        {
          "line_number": 1,
          "severity": "suggestion",
          "rule_id": "unnecessary-constant",
          "message": "Constant is unnecessary.",
          "suggestion": "Remove it."
        }
      ]
    }
    """

    reviewer = LLMReviewer(
        llm_provider=llm_provider
    )

    result = reviewer.review(
        changed_file=create_changed_file(),
        repository_context=(
            create_repository_context()
        ),
    )

    assert len(result) == 1

    assert (
        result[0].rule_id
        == "unnecessary-constant"
    )

    assert (
        result[0].severity
        == Severity.SUGGESTION
    )


def test_map_findings_preserves_diff_position():

    changed_file = create_changed_file()

    llm_finding = Mock()

    llm_finding.line_number = 1
    llm_finding.severity = Severity.LOW
    llm_finding.rule_id = "test-rule"
    llm_finding.message = "Test message."
    llm_finding.suggestion = "Test suggestion."

    result = LLMReviewer._map_findings(
        changed_file=changed_file,
        llm_findings=[
            llm_finding
        ],
    )

    assert len(result) == 1

    assert result[0].diff_position == 1
