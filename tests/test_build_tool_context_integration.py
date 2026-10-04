from pr_reviewer.context.builder import (
    RepositoryContextBuilder,
)
from pr_reviewer.review.models import (
    ChangedFile,
)


def create_changed_file(
    file_path: str,
) -> ChangedFile:

    return ChangedFile(
        file_path=file_path,
        status="modified",
    )


def test_builder_detects_vite():
    builder = RepositoryContextBuilder()

    context = builder.build(
        [
            create_changed_file(
                "vite.config.ts"
            ),
            create_changed_file(
                "package.json"
            ),
            create_changed_file(
                "src/main.ts"
            ),
        ]
    )

    assert context.build_tools == {
        "vite"
    }

    assert context.build_tool_evidence == {
        "vite": [
            "vite.config.ts"
        ]
    }


def test_builder_detects_angular_cli():
    builder = RepositoryContextBuilder()

    context = builder.build(
        [
            create_changed_file(
                "angular.json"
            ),
            create_changed_file(
                "src/app/app.ts"
            ),
        ]
    )

    assert (
        "angular-cli"
        in context.build_tools
    )


def test_builder_detects_multiple_build_tools():
    builder = RepositoryContextBuilder()

    context = builder.build(
        [
            create_changed_file(
                "apps/web/vite.config.ts"
            ),
            create_changed_file(
                "apps/admin/angular.json"
            ),
            create_changed_file(
                "services/api/pom.xml"
            ),
        ]
    )

    assert context.build_tools == {
        "vite",
        "angular-cli",
        "maven",
    }


def test_builder_preserves_build_tool_evidence():
    builder = RepositoryContextBuilder()

    context = builder.build(
        [
            create_changed_file(
                "apps/web/vite.config.ts"
            ),
            create_changed_file(
                "apps/admin/vite.config.ts"
            ),
        ]
    )

    assert context.build_tool_evidence[
        "vite"
    ] == [
        "apps/web/vite.config.ts",
        "apps/admin/vite.config.ts",
    ]


def test_nx_and_vite_are_kept_separate():
    builder = RepositoryContextBuilder()

    context = builder.build(
        [
            create_changed_file(
                "nx.json"
            ),
            create_changed_file(
                "apps/web/vite.config.ts"
            ),
            create_changed_file(
                "package.json"
            ),
        ]
    )

    assert context.workspace == "nx"

    assert context.build_tools == {
        "vite"
    }

    assert (
        "nx"
        not in context.build_tools
    )


def test_angular_and_nx_are_kept_separate():
    builder = RepositoryContextBuilder()

    context = builder.build(
        [
            create_changed_file(
                "nx.json"
            ),
            create_changed_file(
                "angular.json"
            ),
            create_changed_file(
                "apps/web/src/app/app.ts"
            ),
        ]
    )

    assert context.workspace == "nx"

    assert context.framework == "angular"

    assert (
        "angular-cli"
        in context.build_tools
    )


def test_build_tool_does_not_replace_framework():
    builder = RepositoryContextBuilder()

    context = builder.build(
        [
            create_changed_file(
                "vite.config.ts"
            ),
            create_changed_file(
                "src/App.tsx"
            ),
        ]
    )

    assert context.framework == "react"

    assert context.build_tools == {
        "vite"
    }


def test_maven_is_detected_as_build_tool():
    builder = RepositoryContextBuilder()

    context = builder.build(
        [
            create_changed_file(
                "pom.xml"
            ),
            create_changed_file(
                "src/Application.java"
            ),
        ]
    )

    assert (
        "maven"
        in context.build_tools
    )


def test_gradle_is_detected_as_build_tool():
    builder = RepositoryContextBuilder()

    context = builder.build(
        [
            create_changed_file(
                "build.gradle.kts"
            ),
            create_changed_file(
                "src/Main.kt"
            ),
        ]
    )

    assert (
        "gradle"
        in context.build_tools
    )


def test_dotnet_is_detected_as_build_tool():
    builder = RepositoryContextBuilder()

    context = builder.build(
        [
            create_changed_file(
                "SampleApi.csproj"
            ),
            create_changed_file(
                "Program.cs"
            ),
        ]
    )

    assert (
        "dotnet"
        in context.build_tools
    )


def test_unknown_repository_has_no_build_tools():
    builder = RepositoryContextBuilder()

    context = builder.build(
        [
            create_changed_file(
                "src/example.futurelang"
            ),
        ]
    )

    assert context.build_tools == set()

    assert (
        context.build_tool_evidence
        == {}
    )


def test_vite_config_is_metadata():
    builder = RepositoryContextBuilder()

    context = builder.build(
        [
            create_changed_file(
                "vite.config.ts"
            ),
        ]
    )

    assert (
        "vite.config.ts"
        in context.metadata_files
    )


def test_nested_vite_config_is_metadata():
    builder = RepositoryContextBuilder()

    context = builder.build(
        [
            create_changed_file(
                "apps/web/vite.config.ts"
            ),
        ]
    )

    assert (
        "apps/web/vite.config.ts"
        in context.metadata_files
    )


def test_build_tool_detection_does_not_break_package_manager():
    builder = RepositoryContextBuilder()

    context = builder.build(
        [
            create_changed_file(
                "vite.config.ts"
            ),
            create_changed_file(
                "package.json"
            ),
            create_changed_file(
                "pnpm-lock.yaml"
            ),
        ]
    )

    assert context.build_tools == {
        "vite"
    }

    assert (
        context.package_manager
        == "pnpm"
    )