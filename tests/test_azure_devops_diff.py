from pr_reviewer.providers.azure_diff import (
    added_line_numbers,
    build_unified_patch,
    changed_file_status,
    normalize_change_types,
)
from pr_reviewer.review.diff_parser import DiffParser


def test_normalizes_string_and_numeric_change_flags():
    assert normalize_change_types("Edit, Rename") == {"edit", "rename"}
    assert normalize_change_types(2 | 8) == {"edit", "rename"}
    assert normalize_change_types("none") == set()


def test_maps_azure_flags_to_provider_neutral_statuses():
    assert changed_file_status(frozenset({"add"})) == "added"
    assert changed_file_status(frozenset({"edit"})) == "modified"
    assert changed_file_status(frozenset({"edit", "rename"})) == "renamed"
    assert changed_file_status(frozenset({"delete"})) == "removed"


def test_reconstructed_patch_preserves_exact_added_line_numbers():
    patch = build_unified_patch(
        old_content="first\nold value\nlast\n",
        new_content="first\nnew value\nextra\nlast\n",
        old_path="src/app.py",
        new_path="src/app.py",
    )

    assert patch is not None
    assert added_line_numbers(patch) == {2, 3}
    changed_lines = DiffParser().parse_patch("src/app.py", patch)
    assert [(line.line_number, line.content) for line in changed_lines] == [
        (2, "new value"),
        (3, "extra"),
    ]


def test_added_file_patch_marks_every_nonblank_added_line():
    patch = build_unified_patch(
        old_content="",
        new_content="one\n\ntwo\n",
        old_path="src/new.ts",
        new_path="src/new.ts",
    )

    assert added_line_numbers(patch) == {1, 2, 3}
    parsed = DiffParser().parse_patch("src/new.ts", patch or "")
    assert [line.line_number for line in parsed] == [1, 3]


def test_deleted_file_and_content_only_rename_have_no_added_lines():
    deleted = build_unified_patch(
        old_content="remove me\n",
        new_content="",
        old_path="src/deleted.cs",
        new_path="src/deleted.cs",
    )
    renamed = build_unified_patch(
        old_content="same\n",
        new_content="same\n",
        old_path="src/old.java",
        new_path="src/new.java",
    )

    assert deleted is not None
    assert added_line_numbers(deleted) == set()
    assert renamed is None
