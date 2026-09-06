import pytest

from pr_reviewer.detection.build_tool import (
    BuildTool,
    BuildToolDetectionResult,
    BuildToolDetector,
)


@pytest.fixture
def detector() -> BuildToolDetector:
    return BuildToolDetector()


@pytest.mark.parametrize(
    "file_path",
    [
        "vite.config.js",
        "vite.config.mjs",
        "vite.config.cjs",
        "vite.config.ts",
        "vite.config.mts",
        "vite.config.cts",
    ],
)
def test_detects_vite(
    detector: BuildToolDetector,
    file_path: str,
):
    result = detector.detect(
        [
            file_path,
        ]
    )

    assert (
        BuildTool.VITE
        in result.build_tools
    )


def test_detects_nested_vite_configuration(
    detector: BuildToolDetector,
):
    result = detector.detect(
        [
            "apps/web/vite.config.ts",
        ]
    )

    assert (
        BuildTool.VITE
        in result.build_tools
    )

    assert result.evidence[
        BuildTool.VITE
    ] == (
        "apps/web/vite.config.ts",
    )


def test_detects_angular_cli(
    detector: BuildToolDetector,
):
    result = detector.detect(
        [
            "angular.json",
        ]
    )

    assert (
        BuildTool.ANGULAR_CLI
        in result.build_tools
    )


@pytest.mark.parametrize(
    "file_path",
    [
        "webpack.config.js",
        "webpack.config.cjs",
        "webpack.config.mjs",
        "webpack.config.ts",
    ],
)
def test_detects_webpack(
    detector: BuildToolDetector,
    file_path: str,
):
    result = detector.detect(
        [
            file_path,
        ]
    )

    assert (
        BuildTool.WEBPACK
        in result.build_tools
    )


@pytest.mark.parametrize(
    "file_path",
    [
        "rollup.config.js",
        "rollup.config.mjs",
        "rollup.config.cjs",
        "rollup.config.ts",
    ],
)
def test_detects_rollup(
    detector: BuildToolDetector,
    file_path: str,
):
    result = detector.detect(
        [
            file_path,
        ]
    )

    assert (
        BuildTool.ROLLUP
        in result.build_tools
    )


@pytest.mark.parametrize(
    "file_path",
    [
        "esbuild.config.js",
        "esbuild.config.mjs",
        "esbuild.config.cjs",
        "esbuild.config.ts",
    ],
)
def test_detects_esbuild(
    detector: BuildToolDetector,
    file_path: str,
):
    result = detector.detect(
        [
            file_path,
        ]
    )

    assert (
        BuildTool.ESBUILD
        in result.build_tools
    )


def test_detects_maven(
    detector: BuildToolDetector,
):
    result = detector.detect(
        [
            "pom.xml",
        ]
    )

    assert (
        BuildTool.MAVEN
        in result.build_tools
    )


@pytest.mark.parametrize(
    "file_path",
    [
        "build.gradle",
        "build.gradle.kts",
    ],
)
def test_detects_gradle(
    detector: BuildToolDetector,
    file_path: str,
):
    result = detector.detect(
        [
            file_path,
        ]
    )

    assert (
        BuildTool.GRADLE
        in result.build_tools
    )


def test_detects_cargo(
    detector: BuildToolDetector,
):
    result = detector.detect(
        [
            "Cargo.toml",
        ]
    )

    assert (
        BuildTool.CARGO
        in result.build_tools
    )


@pytest.mark.parametrize(
    "file_path",
    [
        "Api.csproj",
        "Library.fsproj",
        "Application.vbproj",
    ],
)
def test_detects_dotnet(
    detector: BuildToolDetector,
    file_path: str,
):
    result = detector.detect(
        [
            file_path,
        ]
    )

    assert (
        BuildTool.DOTNET
        in result.build_tools
    )


def test_supports_multiple_build_tools(
    detector: BuildToolDetector,
):
    result = detector.detect(
        [
            "apps/web/vite.config.ts",
            "apps/admin/angular.json",
            "services/api/pom.xml",
        ]
    )

    assert set(
        result.build_tools
    ) == {
        BuildTool.VITE,
        BuildTool.ANGULAR_CLI,
        BuildTool.MAVEN,
    }


def test_nx_is_not_a_build_tool(
    detector: BuildToolDetector,
):
    result = detector.detect(
        [
            "nx.json",
            "package.json",
        ]
    )

    assert (
        result.build_tools
        == ()
    )


def test_package_manager_files_are_not_build_tools(
    detector: BuildToolDetector,
):
    result = detector.detect(
        [
            "package-lock.json",
            "pnpm-lock.yaml",
            "yarn.lock",
            "uv.lock",
        ]
    )

    assert (
        result.build_tools
        == ()
    )


def test_unknown_repository_returns_no_build_tools(
    detector: BuildToolDetector,
):
    result = detector.detect(
        [
            "src/example.futurelang",
        ]
    )

    assert (
        result.build_tools
        == ()
    )

    assert result.evidence == {}


def test_empty_repository_returns_no_build_tools(
    detector: BuildToolDetector,
):
    result = detector.detect(
        []
    )

    assert (
        result.build_tools
        == ()
    )

    assert result.evidence == {}


def test_supports_windows_paths(
    detector: BuildToolDetector,
):
    result = detector.detect(
        [
            r"apps\web\vite.config.ts",
        ]
    )

    assert (
        BuildTool.VITE
        in result.build_tools
    )

    assert result.evidence[
        BuildTool.VITE
    ] == (
        "apps/web/vite.config.ts",
    )


def test_supports_dot_slash_prefix(
    detector: BuildToolDetector,
):
    result = detector.detect(
        [
            "./vite.config.ts",
        ]
    )

    assert (
        BuildTool.VITE
        in result.build_tools
    )


def test_detection_is_case_insensitive(
    detector: BuildToolDetector,
):
    result = detector.detect(
        [
            "VITE.CONFIG.TS",
            "POM.XML",
            "APP.CSPROJ",
        ]
    )

    assert set(
        result.build_tools
    ) == {
        BuildTool.VITE,
        BuildTool.MAVEN,
        BuildTool.DOTNET,
    }


def test_duplicate_evidence_is_not_added_twice(
    detector: BuildToolDetector,
):
    result = detector.detect(
        [
            "vite.config.ts",
            "vite.config.ts",
        ]
    )

    assert result.evidence[
        BuildTool.VITE
    ] == (
        "vite.config.ts",
    )


def test_multiple_vite_projects_preserve_evidence(
    detector: BuildToolDetector,
):
    result = detector.detect(
        [
            "apps/web/vite.config.ts",
            "apps/admin/vite.config.ts",
        ]
    )

    assert result.evidence[
        BuildTool.VITE
    ] == (
        "apps/web/vite.config.ts",
        "apps/admin/vite.config.ts",
    )


def test_has_tool_returns_true(
    detector: BuildToolDetector,
):
    assert (
        detector.has_tool(
            [
                "vite.config.ts",
            ],
            BuildTool.VITE,
        )
        is True
    )


def test_has_tool_returns_false(
    detector: BuildToolDetector,
):
    assert (
        detector.has_tool(
            [
                "package.json",
            ],
            BuildTool.VITE,
        )
        is False
    )


def test_returns_build_tool_detection_result(
    detector: BuildToolDetector,
):
    result = detector.detect(
        [
            "vite.config.ts",
        ]
    )

    assert isinstance(
        result,
        BuildToolDetectionResult,
    )