from dataclasses import dataclass
from pathlib import PurePosixPath

from pr_reviewer.review.file_classifier import (
    FileCategory,
    FileClassification,
    FileClassifier,
)
from pr_reviewer.review.models import ChangedFile
from pr_reviewer.review.review_strategy import (
    ReviewStrategy,
)


@dataclass(frozen=True)
class ReviewRoute:
    """
    Describes how a changed file should move through
    the semantic AI review pipeline.

    category:
        What kind of file was detected.

    strategy:
        What type of semantic review should be applied.

    should_review_with_llm:
        Whether the file should be sent to the LLM.

    reason:
        Human-readable routing explanation.
    """

    file_path: str

    category: FileCategory

    strategy: ReviewStrategy

    should_review_with_llm: bool

    reason: str


class ReviewRouter:
    """
    Language-agnostic semantic review router.

    Responsibilities:

    1. Classify the changed file.

    2. Decide whether the file should be reviewed
       by the LLM.

    3. Select the appropriate semantic review strategy.

    The router does NOT decide which programming
    languages are supported.

    Unknown source/text files remain reviewable because
    the FileClassifier intentionally keeps unknown file
    types eligible.

    This prevents the routing layer from becoming a
    hard-coded programming-language whitelist.
    """

    STRATEGY_MAP = {
        FileCategory.SOURCE_CODE: (
            ReviewStrategy.SEMANTIC
        ),

        FileCategory.TEST: (
            ReviewStrategy.TEST
        ),

        FileCategory.TEMPLATE: (
            ReviewStrategy.TEMPLATE
        ),

        FileCategory.STYLESHEET: (
            ReviewStrategy.STYLESHEET
        ),

        FileCategory.PROJECT_CONFIGURATION: (
            ReviewStrategy.CONFIGURATION
        ),

        FileCategory.UNKNOWN: (
            ReviewStrategy.SEMANTIC
        ),
    }

    def __init__(
        self,
        file_classifier: FileClassifier | None = None,
    ):
        self.file_classifier = (
            file_classifier
            or FileClassifier()
        )

    def route(
        self,
        changed_file: ChangedFile,
    ) -> ReviewRoute:
        """
        Determine the semantic-review route for one
        changed file.
        """

        classification = (
            self.file_classifier.classify(
                changed_file.file_path
            )
        )

        # --------------------------------------------------
        # No commentable changed lines
        # --------------------------------------------------

        if not changed_file.changed_lines:
            return ReviewRoute(
                file_path=changed_file.file_path,
                category=classification.category,
                strategy=ReviewStrategy.SKIP,
                should_review_with_llm=False,
                reason=(
                    "File has no commentable changed "
                    "source lines."
                ),
            )

        if self._is_import_export_only_support_file(changed_file):
            return ReviewRoute(
                file_path=changed_file.file_path,
                category=classification.category,
                strategy=ReviewStrategy.SKIP,
                should_review_with_llm=False,
                reason=(
                    "Import/export-only barrel or test setup file is "
                    "context-only for semantic review."
                ),
            )

        # --------------------------------------------------
        # File classifier explicitly excludes the file
        # --------------------------------------------------

        if not classification.reviewable:
            return ReviewRoute(
                file_path=changed_file.file_path,
                category=classification.category,
                strategy=ReviewStrategy.SKIP,
                should_review_with_llm=False,
                reason=classification.reason,
            )

        # --------------------------------------------------
        # Determine semantic review strategy
        # --------------------------------------------------

        strategy = self._strategy_for(
            classification
        )

        # --------------------------------------------------
        # Defensive fallback
        # --------------------------------------------------

        if strategy == ReviewStrategy.SKIP:
            return ReviewRoute(
                file_path=changed_file.file_path,
                category=classification.category,
                strategy=ReviewStrategy.SKIP,
                should_review_with_llm=False,
                reason=(
                    "No semantic review strategy is "
                    "configured for this file category."
                ),
            )

        # --------------------------------------------------
        # Reviewable
        # --------------------------------------------------

        return ReviewRoute(
            file_path=changed_file.file_path,
            category=classification.category,
            strategy=strategy,
            should_review_with_llm=True,
            reason=classification.reason,
        )

    def should_review_with_llm(
        self,
        changed_file: ChangedFile,
    ) -> bool:
        """
        Return whether a changed file should be sent
        to the LLM.
        """

        return self.route(
            changed_file
        ).should_review_with_llm

    def strategy_for(
        self,
        changed_file: ChangedFile,
    ) -> ReviewStrategy:
        """Return the semantic strategy associated with the file type.

        Review eligibility and semantic strategy are deliberately separate.
        A context-only file such as ``tsconfig.json`` may still be a
        CONFIGURATION file even though ``route()`` prevents it from consuming
        an LLM call. This keeps prompt/configuration semantics stable for
        callers that inspect strategy directly.
        """

        classification = self.file_classifier.classify(changed_file.file_path)
        if not changed_file.changed_lines:
            return ReviewStrategy.SKIP
        return self._strategy_for(classification)

    def partition(
        self,
        changed_files: list[ChangedFile],
    ) -> tuple[
        list[ChangedFile],
        list[ReviewRoute],
    ]:
        """
        Split changed files into:

        1. Files eligible for semantic LLM review.

        2. Routes describing files skipped by the LLM.

        The original ChangedFile objects are preserved.
        """

        reviewable_files: list[ChangedFile] = []

        skipped_routes: list[ReviewRoute] = []

        for changed_file in changed_files:

            route = self.route(
                changed_file
            )

            if route.should_review_with_llm:
                reviewable_files.append(
                    changed_file
                )

            else:
                skipped_routes.append(
                    route
                )

        return (
            reviewable_files,
            skipped_routes,
        )

    def partition_routes(
        self,
        changed_files: list[ChangedFile],
    ) -> tuple[
        list[ReviewRoute],
        list[ReviewRoute],
    ]:
        """
        Split changed files into complete routing
        information.

        Unlike partition(), this method preserves the
        ReviewRoute for reviewable files as well.

        This will later allow the orchestrator and prompt
        builder to know whether a file requires:

        - semantic review
        - test review
        - template review
        - stylesheet review
        - configuration review
        """

        reviewable_routes: list[ReviewRoute] = []

        skipped_routes: list[ReviewRoute] = []

        for changed_file in changed_files:

            route = self.route(
                changed_file
            )

            if route.should_review_with_llm:
                reviewable_routes.append(
                    route
                )

            else:
                skipped_routes.append(
                    route
                )

        return (
            reviewable_routes,
            skipped_routes,
        )

    def _strategy_for(
        self,
        classification: FileClassification,
    ) -> ReviewStrategy:
        """
        Map a file classification to its semantic
        review strategy.
        """

        return self.STRATEGY_MAP.get(
            classification.category,
            ReviewStrategy.SKIP,
        )

    @staticmethod
    def _is_import_export_only_support_file(
        changed_file: ChangedFile,
    ) -> bool:
        name = PurePosixPath(
            changed_file.file_path.replace("\\", "/")
        ).name.lower()
        if name.endswith(".sln"):
            return True
        if name not in {"index.ts", "index.js", "test-setup.ts", "test-setup.js", "usings.cs"}:
            return False

        meaningful = [
            line.content.strip()
            for line in changed_file.changed_lines
            if line.content.strip()
            and not line.content.strip().startswith(("//", "/*", "*", "*/"))
        ]
        if not meaningful:
            return True
        return all(
            line.startswith("import ")
            or line.startswith(("export *", "export {", "export type {", "export type *"))
            or line.startswith("global using ")
            or line.startswith("using ")
            or line in {"export {};", "export {}"}
            for line in meaningful
        )
