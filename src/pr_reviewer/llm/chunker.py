from dataclasses import dataclass

from pr_reviewer.review.models import ChangedFile, ChangedLine


@dataclass
class ReviewChunk:
    file_path: str
    index: int
    total: int
    changed_lines: list[ChangedLine]


class ChangedFileChunker:
    DEFAULT_CHUNK_SIZE = 30

    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ):
        if chunk_size <= 0:
            raise ValueError(
                "chunk_size must be greater than 0."
            )

        self.chunk_size = chunk_size

    def chunk(
        self,
        changed_file: ChangedFile,
    ) -> list[ReviewChunk]:

        lines = changed_file.changed_lines

        if not lines:
            return []

        chunks: list[list[ChangedLine]] = []

        for start in range(
            0,
            len(lines),
            self.chunk_size,
        ):
            end = start + self.chunk_size

            chunks.append(
                lines[start:end]
            )

        total = len(chunks)

        return [
            ReviewChunk(
                file_path=changed_file.file_path,
                index=index,
                total=total,
                changed_lines=chunk_lines,
            )
            for index, chunk_lines in enumerate(
                chunks,
                start=1,
            )
        ]