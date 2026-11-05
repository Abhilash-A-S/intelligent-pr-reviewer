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


def test_builder_detects_nx_workspace():
    builder = RepositoryContextBuilder()

    files = [
        create_changed_file(
            "nx.json"
        ),
        create_changed_file(
            "package.json"
        ),
        create_changed_file(
            "tsconfig.base.json"
        ),
        create_changed_file(
            "apps/web/src/app/app.ts"
        ),
    ]

    context = builder.build(
        files
    )

    assert context.workspace == "nx"

    assert context.workspace_evidence == [
        "nx.json"
    ]


def test_builder_detects_standalone_workspace():
    builder = RepositoryContextBuilder()

    files = [
        create_changed_file(
            "package.json"
        ),
        create_changed_file(
            "angular.json"
        ),
        create_changed_file(
            "src/app/app.ts"
        ),
    ]

    context = builder.build(
        files
    )

    assert (
        context.workspace
        == "standalone"
    )

    assert (
        context.workspace_evidence
        == []
    )


def test_nx_json_is_repository_metadata():
    builder = RepositoryContextBuilder()

    files = [
        create_changed_file(
            "nx.json"
        ),
        create_changed_file(
            "package.json"
        ),
    ]

    context = builder.build(
        files
    )

    assert (
        "nx.json"
        in context.metadata_files
    )


def test_tsconfig_base_is_repository_metadata():
    builder = RepositoryContextBuilder()

    files = [
        create_changed_file(
            "tsconfig.base.json"
        ),
    ]

    context = builder.build(
        files
    )

    assert (
        "tsconfig.base.json"
        in context.metadata_files
    )


def test_tsconfig_is_repository_metadata():
    builder = RepositoryContextBuilder()

    files = [
        create_changed_file(
            "tsconfig.json"
        ),
    ]

    context = builder.build(
        files
    )

    assert (
        "tsconfig.json"
        in context.metadata_files
    )


def test_nx_workspace_preserves_framework_detection():
    builder = RepositoryContextBuilder()

    files = [
        create_changed_file(
            "nx.json"
        ),
        create_changed_file(
            "angular.json"
        ),
        create_changed_file(
            "package.json"
        ),
        create_changed_file(
            "apps/web/src/app/app.component.ts"
        ),
    ]

    context = builder.build(
        files
    )

    assert context.workspace == "nx"

    assert (
        context.framework
        == "angular"
    )

    assert (
        context.project_type
        == "frontend-web"
    )

    assert (
        "typescript"
        in context.languages
    )


def test_nx_does_not_become_framework():
    builder = RepositoryContextBuilder()

    files = [
        create_changed_file(
            "nx.json"
        ),
        create_changed_file(
            "package.json"
        ),
        create_changed_file(
            "libs/shared/src/index.ts"
        ),
    ]

    context = builder.build(
        files
    )

    assert context.workspace == "nx"

    assert (
        context.framework
        != "nx"
    )


def test_vite_repository_remains_standalone():
    builder = RepositoryContextBuilder()

    files = [
        create_changed_file(
            "package.json"
        ),
        create_changed_file(
            "vite.config.ts"
        ),
        create_changed_file(
            "src/main.ts"
        ),
    ]

    context = builder.build(
        files
    )

    assert (
        context.workspace
        == "standalone"
    )


def test_nested_nx_json_does_not_mark_repository_as_nx():
    builder = RepositoryContextBuilder()

    files = [
        create_changed_file(
            "package.json"
        ),
        create_changed_file(
            "examples/demo/nx.json"
        ),
        create_changed_file(
            "src/main.ts"
        ),
    ]

    context = builder.build(
        files
    )

    assert (
        context.workspace
        == "standalone"
    )

    assert (
        context.workspace_evidence
        == []
    )


def test_windows_style_nx_path_is_supported():
    builder = RepositoryContextBuilder()

    files = [
        create_changed_file(
            r".\nx.json"
        ),
        create_changed_file(
            r"apps\web\src\app\app.ts"
        ),
    ]

    context = builder.build(
        files
    )

    assert context.workspace == "nx"

    assert context.workspace_evidence == [
        "nx.json"
    ]


def test_nx_workspace_can_use_npm():
    builder = RepositoryContextBuilder()

    files = [
        create_changed_file(
            "nx.json"
        ),
        create_changed_file(
            "package.json"
        ),
        create_changed_file(
            "package-lock.json"
        ),
    ]

    context = builder.build(
        files
    )

    assert context.workspace == "nx"

    assert (
        context.package_manager
        == "npm"
    )


def test_nx_workspace_can_use_pnpm():
    builder = RepositoryContextBuilder()

    files = [
        create_changed_file(
            "nx.json"
        ),
        create_changed_file(
            "package.json"
        ),
        create_changed_file(
            "pnpm-lock.yaml"
        ),
    ]

    context = builder.build(
        files
    )

    assert context.workspace == "nx"

    assert (
        context.package_manager
        == "pnpm"
    )


def test_nx_workspace_can_use_yarn():
    builder = RepositoryContextBuilder()

    files = [
        create_changed_file(
            "nx.json"
        ),
        create_changed_file(
            "package.json"
        ),
        create_changed_file(
            "yarn.lock"
        ),
    ]

    context = builder.build(
        files
    )

    assert context.workspace == "nx"

    assert (
        context.package_manager
        == "yarn"
    )


def test_bun_package_manager_is_detected():
    builder = RepositoryContextBuilder()

    files = [
        create_changed_file(
            "package.json"
        ),
        create_changed_file(
            "bun.lock"
        ),
    ]

    context = builder.build(
        files
    )

    assert (
        context.package_manager
        == "bun"
    )


def test_legacy_bun_lockfile_is_detected():
    builder = RepositoryContextBuilder()

    files = [
        create_changed_file(
            "package.json"
        ),
        create_changed_file(
            "bun.lockb"
        ),
    ]

    context = builder.build(
        files
    )

    assert (
        context.package_manager
        == "bun"
    )


def test_workspace_detection_does_not_break_unknown_repository():
    builder = RepositoryContextBuilder()

    files = [
        create_changed_file(
            "src/example.futurelang"
        ),
    ]

    context = builder.build(
        files
    )

    assert (
        context.workspace
        == "standalone"
    )

    assert (
        context.workspace_evidence
        == []
    )