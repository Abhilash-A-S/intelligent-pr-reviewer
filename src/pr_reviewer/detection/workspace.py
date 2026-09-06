from dataclasses import dataclass
from enum import Enum


class WorkspaceType(str, Enum):
    """
    Known repository workspace types.

    Workspace type is intentionally separate from
    framework and build-tool detection.

    Examples:

    Nx
        Workspace/monorepo orchestration system.

    Standalone
        Repository without a recognized workspace
        orchestration system.

    Unknown
        Reserved for cases where repository evidence
        exists but cannot be classified safely.
    """

    NX = "nx"
    STANDALONE = "standalone"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class WorkspaceDetectionResult:
    """
    Result produced by WorkspaceDetector.

    workspace_type:
        Detected workspace architecture.

    evidence:
        Repository files that caused the detection.

    reason:
        Human-readable explanation useful for
        diagnostics and testing.
    """

    workspace_type: WorkspaceType
    evidence: tuple[str, ...]
    reason: str


class WorkspaceDetector:
    """
    Detects repository workspace architecture using
    repository metadata files.

    This detector does NOT detect:

    - programming languages
    - frameworks
    - build tools
    - package managers
    - individual applications

    Those concerns belong to separate detectors.

    The detector is intentionally conservative.
    A repository should only be classified as an Nx
    workspace when there is concrete Nx evidence.
    """

    NX_CONFIG_FILE = "nx.json"

    def detect(
        self,
        metadata_files: list[str]
        | tuple[str, ...]
        | set[str],
        allow_nested: bool = False,
    ) -> WorkspaceDetectionResult:
        """
        Detect the workspace type from repository
        metadata file paths.

        Paths are normalized so both Windows and
        POSIX-style paths are supported.
        """

        normalized_files = {
            self._normalize_path(file_path)
            for file_path in metadata_files
            if file_path
        }

        # --------------------------------------------------
        # Nx workspace
        # --------------------------------------------------

        nx_evidence = self._find_workspace_file(
            normalized_files,
            self.NX_CONFIG_FILE,
            allow_nested=allow_nested,
        )

        if nx_evidence is not None:
            return WorkspaceDetectionResult(
                workspace_type=WorkspaceType.NX,
                evidence=(
                    nx_evidence,
                ),
                reason=(
                    "Repository contains nx.json, "
                    "indicating an Nx workspace."
                ),
            )

        # --------------------------------------------------
        # Standalone/default repository
        # --------------------------------------------------

        return WorkspaceDetectionResult(
            workspace_type=WorkspaceType.STANDALONE,
            evidence=(),
            reason=(
                "No recognized workspace orchestration "
                "metadata was detected."
            ),
        )

    def is_nx(
        self,
        metadata_files: list[str]
        | tuple[str, ...]
        | set[str],
    ) -> bool:
        """
        Convenience method for checking whether a
        repository is an Nx workspace.
        """

        return (
            self.detect(
                metadata_files
            ).workspace_type
            == WorkspaceType.NX
        )

    @staticmethod
    def _normalize_path(
        file_path: str,
    ) -> str:
        """
        Normalize repository paths for reliable
        cross-platform comparison.
        """

        normalized = (
            file_path
            .strip()
            .replace("\\", "/")
        )

        while normalized.startswith("./"):
            normalized = normalized[2:]

        return normalized.strip("/")

    @staticmethod
    def _find_workspace_file(
        normalized_files: set[str],
        expected_file: str,
        allow_nested: bool = False,
    ) -> str | None:
        """Find a workspace marker; nested roots require explicit repository context."""
        expected_lower = expected_file.lower()
        matches = [
            file_path for file_path in normalized_files
            if file_path.split("/")[-1].lower() == expected_lower
            and (allow_nested or "/" not in file_path)
        ]
        if not matches:
            return None
        return min(matches, key=lambda value: (value.count("/"), len(value), value))
