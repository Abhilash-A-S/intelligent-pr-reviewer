import pytest

from pr_reviewer.detection.project import (
    ProjectContext,
    ProjectDetectionResult,
    ProjectDetector,
)
from pr_reviewer.detection.workspace import (
    WorkspaceType,
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


@pytest.fixture
def detector() -> ProjectDetector:
    return ProjectDetector()


# ======================================================
# Standalone repositories
# ======================================================


def test_standalone_repository_has_root_project(
    detector: ProjectDetector,
):
    result = detector.detect(
        [
            create_changed_file(
                "package.json"
            ),
            create_changed_file(
                "src/main.ts"
            ),
        ]
    )

    assert (
        result.workspace
        == WorkspaceType.STANDALONE
    )

    assert len(
        result.projects
    ) == 1

    project = result.projects[0]

    assert project.name == "root"
    assert project.root == "."


def test_standalone_angular_project_detects_angular(
    detector: ProjectDetector,
):
    result = detector.detect(
        [
            create_changed_file(
                "angular.json"
            ),
            create_changed_file(
                "src/app/app.ts"
            ),
        ]
    )

    project = result.projects[0]

    assert (
        project.framework
        == "angular"
    )

    assert (
        project.project_type
        == "frontend-web"
    )

    assert (
        "typescript"
        in project.languages
    )


def test_standalone_react_vite_project(
    detector: ProjectDetector,
):
    result = detector.detect(
        [
            create_changed_file(
                "vite.config.ts"
            ),
            create_changed_file(
                "src/App.tsx"
            ),
        ]
    )

    project = result.projects[0]

    assert project.framework == "react"

    assert "vite" in project.build_tools

    assert (
        "typescript"
        in project.languages
    )


def test_unknown_standalone_project_remains_valid(
    detector: ProjectDetector,
):
    result = detector.detect(
        [
            create_changed_file(
                "src/example.futurelang"
            ),
        ]
    )

    assert len(
        result.projects
    ) == 1

    project = result.projects[0]

    assert (
        project.framework
        == "unknown"
    )

    assert (
        project.project_type
        == "unknown"
    )


# ======================================================
# Nx project.json discovery
# ======================================================


def test_detects_nx_project_from_project_json(
    detector: ProjectDetector,
):
    result = detector.detect(
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
        ]
    )

    assert (
        result.workspace
        == WorkspaceType.NX
    )

    projects = {
        project.root: project
        for project
        in result.projects
    }

    assert (
        "apps/web"
        in projects
    )

    web = projects[
        "apps/web"
    ]

    assert web.name == "web"

    assert web.evidence == (
        "apps/web/project.json",
    )


def test_detects_multiple_explicit_nx_projects(
    detector: ProjectDetector,
):
    result = detector.detect(
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

            create_changed_file(
                "libs/shared/project.json"
            ),
            create_changed_file(
                "libs/shared/src/index.ts"
            ),
        ]
    )

    roots = {
        project.root
        for project
        in result.projects
    }

    assert {
        "apps/web",
        "apps/api",
        "libs/shared",
    }.issubset(
        roots
    )


# ======================================================
# Nx conventional discovery
# ======================================================


@pytest.mark.parametrize(
    (
        "file_path",
        "expected_root",
    ),
    [
        (
            "apps/web/src/main.ts",
            "apps/web",
        ),
        (
            "libs/shared/src/index.ts",
            "libs/shared",
        ),
        (
            "packages/ui/src/index.ts",
            "packages/ui",
        ),
        (
            "services/api/src/server.ts",
            "services/api",
        ),
    ],
)
def test_infers_common_nx_project_roots(
    detector: ProjectDetector,
    file_path: str,
    expected_root: str,
):
    result = detector.detect(
        [
            create_changed_file(
                "nx.json"
            ),
            create_changed_file(
                file_path
            ),
        ]
    )

    roots = {
        project.root
        for project
        in result.projects
    }

    assert (
        expected_root
        in roots
    )


def test_root_configuration_becomes_root_project(
    detector: ProjectDetector,
):
    result = detector.detect(
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

    projects = {
        project.root: project
        for project
        in result.projects
    }

    assert "." in projects
    assert "apps/web" in projects

    assert (
        projects["."].name
        == "root"
    )


# ======================================================
# Multi-framework detection
# ======================================================


def test_nx_projects_detect_frameworks_independently(
    detector: ProjectDetector,
):
    files = [
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
                "import express from 'express';\n"
                "const app = express();"
            ),
        ),
    ]

    result = detector.detect(
        files
    )

    projects = {
        project.root: project
        for project
        in result.projects
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


def test_nx_projects_detect_build_tools_independently(
    detector: ProjectDetector,
):
    result = detector.detect(
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
        in result.projects
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


def test_nx_projects_detect_languages_independently(
    detector: ProjectDetector,
):
    result = detector.detect(
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
        in result.projects
    }

    assert projects[
        "apps/web"
    ].languages == frozenset(
        {
            "typescript",
        }
    )

    assert projects[
        "services/api"
    ].languages == frozenset(
        {
            "java",
        }
    )

    assert projects[
        "services/python-api"
    ].languages == frozenset(
        {
            "python",
        }
    )


# ======================================================
# Project resolution
# ======================================================


def test_find_project_for_file(
    detector: ProjectDetector,
):
    result = detector.detect(
        [
            create_changed_file(
                "nx.json"
            ),
            create_changed_file(
                "apps/web/src/app/app.ts"
            ),
            create_changed_file(
                "apps/api/src/main.ts"
            ),
        ]
    )

    project = detector.find_project_for_file(
        "apps/web/src/app/app.ts",
        result.projects,
    )

    assert project is not None

    assert (
        project.root
        == "apps/web"
    )


def test_find_project_for_nested_file(
    detector: ProjectDetector,
):
    result = detector.detect(
        [
            create_changed_file(
                "nx.json"
            ),
            create_changed_file(
                "libs/shared/src/lib/utils/date.ts"
            ),
        ]
    )

    project = detector.find_project_for_file(
        "libs/shared/src/lib/utils/date.ts",
        result.projects,
    )

    assert project is not None

    assert (
        project.root
        == "libs/shared"
    )


def test_find_project_for_root_file(
    detector: ProjectDetector,
):
    result = detector.detect(
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

    project = detector.find_project_for_file(
        "package.json",
        result.projects,
    )

    assert project is not None

    assert project.root == "."


def test_unknown_file_returns_root_when_root_project_exists(
    detector: ProjectDetector,
):
    result = detector.detect(
        [
            create_changed_file(
                "nx.json"
            ),
            create_changed_file(
                "package.json"
            ),
        ]
    )

    project = detector.find_project_for_file(
        "some/new/file.ts",
        result.projects,
    )

    assert project is not None

    assert project.root == "."


# ======================================================
# Path handling
# ======================================================


def test_windows_paths_are_supported(
    detector: ProjectDetector,
):
    result = detector.detect(
        [
            create_changed_file(
                r".\nx.json"
            ),
            create_changed_file(
                r"apps\web\project.json"
            ),
            create_changed_file(
                r"apps\web\src\main.ts"
            ),
        ]
    )

    roots = {
        project.root
        for project
        in result.projects
    }

    assert (
        "apps/web"
        in roots
    )


def test_dot_slash_paths_are_supported(
    detector: ProjectDetector,
):
    result = detector.detect(
        [
            create_changed_file(
                "./nx.json"
            ),
            create_changed_file(
                "./apps/web/src/main.ts"
            ),
        ]
    )

    roots = {
        project.root
        for project
        in result.projects
    }

    assert (
        "apps/web"
        in roots
    )


# ======================================================
# Type safety / result
# ======================================================


def test_returns_project_detection_result(
    detector: ProjectDetector,
):
    result = detector.detect(
        [
            create_changed_file(
                "src/main.ts"
            ),
        ]
    )

    assert isinstance(
        result,
        ProjectDetectionResult,
    )


def test_projects_are_project_context_instances(
    detector: ProjectDetector,
):
    result = detector.detect(
        [
            create_changed_file(
                "src/main.ts"
            ),
        ]
    )

    assert all(
        isinstance(
            project,
            ProjectContext,
        )
        for project
        in result.projects
    )

def test_nested_package_based_nx_projects_are_discovered_from_repository_context():
    files = [
        ChangedFile(file_path="nx-angular-review/nx.json", status="unchanged"),
        ChangedFile(file_path="nx-angular-review/apps/shop/package.json", status="unchanged"),
        ChangedFile(file_path="nx-angular-review/apps/shop/src/main.ts", status="unchanged", full_content="import { Component } from '@angular/core';"),
        ChangedFile(file_path="nx-angular-review/packages/shared-ui/package.json", status="unchanged"),
        ChangedFile(file_path="nx-angular-review/packages/shared-ui/src/index.ts", status="unchanged", full_content="export * from './lib/button';"),
    ]
    result = ProjectDetector().detect(files, allow_nested_workspace=True)
    roots = {project.root for project in result.projects}
    assert "nx-angular-review/apps/shop" in roots
    assert "nx-angular-review/packages/shared-ui" in roots
    shop = next(project for project in result.projects if project.root == "nx-angular-review/apps/shop")
    assert shop.framework == "angular"


def test_explicit_nx_projects_suppress_synthetic_container_roots(
    detector: ProjectDetector,
):
    result = detector.detect(
        [
            create_changed_file("nx-angular-review/nx.json"),
            create_changed_file("nx-angular-review/apps/shop/project.json"),
            create_changed_file(
                "nx-angular-review/apps/shop/src/app/app.ts",
                "import { Component } from '@angular/core';",
            ),
            create_changed_file("nx-angular-review/apps/api/project.json"),
            create_changed_file("nx-angular-review/apps/api/src/main.ts"),
            create_changed_file("nx-angular-review/packages/shop/feature-products/project.json"),
            create_changed_file(
                "nx-angular-review/packages/shop/feature-products/src/lib/products.component.ts",
                "import { Component } from '@angular/core';",
            ),
            create_changed_file("nx-angular-review/packages/shop/shared-ui/project.json"),
            create_changed_file(
                "nx-angular-review/packages/shop/shared-ui/src/lib/button.component.ts",
                "import { Component } from '@angular/core';",
            ),
            create_changed_file("nx-angular-review/packages/api/products/project.json"),
            create_changed_file("nx-angular-review/packages/api/products/package.json"),
            create_changed_file("nx-angular-review/packages/api/products/src/index.ts"),
            create_changed_file("nx-angular-review/tsconfig.base.json"),
        ],
        allow_nested_workspace=True,
    )

    roots = {project.root for project in result.projects}

    assert "nx-angular-review/apps/shop" in roots
    assert "nx-angular-review/apps/api" in roots
    assert "nx-angular-review/packages/shop/feature-products" in roots
    assert "nx-angular-review/packages/shop/shared-ui" in roots
    assert "nx-angular-review/packages/api/products" in roots

    assert "nx-angular-review/packages/shop" not in roots
    assert "nx-angular-review/packages/api" not in roots
    assert "." not in roots


def test_nx_angular_library_detects_framework_from_nx_metadata(
    detector: ProjectDetector,
):
    result = detector.detect(
        [
            create_changed_file("nx.json"),
            create_changed_file(
                "packages/shop/shared-ui/project.json",
                '{"targets":{"build":{"executor":"@nx/angular:package"}}}',
            ),
            create_changed_file("packages/shop/shared-ui/src/index.ts"),
        ]
    )

    project = next(project for project in result.projects if project.root == "packages/shop/shared-ui")
    assert project.framework == "angular"
    assert project.project_type == "frontend-web"


def test_nx_e2e_project_has_e2e_project_type(detector: ProjectDetector):
    result = detector.detect(
        [
            create_changed_file("nx.json"),
            create_changed_file(
                "apps/shop-e2e/project.json",
                '{"targets":{"e2e":{"executor":"@nx/playwright:playwright"}}}',
            ),
            create_changed_file("apps/shop-e2e/src/example.spec.ts"),
        ]
    )

    project = next(project for project in result.projects if project.root == "apps/shop-e2e")
    assert project.framework == "playwright"
    assert project.project_type == "e2e"
