from pr_reviewer.review.diff_parser import DiffParser
from pr_reviewer.review.models import ChangedFile


def test_parse_added_line():
    parser = DiffParser()

    patch = """@@ -1,2 +1,3 @@
 const value = 10;
+console.log(value);
 return value;
"""

    lines = parser.parse_patch(
        file_path="src/app.js",
        patch=patch,
    )

    assert len(lines) == 1

    line = lines[0]

    assert line.file_path == "src/app.js"
    assert line.line_number == 2
    assert line.content == "console.log(value);"
    assert line.diff_position == 2


def test_deleted_lines_do_not_increment_new_line_number():
    parser = DiffParser()

    patch = """@@ -10,3 +10,3 @@
 const a = 1;
-const oldValue = 2;
+const newValue = 2;
 return a;
"""

    lines = parser.parse_patch(
        file_path="src/app.js",
        patch=patch,
    )

    assert len(lines) == 1

    line = lines[0]

    assert line.line_number == 11
    assert line.content == "const newValue = 2;"


def test_multiple_added_lines():
    parser = DiffParser()

    patch = """@@ -20,1 +20,3 @@
 const value = 1;
+console.log(value);
+const unused = 10;
"""

    lines = parser.parse_patch(
        file_path="src/app.js",
        patch=patch,
    )

    assert len(lines) == 2

    assert lines[0].line_number == 21
    assert lines[0].content == "console.log(value);"

    assert lines[1].line_number == 22
    assert lines[1].content == "const unused = 10;"


def test_empty_added_lines_are_not_reviewed():
    parser = DiffParser()

    patch = """@@ -1,1 +1,3 @@
 const value = 1;
+
+console.log(value);
"""

    lines = parser.parse_patch(
        file_path="src/app.js",
        patch=patch,
    )

    assert len(lines) == 1
    assert lines[0].line_number == 3


def test_parse_changed_file():
    parser = DiffParser()

    changed_file = ChangedFile(
        file_path="src/app.js",
        status="modified",
        patch="""@@ -1,1 +1,2 @@
 const value = 1;
+console.log(value);
""",
    )

    result = parser.parse_file(changed_file)

    assert len(result.changed_lines) == 1
    assert result.changed_lines[0].line_number == 2


def test_file_without_patch_returns_no_changed_lines():
    parser = DiffParser()

    changed_file = ChangedFile(
        file_path="image.png",
        status="modified",
        patch=None,
    )

    result = parser.parse_file(changed_file)

    assert result.changed_lines == []