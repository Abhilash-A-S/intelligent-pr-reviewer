import pytest

from pr_reviewer.llm.parser import LLMResponseParser
from pr_reviewer.review.models import Severity


def test_parse_valid_response():
    response = """
    {
      "findings": [
        {
          "line_number": 2,
          "severity": "low",
          "rule_id": "unused-variable",
          "message": "The variable is unused.",
          "suggestion": "Remove the variable."
        }
      ]
    }
    """

    result = LLMResponseParser.parse(response)

    assert len(result.findings) == 1

    finding = result.findings[0]

    assert finding.line_number == 2
    assert finding.severity == Severity.LOW
    assert finding.rule_id == "unused-variable"


def test_parse_empty_findings():
    result = LLMResponseParser.parse(
        '{"findings": []}'
    )

    assert result.findings == []


def test_parse_markdown_wrapped_json():
    response = """
    ```json
    {
      "findings": []
    }
    ```
    """

    result = LLMResponseParser.parse(response)

    assert result.findings == []


def test_parse_empty_response():
    with pytest.raises(
        ValueError,
        match="LLM response is empty",
    ):
        LLMResponseParser.parse("")


def test_parse_invalid_json():
    with pytest.raises(
        ValueError,
        match="not valid JSON",
    ):
        LLMResponseParser.parse(
            "this is not json"
        )


def test_recovers_only_complete_findings_from_truncated_array():
    response = '''{
      "findings": [
        {
          "file_path": "src/app.js",
          "line_number": 8,
          "severity": "medium",
          "rule_id": "logic-error",
          "message": "A proven defect.",
          "suggestion": "Correct the branch."
        },
        {"file_path": "src/other.js", "line_number":
    '''

    result = LLMResponseParser.parse(response)

    assert len(result.findings) == 1
    assert result.findings[0].file_path == "src/app.js"


def test_does_not_repair_malformed_content_after_a_closed_findings_array():
    with pytest.raises(ValueError, match="not valid JSON"):
        LLMResponseParser.parse('{"findings": [] trailing-invalid}')


def test_parse_invalid_schema():
    response = """
    {
      "findings": [
        {
          "line_number": 1,
          "severity": "invalid",
          "rule_id": "test-rule",
          "message": "Test"
        }
      ]
    }
    """

    with pytest.raises(
        ValueError,
        match="expected review schema",
    ):
        LLMResponseParser.parse(response)
