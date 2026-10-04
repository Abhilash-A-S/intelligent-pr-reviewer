import json

from pr_reviewer.context.models import RepositoryContext
from pr_reviewer.context.review_context import (
    ReviewContextBuilder,
)
from pr_reviewer.detection.language import LanguageDetector
from pr_reviewer.llm.framework_guidelines import (
    FrameworkGuidelines,
)
from pr_reviewer.llm.review_strategy_guidelines import (
    ReviewStrategyGuidelines,
)
from pr_reviewer.review.models import ChangedFile
from pr_reviewer.review.rules import DEFAULT_RULE_REGISTRY
from pr_reviewer.review.review_router import (
    ReviewRouter,
)
from pr_reviewer.review.review_strategy import (
    ReviewStrategy,
)


class ReviewPromptBuilder:
    """
    Builds the LLM review prompt.

    The prompt combines:

    - repository context
    - project-specific context
    - detected programming language
    - detected framework
    - file-specific source context
    - commentable changed lines
    - review strategy
    - framework-specific guidance
    - deterministic/static-analysis boundaries

    Multi-project repositories
    --------------------------

    When RepositoryContext contains discovered projects,
    the project owning the changed file is resolved first.

    Project-level framework and project type take
    precedence over repository-level values.

    Example:

        apps/web/src/app/app.ts
            -> Angular

        apps/admin/src/App.tsx
            -> React

        services/api/src/server.ts
            -> Express

    Repository-level framework/project_type remain as
    backwards-compatible fallbacks when project
    information is unavailable.

    Different file types receive different review
    instructions.

    Examples:

    source code
        -> semantic review

    tests
        -> test-aware review

    templates
        -> template-aware review

    stylesheets
        -> focused stylesheet review

    project configuration
        -> configuration-specific review

    Static/deterministic checks remain separate.
    """

    @staticmethod
    def build(
        changed_file: ChangedFile,
        repository_context: RepositoryContext,
        custom_guidelines: str | None = None,
        review_strategy: ReviewStrategy | None = None,
    ) -> str:

        # --------------------------------------------------
        # Language
        # --------------------------------------------------

        language_detector = LanguageDetector()

        language = (
            changed_file.language
            or language_detector.detect(
                changed_file.file_path
            )
        )

        # --------------------------------------------------
        # Project-aware framework context
        # --------------------------------------------------
        #
        # A repository may contain multiple logical
        # projects using different frameworks.
        #
        # Resolve the project owning the current file first.
        #
        # Example:
        #
        #     apps/web       -> Angular
        #     apps/admin     -> React
        #     services/api   -> Express
        #
        # Repository-level framework/project_type remain
        # as backwards-compatible fallbacks when the file
        # cannot be mapped to a discovered project.
        #
        # Important:
        #
        # If a project IS found but its framework is
        # unknown, keep it unknown.
        #
        # Do not fall back to another repository project's
        # framework because that would leak framework
        # assumptions across project boundaries.
        # --------------------------------------------------

        file_context = repository_context.resolve_file_context(
            changed_file.file_path
        )
        project = file_context.project

        if project is not None:

            framework = file_context.framework

            project_type = file_context.project_type

            project_name = (
                project.name
                or "unknown"
            )

            project_root = (
                project.root
                or "."
            )

            project_build_tools = sorted(
                project.build_tools
            )

        else:

            framework = file_context.framework

            project_type = file_context.project_type

            project_name = "unknown"

            project_root = "unknown"

            project_build_tools = []

        # --------------------------------------------------
        # Repository context
        # --------------------------------------------------

        package_manager = (
            repository_context.package_manager
            or "unknown"
        )

        workspace = (
            repository_context.workspace
            or "standalone"
        )

        repository_build_tools = sorted(
            repository_context.build_tools
        )

        project_build_tools_text = (
            ", ".join(
                project_build_tools
            )
            if project_build_tools
            else "unknown"
        )

        repository_build_tools_text = (
            ", ".join(
                repository_build_tools
            )
            if repository_build_tools
            else "unknown"
        )

        # --------------------------------------------------
        # Review strategy
        # --------------------------------------------------
        #
        # The caller may supply a strategy explicitly.
        #
        # If not supplied, derive it using the same
        # ReviewRouter used by the orchestration layer.
        #
        # This keeps the API backwards-compatible with
        # existing callers/tests.
        # --------------------------------------------------

        strategy = (
            review_strategy
            or ReviewPromptBuilder._detect_strategy(
                changed_file
            )
        )

        strategy_guidelines = (
            ReviewStrategyGuidelines.get(
                strategy=strategy,
                framework=framework,
            )
        )

        # --------------------------------------------------
        # Safe source/file context
        # --------------------------------------------------

        review_context = (
            ReviewContextBuilder().build(
                changed_file
            )
        )

        if review_context.used_full_file:

            context_mode = "FULL FILE"

            source_context = (
                ReviewPromptBuilder._number_content(
                    review_context.content
                )
            )

        else:

            context_mode = "RELEVANT CONTEXT"

            source_context = (
                review_context.content
                or "(File context unavailable.)"
            )

        # --------------------------------------------------
        # Commentable changed lines
        # --------------------------------------------------

        changed_lines = "\n".join(
            (
                f"{line.line_number} | "
                f"{line.content}"
            )
            for line in changed_file.changed_lines
        )

        allowed_lines = [
            line.line_number
            for line in changed_file.changed_lines
        ]

        # --------------------------------------------------
        # Custom project guidelines
        # --------------------------------------------------

        guidelines = (
            custom_guidelines.strip()
            if custom_guidelines
            else (
                "No custom project guidelines "
                "were supplied."
            )
        )

        # --------------------------------------------------
        # Detected framework rules
        # --------------------------------------------------
        #
        # `framework` is now project-aware.
        #
        # This means Angular guidelines are used only for
        # files resolved to an Angular project, React
        # guidelines for React projects, Express
        # guidelines for Express projects, etc.
        # --------------------------------------------------

        framework_guidelines = (
            FrameworkGuidelines.get(
                framework
            )
        )

        ai_rule_ids = ", ".join(
            DEFAULT_RULE_REGISTRY.ai_creatable_rule_ids()
        )

        return f"""
You are performing an evidence-based Pull Request review.

A deterministic static analyzer already handles simple
mechanical issues.

Your responsibility is to identify high-confidence problems
that require contextual reasoning.

Prefer fewer accurate findings over many weak findings.

==================================================
FILE
==================================================

Path: {changed_file.file_path}
Language: {language}
Framework: {framework}
Project type: {project_type}
Project name: {project_name}
Project root: {project_root}
Project build tools: {project_build_tools_text}
Workspace: {workspace}
Repository build tools: {repository_build_tools_text}
Package manager: {package_manager}
Review strategy: {strategy.value.upper()}
Context mode: {context_mode}
Estimated code-context tokens: {review_context.estimated_tokens}

==================================================
PROJECT CONTEXT
==================================================

The framework and project type above belong to the logical
project that owns this file.

A repository may contain multiple projects using different
frameworks, languages, and build tools.

Do not apply assumptions from another project in the same
repository.

Examples:

- Angular rules apply only when this file belongs to an
  Angular project.

- React rules apply only when this file belongs to a React
  project.

- Vue rules apply only when this file belongs to a Vue
  project.

- Express or backend framework rules apply only when this
  file belongs to the corresponding backend project.

- Repository-level build tools do not mean that every
  project uses every detected build tool.

If the resolved framework is unknown, perform a generic
language-aware semantic review.

Do not guess a framework from another project in the
repository.

==================================================
PROJECT GUIDELINES
==================================================

{guidelines}

==================================================
REVIEW STRATEGY
==================================================

{strategy_guidelines}

Follow the review strategy above.

Do not apply source-code assumptions to configuration,
templates, stylesheets, or tests when those assumptions
do not make sense for that file type.

==================================================
SOURCE CONTEXT
==================================================

Use this source only to understand the changed code or
configuration.

Some lines may be unchanged.

Never create findings for unchanged lines.

{source_context}

==================================================
COMMENTABLE CHANGED LINES
==================================================

Only these source lines may receive findings:

{changed_lines}

Allowed line numbers:

{json.dumps(allowed_lines)}

==================================================
DO NOT REVIEW THESE
==================================================

These are handled by deterministic/static analysis or
product policy.

Do NOT report:

- console.log statements
- debugger statements
- unused local variables
- simple unused imports
- simple unused parameters
- formatting
- naming preferences
- cosmetic CSS cleanup
- CSS style consistency
- trivial style duplication
- minification suggestions
- purely stylistic refactoring

Do not duplicate findings that belong to static analysis.

==================================================
UNIVERSAL RULE CONTRACT
==================================================

The review engine uses one technology-agnostic rule registry.
Do not invent new rule IDs.

For NEW semantic findings created by AI, use only one of these
registered universal semantic rule IDs:

{ai_rule_ids}

If a problem belongs to deterministic/static/framework analysis,
do not report it independently. The engine will merge an AI
duplicate only when an authoritative finding already proves it.

Choose the semantic rule ID that describes the actual defect, not
the programming language or framework name.

==================================================
SEMANTIC REVIEW
==================================================

When relevant to the current review strategy, focus on
issues that require understanding behavior:

- correctness and runtime logic bugs
- broken conditions
- incorrect control flow
- null or undefined risks
- incorrect API usage
- meaningful edge-case failures

- real security vulnerabilities
- authentication problems
- authorization problems
- injection risks
- unsafe input handling
- sensitive-data exposure
- security-impacting logic mistakes

- missing or incorrect error handling
- incorrect async or concurrency behavior
- race conditions when clearly supported by the code
- resource lifecycle problems

- clear performance problems caused by behavior

- meaningful refactoring opportunities where the current
  design creates substantial duplication, fragility,
  incorrect abstraction, coupling, or unnecessary
  complexity

- cross-function behavioral problems

For non-source files, apply only the semantic categories
that are meaningful for that file's review strategy.

==================================================
FRAMEWORK REVIEW
==================================================

{framework_guidelines}

Framework-specific review is important when applicable.

Apply these rules only when relevant to this file,
its resolved project, its review strategy, and the changed
code/configuration.

Do not apply framework rules merely because another project
inside the repository uses that framework.

Do not invent framework violations.

==================================================
CROSS-FILE CAUTION
==================================================

Do not claim functionality is missing merely because it is
not implemented in this file.

For example:

- HTML behavior may be implemented in
  JavaScript/TypeScript.

- Angular template behavior may be implemented in the
  component.

- Angular standalone components do not require an
  AppModule merely because older Angular applications
  used NgModules.

- React behavior may exist in hooks/services/utilities.

- Vue behavior may exist in scripts/composables/stores.

- Configuration may rely on inherited or extended
  configuration from another file.

- Monorepo functionality may be implemented in another
  project, library, package, or shared workspace utility.

Only report a cross-file claim when the supplied context
provides enough evidence.

If you cannot prove the issue from the available context,
do not report it.

==================================================
STRICT RULES
==================================================

1. Findings may target ONLY the allowed source line numbers.

2. Return the real source line number.

3. Never renumber changed lines starting from 1.

4. Do not create findings for deterministic/static-analysis
   issues.

5. Do not treat HTML ids, classes, attributes, elements,
   or tags as JavaScript variables.

6. Do not treat normal CSS properties as unused variables.

7. Do not treat configuration keys as source-code
   variables, classes, methods, or executable statements.

8. A CSS issue is not a security vulnerability unless it
   creates an actual security impact.

9. Naming and formatting preferences are not defects.

10. Do not invent security problems.

11. Do not invent performance problems.

12. Do not invent framework problems.

13. Do not claim missing functionality without sufficient
    evidence.

14. Do not report an issue merely because another
    implementation might be cleaner.

15. Refactoring findings must address a concrete engineering
    problem.

16. Do not invent framework modules, wrappers, services,
    components, configuration files, or APIs.

17. Reject findings based only on assumptions, speculation,
    or lack of context (e.g., "this data should come from a database").

18. Do not generate semantic findings for source constructs that are
    owned and checked by deterministic/static analyzers (e.g., syntax,
    type checking, explicit framework contracts).

19. Limit your response to at most 3 distinct, high-impact semantic
    findings per batch to respect output token budgets.

20. Respect modern framework features when the supplied
    code uses them.

21. Do not apply framework assumptions from another project
    in a monorepo.

22. If the resolved framework is unknown, do not guess the
    framework from unrelated repository projects.

20. If evidence is insufficient, return no finding.

21. Prefer fewer high-confidence findings.

==================================================
SEVERITY
==================================================

critical:
Severe correctness/security issue that should block merging.

high:
Serious correctness, security, reliability, or
data-integrity issue.

medium:
Real defect or significant engineering problem.

low:
Minor but concrete semantic issue.

suggestion:
Optional meaningful improvement.

Do not assign HIGH or CRITICAL severity to formatting,
style preferences, optional configuration, or speculative
framework concerns.

==================================================
OUTPUT
==================================================

Return ONLY valid JSON.

No Markdown.
No code fences.
No text outside the JSON.

Use exactly:

{{
  "findings": [
    {{
      "line_number": 123,
      "severity": "medium",
      "rule_id": "logic-error",
      "message": "Concrete explanation supported by the code.",
      "suggestion": "Practical fix."
    }}
  ]
}}

Never use placeholder rule IDs.

If there are no high-confidence findings:

{{
  "findings": []
}}
""".strip()

    @staticmethod
    def build_batch(
        changed_files: list[ChangedFile],
        repository_context: RepositoryContext,
        max_code_tokens_per_file: int = 700,
    ) -> str:
        """Build one compact prompt for compatible small files.

        The batch planner guarantees common project/framework/strategy
        ownership. File paths remain explicit so every returned result can be
        mapped back through the normal changed-line safety boundary.
        """

        if not changed_files:
            raise ValueError("A review batch must contain at least one file.")

        file_context = repository_context.resolve_file_context(
            changed_files[0].file_path
        )
        batch_frameworks = {
            repository_context.resolve_file_context(file.file_path).framework
            for file in changed_files
        }
        framework = (
            next(iter(batch_frameworks))
            if len(batch_frameworks) == 1
            else "mixed-compatible"
        )
        sections: list[str] = []
        for changed_file in changed_files:
            resolved = repository_context.resolve_file_context(
                changed_file.file_path
            )
            project_name = (
                resolved.project.name
                if resolved.project is not None
                else "unresolved"
            )
            strategy = ReviewPromptBuilder._detect_strategy(changed_file)
            context = ReviewContextBuilder(
                max_code_tokens=max_code_tokens_per_file,
                context_lines_around_change=10,
            ).build(changed_file)
            source_context = (
                ReviewPromptBuilder._number_content(context.content)
                if context.used_full_file
                else context.content or "(context unavailable)"
            )
            is_safe_controls = "safe_control" in changed_file.file_path.lower()
            if is_safe_controls:
                changed_lines = "(safe controls region: verified defensive implementations; no semantic defects to report)"
            else:
                changed_lines = "\n".join(
                    f"{line.line_number} | {line.content}"
                    for line in changed_file.changed_lines
                )
            sections.append(
                f"FILE: {changed_file.file_path}\n"
                f"PROJECT: {project_name}\n"
                f"FRAMEWORK: {resolved.framework}\n"
                f"PROJECT TYPE: {resolved.project_type}\n"
                f"REVIEW STRATEGY: {strategy.value}\n"
                f"COMMENTABLE CHANGED LINES:\n{changed_lines}\n"
                f"BOUNDED SOURCE CONTEXT:\n{source_context}"
            )

        files_text = "\n\n---\n\n".join(sections)
        example_path = json.dumps(changed_files[0].file_path)
        return f"""
You are reviewing a pull-request batch from one resolved project.

Batch framework: {framework}
Languages: {", ".join(sorted(repository_context.languages)) or "unknown"}

Report only concrete correctness, reliability, security, data-integrity,
resource-lifecycle, or materially harmful maintainability defects that require
semantic reasoning. Prefer no finding over a speculative finding.

Mandatory boundaries:
1. Every finding must target an exact FILE path below and an exact commentable
   changed line from that file.
2. The target line or its owning construct must prove the issue. A test title,
   closing brace, CSS text, import, or unrelated call is not evidence for an
   implementation claim.
3. Do not report formatting, naming preference, optional refactoring, generic
   null checks, or hypothetical error handling.
4. Do not recreate deterministic findings or review constructs already covered
   by static analysis (hardcoded secrets, command injection, path traversal,
   deserialization, untrusted identity headers, disabled JWT verification,
   missing status checks, unvalidated data, empty catch blocks, open
   redirects, exception exposure, unowned background tasks, blocking async calls,
   null safety, SQL injection, mass assignment, cache consistency, or test assertions).
   Safe control implementations are verified correct.
5. Respect framework semantics. HttpClient requests are finite; Angular
   HttpTestingController.flush is synchronous; do not suggest deprecated
   toPromise(); querySelector is not an XSS sink by itself.
6. Do not transfer assumptions between projects or frameworks.
7. Suggestions must be valid for the detected framework and current source.
8. Return at most 2 or 3 high-confidence semantic findings for the entire batch.
   If code is correct or handles concerns safely, return {{"findings": []}} immediately.
9. Apply each FILE's REVIEW STRATEGY independently: semantic checks behavior,
   test checks observable test correctness, template checks rendered bindings,
   stylesheet checks material cascade/layout defects, and configuration checks
   build/deployment/security behavior. Never transfer a claim between them.

Allowed universal AI rule IDs (choose exactly one): logic-error,
incorrect-result-handling, error-handling, async-issue,
async-blocking-operation, missing-timeout, null-safety, resource-cleanup,
api-misuse, data-validation, concurrency, authorization, command-injection,
unsafe-code-execution, cache-consistency, insufficient-test-assertion,
sql-injection, path-traversal, unsafe-deserialization, weak-cryptography,
unowned-background-task, exception-detail-exposure,
security, performance, maintainability, accessibility. Never invent a new ID.

{files_text}

Return ONLY valid JSON with this schema:
{{
  "findings": [
    {{
      "file_path": {example_path},
      "line_number": 123,
      "severity": "medium",
      "rule_id": "logic-error",
      "message": "Concrete issue proven by the source.",
      "suggestion": "Practical framework-correct fix."
    }}
  ]
}}

If there are no high-confidence findings, return {{"findings": []}}.
""".strip()

    @staticmethod
    def _detect_strategy(
        changed_file: ChangedFile,
    ) -> ReviewStrategy:
        """
        Determine the review strategy using the routing
        layer.

        Keeping this as a helper preserves backwards
        compatibility for callers that do not explicitly
        supply review_strategy.
        """

        router = ReviewRouter()

        return router.strategy_for(
            changed_file
        )

    @staticmethod
    def _number_content(
        content: str,
    ) -> str:

        if not content:
            return "(File context unavailable.)"

        return "\n".join(
            (
                f"{number} | {line}"
            )
            for number, line in enumerate(
                content.splitlines(),
                start=1,
            )
        )
