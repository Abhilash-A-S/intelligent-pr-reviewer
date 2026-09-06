import pytest

from pr_reviewer.review.models import (
    ChangedFile,
    ChangedLine,
)
from pr_reviewer.llm.review_planner import (
    FileReviewPlanner,
    ReviewMode,
)

def create_changed_file(
    line_count: int,
    content: str = "const value = 1;",
    file_path: str = "src/app.js",
) -> ChangedFile:

    return ChangedFile(
        file_path=file_path,
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path=file_path,
                line_number=index,
                content=content,
            )
            for index in range(
                1,
                line_count + 1,
            )
        ],
    )


def test_empty_file_creates_no_review_parts():
    planner = FileReviewPlanner()

    changed_file = ChangedFile(
        file_path="src/app.js",
        status="modified",
        changed_lines=[],
    )

    plan = planner.plan(
        changed_file
    )

    assert (
        plan.mode
        == ReviewMode.FULL_FILE
    )

    assert plan.parts == []

    assert plan.llm_call_count == 0


def test_small_change_uses_single_llm_call():
    planner = FileReviewPlanner()

    changed_file = create_changed_file(
        line_count=20
    )

    plan = planner.plan(
        changed_file
    )

    assert (
        plan.mode
        == ReviewMode.FULL_FILE
    )

    assert plan.llm_call_count == 1

    assert (
        len(plan.parts[0].changed_lines)
        == 20
    )


def test_more_than_old_80_line_limit_can_use_one_call():
    """
    This is the main behavior introduced by 27E.3.

    The previous planner split every change set above
    80 lines.

    Short changed lines should remain in one request when
    the estimated token budget allows it.
    """

    planner = FileReviewPlanner()

    changed_file = create_changed_file(
        line_count=134,
        content="const x = 1;",
    )

    plan = planner.plan(
        changed_file
    )

    assert (
        plan.mode
        == ReviewMode.FULL_FILE
    )

    assert plan.llm_call_count == 1


def test_short_100_line_stylesheet_can_use_one_call():
    planner = FileReviewPlanner()

    changed_file = create_changed_file(
        line_count=100,
        content="margin: 0;",
        file_path="src/styles.css",
    )

    plan = planner.plan(
        changed_file
    )

    assert (
        plan.mode
        == ReviewMode.FULL_FILE
    )

    assert plan.llm_call_count == 1


def test_long_lines_trigger_token_based_split():
    planner = FileReviewPlanner(
        max_estimated_tokens_per_call=100,
        max_changed_lines_per_call=250,
        max_parts=4,
    )

    changed_file = create_changed_file(
        line_count=10,
        content="x" * 100,
    )

    plan = planner.plan(
        changed_file
    )

    assert (
        plan.mode
        == ReviewMode.SPLIT
    )

    assert plan.llm_call_count > 1


def test_line_limit_can_trigger_split():
    planner = FileReviewPlanner(
        max_estimated_tokens_per_call=10000,
        max_changed_lines_per_call=50,
        max_parts=4,
    )

    changed_file = create_changed_file(
        line_count=120,
        content="x",
    )

    plan = planner.plan(
        changed_file
    )

    assert (
        plan.mode
        == ReviewMode.SPLIT
    )

    assert plan.llm_call_count == 3


def test_split_preserves_all_changed_lines():
    planner = FileReviewPlanner(
        max_estimated_tokens_per_call=100,
        max_changed_lines_per_call=50,
        max_parts=4,
    )

    changed_file = create_changed_file(
        line_count=120,
        content="const value = 123456789;",
    )

    plan = planner.plan(
        changed_file
    )

    resulting_lines = [
        changed_line
        for part in plan.parts
        for changed_line in part.changed_lines
    ]

    assert (
        resulting_lines
        == changed_file.changed_lines
    )


def test_split_preserves_line_order():
    planner = FileReviewPlanner(
        max_estimated_tokens_per_call=100,
        max_changed_lines_per_call=50,
        max_parts=4,
    )

    changed_file = create_changed_file(
        line_count=120,
        content="const value = 123456789;",
    )

    plan = planner.plan(
        changed_file
    )

    line_numbers = [
        line.line_number
        for part in plan.parts
        for line in part.changed_lines
    ]

    assert line_numbers == list(
        range(1, 121)
    )


def test_number_of_parts_never_exceeds_max_parts():
    planner = FileReviewPlanner(
        max_estimated_tokens_per_call=20,
        max_changed_lines_per_call=10,
        max_parts=3,
    )

    changed_file = create_changed_file(
        line_count=200,
        content="x" * 100,
    )

    plan = planner.plan(
        changed_file
    )

    assert (
        plan.llm_call_count
        <= 3
    )


def test_review_part_indexes_are_correct():
    planner = FileReviewPlanner(
        max_estimated_tokens_per_call=10000,
        max_changed_lines_per_call=50,
        max_parts=4,
    )

    changed_file = create_changed_file(
        line_count=120,
        content="x",
    )

    plan = planner.plan(
        changed_file
    )

    assert plan.llm_call_count == 3

    assert [
        part.index
        for part in plan.parts
    ] == [
        1,
        2,
        3,
    ]

    assert all(
        part.total == 3
        for part in plan.parts
    )


def test_java_file_uses_same_planning_strategy():
    planner = FileReviewPlanner()

    changed_file = create_changed_file(
        line_count=100,
        content=(
            "public String getName() "
            "{ return name; }"
        ),
        file_path="src/UserService.java",
    )

    plan = planner.plan(
        changed_file
    )

    assert plan.llm_call_count == 1


def test_csharp_file_uses_same_planning_strategy():
    planner = FileReviewPlanner()

    changed_file = create_changed_file(
        line_count=100,
        content=(
            "public string Name "
            "{ get; set; }"
        ),
        file_path="src/UserService.cs",
    )

    plan = planner.plan(
        changed_file
    )

    assert plan.llm_call_count == 1


def test_python_file_uses_same_planning_strategy():
    planner = FileReviewPlanner()

    changed_file = create_changed_file(
        line_count=100,
        content="value = calculate_total()",
        file_path="src/service.py",
    )

    plan = planner.plan(
        changed_file
    )

    assert plan.llm_call_count == 1


@pytest.mark.parametrize(
    "file_path",
    [
        "src/app.ts",
        "src/App.tsx",
        "src/App.vue",
        "src/Main.java",
        "src/Service.cs",
        "src/main.py",
        "src/main.go",
        "src/lib.rs",
        "src/main.cpp",
        "src/main.kt",
    ],
)
def test_planner_is_language_agnostic(
    file_path: str,
):
    planner = FileReviewPlanner()

    changed_file = create_changed_file(
        line_count=100,
        content="short changed source line",
        file_path=file_path,
    )

    plan = planner.plan(
        changed_file
    )

    assert plan.llm_call_count == 1


def test_invalid_token_budget_is_rejected():
    with pytest.raises(
        ValueError,
        match=(
            "max_estimated_tokens_per_call "
            "must be greater than 0"
        ),
    ):
        FileReviewPlanner(
            max_estimated_tokens_per_call=0
        )


def test_invalid_line_limit_is_rejected():
    with pytest.raises(
        ValueError,
        match=(
            "max_changed_lines_per_call "
            "must be greater than 0"
        ),
    ):
        FileReviewPlanner(
            max_changed_lines_per_call=0
        )


def test_invalid_max_parts_is_rejected():
    with pytest.raises(
        ValueError,
        match=(
            "max_parts must be greater than 0"
        ),
    ):
        FileReviewPlanner(
            max_parts=0
        )