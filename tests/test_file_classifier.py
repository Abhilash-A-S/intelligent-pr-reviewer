import pytest

from pr_reviewer.review.file_classifier import (
    FileCategory,
    FileClassifier,
)


@pytest.fixture
def classifier() -> FileClassifier:
    return FileClassifier()


@pytest.mark.parametrize(
    "file_path",
    [
        "src/app.ts",
        "src/App.tsx",
        "src/index.js",
        "src/main.py",
        "src/UserService.java",
        "src/OrderService.cs",
        "src/main.go",
        "src/lib.rs",
        "src/main.cpp",
        "src/UserController.php",
        "src/user.rb",
        "src/Main.kt",
        "src/App.swift",
        "src/main.dart",
        "src/query.sql",
    ],
)
def test_classifies_common_languages_as_source_code(
    classifier: FileClassifier,
    file_path: str,
):
    result = classifier.classify(
        file_path
    )

    assert (
        result.category
        == FileCategory.SOURCE_CODE
    )

    assert result.reviewable is True


@pytest.mark.parametrize(
    "file_path",
    [
        "src/App.vue",
        "src/App.svelte",
        "src/page.astro",
    ],
)
def test_component_files_are_source_code(
    classifier: FileClassifier,
    file_path: str,
):
    result = classifier.classify(
        file_path
    )

    assert (
        result.category
        == FileCategory.SOURCE_CODE
    )

    assert result.reviewable is True


@pytest.mark.parametrize(
    "file_path",
    [
        "templates/index.html",
        "views/login.cshtml",
        "views/home.hbs",
        "templates/page.twig",
    ],
)
def test_classifies_templates(
    classifier: FileClassifier,
    file_path: str,
):
    result = classifier.classify(
        file_path
    )

    assert (
        result.category
        == FileCategory.TEMPLATE
    )

    assert result.reviewable is True


@pytest.mark.parametrize(
    "file_path",
    [
        "src/styles.css",
        "src/app.scss",
        "src/theme.less",
    ],
)
def test_classifies_stylesheets(
    classifier: FileClassifier,
    file_path: str,
):
    result = classifier.classify(
        file_path
    )

    assert (
        result.category
        == FileCategory.STYLESHEET
    )

    assert result.reviewable is True


@pytest.mark.parametrize(
    "file_path",
    [
        "config/app.json",
        "config/app.yaml",
        "config/application.yml",
        "app.properties",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "docker-compose.yml",
        "src/App.csproj",
    ],
)
def test_classifies_project_configuration(
    classifier: FileClassifier,
    file_path: str,
):
    result = classifier.classify(
        file_path
    )

    assert (
        result.category
        == FileCategory.PROJECT_CONFIGURATION
    )

    assert result.reviewable is True


@pytest.mark.parametrize(
    "file_path",
    [
        ".editorconfig",
        ".gitignore",
        ".dockerignore",
        ".prettierignore",
        ".eslintignore",
        ".npmignore",
        ".gitattributes",
        ".prettierrc",
        ".prettierrc.json",
        ".eslintrc",
        ".eslintrc.json",
        ".stylelintrc",
        ".stylelintrc.json",
    ],
)
def test_classifies_tool_configuration_as_not_reviewable(
    classifier: FileClassifier,
    file_path: str,
):
    result = classifier.classify(
        file_path
    )

    assert (
        result.category
        == FileCategory.TOOL_CONFIGURATION
    )

    assert result.reviewable is False


@pytest.mark.parametrize(
    "file_path",
    [
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "Cargo.lock",
        "poetry.lock",
        "Gemfile.lock",
    ],
)
def test_skips_lock_files(
    classifier: FileClassifier,
    file_path: str,
):
    result = classifier.classify(
        file_path
    )

    assert (
        result.category
        == FileCategory.LOCK_FILE
    )

    assert result.reviewable is False


@pytest.mark.parametrize(
    "file_path",
    [
        "dist/main.js",
        "build/app.js",
        "target/generated.java",
        "obj/Debug/App.cs",
        "coverage/report.js",
        "src/app.min.js",
        "src/styles.min.css",
        "src/model.generated.cs",
    ],
)
def test_skips_generated_files(
    classifier: FileClassifier,
    file_path: str,
):
    result = classifier.classify(
        file_path
    )

    assert (
        result.category
        == FileCategory.GENERATED
    )

    assert result.reviewable is False


@pytest.mark.parametrize(
    "file_path",
    [
        "assets/logo.png",
        "assets/photo.jpg",
        "docs/manual.pdf",
        "lib/example.dll",
        "bin/program.exe",
        "fonts/app.woff2",
    ],
)
def test_skips_binary_files(
    classifier: FileClassifier,
    file_path: str,
):
    result = classifier.classify(
        file_path
    )

    assert (
        result.category
        == FileCategory.BINARY
    )

    assert result.reviewable is False


@pytest.mark.parametrize(
    "file_path",
    [
        "tests/test_service.py",
        "test/UserServiceTest.java",
        "src/app.spec.ts",
        "src/App.test.tsx",
        "__tests__/service.js",
    ],
)
def test_test_files_remain_reviewable(
    classifier: FileClassifier,
    file_path: str,
):
    result = classifier.classify(
        file_path
    )

    assert (
        result.category
        == FileCategory.TEST
    )

    assert result.reviewable is True


@pytest.mark.parametrize(
    "file_path",
    [
        "README.md",
        "docs/architecture.rst",
        "CHANGELOG.md",
    ],
)
def test_documentation_is_not_reviewed_by_default(
    classifier: FileClassifier,
    file_path: str,
):
    result = classifier.classify(
        file_path
    )

    assert (
        result.category
        == FileCategory.DOCUMENTATION
    )

    assert result.reviewable is False


def test_unknown_extension_remains_reviewable(
    classifier: FileClassifier,
):
    result = classifier.classify(
        "src/example.futurelang"
    )

    assert (
        result.category
        == FileCategory.UNKNOWN
    )

    assert result.reviewable is True


def test_windows_paths_are_supported(
    classifier: FileClassifier,
):
    result = classifier.classify(
        r"src\Services\UserService.cs"
    )

    assert (
        result.category
        == FileCategory.SOURCE_CODE
    )

    assert result.reviewable is True


def test_configuration_alias_is_backward_compatible():
    assert (
        FileCategory.CONFIGURATION
        == FileCategory.PROJECT_CONFIGURATION
    )


def test_should_review_returns_boolean(
    classifier: FileClassifier,
):
    assert (
        classifier.should_review(
            "src/UserService.java"
        )
        is True
    )

    assert (
        classifier.should_review(
            "package-lock.json"
        )
        is False
    )

    assert (
        classifier.should_review(
            ".editorconfig"
        )
        is False
    )

    assert (
        classifier.should_review(
            "tsconfig.json"
        )
        is False
    )

def test_ai_agent_tooling_directories_are_not_application_reviewable():
    classifier = FileClassifier()
    for path in (
        ".agents/skills/monitor-ci/scripts/ci-poll-decide.mjs",
        ".cursor/commands/monitor-ci.md",
        ".codex/agents/ci-monitor-subagent.toml",
        ".claude/settings.json",
    ):
        result = classifier.classify(path)
        assert result.category == FileCategory.TOOL_CONFIGURATION
        assert result.reviewable is False


@pytest.mark.parametrize(
    "file_path",
    [
        "package.json",
        "nx.json",
        "angular.json",
        "project.json",
        "apps/shop/project.json",
        "tsconfig.json",
        "tsconfig.base.json",
        "tsconfig.app.json",
        "tsconfig.spec.json",
        "tsconfig.lib.json",
        "vite.config.ts",
        "vite.config.mts",
        "eslint.config.mjs",
        "Dockerfile",
        "apps/api/Dockerfile",
    ],
)
def test_workspace_metadata_is_context_only(
    classifier: FileClassifier,
    file_path: str,
):
    result = classifier.classify(file_path)
    assert result.reviewable is False
    assert result.category in {
        FileCategory.PROJECT_CONFIGURATION,
        FileCategory.TOOL_CONFIGURATION,
    }


@pytest.mark.parametrize(
    "file_path",
    [
        ".gemini/commands/review.toml",
        ".opencode/skills/review/script.ts",
        ".vscode/settings.json",
        ".nx/workspace-data/cache.json",
        ".github/skills/reviewer/SKILL.md",
    ],
)
def test_tool_control_directories_are_skipped(
    classifier: FileClassifier,
    file_path: str,
):
    result = classifier.classify(file_path)
    assert result.category == FileCategory.TOOL_CONFIGURATION
    assert result.reviewable is False


def test_github_workflows_remain_reviewable(
    classifier: FileClassifier,
):
    result = classifier.classify(".github/workflows/ci.yml")
    assert result.category == FileCategory.PROJECT_CONFIGURATION
    assert result.reviewable is True


@pytest.mark.parametrize(
    "file_path",
    [
        "apps/shop-e2e/src/shop.spec.ts",
        "e2e/login.spec.ts",
        "tests/cart.e2e.ts",
        "cypress/e2e/checkout.cy.ts",
    ],
)
def test_e2e_files_are_skipped_by_default(
    classifier: FileClassifier,
    file_path: str,
):
    result = classifier.classify(file_path)
    assert result.category == FileCategory.TEST
    assert result.reviewable is False


def test_unit_tests_remain_reviewable_after_e2e_exclusion(
    classifier: FileClassifier,
):
    result = classifier.classify("src/app.spec.ts")
    assert result.category == FileCategory.TEST
    assert result.reviewable is True
