import pytest

from pr_reviewer.detection.workspace import (
    WorkspaceDetectionResult,
    WorkspaceDetector,
    WorkspaceType,
)


@pytest.fixture
def detector() -> WorkspaceDetector:
    return WorkspaceDetector()


def test_detects_nx_workspace(
    detector: WorkspaceDetector,
):
    result = detector.detect(
        [
            "package.json",
            "nx.json",
            "tsconfig.base.json",
        ]
    )

    assert (
        result.workspace_type
        == WorkspaceType.NX
    )

    assert result.evidence == (
        "nx.json",
    )

    assert "nx" in result.reason.lower()


def test_detects_nx_with_only_nx_json(
    detector: WorkspaceDetector,
):
    result = detector.detect(
        [
            "nx.json",
        ]
    )

    assert (
        result.workspace_type
        == WorkspaceType.NX
    )


def test_detects_standalone_repository(
    detector: WorkspaceDetector,
):
    result = detector.detect(
        [
            "package.json",
            "angular.json",
            "tsconfig.json",
        ]
    )

    assert (
        result.workspace_type
        == WorkspaceType.STANDALONE
    )

    assert result.evidence == ()


def test_empty_metadata_is_standalone(
    detector: WorkspaceDetector,
):
    result = detector.detect(
        []
    )

    assert (
        result.workspace_type
        == WorkspaceType.STANDALONE
    )


def test_supports_tuple_input(
    detector: WorkspaceDetector,
):
    result = detector.detect(
        (
            "package.json",
            "nx.json",
        )
    )

    assert (
        result.workspace_type
        == WorkspaceType.NX
    )


def test_supports_set_input(
    detector: WorkspaceDetector,
):
    result = detector.detect(
        {
            "package.json",
            "nx.json",
        }
    )

    assert (
        result.workspace_type
        == WorkspaceType.NX
    )


def test_supports_windows_paths(
    detector: WorkspaceDetector,
):
    result = detector.detect(
        [
            r".\nx.json",
            r".\apps\web\project.json",
        ]
    )

    assert (
        result.workspace_type
        == WorkspaceType.NX
    )


def test_supports_dot_slash_prefix(
    detector: WorkspaceDetector,
):
    result = detector.detect(
        [
            "./nx.json",
        ]
    )

    assert (
        result.workspace_type
        == WorkspaceType.NX
    )


def test_detection_is_case_insensitive(
    detector: WorkspaceDetector,
):
    result = detector.detect(
        [
            "NX.JSON",
        ]
    )

    assert (
        result.workspace_type
        == WorkspaceType.NX
    )


def test_nested_nx_json_does_not_mark_root_as_nx(
    detector: WorkspaceDetector,
):
    result = detector.detect(
        [
            "package.json",
            "examples/demo/nx.json",
        ]
    )

    assert (
        result.workspace_type
        == WorkspaceType.STANDALONE
    )


def test_angular_repository_is_not_automatically_nx(
    detector: WorkspaceDetector,
):
    result = detector.detect(
        [
            "angular.json",
            "package.json",
            "tsconfig.json",
        ]
    )

    assert (
        result.workspace_type
        == WorkspaceType.STANDALONE
    )


def test_vite_repository_is_not_automatically_nx(
    detector: WorkspaceDetector,
):
    result = detector.detect(
        [
            "package.json",
            "vite.config.ts",
            "tsconfig.json",
        ]
    )

    assert (
        result.workspace_type
        == WorkspaceType.STANDALONE
    )


def test_package_json_alone_does_not_mean_nx(
    detector: WorkspaceDetector,
):
    result = detector.detect(
        [
            "package.json",
        ]
    )

    assert (
        result.workspace_type
        == WorkspaceType.STANDALONE
    )


def test_is_nx_returns_true_for_nx(
    detector: WorkspaceDetector,
):
    assert (
        detector.is_nx(
            [
                "nx.json",
                "package.json",
            ]
        )
        is True
    )


def test_is_nx_returns_false_for_standalone(
    detector: WorkspaceDetector,
):
    assert (
        detector.is_nx(
            [
                "package.json",
                "vite.config.ts",
            ]
        )
        is False
    )


def test_returns_detection_result(
    detector: WorkspaceDetector,
):
    result = detector.detect(
        [
            "nx.json",
        ]
    )

    assert isinstance(
        result,
        WorkspaceDetectionResult,
    )


def test_does_not_confuse_framework_with_workspace(
    detector: WorkspaceDetector,
):
    angular = detector.detect(
        [
            "angular.json",
            "package.json",
        ]
    )

    react = detector.detect(
        [
            "package.json",
            "src/App.tsx",
        ]
    )

    vue = detector.detect(
        [
            "package.json",
            "src/App.vue",
        ]
    )

    assert (
        angular.workspace_type
        == WorkspaceType.STANDALONE
    )

    assert (
        react.workspace_type
        == WorkspaceType.STANDALONE
    )

    assert (
        vue.workspace_type
        == WorkspaceType.STANDALONE
    )

def test_nested_nx_can_be_detected_with_repository_tree_context(detector: WorkspaceDetector):
    result = detector.detect(
        ["package.json", "nx-angular-review/nx.json", "nx-angular-review/apps/shop/src/main.ts"],
        allow_nested=True,
    )
    assert result.workspace_type == WorkspaceType.NX
    assert result.evidence == ("nx-angular-review/nx.json",)
