from dataclasses import dataclass

from pr_reviewer.context.models import RepositoryContext
from pr_reviewer.llm.review_planner import FileReviewPlanner
from pr_reviewer.review.models import ChangedFile
from pr_reviewer.review.review_router import ReviewRouter


@dataclass(frozen=True)
class ReviewBatch:
    index: int
    files: tuple[ChangedFile, ...]


class ProjectAwareBatchPlanner:
    """Batch only small, compatible files from the same semantic owner."""

    DEFAULT_MAX_FILES = 10
    DEFAULT_MAX_CHANGED_TOKENS = 9000

    def __init__(
        self,
        file_planner: FileReviewPlanner | None = None,
        router: ReviewRouter | None = None,
        max_files: int = DEFAULT_MAX_FILES,
        max_changed_tokens: int = DEFAULT_MAX_CHANGED_TOKENS,
    ):
        self.file_planner = file_planner or FileReviewPlanner()
        self.router = router or ReviewRouter()
        self.max_files = max_files
        self.max_changed_tokens = max_changed_tokens

    def plan(
        self,
        changed_files: list[ChangedFile],
        repository_context: RepositoryContext,
    ) -> list[ReviewBatch]:
        original_order = {
            changed_file.file_path: index
            for index, changed_file in enumerate(changed_files)
        }
        groups: dict[str, list[ChangedFile]] = {}

        for changed_file in changed_files:
            plan = self.file_planner.plan(changed_file)
            file_context = repository_context.resolve_file_context(
                changed_file.file_path
            )
            framework = file_context.framework
            # Project ownership is carried per file in the prompt. Grouping by
            # project unnecessarily serialized compatible libraries in large
            # monorepos. The resolved framework is the compatibility boundary;
            # the per-file review strategy is carried explicitly in the prompt.
            compatibility_key = framework
            if changed_file.file_path.lower().endswith((".py", ".pyw")) and framework in {
                "python", "django", "flask", "fastapi"
            }:
                compatibility_key = "python-backend"
            groups.setdefault(compatibility_key, []).append(changed_file)

        batches: list[ReviewBatch] = []
        for files in groups.values():
            current: list[ChangedFile] = []
            current_tokens = 0
            for changed_file in files:
                tokens = self.file_planner.estimate_changed_tokens(changed_file)
                if current and (
                    len(current) >= self.max_files
                    or current_tokens + tokens > self.max_changed_tokens
                ):
                    batches.append(ReviewBatch(len(batches) + 1, tuple(current)))
                    current = []
                    current_tokens = 0
                current.append(changed_file)
                current_tokens += tokens
            if current:
                batches.append(ReviewBatch(len(batches) + 1, tuple(current)))

        batches.sort(
            key=lambda batch: min(
                original_order[file.file_path]
                for file in batch.files
            )
        )
        return [
            ReviewBatch(index=index, files=batch.files)
            for index, batch in enumerate(batches, start=1)
        ]
