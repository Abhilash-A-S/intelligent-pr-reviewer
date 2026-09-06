from dataclasses import dataclass, field
from pathlib import PurePosixPath

from pr_reviewer.detection.build_tool import (
    BuildToolDetector,
)
from pr_reviewer.detection.framework import (
    FrameworkDetector,
)
from pr_reviewer.detection.language import (
    LanguageDetector,
)
from pr_reviewer.detection.workspace import (
    WorkspaceDetector,
    WorkspaceType,
)
from pr_reviewer.review.models import (
    ChangedFile,
)


@dataclass(frozen=True)
class ProjectContext:
    """
    Represents one logical project inside a repository.

    Examples:

    Standalone repository
        root = "."
        name = "root"

    Nx workspace
        root = "apps/web"
        name = "web"

        root = "apps/api"
        name = "api"

        root = "libs/shared"
        name = "shared"

    Project-level context is intentionally separate from
    repository-level context.

    This allows a single repository to contain:

        Angular
        React
        Express
        NestJS
        Spring Boot
        unknown/custom projects

    without forcing one framework onto every changed file.
    """

    name: str

    root: str

    languages: frozenset[str] = field(
        default_factory=frozenset
    )

    framework: str = "unknown"

    project_type: str = "unknown"

    build_tools: frozenset[str] = field(
        default_factory=frozenset
    )

    evidence: tuple[str, ...] = field(
        default_factory=tuple
    )


@dataclass(frozen=True)
class ProjectDetectionResult:
    """
    Result returned by ProjectDetector.

    projects:
        Logical projects discovered in the repository.

    workspace:
        Workspace architecture used while discovering
        projects.
    """

    projects: tuple[ProjectContext, ...]

    workspace: WorkspaceType


class ProjectDetector:
    """
    Discovers logical projects inside a repository.

    The detector is intentionally framework-independent.

    Responsibilities:

    1. Determine whether the repository is Nx or
       standalone.

    2. Discover project roots.

    3. Group ChangedFile objects by project.

    4. Run existing language/framework/build-tool
       detection independently for each project.

    Current discovery strategy
    --------------------------

    Nx:

        Strongest evidence:
            <project-root>/project.json

        Fallback convention:
            apps/<project>
            libs/<project>
            packages/<project>
            services/<project>

    Standalone:

        The complete repository is represented as one
        project rooted at ".".

    Important:

    Unknown frameworks remain valid projects.

    Project discovery must never prevent generic LLM
    review simply because a framework is not recognized.
    """

    COMMON_MULTI_PROJECT_ROOTS = {
        "apps",
        "libs",
        "packages",
        "services",
    }

    PROJECT_CONFIG_FILE = "project.json"

    def __init__(
        self,
        workspace_detector: WorkspaceDetector | None = None,
        language_detector: LanguageDetector | None = None,
        framework_detector: FrameworkDetector | None = None,
        build_tool_detector: BuildToolDetector | None = None,
    ):
        self.workspace_detector = (
            workspace_detector
            or WorkspaceDetector()
        )

        self.language_detector = (
            language_detector
            or LanguageDetector()
        )

        self.framework_detector = (
            framework_detector
            or FrameworkDetector()
        )

        self.build_tool_detector = (
            build_tool_detector
            or BuildToolDetector()
        )

    def detect(
        self,
        changed_files: list[ChangedFile],
        allow_nested_workspace: bool = False,
    ) -> ProjectDetectionResult:
        """
        Discover repository projects and build project-level
        context for each one.
        """

        file_paths = [
            changed_file.file_path
            for changed_file in changed_files
        ]

        workspace_result = (
            self.workspace_detector.detect(
                file_paths,
                allow_nested=allow_nested_workspace,
            )
        )

        if (
            workspace_result.workspace_type
            == WorkspaceType.NX
        ):
            projects = self._detect_nx_projects(
                changed_files
            )

        else:
            projects = (
                self._build_project_context(
                    name="root",
                    root=".",
                    changed_files=changed_files,
                    evidence=(),
                ),
            )

        return ProjectDetectionResult(
            projects=projects,
            workspace=(
                workspace_result.workspace_type
            ),
        )

    def find_project_for_file(
        self,
        file_path: str,
        projects: tuple[ProjectContext, ...]
        | list[ProjectContext],
    ) -> ProjectContext | None:
        """
        Resolve the project that owns a file.

        The deepest matching project root wins.

        This matters when roots are nested.

        Example:

            apps/web
            apps/web-e2e

        or future nested project structures.
        """

        normalized_file = (
            self._normalize_path(
                file_path
            )
        )

        matching_projects: list[
            ProjectContext
        ] = []

        for project in projects:

            if self._file_belongs_to_root(
                normalized_file,
                project.root,
            ):
                matching_projects.append(
                    project
                )

        if not matching_projects:
            return None

        return max(
            matching_projects,
            key=lambda project: len(
                self._normalize_path(
                    project.root
                )
            ),
        )

    # ======================================================
    # Nx discovery
    # ======================================================

    def _detect_nx_projects(
        self,
        changed_files: list[ChangedFile],
    ) -> tuple[ProjectContext, ...]:

        explicit_roots = (
            self._detect_project_json_roots(
                changed_files
            )
        )
        package_roots = self._detect_package_project_roots(changed_files)

        inferred_roots = (
            self._detect_conventional_roots(
                changed_files
            )
        )

        # Explicit Nx project.json roots are authoritative. Conventional
        # directory inference is only a fallback and must never create
        # synthetic container projects such as packages/shop when concrete
        # projects exist below it (packages/shop/feature-products, etc.).
        authoritative_roots = {
            *explicit_roots,
            *package_roots,
        }

        filtered_inferred_roots = {
            root
            for root in inferred_roots
            if not any(
                self._roots_overlap(root, authoritative_root)
                for authoritative_root in authoritative_roots
            )
        }

        project_roots = {
            *authoritative_roots,
            *filtered_inferred_roots,
        }

        if not project_roots:
            # An Nx workspace can legitimately have changes
            # only in root-level configuration.
            #
            # Preserve those files through a root project
            # rather than returning no project.
            return (
                self._build_project_context(
                    name="root",
                    root=".",
                    changed_files=changed_files,
                    evidence=("nx.json",),
                ),
            )

        projects: list[
            ProjectContext
        ] = []

        assigned_file_paths: set[str] = set()

        for root in sorted(
            project_roots
        ):

            project_files = [
                changed_file
                for changed_file in changed_files
                if self._file_belongs_to_root(
                    changed_file.file_path,
                    root,
                )
            ]

            if not project_files:
                continue

            for changed_file in project_files:
                assigned_file_paths.add(
                    self._normalize_path(
                        changed_file.file_path
                    )
                )

            evidence = self._project_evidence(
                root=root,
                changed_files=project_files,
            )

            projects.append(
                self._build_project_context(
                    name=self._project_name(
                        root
                    ),
                    root=root,
                    changed_files=project_files,
                    evidence=evidence,
                )
            )

        # --------------------------------------------------
        # Nx root-level files
        # --------------------------------------------------
        #
        # Files such as:
        #
        # nx.json
        # package.json
        # tsconfig.base.json
        #
        # do not belong to a specific app/lib.
        #
        # Represent them with a root workspace project.
        # --------------------------------------------------

        root_files = [
            changed_file
            for changed_file in changed_files
            if (
                self._normalize_path(
                    changed_file.file_path
                )
                not in assigned_file_paths
            )
        ]

        # Once explicit/package Nx projects are available, repository-level
        # configuration remains repository context rather than a synthetic
        # Nx project. This keeps the project list aligned with Nx itself.
        # For convention-only workspaces we preserve the historical root
        # project fallback so root configuration still has an owner.
        if root_files and not authoritative_roots:
            projects.insert(
                0,
                self._build_project_context(
                    name="root",
                    root=".",
                    changed_files=root_files,
                    evidence=("nx.json",),
                ),
            )

        return tuple(
            projects
        )

    def _detect_project_json_roots(
        self,
        changed_files: list[ChangedFile],
    ) -> set[str]:
        """
        Discover explicit Nx project roots from
        project.json paths.

        Example:

            apps/web/project.json
                -> apps/web

            libs/shared/project.json
                -> libs/shared
        """

        roots: set[str] = set()

        for changed_file in changed_files:

            normalized = (
                self._normalize_path(
                    changed_file.file_path
                )
            )

            path = PurePosixPath(
                normalized
            )

            if (
                path.name.lower()
                != self.PROJECT_CONFIG_FILE
            ):
                continue

            parent = str(
                path.parent
            )

            if parent == ".":
                continue

            roots.add(
                parent
            )

        return roots

    def _detect_package_project_roots(
        self,
        changed_files: list[ChangedFile],
    ) -> set[str]:
        """Discover package-based Nx projects from nested package.json files."""
        roots: set[str] = set()
        for changed_file in changed_files:
            normalized = self._normalize_path(changed_file.file_path)
            path = PurePosixPath(normalized)
            if path.name.lower() != "package.json" or str(path.parent) == ".":
                continue
            parts = list(path.parent.parts)
            if any(part.lower() in self.COMMON_MULTI_PROJECT_ROOTS for part in parts):
                roots.add(str(path.parent))
        return roots

    def _detect_conventional_roots(
        self,
        changed_files: list[ChangedFile],
    ) -> set[str]:
        """
        Infer common monorepo project roots.

        Examples:

            apps/web/src/main.ts
                -> apps/web

            libs/shared/src/index.ts
                -> libs/shared

            packages/ui/src/index.ts
                -> packages/ui

            services/api/src/server.ts
                -> services/api

        This is a fallback when project.json is not part
        of the current PR changes.
        """

        roots: set[str] = set()

        for changed_file in changed_files:

            normalized = (
                self._normalize_path(
                    changed_file.file_path
                )
            )

            parts = normalized.split(
                "/"
            )

            if len(parts) < 2:
                continue

            for index, part in enumerate(parts[:-1]):
                if part.lower() not in self.COMMON_MULTI_PROJECT_ROOTS:
                    continue
                if index + 1 >= len(parts):
                    continue
                project_name = parts[index + 1]
                if project_name:
                    roots.add("/".join(parts[: index + 2]))
                break

        return roots

    # ======================================================
    # Project context
    # ======================================================

    def _build_project_context(
        self,
        name: str,
        root: str,
        changed_files: list[ChangedFile],
        evidence: tuple[str, ...],
    ) -> ProjectContext:

        languages: set[str] = set()

        for changed_file in changed_files:

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

        framework_result = (
            self.framework_detector.detect(
                changed_files
            )
        )

        framework = framework_result.framework
        project_type = framework_result.project_type

        # Nx e2e projects are first-class projects even when they contain no
        # application-framework source. Keep their ownership explicit rather
        # than reporting them as an unknown application.
        normalized_name = name.lower()
        normalized_root = self._normalize_path(root).lower()
        if project_type == "unknown" and (
            normalized_name.endswith("-e2e")
            or normalized_root.endswith("-e2e")
            or "/e2e/" in f"/{normalized_root}/"
        ):
            combined = "\n".join(
                (changed_file.full_content or "")
                for changed_file in changed_files
            ).lower()
            if "playwright" in combined:
                framework = "playwright"
            elif "cypress" in combined:
                framework = "cypress"
            project_type = "e2e"

        build_tool_result = (
            self.build_tool_detector.detect(
                [
                    changed_file.file_path
                    for changed_file
                    in changed_files
                ]
            )
        )

        build_tools = frozenset(
            build_tool.value
            for build_tool
            in build_tool_result.build_tools
        )

        return ProjectContext(
            name=name,
            root=root,
            languages=frozenset(
                languages
            ),
            framework=framework,
            project_type=project_type,
            build_tools=build_tools,
            evidence=evidence,
        )

    def _project_evidence(
        self,
        root: str,
        changed_files: list[ChangedFile],
    ) -> tuple[str, ...]:

        evidence: list[str] = []

        expected_project_json = (
            f"{self._normalize_path(root)}/"
            f"{self.PROJECT_CONFIG_FILE}"
        )

        for changed_file in changed_files:

            normalized = (
                self._normalize_path(
                    changed_file.file_path
                )
            )

            if (
                normalized.lower()
                == expected_project_json.lower()
            ):
                evidence.append(
                    normalized
                )

        return tuple(
            evidence
        )

    # ======================================================
    # Helpers
    # ======================================================


    @classmethod
    def _roots_overlap(cls, left: str, right: str) -> bool:
        """Return True when roots are equal or one is a container of the other."""
        left_n = cls._normalize_path(left)
        right_n = cls._normalize_path(right)
        if left_n == right_n:
            return True
        return (
            left_n.startswith(right_n.rstrip("/") + "/")
            or right_n.startswith(left_n.rstrip("/") + "/")
        )

    @staticmethod
    def _project_name(
        root: str,
    ) -> str:

        normalized = (
            ProjectDetector._normalize_path(
                root
            )
        )

        if normalized in {
            "",
            ".",
        }:
            return "root"

        return normalized.split(
            "/"
        )[-1]

    @staticmethod
    def _normalize_path(
        file_path: str,
    ) -> str:

        normalized = (
            file_path
            .strip()
            .replace(
                "\\",
                "/",
            )
        )

        while normalized.startswith(
            "./"
        ):
            normalized = (
                normalized[2:]
            )

        normalized = (
            normalized.strip(
                "/"
            )
        )

        return normalized or "."

    @classmethod
    def _file_belongs_to_root(
        cls,
        file_path: str,
        root: str,
    ) -> bool:

        normalized_file = (
            cls._normalize_path(
                file_path
            )
        )

        normalized_root = (
            cls._normalize_path(
                root
            )
        )

        if normalized_root == ".":
            return True

        return (
            normalized_file
            == normalized_root
            or normalized_file.startswith(
                f"{normalized_root}/"
            )
        )