import pytest

from pr_reviewer.llm.chunker import (
    ChangedFileChunker,
)
from pr_reviewer.review.models import (
    ChangedFile,
    ChangedLine,
)


def create_changed_file(
    line_count: int,
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
    )


def test_empty_file_returns_no_chunks():
    chunker = ChangedFileChunker(
        chunk_size=30
    )

    changed_file = create_changed_file(0)

    result = chunker.chunk(
        changed_file
    )

    assert result == []


def test_single_chunk():
    chunker = ChangedFileChunker(
        chunk_size=30
    )

    changed_file = create_changed_file(10)

    result = chunker.chunk(
        changed_file
    )

    assert len(result) == 1

    chunk = result[0]

    assert chunk.index == 1
    assert chunk.total == 1
    assert len(chunk.changed_lines) == 10


def test_multiple_chunks():
    chunker = ChangedFileChunker(
        chunk_size=30
    )

    changed_file = create_changed_file(65)

    result = chunker.chunk(
        changed_file
    )

    assert len(result) == 3

    assert len(
        result[0].changed_lines
    ) == 30

    assert len(
        result[1].changed_lines
    ) == 30

    assert len(
        result[2].changed_lines
    ) == 5

    assert result[0].index == 1
    assert result[1].index == 2
    assert result[2].index == 3

    assert result[0].total == 3
    assert result[2].total == 3


def test_chunk_preserves_actual_line_numbers():
    chunker = ChangedFileChunker(
        chunk_size=2
    )

    changed_file = ChangedFile(
        file_path="src/app.js",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app.js",
                line_number=172,
                content='console.log("debug");',
                diff_position=20,
            ),
            ChangedLine(
                file_path="src/app.js",
                line_number=173,
                content="const abc = 123;",
                diff_position=21,
            ),
            ChangedLine(
                file_path="src/app.js",
                line_number=200,
                content="debugger;",
                diff_position=40,
            ),
        ],
    )

    result = chunker.chunk(
        changed_file
    )

    assert len(result) == 2

    assert (
        result[0]
        .changed_lines[0]
        .line_number
        == 172
    )

    assert (
        result[0]
        .changed_lines[1]
        .line_number
        == 173
    )

    assert (
        result[1]
        .changed_lines[0]
        .line_number
        == 200
    )

    assert (
        result[1]
        .changed_lines[0]
        .diff_position
        == 40
    )


def test_invalid_chunk_size():
    with pytest.raises(
        ValueError,
        match="chunk_size must be greater than 0",
    ):
        ChangedFileChunker(
            chunk_size=0
        )