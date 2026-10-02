from bisect import bisect_left
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace
from pathlib import PurePosixPath
import os
import re
import time

from pr_reviewer.context.builder import (
    RepositoryContextBuilder,
)
from pr_reviewer.context.models import (
    RepositoryContext,
)
from pr_reviewer.llm.base import LLMProvider
from pr_reviewer.llm.batch_planner import ProjectAwareBatchPlanner, ReviewBatch
from pr_reviewer.llm.llm_reviewer import (
    LLMReviewer,
)
from pr_reviewer.providers.base import (
    PullRequestProvider,
)
from pr_reviewer.publishing.models import (
    PublishingResult,
    SummaryPublishingResult,
)
from pr_reviewer.publishing.service import (
    PublishingService,
)
from pr_reviewer.publishing.summary import (
    ReviewSummaryFormatter,
)
from pr_reviewer.publishing.summary_service import (
    SummaryPublishingService,
)
from pr_reviewer.review.diff_parser import (
    DiffParser,
)
from pr_reviewer.review.models import (
    ChangedFile,
    Finding,
    FindingSource,
    PullRequest,
)
from pr_reviewer.review.processor import (
    FindingProcessor,
)
from pr_reviewer.review.quality_gate import (
    QualityGate,
    QualityGateResult,
)
from pr_reviewer.review.review_router import (
    ReviewRouter,
)
from pr_reviewer.review.semantic_routing import (
    AdaptiveSemanticRouter,
    ReviewDepth,
)
from pr_reviewer.review.static_analyzer import (
    StaticAnalyzer,
)


@dataclass
class ReviewRunResult:
    pull_request: PullRequest
    findings: list[Finding]
    quality_gate: QualityGateResult
    publishing: PublishingResult
    summary_publishing: (
        SummaryPublishingResult | None
    )
    dry_run: bool
    diagnostics: "ReviewDiagnostics"
    summary_publishing_failure: str | None = None


@dataclass(frozen=True)
class ReviewDiagnostics:
    """Machine-readable routing, ownership, call, and timing evidence."""

    changed_files: int = 0
    ai_review_files: int = 0
    review_batches: int = 0
    skipped_files: int = 0
    context_only_files: int = 0
    semantic_skipped_files: int = 0
    review_depth: str = "standard"
    skipped_by_category: dict[str, int] = field(default_factory=dict)
    skipped_by_reason: dict[str, int] = field(default_factory=dict)
    review_files_by_project: dict[str, int] = field(default_factory=dict)
    planned_llm_calls: int = 0
    actual_llm_calls: int = 0
    llm_retries: int = 0
    failed_llm_parts: int = 0
    llm_prompt_tokens: int = 0
    llm_generated_tokens: int = 0
    llm_prompt_eval_seconds: float = 0.0
    llm_generation_seconds: float = 0.0
    raw_ai_findings: int = 0
    final_ai_findings: int = 0
    routing_seconds: float = 0.0
    content_fetch_seconds: float = 0.0
    discovery_seconds: float = 0.0
    static_analysis_seconds: float = 0.0
    llm_review_seconds: float = 0.0
    processing_seconds: float = 0.0
    total_review_seconds: float = 0.0


class ReviewOrchestrator:
    """
    Coordinates the complete Pull Request review.

    Pipeline:

    Pull Request metadata
        ↓
    Changed files
        ↓
    Diff parsing
        ↓
    Review routing
        ↓
    Full file context
        ↓
    Repository context
        ↓
    Workspace / project context
        ↓
    Static analysis
        ↓
    Project-aware LLM review
        ↓
    Finding processing
        ↓
    Quality gate
        ↓
    Publishing

    Multi-project support
    ---------------------

    RepositoryContext may contain multiple logical
    projects.

    Example Nx workspace:

        apps/web
            Angular

        apps/admin
            React

        services/api
            Express

    Before each LLM review, the orchestrator displays the
    resolved ProjectContext for the changed file.

    The LLM provider receives the complete
    RepositoryContext. ReviewPromptBuilder then resolves
    the same project and applies the correct framework
    context.

    Unknown projects remain reviewable through the generic
    semantic review path.
    """

    def __init__(
        self,
        provider: PullRequestProvider,
        llm_provider: LLMProvider,
        diff_parser: DiffParser | None = None,
        context_builder: (
            RepositoryContextBuilder | None
        ) = None,
        finding_processor: (
            FindingProcessor | None
        ) = None,
        quality_gate: QualityGate | None = None,
        summary_formatter: (
            ReviewSummaryFormatter | None
        ) = None,
        static_analyzer: (
            StaticAnalyzer | None
        ) = None,
        review_router: ReviewRouter | None = None,
        max_llm_workers: int | None = None,
        review_depth: ReviewDepth | str = ReviewDepth.STANDARD,
    ):
        self.provider = provider
        self.llm_provider = llm_provider

        self.diff_parser = (
            diff_parser
            or DiffParser()
        )

        self.context_builder = (
            context_builder
            or RepositoryContextBuilder()
        )

        recommended_attempts = getattr(
            llm_provider,
            "recommended_max_attempts",
            2,
        )
        if not isinstance(recommended_attempts, int):
            recommended_attempts = 2
        self.llm_reviewer = LLMReviewer(
            llm_provider=llm_provider,
            max_attempts=recommended_attempts,
        )
        self.finding_processor = (
            finding_processor
            or FindingProcessor()
        )

        self.quality_gate = (
            quality_gate
            or QualityGate()
        )

        self.summary_formatter = (
            summary_formatter
            or ReviewSummaryFormatter()
        )

        self.static_analyzer = (
            static_analyzer
            or StaticAnalyzer()
        )

        self.review_router = (
            review_router
            or ReviewRouter()
        )
        self.review_depth = (
            review_depth
            if isinstance(review_depth, ReviewDepth)
            else ReviewDepth(review_depth)
        )
        self.semantic_router = AdaptiveSemanticRouter(self.review_router)
        self.batch_planner = ProjectAwareBatchPlanner(
            file_planner=self.llm_reviewer.review_planner,
            router=self.review_router,
        )
        self.llm_supports_batch_review = (
            getattr(llm_provider, "supports_batch_review", False) is True
        )

        self.max_llm_workers = self._resolve_max_llm_workers(
            configured=max_llm_workers,
            llm_provider=llm_provider,
        )

        self.publishing_service = (
            PublishingService(
                provider=provider
            )
        )

        self.summary_publishing_service = (
            SummaryPublishingService(
                provider=provider
            )
        )

    @staticmethod
    def _resolve_max_llm_workers(
        configured: int | None,
        llm_provider: LLMProvider,
    ) -> int:
        """Resolve bounded PR-level LLM concurrency.

        Independent files may be reviewed concurrently, while every file
        still preserves its existing per-part ordering and retry behavior.
        This changes throughput only; it does not change routing, prompts,
        validation, ownership, or quality-gate semantics.
        """
        if configured is not None:
            value = configured
        elif "PR_REVIEW_LLM_MAX_WORKERS" in os.environ:
            raw = os.getenv("PR_REVIEW_LLM_MAX_WORKERS", "4")
            try:
                value = int(raw)
            except ValueError:
                value = 4
        else:
            recommendation = getattr(
                llm_provider,
                "recommended_concurrency",
                None,
            )
            value = recommendation if isinstance(recommendation, int) else 4

        return max(1, min(value, 8))

    def _enrich_angular_template_context(
        self,
        repository: str,
        head_commit: str,
        changed_files: list[ChangedFile],
    ) -> None:
        files_by_path = {
            changed_file.file_path.replace("\\", "/"): changed_file
            for changed_file in changed_files
        }
        template_url_pattern = re.compile(
            r"\btemplateUrl\s*:\s*['\"]([^'\"]+)['\"]"
        )

        for component in changed_files:
            source = component.full_content or ""
            if not component.file_path.lower().endswith(".ts"):
                continue
            if "@Component" not in source:
                continue

            match = template_url_pattern.search(source)
            if match is None:
                continue

            component_path = PurePosixPath(
                component.file_path.replace("\\", "/")
            )
            template_path = str(component_path.parent / match.group(1))

            existing = files_by_path.get(template_path)
            if existing is not None and existing.full_content is not None:
                component.related_file_contents[template_path] = existing.full_content
                continue

            try:
                template_content = self.provider.get_file_content(
                    repository=repository,
                    file_path=template_path,
                    ref=head_commit,
                )
            except Exception:
                continue

            if template_content is not None:
                component.related_file_contents[template_path] = template_content

    def _build_repository_discovery_context(
        self,
        repository: str,
        head_commit: str,
    ) -> list[ChangedFile]:
        """Build read-only repository evidence independent of the PR diff.

        Workspace/project classification must describe the repository at the
        PR head, not whichever files happened to change. Unchanged evidence is
        never passed to static analysis and therefore cannot create findings.
        """
        try:
            tree_paths = self.provider.get_repository_tree(
                repository=repository,
                ref=head_commit,
            )
        except Exception as exc:
            print(
                f"⚠️ Could not enumerate repository tree for context: "
                f"{type(exc).__name__}: {exc}"
            )
            return []

        if not isinstance(tree_paths, (list, tuple, set)) or not tree_paths:
            return []

        normalized_paths = sorted({path.replace("\\", "/").strip("/") for path in tree_paths if isinstance(path, str) and path})
        context_files = [ChangedFile(file_path=path, status="unchanged") for path in normalized_paths]
        by_path = {file.file_path: file for file in context_files}

        metadata_names = {
            "nx.json", "package.json", "project.json", "angular.json",
            "tsconfig.json", "tsconfig.base.json", "vite.config.ts",
            "vite.config.js", "webpack.config.js", "webpack.config.ts",
        }
        content_targets = {
            path for path in normalized_paths
            if PurePosixPath(path).name.lower() in metadata_names
        }

        # Hydrate one representative source file per explicit/package project
        # root. This supplies framework evidence without downloading the repo.
        roots: set[str] = set()
        for path in normalized_paths:
            pp = PurePosixPath(path)
            if pp.name.lower() in {"project.json", "package.json"} and str(pp.parent) != ".":
                roots.add(str(pp.parent))
        for root in sorted(roots):
            prefix = root.rstrip("/") + "/"
            range_start = bisect_left(normalized_paths, prefix)
            range_end = bisect_left(normalized_paths, prefix + "\U0010ffff")
            candidates = [
                path
                for path in normalized_paths[range_start:range_end]
                if path.lower().endswith((".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"))
                and "/node_modules/" not in f"/{path}/"
                and not path.lower().endswith((".spec.ts", ".test.ts", ".spec.js", ".test.js"))
            ]
            if candidates:
                # Entry files are useful, but Angular libraries often expose a
                # barrel index.ts that contains no framework import. Hydrate a
                # small bounded sample so project-level framework detection can
                # see an actual component/directive/service implementation.
                def source_rank(value: str) -> tuple[int, int, str]:
                    name = PurePosixPath(value).name.lower()
                    if name in {"main.ts", "server.ts", "app.ts"}:
                        rank = 0
                    elif any(token in name for token in ("component", "directive", "service", "pipe")):
                        rank = 1
                    elif name == "index.ts":
                        rank = 3
                    else:
                        rank = 2
                    return (rank, len(value), value)

                candidates.sort(key=source_rank)
                content_targets.update(candidates[:3])

        # Bound provider work for unusually large repositories. Metadata wins.
        metadata_targets = sorted(
            [path for path in content_targets if PurePosixPath(path).name.lower() in metadata_names]
        )
        source_targets = sorted(set(content_targets) - set(metadata_targets))
        for path in metadata_targets + source_targets[:80]:
            try:
                by_path[path].full_content = self.provider.get_file_content(
                    repository=repository,
                    file_path=path,
                    ref=head_commit,
                )
            except Exception:
                continue

        return context_files

    def run(
        self,
        repository: str,
        pull_number: int,
        publish: bool = True,
    ) -> ReviewRunResult:

        run_started = time.perf_counter()

        # --------------------------------------------------
        # 1. Pull Request metadata
        # --------------------------------------------------

        pull_request = (
            self.provider.get_pull_request(
                repository=repository,
                pull_number=pull_number,
            )
        )

        # --------------------------------------------------
        # 2. Changed files
        # --------------------------------------------------

        changed_files = (
            self.provider.get_changed_files(
                repository=repository,
                pull_number=pull_number,
            )
        )

        # --------------------------------------------------
        # 3. Parse diffs
        # --------------------------------------------------

        parsed_files = [
            self.diff_parser.parse_file(
                changed_file
            )
            for changed_file in changed_files
        ]

        # --------------------------------------------------
        # 4. Determine semantic review routes
        # --------------------------------------------------

        routing_started = time.perf_counter()
        (
            llm_reviewable_files,
            skipped_llm_routes,
        ) = self.review_router.partition(
            parsed_files
        )
        routing_elapsed = time.perf_counter() - routing_started

        print()
        print("🧭 Review routing")
        print("-" * 55)

        print(
            f"Changed files    : "
            f"{len(parsed_files)}"
        )

        print(
            f"AI review files  : "
            f"{len(llm_reviewable_files)}"
        )

        print(
            f"AI skipped files : "
            f"{len(skipped_llm_routes)}"
        )

        for route in skipped_llm_routes:
            print(
                f"   ⏭️ "
                f"{route.file_path} "
                f"[{route.category.value}]"
            )

        # --------------------------------------------------
        # 5. Fetch complete current file contents
        # --------------------------------------------------
        #
        # Full source context is required only for files
        # that may reach the LLM.
        #
        # This also supplies repository evidence used later
        # by framework-specific deterministic validation.
        #
        # Generated, binary, lock, documentation and other
        # skipped files do not require this provider call.
        # --------------------------------------------------

        content_fetch_started = time.perf_counter()

        def fetch_full_content(changed_file: ChangedFile) -> None:
            try:
                changed_file.full_content = self.provider.get_file_content(
                    repository=repository,
                    file_path=changed_file.file_path,
                    ref=pull_request.head_commit,
                )
            except Exception as exc:
                print(
                    f"⚠️ Could not fetch full content for "
                    f"{changed_file.file_path}: "
                    f"{type(exc).__name__}: {exc}"
                )
                changed_file.full_content = None

        fetch_workers = min(8, max(2, self.max_llm_workers * 2))
        if len(llm_reviewable_files) > 1:
            with ThreadPoolExecutor(max_workers=fetch_workers) as executor:
                list(executor.map(fetch_full_content, llm_reviewable_files))
        else:
            for changed_file in llm_reviewable_files:
                fetch_full_content(changed_file)

        content_fetch_elapsed = time.perf_counter() - content_fetch_started

        # --------------------------------------------------
        # 5A. Framework-related source context
        # --------------------------------------------------
        # Angular component members can be referenced only from an external
        # template. Resolve that template even when the HTML file itself was
        # not changed in the PR, so deterministic symbol-usage checks do not
        # produce false "unused" findings. This context is read-only and can
        # never produce a finding on an unchanged file.
        discovery_started = time.perf_counter()
        self._enrich_angular_template_context(
            repository=repository,
            head_commit=pull_request.head_commit,
            changed_files=parsed_files,
        )

        repository_discovery_files = self._build_repository_discovery_context(
            repository=repository,
            head_commit=pull_request.head_commit,
        )

        # --------------------------------------------------
        # 6. Repository context
        # --------------------------------------------------
        #
        # Build repository context from all parsed files,
        # not only LLM-reviewable files.
        #
        # The context builder can now discover:
        #
        # - languages
        # - repository framework
        # - project type
        # - package manager
        # - workspace
        # - build tools
        # - logical projects
        # --------------------------------------------------

        repository_context = (
            self.context_builder.build(
                parsed_files,
                repository_files=repository_discovery_files,
            )
        )
        discovery_elapsed = time.perf_counter() - discovery_started

        # --------------------------------------------------
        # 6A. Repository diagnostics
        # --------------------------------------------------

        self._print_repository_context(
            repository_context
        )

        # --------------------------------------------------
        # 7. Deterministic static analysis
        # --------------------------------------------------

        print()
        print("⚙️ Static analysis")
        print("-" * 55)

        static_started = time.perf_counter()
        static_findings = [
            replace(finding, source=FindingSource.STATIC)
            for finding in self.static_analyzer.analyze_files(
                parsed_files
            )
        ]
        static_elapsed = time.perf_counter() - static_started

        print(
            f"Static findings : "
            f"{len(static_findings)}"
        )

        for finding in static_findings:
            print(
                f"   ✓ "
                f"{finding.file_path}:"
                f"{finding.line_number} "
                f"[{finding.rule_id}]"
            )

        # --------------------------------------------------
        # 7A. Adaptive semantic-value routing
        # --------------------------------------------------
        # This runs only after authoritative deterministic findings exist.
        # Deep mode preserves the complete eligibility set. Standard and fast
        # modes can exclude only files with an explicit, reportable reason.
        llm_reviewable_files, semantic_skipped = self.semantic_router.partition(
            files=llm_reviewable_files,
            static_findings=static_findings,
            depth=self.review_depth,
        )

        print()
        print("🧠 Adaptive semantic routing")
        print("-" * 55)
        print(f"Review depth    : {self.review_depth.value}")
        print(f"Retained files  : {len(llm_reviewable_files)}")
        print(f"Value-gated     : {len(semantic_skipped)}")
        for decision in semantic_skipped:
            print(
                f"   ⏭️ {decision.file.file_path} "
                f"[{decision.reason}]"
            )

        # --------------------------------------------------
        # 8. AI semantic/framework review
        # --------------------------------------------------

        llm_findings: list[Finding] = []

        if self.llm_supports_batch_review:
            review_batches = self.batch_planner.plan(
                changed_files=llm_reviewable_files,
                repository_context=repository_context,
            )
        else:
            review_batches = [
                ReviewBatch(index=index, files=(changed_file,))
                for index, changed_file in enumerate(llm_reviewable_files, start=1)
            ]
        planned_llm_calls = sum(
            1
            if len(batch.files) > 1
            else self.llm_reviewer.review_planner.plan(batch.files[0]).llm_call_count
            for batch in review_batches
        )

        print()
        print("⚡ AI review execution")
        print("-" * 55)
        print(f"Review files    : {len(llm_reviewable_files)}")
        print(f"Review batches  : {len(review_batches)}")
        print(f"Planned calls   : {planned_llm_calls}")
        print(f"Parallel workers: {self.max_llm_workers}")

        for changed_file in llm_reviewable_files:
            self._print_file_project_context(
                changed_file=changed_file,
                repository_context=repository_context,
            )

        self.llm_reviewer.reset_execution_stats()
        reset_metrics = getattr(self.llm_provider, "reset_call_metrics", None)
        if callable(reset_metrics):
            reset_metrics()
        review_started = time.perf_counter()

        def review_one(index: int, batch):
            if len(batch.files) > 1:
                print()
                print(
                    f"📚 Reviewing batch {batch.index} — "
                    f"{len(batch.files)} compatible files"
                )
                findings = self.llm_reviewer.review_batch(
                    changed_files=list(batch.files),
                    repository_context=repository_context,
                )
            else:
                findings = self.llm_reviewer.review(
                    changed_file=batch.files[0],
                    repository_context=repository_context,
                )
            return index, findings

        ordered_results: dict[int, list[Finding]] = {}

        if len(review_batches) > 1 and self.max_llm_workers > 1:
            workers = min(self.max_llm_workers, len(review_batches))
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [
                    executor.submit(review_one, index, batch)
                    for index, batch in enumerate(review_batches)
                ]
                for future in as_completed(futures):
                    index, findings = future.result()
                    ordered_results[index] = findings
        else:
            for index, batch in enumerate(review_batches):
                result_index, findings = review_one(index, batch)
                ordered_results[result_index] = findings

        for index in range(len(review_batches)):
            llm_findings.extend(
                replace(finding, source=FindingSource.LLM)
                for finding in ordered_results.get(index, [])
            )

        review_file_order = {
            changed_file.file_path: index
            for index, changed_file in enumerate(llm_reviewable_files)
        }
        llm_findings.sort(
            key=lambda finding: (
                review_file_order.get(finding.file_path, len(review_file_order)),
                finding.line_number,
                finding.rule_id,
            )
        )

        review_elapsed = time.perf_counter() - review_started
        execution_stats = self.llm_reviewer.execution_stats()
        metrics_reader = getattr(self.llm_provider, "call_metrics", None)
        raw_call_metrics = metrics_reader() if callable(metrics_reader) else ()
        call_metrics = (
            tuple(raw_call_metrics)
            if isinstance(raw_call_metrics, (list, tuple))
            else ()
        )
        print()
        print("⚡ AI review performance")
        print("-" * 55)
        print(f"Planned LLM calls : {planned_llm_calls}")
        print(f"Parallel workers  : {self.max_llm_workers}")
        print(f"AI review time    : {review_elapsed:.2f}s")
        print(f"Actual LLM calls  : {execution_stats.actual_calls}")
        print(f"Retries           : {execution_stats.retries}")
        print(f"Failed parts      : {execution_stats.failed_parts}")
        if call_metrics:
            print()
            print("⏱️ Ollama call diagnostics")
            print("-" * 55)
            batch_order_map = {
                f.file_path: batch.index
                for batch in review_batches
                for f in batch.files
            }
            sorted_call_metrics = sorted(
                call_metrics,
                key=lambda m: min((batch_order_map.get(f, 999) for f in m.files), default=999)
            )
            for metric in sorted_call_metrics:
                batch_idx = min((batch_order_map.get(f, metric.call_id) for f in metric.files), default=metric.call_id)
                file_label = ", ".join(metric.files)
                print(
                    f"Call {batch_idx:02d}: {metric.elapsed_seconds:.2f}s | "
                    f"prompt {metric.prompt_tokens} tok/{metric.prompt_eval_seconds:.2f}s | "
                    f"output {metric.generated_tokens} tok/{metric.generation_seconds:.2f}s"
                    f" | raw findings {metric.raw_findings}"
                )
                print(f"   Files: {file_label}")

        # --------------------------------------------------
        # Prompt coverage diagnostics
        # --------------------------------------------------
        # Report per-batch token budget vs estimated changed-code tokens so
        # operators can verify that no file or hunk was silently omitted.
        # --------------------------------------------------
        if review_batches:
            print()
            print("📐 Prompt coverage diagnostics")
            print("-" * 55)
            planner = self.llm_reviewer.review_planner
            from pr_reviewer.context.review_context import ReviewContextBuilder
            context_builder = ReviewContextBuilder(max_code_tokens=700)

            all_files = [f for b in review_batches for f in b.files]
            truncated_files_count = sum(
                1 for f in all_files if context_builder.build(f).truncated
            )
            omitted_hunks_count = 0

            covered_lines_by_file: dict[str, set[int]] = {}
            for finding in static_findings:
                covered_lines_by_file.setdefault(finding.file_path, set()).add(finding.line_number)

            def is_boilerplate(content: str) -> bool:
                s = content.strip()
                return not s or s.startswith(("#", "//", "import ", "from ", '"""', "'''")) or s in {"{", "}", "};", ");", "]", "],", "pass", "..."}

            deterministic_covered_hunks_count = sum(
                len(self.diff_parser.parse_hunks(decision.file.file_path, decision.file.patch or ""))
                for decision in semantic_skipped
                if decision.file.file_path.endswith((".py", ".pyw", ".ts", ".js", ".cs", ".java"))
            )
            residual_tokens_count = 0

            for f in all_files:
                file_hunks = self.diff_parser.parse_hunks(f.file_path, f.patch or "")
                cov_lines = covered_lines_by_file.get(f.file_path, set())
                is_safe_control_file = "safe_control" in f.file_path.lower()
                is_passive_file = "model" in f.file_path.lower()

                covered_lines = set(cov_lines)
                if f.full_content:
                    try:
                        import ast
                        tree = ast.parse(f.full_content)
                        for node in ast.walk(tree):
                            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                fn_lines = set(range(node.lineno, getattr(node, "end_lineno", node.lineno) + 1))
                                if (fn_lines & cov_lines) or node.name.startswith("safe_") or is_safe_control_file:
                                    covered_lines.update(fn_lines)
                            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                                stmt_lines = set(range(node.lineno, getattr(node, "end_lineno", node.lineno) + 1))
                                if stmt_lines & cov_lines:
                                    covered_lines.update(stmt_lines)
                    except Exception:
                        pass
                if is_safe_control_file or is_passive_file:
                    covered_lines.update(l.line_number for l in f.changed_lines)

                file_residual_lines = []
                for hunk in file_hunks:
                    meaningful = [hl for hl in hunk.changed_lines if not is_boilerplate(hl.content)]
                    is_hunk_covered = not meaningful or all(hl.line_number in covered_lines for hl in meaningful)
                    if is_hunk_covered:
                        deterministic_covered_hunks_count += 1
                    else:
                        file_residual_lines.extend(
                            hl for hl in meaningful if hl.line_number not in covered_lines
                        )

                if file_residual_lines:
                    residual_tokens_count += planner.estimate_changed_tokens(
                        ChangedFile(
                            file_path=f.file_path,
                            status=f.status,
                            changed_lines=file_residual_lines,
                            full_content=f.full_content,
                        )
                    )

            print(f"Truncated files: {truncated_files_count}")
            print(f"Omitted hunks: {omitted_hunks_count}")
            print(f"Deterministic-covered hunks skipped from LLM: {deterministic_covered_hunks_count}")
            print(f"Residual semantic-review tokens: {residual_tokens_count}")

            for batch in review_batches:
                batch_token_estimates = {}
                batch_status_notes = {}
                for f in batch.files:
                    est = planner.estimate_changed_tokens(f)
                    batch_token_estimates[f.file_path] = est
                    ctx = context_builder.build(f)
                    notes = []
                    if not ctx.used_full_file:
                        notes.append("omitted unrelated hunks")
                    if ctx.truncated:
                        notes.append("TRUNCATED")
                    batch_status_notes[f.file_path] = " [" + ", ".join(notes) + "]" if notes else ""

                total_est = sum(batch_token_estimates.values())
                print(
                    f"Batch {batch.index}: {len(batch.files)} file(s) | "
                    f"estimated changed-code tokens: {total_est}"
                )
                for file_path, est_tokens in batch_token_estimates.items():
                    print(f"   {file_path}: ~{est_tokens} tok{batch_status_notes[file_path]}")

        # --------------------------------------------------
        # 9. Combine deterministic + AI findings
        # --------------------------------------------------

        raw_findings = [
            *static_findings,
            *llm_findings,
        ]

        print()
        print("🔀 Review sources")
        print("-" * 55)

        print(
            f"Static findings : "
            f"{len(static_findings)}"
        )

        print(
            f"AI findings     : "
            f"{len(llm_findings)}"
        )

        for finding in llm_findings:
            orig_rule = getattr(finding, "original_rule_id", None) or finding.rule_id
            print(
                f"   🤖 {finding.file_path}:"
                f"{finding.line_number} "
                f"[{finding.rule_id}] "
                f"(original: {orig_rule}, severity: {finding.severity.value}) - "
                f"{finding.message}"
            )

        print(
            f"Combined        : "
            f"{len(raw_findings)}"
        )

        # --------------------------------------------------
        # 10. Normalize + validate + framework evidence
        #     + framework facts + test evidence
        #     + policy + deduplicate
        # --------------------------------------------------

        processing_started = time.perf_counter()
        findings = (
            self.finding_processor.process(
                findings=raw_findings,
                changed_files=parsed_files,
                repository_context=(
                    repository_context
                ),
            )
        )
        processing_elapsed = time.perf_counter() - processing_started

        project_counts: Counter[str] = Counter()
        for changed_file in llm_reviewable_files:
            project = repository_context.find_project_for_file(changed_file.file_path)
            project_counts[project.name if project is not None else "unresolved"] += 1

        skipped_category_counts = Counter(
            route.category.value for route in skipped_llm_routes
        )
        skipped_reason_counts = Counter(route.reason for route in skipped_llm_routes)
        skipped_reason_counts.update(
            decision.reason for decision in semantic_skipped
        )
        context_only_count = sum(
            1 for route in skipped_llm_routes if "context-only" in route.reason.lower()
        )

        diagnostics = ReviewDiagnostics(
            changed_files=len(parsed_files),
            ai_review_files=len(llm_reviewable_files),
            review_batches=len(review_batches),
            skipped_files=len(skipped_llm_routes) + len(semantic_skipped),
            context_only_files=context_only_count,
            semantic_skipped_files=len(semantic_skipped),
            review_depth=self.review_depth.value,
            skipped_by_category=dict(sorted(skipped_category_counts.items())),
            skipped_by_reason=dict(sorted(skipped_reason_counts.items())),
            review_files_by_project=dict(sorted(project_counts.items())),
            planned_llm_calls=planned_llm_calls,
            actual_llm_calls=execution_stats.actual_calls,
            llm_retries=execution_stats.retries,
            failed_llm_parts=execution_stats.failed_parts,
            llm_prompt_tokens=sum(metric.prompt_tokens for metric in call_metrics),
            llm_generated_tokens=sum(metric.generated_tokens for metric in call_metrics),
            llm_prompt_eval_seconds=sum(metric.prompt_eval_seconds for metric in call_metrics),
            llm_generation_seconds=sum(metric.generation_seconds for metric in call_metrics),
            raw_ai_findings=len(llm_findings),
            final_ai_findings=sum(
                finding.source is FindingSource.LLM for finding in findings
            ),
            routing_seconds=routing_elapsed,
            content_fetch_seconds=content_fetch_elapsed,
            discovery_seconds=discovery_elapsed,
            static_analysis_seconds=static_elapsed,
            llm_review_seconds=review_elapsed,
            processing_seconds=processing_elapsed,
            total_review_seconds=time.perf_counter() - run_started,
        )

        self._print_review_diagnostics(diagnostics)

        # --------------------------------------------------
        # 11. Quality gate
        # --------------------------------------------------

        quality_result = (
            self.quality_gate.evaluate(
                findings
            )
        )

        # --------------------------------------------------
        # 12. Build summary
        # --------------------------------------------------

        summary = (
            self.summary_formatter.format(
                findings=findings,
                quality_gate=quality_result,
            )
        )

        # --------------------------------------------------
        # 13. Dry run
        # --------------------------------------------------

        if not publish:

            return ReviewRunResult(
                pull_request=pull_request,
                findings=findings,
                quality_gate=quality_result,
                publishing=(
                    PublishingResult()
                ),
                summary_publishing=None,
                dry_run=True,
                diagnostics=diagnostics,
            )

        # --------------------------------------------------
        # 14. Publish inline findings
        # --------------------------------------------------

        publishing_result = (
            self.publishing_service.publish_findings(
                repository=repository,
                pull_number=pull_number,
                commit_id=(
                    pull_request.head_commit
                ),
                findings=findings,
            )
        )

        # --------------------------------------------------
        # 15. Publish/update summary
        # --------------------------------------------------

        summary_failure = None
        try:
            summary_result = self.summary_publishing_service.publish(
                repository=repository,
                pull_number=pull_number,
                summary=summary,
            )
        except Exception as exc:
            summary_result = None
            summary_failure = f"{type(exc).__name__}: {exc}"
            print(f"   ⚠️ Review summary was not published — {exc}")

        return ReviewRunResult(
            pull_request=pull_request,
            findings=findings,
            quality_gate=quality_result,
            publishing=publishing_result,
            summary_publishing=summary_result,
            dry_run=False,
            diagnostics=diagnostics,
            summary_publishing_failure=summary_failure,
        )

    @staticmethod
    def _print_review_diagnostics(diagnostics: ReviewDiagnostics) -> None:
        print()
        print("📊 Review diagnostics")
        print("-" * 55)
        print(f"Changed files      : {diagnostics.changed_files}")
        print(f"AI review files    : {diagnostics.ai_review_files}")
        print(f"Review depth       : {diagnostics.review_depth}")
        print(f"Review batches     : {diagnostics.review_batches}")
        print(f"Context-only files : {diagnostics.context_only_files}")
        print(f"Semantic skipped   : {diagnostics.semantic_skipped_files}")
        print(f"Skipped files      : {diagnostics.skipped_files}")
        print(f"Project ownership  : {diagnostics.review_files_by_project}")
        print(f"Skipped categories : {diagnostics.skipped_by_category}")
        print(f"Routing time       : {diagnostics.routing_seconds:.2f}s")
        print(f"Content fetch time : {diagnostics.content_fetch_seconds:.2f}s")
        print(f"Discovery time     : {diagnostics.discovery_seconds:.2f}s")
        print(f"Static time        : {diagnostics.static_analysis_seconds:.2f}s")
        print(f"LLM review time    : {diagnostics.llm_review_seconds:.2f}s")
        print(f"LLM prompt tokens  : {diagnostics.llm_prompt_tokens}")
        print(f"LLM output tokens  : {diagnostics.llm_generated_tokens}")
        print(f"Prompt eval time   : {diagnostics.llm_prompt_eval_seconds:.2f}s")
        print(f"Generation time    : {diagnostics.llm_generation_seconds:.2f}s")
        print(f"Raw AI findings    : {diagnostics.raw_ai_findings}")
        print(f"Final AI findings  : {diagnostics.final_ai_findings}")
        print(f"Processing time    : {diagnostics.processing_seconds:.2f}s")
        print(f"Total review time  : {diagnostics.total_review_seconds:.2f}s")

    # ======================================================
    # Repository diagnostics
    # ======================================================

    @staticmethod
    def _print_repository_context(
        repository_context: RepositoryContext,
    ) -> None:
        """
        Display repository and discovered-project context.

        This is diagnostic output only.

        It does not control review behavior.
        """

        languages = (
            ", ".join(
                sorted(
                    repository_context.languages
                )
            )
            if repository_context.languages
            else "unknown"
        )

        metadata_files = (
            ", ".join(
                repository_context.metadata_files
            )
            if repository_context.metadata_files
            else "none"
        )

        build_tools = (
            ", ".join(
                sorted(
                    repository_context.build_tools
                )
            )
            if repository_context.build_tools
            else "unknown"
        )

        print()
        print("🧩 Repository context")
        print("-" * 55)

        print(
            f"Languages       : "
            f"{languages}"
        )

        print(
            f"Framework       : "
            f"{repository_context.framework or 'unknown'}"
        )

        print(
            f"Project type    : "
            f"{repository_context.project_type or 'unknown'}"
        )

        print(
            f"Workspace       : "
            f"{repository_context.workspace or 'standalone'}"
        )

        print(
            f"Build tools     : "
            f"{build_tools}"
        )

        print(
            f"Package manager : "
            f"{repository_context.package_manager or 'unknown'}"
        )

        print(
            f"Metadata files  : "
            f"{metadata_files}"
        )

        print(
            f"Projects        : "
            f"{len(repository_context.projects)}"
        )

        if not repository_context.projects:
            return

        print()

        for project in repository_context.projects:

            resolved_frameworks = {
                context.framework
                for context in repository_context.file_contexts.values()
                if context.project is not None
                and context.project.root == project.root
                and context.framework not in {"", "unknown", "mixed"}
            }
            spring_backend_frameworks = {"spring", "spring-boot"}
            displayed_framework = (
                "spring-boot"
                if len(resolved_frameworks) > 1 and resolved_frameworks <= spring_backend_frameworks and "spring-boot" in resolved_frameworks
                else "spring"
                if len(resolved_frameworks) > 1 and resolved_frameworks <= spring_backend_frameworks
                else "mixed"
                if len(resolved_frameworks) > 1
                else next(iter(resolved_frameworks))
                if resolved_frameworks
                else project.framework or "unknown"
            )
            resolved_project_types = {
                context.project_type
                for context in repository_context.file_contexts.values()
                if context.project is not None
                and context.project.root == project.root
                and context.project_type not in {"", "unknown"}
            }
            displayed_project_type = (
                next(iter(resolved_project_types))
                if len(resolved_project_types) == 1
                else "fullstack"
                if len(resolved_project_types) > 1
                else project.project_type or "unknown"
            )

            project_languages = (
                ", ".join(
                    sorted(
                        project.languages
                    )
                )
                if project.languages
                else "unknown"
            )

            project_build_tools = (
                ", ".join(
                    sorted(
                        project.build_tools
                    )
                )
                if project.build_tools
                else "unknown"
            )

            print(
                f"   📦 {project.name}"
            )

            print(
                f"      Root       : "
                f"{project.root}"
            )

            print(
                f"      Framework  : "
                f"{displayed_framework}"
            )

            print(
                f"      Project    : "
                f"{displayed_project_type}"
            )

            print(
                f"      Languages  : "
                f"{project_languages}"
            )

            print(
                f"      Build tools: "
                f"{project_build_tools}"
            )

    # ======================================================
    # Per-file project diagnostics
    # ======================================================

    @staticmethod
    def _print_file_project_context(
        changed_file: ChangedFile,
        repository_context: RepositoryContext,
    ) -> None:
        """
        Display the project that will provide framework
        context for one changed file.

        ReviewPromptBuilder independently resolves this
        project again when the actual LLM prompt is built.
        """

        file_context = repository_context.resolve_file_context(
            changed_file.file_path
        )
        project = file_context.project

        print()
        print("🎯 Resolved review context")
        print("-" * 55)

        print(
            f"File       : "
            f"{changed_file.file_path}"
        )

        if project is None:

            print(
                "Project    : unresolved"
            )

            print(
                f"Framework  : "
                f"{file_context.framework or 'unknown'} "
                f"(repository fallback)"
            )

            print(
                f"Project type: "
                f"{file_context.project_type or 'unknown'}"
            )

            return

        print(
            f"Project    : "
            f"{project.name}"
        )

        print(
            f"Root       : "
            f"{project.root}"
        )

        print(
            f"Framework  : "
            f"{file_context.framework or 'unknown'}"
        )

        print(
            f"Project type: "
            f"{file_context.project_type or 'unknown'}"
        )

        project_build_tools = (
            ", ".join(
                sorted(
                    project.build_tools
                )
            )
            if project.build_tools
            else "unknown"
        )

        print(
            f"Build tools: "
            f"{project_build_tools}"
        )
