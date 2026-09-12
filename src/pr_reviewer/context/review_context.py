from dataclasses import dataclass

from pr_reviewer.review.models import ChangedFile, ChangedLine


@dataclass
class ReviewContext:
    content: str
    used_full_file: bool
    estimated_tokens: int
    truncated: bool = False


class ReviewContextBuilder:
    """
    Builds safe source-code context for the LLM.

    The local model currently runs with a limited context window,
    so we avoid blindly sending the complete file when it is too large.

    Strategy:
    - Small file -> use complete file.
    - Large file -> use surrounding source context around changed lines.
    """

    DEFAULT_MAX_CODE_TOKENS = 1800
    DEFAULT_CONTEXT_LINES_AROUND_CHANGE = 20

    def __init__(
        self,
        max_code_tokens: int = DEFAULT_MAX_CODE_TOKENS,
        context_lines_around_change: int = (
            DEFAULT_CONTEXT_LINES_AROUND_CHANGE
        ),
    ):
        if max_code_tokens <= 0:
            raise ValueError(
                "max_code_tokens must be greater than 0."
            )

        if context_lines_around_change < 0:
            raise ValueError(
                "context_lines_around_change cannot be negative."
            )

        self.max_code_tokens = max_code_tokens
        self.context_lines_around_change = (
            context_lines_around_change
        )

    def build(
        self,
        changed_file: ChangedFile,
    ) -> ReviewContext:

        full_content = changed_file.full_content or ""

        if not full_content:
            return ReviewContext(
                content="",
                used_full_file=False,
                estimated_tokens=0,
            )

        full_tokens = self.estimate_tokens(
            full_content
        )

        # Small enough: use entire file.
        if full_tokens <= self.max_code_tokens:
            return ReviewContext(
                content=full_content,
                used_full_file=True,
                estimated_tokens=full_tokens,
            )

        # Large file: build relevant context only.
        contextual_content = (
            self._build_surrounding_context(
                full_content=full_content,
                changed_lines=changed_file.changed_lines,
            )
        )

        contextual_content, truncated = (
            self._trim_to_token_budget(
                contextual_content
            )
        )

        return ReviewContext(
            content=contextual_content,
            used_full_file=False,
            estimated_tokens=self.estimate_tokens(
                contextual_content
            ),
            truncated=truncated,
        )

    @staticmethod
    def estimate_tokens(
        text: str,
    ) -> int:
        """
        Lightweight approximation.

        For source code, ~4 characters/token is a reasonable
        conservative estimate for budgeting purposes.
        """

        if not text:
            return 0

        return max(
            1,
            (len(text) + 3) // 4,
        )

    def _build_surrounding_context(
        self,
        full_content: str,
        changed_lines: list[ChangedLine],
    ) -> str:

        source_lines = full_content.splitlines()

        if not changed_lines:
            return ""

        selected_line_numbers: set[int] = set()

        total_lines = len(source_lines)

        for changed_line in changed_lines:
            start = max(
                1,
                changed_line.line_number
                - self.context_lines_around_change,
            )

            end = min(
                total_lines,
                changed_line.line_number
                + self.context_lines_around_change,
            )

            for line_number in range(
                start,
                end + 1,
            ):
                selected_line_numbers.add(
                    line_number
                )

        ordered_numbers = sorted(
            selected_line_numbers
        )

        context_lines: list[str] = []

        previous_line_number: int | None = None

        for line_number in ordered_numbers:

            if (
                previous_line_number is not None
                and line_number
                > previous_line_number + 1
            ):
                context_lines.append(
                    "... omitted unrelated lines ..."
                )

            content = source_lines[
                line_number - 1
            ]

            context_lines.append(
                f"{line_number} | {content}"
            )

            previous_line_number = (
                line_number
            )

        return "\n".join(
            context_lines
        )

    def _trim_to_token_budget(
        self,
        content: str,
    ) -> tuple[str, bool]:

        if (
            self.estimate_tokens(content)
            <= self.max_code_tokens
        ):
            return content, False

        max_characters = (
            self.max_code_tokens * 4
        )

        trimmed = content[
            :max_characters
        ]

        return (
            trimmed.rstrip()
            + "\n... context trimmed to fit model budget ...",
            True
        )