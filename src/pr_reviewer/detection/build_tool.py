from dataclasses import dataclass
from enum import Enum


class BuildTool(str, Enum):
    """
    Build tools recognized by repository metadata.

    Build-tool detection is intentionally separate from:

    - programming-language detection
    - framework detection
    - workspace detection
    - package-manager detection
    """

    VITE = "vite"
    ANGULAR_CLI = "angular-cli"
    WEBPACK = "webpack"
    ROLLUP = "rollup"
    ESBUILD = "esbuild"

    MAVEN = "maven"
    GRADLE = "gradle"

    CARGO = "cargo"

    DOTNET = "dotnet"

    UNKNOWN = "unknown"


@dataclass(frozen=True)
class BuildToolDetectionResult:
    """
    Result of repository build-tool detection.

    build_tools:
        All build tools supported by concrete repository
        evidence.

    evidence:
        Mapping between detected build tools and the
        repository files supporting that detection.
    """

    build_tools: tuple[BuildTool, ...]

    evidence: dict[
        BuildTool,
        tuple[str, ...],
    ]


class BuildToolDetector:
    """
    Detects build tools from repository file paths.

    Multiple build tools may exist in the same repository.

    This is important for monorepos.

    Example:

        nx.json
        apps/web/vite.config.ts
        apps/admin/angular.json
        services/api/pom.xml

    Such a repository may contain:

        Vite
        Angular CLI
        Maven

    Nx itself is NOT returned here because Nx belongs to
    workspace/orchestration detection.
    """

    VITE_FILES = {
        "vite.config.js",
        "vite.config.mjs",
        "vite.config.cjs",
        "vite.config.ts",
        "vite.config.mts",
        "vite.config.cts",
    }

    WEBPACK_FILES = {
        "webpack.config.js",
        "webpack.config.cjs",
        "webpack.config.mjs",
        "webpack.config.ts",
    }

    ROLLUP_FILES = {
        "rollup.config.js",
        "rollup.config.mjs",
        "rollup.config.cjs",
        "rollup.config.ts",
    }

    ESBUILD_FILES = {
        "esbuild.config.js",
        "esbuild.config.mjs",
        "esbuild.config.cjs",
        "esbuild.config.ts",
    }

    ANGULAR_CLI_FILES = {
        "angular.json",
    }

    MAVEN_FILES = {
        "pom.xml",
    }

    GRADLE_FILES = {
        "build.gradle",
        "build.gradle.kts",
    }

    CARGO_FILES = {
        "cargo.toml",
    }

    def detect(
        self,
        file_paths: list[str]
        | tuple[str, ...]
        | set[str],
    ) -> BuildToolDetectionResult:

        detected: dict[
            BuildTool,
            list[str],
        ] = {}

        for original_path in file_paths:

            if not original_path:
                continue

            normalized = self._normalize_path(
                original_path
            )

            file_name = (
                normalized
                .split("/")[-1]
                .lower()
            )

            self._record_if_matches(
                detected=detected,
                build_tool=BuildTool.VITE,
                file_name=file_name,
                expected_files=self.VITE_FILES,
                evidence=normalized,
            )

            self._record_if_matches(
                detected=detected,
                build_tool=BuildTool.ANGULAR_CLI,
                file_name=file_name,
                expected_files=self.ANGULAR_CLI_FILES,
                evidence=normalized,
            )

            self._record_if_matches(
                detected=detected,
                build_tool=BuildTool.WEBPACK,
                file_name=file_name,
                expected_files=self.WEBPACK_FILES,
                evidence=normalized,
            )

            self._record_if_matches(
                detected=detected,
                build_tool=BuildTool.ROLLUP,
                file_name=file_name,
                expected_files=self.ROLLUP_FILES,
                evidence=normalized,
            )

            self._record_if_matches(
                detected=detected,
                build_tool=BuildTool.ESBUILD,
                file_name=file_name,
                expected_files=self.ESBUILD_FILES,
                evidence=normalized,
            )

            self._record_if_matches(
                detected=detected,
                build_tool=BuildTool.MAVEN,
                file_name=file_name,
                expected_files=self.MAVEN_FILES,
                evidence=normalized,
            )

            self._record_if_matches(
                detected=detected,
                build_tool=BuildTool.GRADLE,
                file_name=file_name,
                expected_files=self.GRADLE_FILES,
                evidence=normalized,
            )

            self._record_if_matches(
                detected=detected,
                build_tool=BuildTool.CARGO,
                file_name=file_name,
                expected_files=self.CARGO_FILES,
                evidence=normalized,
            )

            if self._is_dotnet_project(
                file_name
            ):
                self._record(
                    detected=detected,
                    build_tool=BuildTool.DOTNET,
                    evidence=normalized,
                )

        build_tools = tuple(
            detected.keys()
        )

        evidence = {
            build_tool: tuple(paths)
            for build_tool, paths
            in detected.items()
        }

        return BuildToolDetectionResult(
            build_tools=build_tools,
            evidence=evidence,
        )

    def has_tool(
        self,
        file_paths: list[str]
        | tuple[str, ...]
        | set[str],
        build_tool: BuildTool,
    ) -> bool:

        result = self.detect(
            file_paths
        )

        return (
            build_tool
            in result.build_tools
        )

    @staticmethod
    def _normalize_path(
        file_path: str,
    ) -> str:

        normalized = (
            file_path
            .strip()
            .replace("\\", "/")
        )

        while normalized.startswith("./"):
            normalized = normalized[2:]

        return normalized.strip("/")

    @staticmethod
    def _record_if_matches(
        detected: dict[
            BuildTool,
            list[str],
        ],
        build_tool: BuildTool,
        file_name: str,
        expected_files: set[str],
        evidence: str,
    ) -> None:

        if file_name not in expected_files:
            return

        BuildToolDetector._record(
            detected=detected,
            build_tool=build_tool,
            evidence=evidence,
        )

    @staticmethod
    def _record(
        detected: dict[
            BuildTool,
            list[str],
        ],
        build_tool: BuildTool,
        evidence: str,
    ) -> None:

        evidence_files = (
            detected.setdefault(
                build_tool,
                [],
            )
        )

        if evidence not in evidence_files:
            evidence_files.append(
                evidence
            )

    @staticmethod
    def _is_dotnet_project(
        file_name: str,
    ) -> bool:

        return file_name.endswith(
            (
                ".csproj",
                ".fsproj",
                ".vbproj",
            )
        )