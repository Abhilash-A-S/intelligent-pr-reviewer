from pr_reviewer.context.builder import (
    RepositoryContextBuilder,
)
from pr_reviewer.review.models import (
    ChangedFile,
    ChangedLine,
)


def create_changed_file(
    file_path: str,
    content: str | None = None,
) -> ChangedFile:

    changed_lines: list[
        ChangedLine
    ] = []

    if content is not None:
        changed_lines = [
            ChangedLine(
                file_path=file_path,
                line_number=1,
                content=content,
            )
        ]

    return ChangedFile(
        file_path=file_path,
        status="modified",
        changed_lines=changed_lines,
        full_content=content,
    )


# ======================================================
# Standalone repository
# ======================================================


def test_standalone_repository_contains_root_project():
    builder = RepositoryContextBuilder()

    context = builder.build(
        [
            create_changed_file(
                "package.json"
            ),
            create_changed_file(
                "src/main.ts"
            ),
        ]
    )

    assert len(
        context.projects
    ) == 1

    project = (
        context.projects[0]
    )

    assert project.name == "root"

    assert project.root == "."


def test_standalone_angular_project_context():
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

    project = (
        context.projects[0]
    )

    assert (
        project.framework
        == "angular"
    )

    assert (
        project.project_type
        == "frontend-web"
    )


def test_standalone_react_vite_project_context():
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

    project = (
        context.projects[0]
    )

    assert (
        project.framework
        == "react"
    )

    assert (
        "vite"
        in project.build_tools
    )


# ======================================================
# Nx project integration
# ======================================================


def test_nx_projects_are_added_to_repository_context():
    builder = RepositoryContextBuilder()

    context = builder.build(
        [
            create_changed_file(
                "nx.json"
            ),
            create_changed_file(
                "apps/web/project.json"
            ),
            create_changed_file(
                "apps/web/src/main.ts"
            ),
            create_changed_file(
                "apps/api/project.json"
            ),
            create_changed_file(
                "apps/api/src/main.ts"
            ),
        ]
    )

    roots = {
        project.root
        for project
        in context.projects
    }

    assert (
        "apps/web"
        in roots
    )

    assert (
        "apps/api"
        in roots
    )


def test_nx_root_configuration_has_root_project():
    builder = RepositoryContextBuilder()

    context = builder.build(
        [
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
                "apps/web/src/main.ts"
            ),
        ]
    )

    roots = {
        project.root
        for project
        in context.projects
    }

    assert "." in roots

    assert (
        "apps/web"
        in roots
    )


def test_nx_projects_can_have_different_frameworks():
    builder = RepositoryContextBuilder()

    context = builder.build(
        [
            create_changed_file(
                "nx.json"
            ),

            create_changed_file(
                "apps/web/angular.json"
            ),
            create_changed_file(
                "apps/web/src/app/app.ts",
                content=(
                    "import { Component } "
                    "from '@angular/core';\n"
                    "@Component({})\n"
                    "export class App {}"
                ),
            ),

            create_changed_file(
                "apps/admin/vite.config.ts"
            ),
            create_changed_file(
                "apps/admin/src/App.tsx"
            ),

            create_changed_file(
                "services/api/src/server.ts",
                content=(
                    "import express "
                    "from 'express';\n"
                    "const app = express();"
                ),
            ),
        ]
    )

    projects = {
        project.root: project
        for project
        in context.projects
    }

    assert (
        projects[
            "apps/web"
        ].framework
        == "angular"
    )

    assert (
        projects[
            "apps/admin"
        ].framework
        == "react"
    )

    assert (
        projects[
            "services/api"
        ].framework
        == "express"
    )


def test_nx_projects_can_have_different_languages():
    builder = RepositoryContextBuilder()

    context = builder.build(
        [
            create_changed_file(
                "nx.json"
            ),
            create_changed_file(
                "apps/web/src/main.ts"
            ),
            create_changed_file(
                "services/api/src/Application.java"
            ),
            create_changed_file(
                "services/python-api/main.py"
            ),
        ]
    )

    projects = {
        project.root: project
        for project
        in context.projects
    }

    assert (
        projects[
            "apps/web"
        ].languages
        == frozenset(
            {
                "typescript",
            }
        )
    )

    assert (
        projects[
            "services/api"
        ].languages
        == frozenset(
            {
                "java",
            }
        )
    )

    assert (
        projects[
            "services/python-api"
        ].languages
        == frozenset(
            {
                "python",
            }
        )
    )


def test_nx_projects_can_have_different_build_tools():
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
                "apps/web/src/main.ts"
            ),

            create_changed_file(
                "services/api/pom.xml"
            ),
            create_changed_file(
                "services/api/src/Application.java"
            ),
        ]
    )

    projects = {
        project.root: project
        for project
        in context.projects
    }

    assert (
        "vite"
        in projects[
            "apps/web"
        ].build_tools
    )

    assert (
        "maven"
        in projects[
            "services/api"
        ].build_tools
    )


# ======================================================
# Per-file project resolution
# ======================================================


def test_repository_context_resolves_angular_project_for_file():
    builder = RepositoryContextBuilder()

    context = builder.build(
        [
            create_changed_file(
                "nx.json"
            ),

            create_changed_file(
                "apps/web/angular.json"
            ),

            create_changed_file(
                "apps/web/src/app/app.ts",
                content=(
                    "import { Component } "
                    "from '@angular/core';"
                ),
            ),

            create_changed_file(
                "apps/admin/src/App.tsx"
            ),
        ]
    )

    project = (
        context.find_project_for_file(
            "apps/web/src/app/app.ts"
        )
    )

    assert project is not None

    assert project.root == "apps/web"

    assert (
        project.framework
        == "angular"
    )


def test_repository_context_resolves_react_project_for_file():
    builder = RepositoryContextBuilder()

    context = builder.build(
        [
            create_changed_file(
                "nx.json"
            ),
            create_changed_file(
                "apps/web/src/main.ts"
            ),
            create_changed_file(
                "apps/admin/src/App.tsx"
            ),
        ]
    )

    project = (
        context.find_project_for_file(
            "apps/admin/src/App.tsx"
        )
    )

    assert project is not None

    assert (
        project.root
        == "apps/admin"
    )

    assert (
        project.framework
        == "react"
    )


def test_repository_context_resolves_express_project_for_file():
    builder = RepositoryContextBuilder()

    context = builder.build(
        [
            create_changed_file(
                "nx.json"
            ),

            create_changed_file(
                "services/api/src/server.ts",
                content=(
                    "import express "
                    "from 'express';\n"
                    "const app = express();"
                ),
            ),
        ]
    )

    project = (
        context.find_project_for_file(
            "services/api/src/server.ts"
        )
    )

    assert project is not None

    assert (
        project.framework
        == "express"
    )


def test_repository_context_resolves_root_file():
    builder = RepositoryContextBuilder()

    context = builder.build(
        [
            create_changed_file(
                "nx.json"
            ),
            create_changed_file(
                "package.json"
            ),
            create_changed_file(
                "apps/web/src/main.ts"
            ),
        ]
    )

    project = (
        context.find_project_for_file(
            "package.json"
        )
    )

    assert project is not None

    assert project.root == "."


def test_deep_project_match_wins_over_root():
    builder = RepositoryContextBuilder()

    context = builder.build(
        [
            create_changed_file(
                "nx.json"
            ),
            create_changed_file(
                "package.json"
            ),
            create_changed_file(
                "apps/web/src/main.ts"
            ),
        ]
    )

    project = (
        context.find_project_for_file(
            "apps/web/src/main.ts"
        )
    )

    assert project is not None

    assert (
        project.root
        == "apps/web"
    )


# ======================================================
# Backward compatibility
# ======================================================


def test_repository_level_framework_is_preserved():
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
        context.framework
        == "angular"
    )

    assert (
        context.project_type
        == "frontend-web"
    )


def test_existing_workspace_information_is_preserved():
    builder = RepositoryContextBuilder()

    context = builder.build(
        [
            create_changed_file(
                "nx.json"
            ),
            create_changed_file(
                "apps/web/src/main.ts"
            ),
        ]
    )

    assert (
        context.workspace
        == "nx"
    )

    assert (
        context.workspace_evidence
        == [
            "nx.json"
        ]
    )


def test_existing_build_tool_information_is_preserved():
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

    assert context.build_tools == {
        "vite"
    }


def test_project_json_is_repository_metadata():
    builder = RepositoryContextBuilder()

    context = builder.build(
        [
            create_changed_file(
                "nx.json"
            ),
            create_changed_file(
                "apps/web/project.json"
            ),
        ]
    )

    assert (
        "apps/web/project.json"
        in context.metadata_files
    )


# ======================================================
# Unknown ecosystem behavior
# ======================================================


def test_unknown_project_still_exists():
    builder = RepositoryContextBuilder()

    context = builder.build(
        [
            create_changed_file(
                "src/example.futurelang"
            ),
        ]
    )

    assert len(
        context.projects
    ) == 1

    project = (
        context.projects[0]
    )

    assert (
        project.framework
        == "unknown"
    )


def test_unknown_project_can_be_resolved():
    builder = RepositoryContextBuilder()

    context = builder.build(
        [
            create_changed_file(
                "src/example.futurelang"
            ),
        ]
    )

    project = (
        context.find_project_for_file(
            "src/example.futurelang"
        )
    )

    assert project is not None

    assert project.root == "."

    assert (
        project.framework
        == "unknown"
    )


# ======================================================
# Windows paths
# ======================================================


def test_windows_project_file_resolution():
    builder = RepositoryContextBuilder()

    context = builder.build(
        [
            create_changed_file(
                r".\nx.json"
            ),
            create_changed_file(
                r"apps\web\src\app\app.ts"
            ),
        ]
    )

    project = (
        context.find_project_for_file(
            r"apps\web\src\app\app.ts"
        )
    )

    assert project is not None

    assert (
        project.root
        == "apps/web"
    )

def test_nx_multi_framework_repository_reports_mixed_monorepo_context():
    builder = RepositoryContextBuilder()
    context = builder.build(
        [
            create_changed_file("nx.json"),
            create_changed_file("apps/shop/project.json"),
            create_changed_file(
                "apps/shop/src/app/app.ts",
                "import { Component } from '@angular/core'; @Component({}) export class App {}",
            ),
            create_changed_file("apps/api/project.json"),
            create_changed_file(
                "apps/api/src/main.ts",
                "import express from 'express'; const app = express();",
            ),
        ]
    )
    assert context.framework == "mixed"
    assert context.project_type == "monorepo"
    assert len(context.projects) == 2
