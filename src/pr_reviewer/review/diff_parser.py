import re

from pr_reviewer.review.models import ChangedFile, ChangedLine


class DiffParser:
    HUNK_HEADER_PATTERN = re.compile(
        r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@"
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

            if line.startswith("\\"):
                continue

            current_new_line += 1

        return changed_lines