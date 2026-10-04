import pytest

from pr_reviewer.context.review_context import (
    ReviewContextBuilder,
)
from pr_reviewer.review.models import (
    ChangedFile,
    ChangedLine,
)


def test_small_file_uses_full_content():
    builder = ReviewContextBuilder(
        max_code_tokens=1000
    )

    content = (
        "const value = 10;\n"
        "console.log(value);\n"
    )

    changed_file = ChangedFile(
        file_path="src/app.js",
        status="modified",
        full_content=content,
        changed_lines=[
            ChangedLine(
                file_path="src/app.js",
                line_number=2,
                content="console.log(value);",
            )
        ],
    )

    result = builder.build(
        changed_file
    )

    assert result.used_full_file is True
    assert result.content == content
    assert result.estimated_tokens > 0


def test_large_file_uses_surrounding_context():
    builder = ReviewContextBuilder(
        max_code_tokens=100,
        context_lines_around_change=2,
    )

    full_content = "\n".join(
        f"line {index}"
        for index in range(
            1,
            101,
        )
    )

    changed_file = ChangedFile(
        file_path="src/app.js",
        status="modified",
        full_content=full_content,
        changed_lines=[
            ChangedLine(
                file_path="src/app.js",
                line_number=50,
                content="line 50",
            )
        ],
    )

    result = builder.build(
        changed_file
    )

    assert result.used_full_file is False

    assert "48 | line 48" in result.content
    assert "49 | line 49" in result.content
    assert "50 | line 50" in result.content
    assert "51 | line 51" in result.content
    assert "52 | line 52" in result.content

    assert "1 | line 1" not in result.content


def test_multiple_changed_regions_are_included():
    # Intentionally use a small token budget.
    #
    # The complete 100-line file is larger than this
    # budget, which forces ReviewContextBuilder into
    # surrounding-context mode.
    builder = ReviewContextBuilder(
        max_code_tokens=100,
        context_lines_around_change=1,
    )

    full_content = "\n".join(
        f"line {index}"
        for index in range(
            1,
            101,
        )
    )

    changed_file = ChangedFile(
        file_path="src/app.js",
        status="modified",
        full_content=full_content,
        changed_lines=[
            ChangedLine(
                file_path="src/app.js",
                line_number=10,
                content="line 10",
            ),
            ChangedLine(
                file_path="src/app.js",
                line_number=90,
                content="line 90",
            ),
        ],
    )

    result = builder.build(
        changed_file
    )

    assert result.used_full_file is False

    # First changed region.
    assert "9 | line 9" in result.content
    assert "10 | line 10" in result.content
    assert "11 | line 11" in result.content

    # Second changed region.
    assert "89 | line 89" in result.content
    assert "90 | line 90" in result.content
    assert "91 | line 91" in result.content

    # The unrelated section between the two changed
    # regions should not be sent to the model.
    assert (
        "... omitted unrelated lines ..."
        in result.content
    )


def test_missing_full_content_returns_empty_context():
    builder = ReviewContextBuilder()

    changed_file = ChangedFile(
        file_path="src/app.js",
        status="modified",
        full_content=None,
    )

    result = builder.build(
        changed_file
    )

    assert result.content == ""
    assert result.used_full_file is False
    assert result.estimated_tokens == 0


def test_estimate_tokens():
    builder = ReviewContextBuilder()

    result = builder.estimate_tokens(
        "12345678"
    )

    assert result == 2


def test_invalid_token_budget():
    with pytest.raises(
        ValueError,
        match=(
            "max_code_tokens must be greater than 0"
        ),
    ):
        ReviewContextBuilder(
            max_code_tokens=0
        )


def test_invalid_context_lines():
    with pytest.raises(
        ValueError,
        match=(
            "context_lines_around_change "
            "cannot be negative"
        ),
    ):
        ReviewContextBuilder(
            context_lines_around_change=-1
        )