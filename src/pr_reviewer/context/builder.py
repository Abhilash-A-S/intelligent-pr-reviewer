from pr_reviewer.context.file_context import FileContextResolver
from pr_reviewer.context.models import RepositoryContext
from pr_reviewer.detection.build_tool import (
    BuildToolDetector,
)
from pr_reviewer.detection.framework import (
    FrameworkDetector,
)
from pr_reviewer.detection.language import (
    LanguageDetector,
)
from pr_reviewer.detection.project import (
    ProjectDetector,
)
from pr_reviewer.detection.workspace import (
    WorkspaceDetector,
)
from pr_reviewer.review.models import ChangedFile


class RepositoryContextBuilder:
    """
    Builds repository-level context used by the review
    pipeline.

    Context includes:

    - detected programming languages
    - primary repository framework
    - repository project type
    - package manager
    - metadata/configuration files
    - workspace type
    - workspace evidence
    - detected build tools
    - build-tool evidence
    - discovered logical projects

    Repository-level framework and project_type are
    retained for backward compatibility.

    Project-level context enables multi-framework
    repositories.

    Example Nx repository:

        apps/web
            Angular

        apps/admin
            React + Vite

        services/api
            Express

    Each project can now carry its own framework instead
    of forcing one repository framework onto every file.
    """

    def __init__(
        self,
        language_detector: LanguageDetector | None = None,
        framework_detector: FrameworkDetector | None = None,
        workspace_detector: WorkspaceDetector | None = None,
        build_tool_detector: BuildToolDetector | None = None,
        project_detector: ProjectDetector | None = None,
    ):
        self.language_detector = (
            language_detector
            or LanguageDetector()
        )

        self.framework_detector = (
            framework_detector
            or FrameworkDetector()
        )

        self.workspace_detector = (
            workspace_detector
            or WorkspaceDetector()
        )

        self.build_tool_detector = (
            build_tool_detector
            or BuildToolDetector()
        )

        self.project_detector = (
            project_detector
            or ProjectDetector(
                workspace_detector=(
                    self.workspace_detector
                ),
                language_detector=(
                    self.language_detector
                ),
                framework_detector=(
                    self.framework_detector
                ),
                build_tool_detector=(
                    self.build_tool_detector
                ),
            )
        )

    def build(
        self,
        changed_files: list[ChangedFile],
        repository_files: list[ChangedFile] | None = None,
    ) -> RepositoryContext:

        # Unchanged repository files are context-only evidence. They improve
        # workspace/project/framework discovery but are never analyzed for
        # findings because only changed_files flow into analyzers.
        detection_files = list(changed_files)
        seen_paths = {file.file_path.replace("\\", "/") for file in detection_files}
        for repository_file in repository_files or []:
            normalized = repository_file.file_path.replace("\\", "/")
            if normalized not in seen_paths:
                detection_files.append(repository_file)
                seen_paths.add(normalized)

        file_paths = [file.file_path for file in detection_files]

        # --------------------------------------------------
        # Languages
        # --------------------------------------------------

        languages: set[str] = set()

        for changed_file in detection_files:

            language = (
                changed_file.language
                or self.language_detector.detect(
                    changed_file.file_path
                )
            )

            if language != "unknown":
                languages.add(
                    language
                )

        # --------------------------------------------------
        # Repository-level framework / project type
        # --------------------------------------------------
        #
        # This remains for backward compatibility.
        #
        # The next review-pipeline phase will resolve the
        # owning ProjectContext for each changed file and
        # prefer that project's framework.
        # --------------------------------------------------

        repository_project_context = (
            self.framework_detector.detect(
                detection_files
            )
        )

        # --------------------------------------------------
        # Repository metadata
        # --------------------------------------------------

        metadata_files = (
            self._detect_metadata_files(
                file_paths
            )
        )

        # --------------------------------------------------
        # Workspace detection
        # --------------------------------------------------

        workspace_result = (
            self.workspace_detector.detect(
                file_paths,
                allow_nested=bool(repository_files),
            )
        )

        # --------------------------------------------------
        # Build-tool detection
        # --------------------------------------------------

        build_tool_result = (
            self.build_tool_detector.detect(
                file_paths
            )
        )

        build_tools = {
            build_tool.value
            for build_tool
            in build_tool_result.build_tools
        }

        build_tool_evidence = {
            build_tool.value: list(
                evidence
            )
            for build_tool, evidence
            in build_tool_result.evidence.items()
        }

        # --------------------------------------------------
        # Project discovery
        # --------------------------------------------------
        #
        # ProjectDetector independently groups changed
        # files into logical projects and runs framework,
        # language and build-tool detection for each one.
        # --------------------------------------------------

        project_detection = (
            self.project_detector.detect(
                detection_files,
                allow_nested_workspace=bool(repository_files),
            )
        )

        projects = list(
            project_detection.projects
        )

        effective_framework = repository_project_context.framework
        effective_project_type = repository_project_context.project_type
        if workspace_result.workspace_type.value == "nx":
            recognized_frameworks = {
                project.framework
                for project in projects
                if project.framework not in {"unknown", "playwright", "cypress"}
            }
            if len(recognized_frameworks) > 1:
                effective_framework = "mixed"
                effective_project_type = "monorepo"
            elif len(recognized_frameworks) == 1:
                effective_framework = next(iter(recognized_frameworks))

        # --------------------------------------------------
        # Package manager
        # --------------------------------------------------

        package_manager = (
            self._detect_package_manager(
                file_paths
            )
        )

        # --------------------------------------------------
        # Repository context
        # --------------------------------------------------

        repository_context = RepositoryContext(
            languages=languages,
            framework=effective_framework,
            project_type=effective_project_type,
            package_manager=package_manager,
            metadata_files=metadata_files,
            workspace=(
                workspace_result
                .workspace_type
                .value
            ),
            workspace_evidence=list(
                workspace_result.evidence
            ),
            build_tools=build_tools,
            build_tool_evidence=(
                build_tool_evidence
            ),
            projects=projects,
        )
        repository_context.file_contexts = FileContextResolver(
            self.framework_detector
        ).resolve_all(
            changed_files=detection_files,
            repository_context=repository_context,
        )
        resolved_frameworks = {
            context.framework
            for context in repository_context.file_contexts.values()
            if context.framework not in {"", "unknown"}
        }
        python_backend_frameworks = {"python", "django", "flask", "fastapi"}
        if len(resolved_frameworks) > 1 and resolved_frameworks <= python_backend_frameworks:
            repository_context.framework = "mixed"
            repository_context.project_type = "backend"
        elif len(resolved_frameworks) > 1:
            repository_context.framework = "mixed"
            if repository_context.project_type != "monorepo":
                repository_context.project_type = "mixed"
        return repository_context

    # ======================================================
    # Metadata detection
    # ======================================================

    @staticmethod
    def _detect_metadata_files(
        file_paths: list[str],
    ) -> list[str]:

        known_metadata = {
            # --------------------------------------------------
            # JavaScript / TypeScript
            # --------------------------------------------------

            "package.json",

            # Framework / workspace
            "angular.json",
            "nx.json",
            "project.json",

            # TypeScript
            "tsconfig.json",
            "tsconfig.base.json",

            # --------------------------------------------------
            # Build tools
            # --------------------------------------------------

            "vite.config.js",
            "vite.config.mjs",
            "vite.config.cjs",
            "vite.config.ts",
            "vite.config.mts",
            "vite.config.cts",

            "webpack.config.js",
            "webpack.config.cjs",
            "webpack.config.mjs",
            "webpack.config.ts",

            "rollup.config.js",
            "rollup.config.mjs",
            "rollup.config.cjs",
            "rollup.config.ts",

            "esbuild.config.js",
            "esbuild.config.mjs",
            "esbuild.config.cjs",
            "esbuild.config.ts",

            # --------------------------------------------------
            # Python
            # --------------------------------------------------

            "pyproject.toml",
            "requirements.txt",

            # --------------------------------------------------
            # Java / JVM
            # --------------------------------------------------

            "pom.xml",
            "build.gradle",
            "build.gradle.kts",

            # --------------------------------------------------
            # Rust
            # --------------------------------------------------

            "cargo.toml",

            # --------------------------------------------------
            # Go
            # --------------------------------------------------

            "go.mod",

            # --------------------------------------------------
            # PHP
            # --------------------------------------------------

            "composer.json",

            # --------------------------------------------------
            # Ruby
            # --------------------------------------------------

            "gemfile",

            # --------------------------------------------------
            # Docker / deployment
            # --------------------------------------------------

            "dockerfile",
            "docker-compose.yml",
            "docker-compose.yaml",

            # --------------------------------------------------
            # Generic environment/config
            # --------------------------------------------------

            ".env.example",
        }

        metadata_files: list[str] = []

        for file_path in file_paths:

            normalized = (
                file_path
                .lower()
                .replace(
                    "\\",
                    "/",
                )
            )

            file_name = (
                normalized
                .split("/")[-1]
            )

            if (
                file_name in known_metadata
                or file_name.endswith(
                    ".csproj"
                )
                or file_name.endswith(
                    ".fsproj"
                )
                or file_name.endswith(
                    ".vbproj"
                )
            ):
                metadata_files.append(
                    file_path
                )

        return metadata_files

    # ======================================================
    # Package-manager detection
    # ======================================================

    @staticmethod
    def _detect_package_manager(
        file_paths: list[str],
    ) -> str | None:

        normalized = {
            path
            .lower()
            .replace(
                "\\",
                "/",
            )
            for path in file_paths
        }

        file_names = {
            path.split("/")[-1]
            for path in normalized
        }

        # --------------------------------------------------
        # JavaScript / TypeScript
        # --------------------------------------------------

        if "pnpm-lock.yaml" in file_names:
            return "pnpm"

        if "yarn.lock" in file_names:
            return "yarn"

        if "package-lock.json" in file_names:
            return "npm"

        if "bun.lock" in file_names:
            return "bun"

        if "bun.lockb" in file_names:
            return "bun"

        # --------------------------------------------------
        # Python
        # --------------------------------------------------

        if "uv.lock" in file_names:
            return "uv"

        if "poetry.lock" in file_names:
            return "poetry"

        if "requirements.txt" in file_names:
            return "pip"

        # --------------------------------------------------
        # Java / JVM
        # --------------------------------------------------

        if "pom.xml" in file_names:
            return "maven"

        if (
            "build.gradle" in file_names
            or "build.gradle.kts"
            in file_names
        ):
            return "gradle"

        # --------------------------------------------------
        # Rust
        # --------------------------------------------------

        if "cargo.toml" in file_names:
            return "cargo"

        # --------------------------------------------------
        # Go
        # --------------------------------------------------

        if "go.mod" in file_names:
            return "go-modules"

        # --------------------------------------------------
        # PHP
        # --------------------------------------------------

        if "composer.json" in file_names:
            return "composer"

        # --------------------------------------------------
        # Ruby
        # --------------------------------------------------

        if "gemfile" in file_names:
            return "bundler"

        # --------------------------------------------------
        # .NET
        # --------------------------------------------------

        if any(
            file_name.endswith(
                (
                    ".csproj",
                    ".fsproj",
                    ".vbproj",
                )
            )
            for file_name in file_names
        ):
            return "dotnet"

        return None
