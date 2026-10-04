import pytest

from pr_reviewer.review.file_classifier import (
    FileCategory,
)
from pr_reviewer.review.models import (
    ChangedFile,
    ChangedLine,
)
from pr_reviewer.review.review_router import (
    ReviewRouter,
)
from pr_reviewer.review.review_strategy import (
    ReviewStrategy,
)


def create_changed_file(
    file_path: str,
    line_number: int = 10,
    content: str = "changed code",
) -> ChangedFile:

    return ChangedFile(
        file_path=file_path,
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path=file_path,
                line_number=line_number,
                content=content,
            )
        ],
    )


@pytest.fixture
def router() -> ReviewRouter:
    return ReviewRouter()


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
    ],
)
def test_routes_source_languages_to_semantic_review(
    router: ReviewRouter,
    file_path: str,
):
    changed_file = create_changed_file(
        file_path
    )

    route = router.route(
        changed_file
    )

    assert (
        route.should_review_with_llm
        is True
    )

    assert (
        route.category
        == FileCategory.SOURCE_CODE
    )

    assert (
        route.strategy
        == ReviewStrategy.SEMANTIC
    )


@pytest.mark.parametrize(
    "file_path",
    [
        "src/App.vue",
        "src/App.svelte",
        "src/page.astro",
    ],
)
def test_routes_component_files_to_semantic_review(
    router: ReviewRouter,
    file_path: str,
):
    changed_file = create_changed_file(
        file_path
    )

    route = router.route(
        changed_file
    )

    assert (
        route.should_review_with_llm
        is True
    )

    assert (
        route.category
        == FileCategory.SOURCE_CODE
    )

    assert (
        route.strategy
        == ReviewStrategy.SEMANTIC
    )


@pytest.mark.parametrize(
    "file_path",
    [
        "templates/index.html",
        "views/login.cshtml",
        "views/home.hbs",
    ],
)
def test_routes_templates_to_template_review(
    router: ReviewRouter,
    file_path: str,
):
    changed_file = create_changed_file(
        file_path
    )

    route = router.route(
        changed_file
    )

    assert (
        route.should_review_with_llm
        is True
    )

    assert (
        route.category
        == FileCategory.TEMPLATE
    )

    assert (
        route.strategy
        == ReviewStrategy.TEMPLATE
    )


@pytest.mark.parametrize(
    "file_path",
    [
        "src/styles.css",
        "src/theme.scss",
        "src/app.less",
    ],
)
def test_routes_stylesheets_to_stylesheet_review(
    router: ReviewRouter,
    file_path: str,
):
    changed_file = create_changed_file(
        file_path
    )

    route = router.route(
        changed_file
    )

    assert (
        route.should_review_with_llm
        is True
    )

    assert (
        route.category
        == FileCategory.STYLESHEET
    )

    assert (
        route.strategy
        == ReviewStrategy.STYLESHEET
    )


@pytest.mark.parametrize(
    "file_path",
    [
        "application.yml",
        "config/app.json",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
    ],
)
def test_routes_project_configuration_to_configuration_review(
    router: ReviewRouter,
    file_path: str,
):
    changed_file = create_changed_file(
        file_path
    )

    route = router.route(
        changed_file
    )

    assert (
        route.should_review_with_llm
        is True
    )

    assert (
        route.category
        == FileCategory.PROJECT_CONFIGURATION
    )

    assert (
        route.strategy
        == ReviewStrategy.CONFIGURATION
    )


@pytest.mark.parametrize(
    "file_path",
    [
        "tests/test_service.py",
        "test/UserServiceTest.java",
        "src/app.spec.ts",
        "src/App.test.tsx",
    ],
)
def test_routes_tests_to_test_review(
    router: ReviewRouter,
    file_path: str,
):
    changed_file = create_changed_file(
        file_path
    )

    route = router.route(
        changed_file
    )

    assert (
        route.should_review_with_llm
        is True
    )

    assert (
        route.category
        == FileCategory.TEST
    )

    assert (
        route.strategy
        == ReviewStrategy.TEST
    )


@pytest.mark.parametrize(
    "file_path",
    [
        ".editorconfig",
        ".gitignore",
        ".prettierrc",
        ".eslintrc.json",
    ],
)
def test_tool_configuration_is_skipped(
    router: ReviewRouter,
    file_path: str,
):
    changed_file = create_changed_file(
        file_path
    )

    route = router.route(
        changed_file
    )

    assert (
        route.should_review_with_llm
        is False
    )

    assert (
        route.category
        == FileCategory.TOOL_CONFIGURATION
    )

    assert (
        route.strategy
        == ReviewStrategy.SKIP
    )


@pytest.mark.parametrize(
    "file_path",
    [
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
    ],
)
def test_lock_files_are_skipped(
    router: ReviewRouter,
    file_path: str,
):
    changed_file = create_changed_file(
        file_path
    )

    route = router.route(
        changed_file
    )

    assert (
        route.should_review_with_llm
        is False
    )

    assert (
        route.category
        == FileCategory.LOCK_FILE
    )

    assert (
        route.strategy
        == ReviewStrategy.SKIP
    )


@pytest.mark.parametrize(
    "file_path",
    [
        "dist/main.js",
        "build/app.js",
        "obj/Debug/App.cs",
        "target/generated.java",
        "src/app.min.js",
    ],
)
def test_generated_files_are_skipped(
    router: ReviewRouter,
    file_path: str,
):
    changed_file = create_changed_file(
        file_path
    )

    route = router.route(
        changed_file
    )

    assert (
        route.should_review_with_llm
        is False
    )

    assert (
        route.category
        == FileCategory.GENERATED
    )

    assert (
        route.strategy
        == ReviewStrategy.SKIP
    )


@pytest.mark.parametrize(
    "file_path",
    [
        "assets/logo.png",
        "bin/App.dll",
        "bin/program.exe",
        "docs/manual.pdf",
    ],
)
def test_binary_files_are_skipped(
    router: ReviewRouter,
    file_path: str,
):
    changed_file = create_changed_file(
        file_path
    )

    route = router.route(
        changed_file
    )

    assert (
        route.should_review_with_llm
        is False
    )

    assert (
        route.category
        == FileCategory.BINARY
    )

    assert (
        route.strategy
        == ReviewStrategy.SKIP
    )


@pytest.mark.parametrize(
    "file_path",
    [
        "README.md",
        "docs/architecture.rst",
    ],
)
def test_documentation_is_skipped(
    router: ReviewRouter,
    file_path: str,
):
    changed_file = create_changed_file(
        file_path
    )

    route = router.route(
        changed_file
    )

    assert (
        route.should_review_with_llm
        is False
    )

    assert (
        route.category
        == FileCategory.DOCUMENTATION
    )

    assert (
        route.strategy
        == ReviewStrategy.SKIP
    )


def test_unknown_language_uses_semantic_review(
    router: ReviewRouter,
):
    changed_file = create_changed_file(
        "src/example.futurelang"
    )

    route = router.route(
        changed_file
    )

    assert (
        route.category
        == FileCategory.UNKNOWN
    )

    assert (
        route.should_review_with_llm
        is True
    )

    assert (
        route.strategy
        == ReviewStrategy.SEMANTIC
    )


def test_file_without_changed_lines_is_skipped(
    router: ReviewRouter,
):
    changed_file = ChangedFile(
        file_path="src/UserService.java",
        status="modified",
        changed_lines=[],
    )

    route = router.route(
        changed_file
    )

    assert (
        route.should_review_with_llm
        is False
    )

    assert (
        route.strategy
        == ReviewStrategy.SKIP
    )

    assert (
        "no commentable changed"
        in route.reason.lower()
    )


def test_should_review_with_llm_returns_boolean(
    router: ReviewRouter,
):
    source_file = create_changed_file(
        "src/OrderService.cs"
    )

    lock_file = create_changed_file(
        "package-lock.json"
    )

    assert (
        router.should_review_with_llm(
            source_file
        )
        is True
    )

    assert (
        router.should_review_with_llm(
            lock_file
        )
        is False
    )


def test_strategy_for_returns_semantic_strategy(
    router: ReviewRouter,
):
    changed_file = create_changed_file(
        "src/UserService.java"
    )

    assert (
        router.strategy_for(
            changed_file
        )
        == ReviewStrategy.SEMANTIC
    )


def test_strategy_for_returns_test_strategy(
    router: ReviewRouter,
):
    changed_file = create_changed_file(
        "src/app.spec.ts"
    )

    assert (
        router.strategy_for(
            changed_file
        )
        == ReviewStrategy.TEST
    )


def test_strategy_for_returns_configuration_strategy(
    router: ReviewRouter,
):
    changed_file = create_changed_file(
        "tsconfig.json"
    )

    assert (
        router.strategy_for(
            changed_file
        )
        == ReviewStrategy.CONFIGURATION
    )


def test_strategy_for_returns_skip_for_excluded_file(
    router: ReviewRouter,
):
    changed_file = create_changed_file(
        ".editorconfig"
    )

    assert (
        router.strategy_for(
            changed_file
        )
        == ReviewStrategy.SKIP
    )


def test_partition_separates_reviewable_and_skipped_files(
    router: ReviewRouter,
):
    java_file = create_changed_file(
        "src/UserService.java"
    )

    python_file = create_changed_file(
        "src/service.py"
    )

    lock_file = create_changed_file(
        "package-lock.json"
    )

    binary_file = create_changed_file(
        "assets/logo.png"
    )

    reviewable, skipped = (
        router.partition(
            [
                java_file,
                python_file,
                lock_file,
                binary_file,
            ]
        )
    )

    assert reviewable == [
        java_file,
        python_file,
    ]

    assert len(skipped) == 2

    skipped_paths = {
        route.file_path
        for route in skipped
    }

    assert skipped_paths == {
        "package-lock.json",
        "assets/logo.png",
    }


def test_partition_routes_preserves_review_strategies(
    router: ReviewRouter,
):
    source_file = create_changed_file(
        "src/app.ts"
    )

    test_file = create_changed_file(
        "src/app.spec.ts"
    )

    template_file = create_changed_file(
        "src/app.html"
    )

    stylesheet_file = create_changed_file(
        "src/app.css"
    )

    config_file = create_changed_file(
        "tsconfig.json"
    )

    tool_file = create_changed_file(
        ".editorconfig"
    )

    reviewable, skipped = (
        router.partition_routes(
            [
                source_file,
                test_file,
                template_file,
                stylesheet_file,
                config_file,
                tool_file,
            ]
        )
    )

    assert len(reviewable) == 4
    assert len(skipped) == 2

    strategies = {
        route.file_path: route.strategy
        for route in reviewable
    }

    assert (
        strategies["src/app.ts"]
        == ReviewStrategy.SEMANTIC
    )

    assert (
        strategies["src/app.spec.ts"]
        == ReviewStrategy.TEST
    )

    assert (
        strategies["src/app.html"]
        == ReviewStrategy.TEMPLATE
    )

    assert (
        strategies["src/app.css"]
        == ReviewStrategy.STYLESHEET
    )


    assert (
        skipped[0].strategy
        == ReviewStrategy.SKIP
    )

@pytest.mark.parametrize(
    "file_path",
    [
        "package.json",
        "nx.json",
        "angular.json",
        "project.json",
        "tsconfig.json",
        "tsconfig.base.json",
        "tsconfig.lib.json",
        "vite.config.mts",
        "eslint.config.mjs",
        "vitest.config.mts",
        "opencode.json",
        "Dockerfile",
        ".gemini/settings.json",
        ".opencode/config.toml",
        ".vscode/launch.json",
        ".github/skills/monitor-ci/script.mjs",
        "apps/shop-e2e/src/shop-homepage.spec.ts",
    ],
)
def test_low_value_context_and_e2e_files_do_not_reach_llm(
    router: ReviewRouter,
    file_path: str,
):
    route = router.route(create_changed_file(file_path))
    assert route.should_review_with_llm is False
    assert route.strategy == ReviewStrategy.SKIP


def test_github_workflow_still_reaches_configuration_review(
    router: ReviewRouter,
):
    route = router.route(create_changed_file(".github/workflows/ci.yml"))
    assert route.should_review_with_llm is True
    assert route.strategy == ReviewStrategy.CONFIGURATION


def test_unit_test_still_reaches_test_review(
    router: ReviewRouter,
):
    route = router.route(create_changed_file("src/app.spec.ts"))
    assert route.should_review_with_llm is True
    assert route.strategy == ReviewStrategy.TEST
