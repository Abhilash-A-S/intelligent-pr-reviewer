from dataclasses import dataclass, field

from pr_reviewer.detection.project import (
    ProjectContext,
)


@dataclass(frozen=True)
class ResolvedFileContext:
    project: ProjectContext | None
    framework: str
    project_type: str
    evidence: tuple[str, ...] = ()


@dataclass
class RepositoryContext:
    """
    Repository-level information discovered before
    the review begins.

    Repository concepts are intentionally kept separate.

    languages
        All programming/source languages detected from
        available repository evidence.

    framework
        Existing primary repository framework.

        This field is retained for backward compatibility.

        New multi-project review logic should gradually
        prefer project-level framework information from:

            projects

    project_type
        Existing repository-level project classification.

        Retained for backward compatibility.

    package_manager
        Detected package manager when available.

    metadata_files
        Repository metadata/configuration files discovered
        from available repository evidence.

    workspace
        Repository workspace/orchestration architecture.

        Examples:

            nx
            standalone
            unknown

    workspace_evidence
        Files supporting workspace detection.

    build_tools
        Build systems/tools detected anywhere in the
        repository.

        Multiple values are allowed because a monorepo may
        contain projects using different build systems.

    build_tool_evidence
        Mapping between build tools and files supporting
        their detection.

    projects
        Logical projects discovered inside the repository.

        Each ProjectContext can independently describe:

            root
            name
            languages
            framework
            project type
            build tools

        This is the foundation for multi-framework
        repositories.

    Important:

    Repository-level framework/project_type remain for
    backward compatibility while the review pipeline is
    migrated toward per-file project context.

    Unknown projects remain valid and can still receive
    generic semantic LLM review.
    """

    languages: set[str] = field(
        default_factory=set
    )

    framework: str = "unknown"

    project_type: str = "unknown"

    package_manager: str | None = None

    metadata_files: list[str] = field(
        default_factory=list
    )

    workspace: str = "standalone"

    workspace_evidence: list[str] = field(
        default_factory=list
    )

    build_tools: set[str] = field(
        default_factory=set
    )

    build_tool_evidence: dict[
        str,
        list[str],
    ] = field(
        default_factory=dict
    )

    projects: list[
        ProjectContext
    ] = field(
        default_factory=list
    )

    file_contexts: dict[str, ResolvedFileContext] = field(default_factory=dict)

    def resolve_file_context(self, file_path: str) -> ResolvedFileContext:
        normalized = self._normalize_path(file_path)
        resolved = self.file_contexts.get(normalized)
        if resolved is not None:
            return resolved

        project = self.find_project_for_file(normalized)
        # An explicitly owned project is authoritative even when detection did
        # not identify its framework. Falling back to a repository-wide
        # framework here leaks sibling-project semantics into root scripts and
        # mixed monorepos.
        framework = project.framework if project is not None else self.framework
        project_type = (
            project.project_type if project is not None else self.project_type
        )
        return ResolvedFileContext(
            project=project,
            framework=framework or "unknown",
            project_type=project_type or "unknown",
            evidence=("project/repository fallback",),
        )

    def find_project_for_file(
        self,
        file_path: str,
    ) -> ProjectContext | None:
        """
        Resolve the most specific project owning a file.

        The deepest matching project root wins.

        A root project (".") acts as a fallback when one
        exists.
        """

        if not self.projects:
            return None

        normalized_file = (
            self._normalize_path(
                file_path
            )
        )

        matching_projects: list[
            ProjectContext
        ] = []

        for project in self.projects:

            normalized_root = (
                self._normalize_path(
                    project.root
                )
            )

            if normalized_root == ".":
                matching_projects.append(
                    project
                )

                continue

            if (
                normalized_file
                == normalized_root
                or normalized_file.startswith(
                    f"{normalized_root}/"
                )
            ):
                matching_projects.append(
                    project
                )

        if not matching_projects:
            return None

        return max(
            matching_projects,
            key=lambda project: (
                0
                if self._normalize_path(
                    project.root
                )
                == "."
                else len(
                    self._normalize_path(
                        project.root
                    )
                )
            ),
        )

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
