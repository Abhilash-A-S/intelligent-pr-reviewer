from dataclasses import dataclass
from enum import Enum

from pr_reviewer.review.models import (
    ChangedFile,
    ChangedLine,
)


class ReviewMode(str, Enum):
    FULL_FILE = "full_file"
    SPLIT = "split"


@dataclass
class ReviewPart:
    index: int
    total: int
    changed_lines: list[ChangedLine]


@dataclass
class FileReviewPlan:
    file_path: str
    mode: ReviewMode
    parts: list[ReviewPart]

    @property
    def llm_call_count(self) -> int:
        return len(self.parts)


class FileReviewPlanner:
    """
    Creates a language-agnostic review plan for a changed file.

    Planning is primarily based on estimated changed-code
    tokens instead of a fixed changed-line threshold.

    Why:

    - 100 short lines can easily fit in one request.
    - 30 extremely long lines may require splitting.
    - Different programming languages have very different
      average line lengths.

    A hard changed-line limit remains as a safety guard for
    unusually large changes.
    """

    DEFAULT_MAX_ESTIMATED_TOKENS_PER_CALL = 6000
    DEFAULT_MAX_CHANGED_LINES_PER_CALL = 500
    DEFAULT_MAX_PARTS = 2

    # A lightweight deterministic approximation.
    #
    # Code commonly averages around 3-4 characters/token.
    # Using 3 makes the estimate intentionally conservative.
    ESTIMATED_CHARACTERS_PER_TOKEN = 3

    def __init__(
        self,
        max_estimated_tokens_per_call: int = (
            DEFAULT_MAX_ESTIMATED_TOKENS_PER_CALL
        ),
        max_changed_lines_per_call: int = (
            DEFAULT_MAX_CHANGED_LINES_PER_CALL
        ),
        max_parts: int = DEFAULT_MAX_PARTS,
    ):
        if max_estimated_tokens_per_call <= 0:
            raise ValueError(
                "max_estimated_tokens_per_call "
                "must be greater than 0."
            )

        if max_changed_lines_per_call <= 0:
            raise ValueError(
                "max_changed_lines_per_call "
                "must be greater than 0."
            )

        if max_parts <= 0:
            raise ValueError(
                "max_parts must be greater than 0."
            )

        self.max_estimated_tokens_per_call = (
            max_estimated_tokens_per_call
        )

        self.max_changed_lines_per_call = (
            max_changed_lines_per_call
        )

        self.max_parts = max_parts

    def plan(
        self,
        changed_file: ChangedFile,
    ) -> FileReviewPlan:

        changed_lines = changed_file.changed_lines

        if not changed_lines:
            return FileReviewPlan(
                file_path=changed_file.file_path,
                mode=ReviewMode.FULL_FILE,
                parts=[],
            )

        estimated_tokens = (
            self._estimate_tokens(
                changed_lines
            )
        )

        # --------------------------------------------------
        # One-call path
        # --------------------------------------------------
        #
        # Prefer one request whenever both:
        #
        # 1. estimated changed-code tokens fit the budget
        # 2. the hard changed-line safety limit is respected
        # --------------------------------------------------

        if (
            estimated_tokens
            <= self.max_estimated_tokens_per_call
            and len(changed_lines)
            <= self.max_changed_lines_per_call
        ):
            return FileReviewPlan(
                file_path=changed_file.file_path,
                mode=ReviewMode.FULL_FILE,
                parts=[
                    ReviewPart(
                        index=1,
                        total=1,
                        changed_lines=list(
                            changed_lines
                        ),
                    )
                ],
            )

        # --------------------------------------------------
        # Split path
        # --------------------------------------------------

        raw_parts = self._split_changed_lines(
            changed_lines
        )

        total = len(raw_parts)

        review_parts = [
            ReviewPart(
                index=index,
                total=total,
                changed_lines=part,
            )
            for index, part in enumerate(
                raw_parts,
                start=1,
            )
        ]

        return FileReviewPlan(
            file_path=changed_file.file_path,
            mode=ReviewMode.SPLIT,
            parts=review_parts,
        )

    def estimate_changed_tokens(self, changed_file: ChangedFile) -> int:
        """Public token estimate used by higher-level batch planning."""

        return self._estimate_tokens(changed_file.changed_lines)

    def _split_changed_lines(
        self,
        changed_lines: list[ChangedLine],
    ) -> list[list[ChangedLine]]:
        """
        Split changed lines using both token and line budgets.

        The split preserves the original changed-line order.

        We first create natural budget-constrained chunks.
        If that produces more than max_parts, the chunks are
        redistributed into at most max_parts larger groups.

        max_parts is therefore a protection against excessive
        LLM calls.
        """

        parts: list[list[ChangedLine]] = []

        current_part: list[ChangedLine] = []
        current_tokens = 0

        for changed_line in changed_lines:

            line_tokens = (
                self._estimate_line_tokens(
                    changed_line
                )
            )

            token_limit_reached = (
                current_part
                and (
                    current_tokens
                    + line_tokens
                    > self.max_estimated_tokens_per_call
                )
            )

            line_limit_reached = (
                current_part
                and (
                    len(current_part)
                    >= self.max_changed_lines_per_call
                )
            )

            if (
                token_limit_reached
                or line_limit_reached
            ):
                parts.append(
                    current_part
                )

                current_part = []
                current_tokens = 0

            current_part.append(
                changed_line
            )

            current_tokens += line_tokens

        if current_part:
            parts.append(
                current_part
            )

        if len(parts) <= self.max_parts:
            return parts

        # --------------------------------------------------
        # Too many natural chunks.
        #
        # Cap the number of LLM calls and distribute the
        # original changed lines approximately evenly.
        # --------------------------------------------------

        return self._redistribute(
            changed_lines=changed_lines,
            part_count=self.max_parts,
        )

    def _redistribute(
        self,
        changed_lines: list[ChangedLine],
        part_count: int,
    ) -> list[list[ChangedLine]]:

        total_lines = len(
            changed_lines
        )

        part_size = (
            total_lines
            + part_count
            - 1
        ) // part_count

        return [
            changed_lines[
                start:start + part_size
            ]
            for start in range(
                0,
                total_lines,
                part_size,
            )
        ]

    def _estimate_tokens(
        self,
        changed_lines: list[ChangedLine],
    ) -> int:

        return sum(
            self._estimate_line_tokens(
                changed_line
            )
            for changed_line in changed_lines
        )

    def _estimate_line_tokens(
        self,
        changed_line: ChangedLine,
    ) -> int:
        """
        Conservative token approximation for source code.

        Include a small amount of overhead for the line
        number and prompt formatting.
        """

        content_length = len(
            changed_line.content
        )

        content_tokens = max(
            1,
            (
                content_length
                + self.ESTIMATED_CHARACTERS_PER_TOKEN
                - 1
            )
            // self.ESTIMATED_CHARACTERS_PER_TOKEN,
        )

        # Approximate overhead for:
        #
        # 172 | const value = ...
        #
        return content_tokens + 4
