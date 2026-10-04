from dataclasses import dataclass
import re

from pr_reviewer.review.models import ChangedFile, ChangedLine


@dataclass(frozen=True)
class DiffHunk:
    file_path: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    changed_lines: tuple[ChangedLine, ...]

    @property
    def line_numbers(self) -> set[int]:
        return {line.line_number for line in self.changed_lines}


class DiffParser:
    HUNK_HEADER_PATTERN = re.compile(
        r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@"
    )
    HUNK_HEADER_FULL_PATTERN = re.compile(
        r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@"
    )

    def parse_file(
        self,
        changed_file: ChangedFile,
    ) -> ChangedFile:
        patch = changed_file.patch

        if not patch:
            changed_file.changed_lines = []
            return changed_file

        changed_file.changed_lines = self.parse_patch(
            file_path=changed_file.file_path,
            patch=patch,
        )

        return changed_file

    def parse_patch(
        self,
        file_path: str,
        patch: str,
    ) -> list[ChangedLine]:
        changed_lines: list[ChangedLine] = []

        current_new_line = 0
        diff_position = 0

        for line in patch.splitlines():
            hunk_match = self.HUNK_HEADER_PATTERN.match(line)

            if hunk_match:
                current_new_line = int(
                    hunk_match.group(1)
                )
                continue

            diff_position += 1

            if line.startswith("+++"):
                continue

            if line.startswith("+"):
                content = line[1:]

                if content.strip():
                    changed_lines.append(
                        ChangedLine(
                            file_path=file_path,
                            line_number=current_new_line,
                            content=content,
                            diff_position=diff_position,
                        )
                    )

                current_new_line += 1
                continue

            if line.startswith("-"):
                continue

            current_new_line += 1

        return changed_lines

    def parse_hunks(
        self,
        file_path: str,
        patch: str,
    ) -> list[DiffHunk]:
        if not patch:
            return []

        hunks: list[DiffHunk] = []
        current_hunk_info = None
        current_hunk_lines: list[ChangedLine] = []
        current_new_line = 0
        diff_position = 0

        for line in patch.splitlines():
            m = self.HUNK_HEADER_FULL_PATTERN.match(line)
            if m:
                if current_hunk_info is not None:
                    hunks.append(
                        DiffHunk(
                            file_path=file_path,
                            old_start=current_hunk_info[0],
                            old_count=current_hunk_info[1],
                            new_start=current_hunk_info[2],
                            new_count=current_hunk_info[3],
                            changed_lines=tuple(current_hunk_lines),
                        )
                    )
                    current_hunk_lines = []
                old_start = int(m.group(1))
                old_count = int(m.group(2)) if m.group(2) else 1
                new_start = int(m.group(3))
                new_count = int(m.group(4)) if m.group(4) else 1
                current_hunk_info = (old_start, old_count, new_start, new_count)
                current_new_line = new_start
                continue

            diff_position += 1

            if line.startswith("+++"):
                continue

            if line.startswith("+"):
                content = line[1:]
                if content.strip():
                    current_hunk_lines.append(
                        ChangedLine(
                            file_path=file_path,
                            line_number=current_new_line,
                            content=content,
                            diff_position=diff_position,
                        )
                    )
                current_new_line += 1
                continue

            if line.startswith("-") or line.startswith("\\"):
                continue

            current_new_line += 1

        if current_hunk_info is not None:
            hunks.append(
                DiffHunk(
                    file_path=file_path,
                    old_start=current_hunk_info[0],
                    old_count=current_hunk_info[1],
                    new_start=current_hunk_info[2],
                    new_count=current_hunk_info[3],
                    changed_lines=tuple(current_hunk_lines),
                )
            )

        return hunks