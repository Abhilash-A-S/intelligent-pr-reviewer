from pr_reviewer.context.models import RepositoryContext
from pr_reviewer.llm.prompt import ReviewPromptBuilder
from pr_reviewer.review.models import (
    ChangedFile,
    ChangedLine,
)
from pr_reviewer.review.review_strategy import (
    ReviewStrategy,
)

from pr_reviewer.context.models import RepositoryContext
from pr_reviewer.detection.project import ProjectContext
from pr_reviewer.llm.prompt import ReviewPromptBuilder
from pr_reviewer.review.models import (
    ChangedFile,
    ChangedLine,
)
from pr_reviewer.review.review_strategy import (
    ReviewStrategy,
)
def test_prompt_contains_repository_context():
    changed_file = ChangedFile(
        file_path="src/app.tsx",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app.tsx",
                line_number=10,
                content="const unused = 10;",
            )
        ],
        full_content=(
            "import React from 'react';\n"
            "\n"
            "const unused = 10;\n"
        ),
    )

    context = RepositoryContext(
        languages={"typescript"},
        framework="react",
        project_type="frontend-web",
        package_manager="npm",
    )

    prompt = ReviewPromptBuilder.build(
        changed_file=changed_file,
        repository_context=context,
    )

    assert "src/app.tsx" in prompt
    assert "typescript" in prompt
    assert "react" in prompt
    assert "frontend-web" in prompt
    assert "npm" in prompt


def test_prompt_reviews_without_custom_guidelines():
    changed_file = ChangedFile(
        file_path="src/app.js",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app.js",
                line_number=5,
                content='console.log("debug");',
            )
        ],
    )

    context = RepositoryContext(
        languages={"javascript"},
    )

    prompt = ReviewPromptBuilder.build(
        changed_file=changed_file,
        repository_context=context,
    )

    assert (
        "No custom project guidelines "
        "were supplied."
        in prompt
    )

    assert (
        "security vulnerabilities"
        in prompt
    )

    assert (
        "correctness and runtime logic bugs"
        in prompt
    )

    assert (
        "authentication problems"
        in prompt
    )

    assert (
        "meaningful refactoring opportunities"
        in prompt
    )

    assert (
        "deterministic static analyzer"
        in prompt
    )

    assert (
        "unused local variables"
        in prompt
    )

    assert (
        "console.log statements"
        in prompt
    )

    assert (
        "debugger statements"
        in prompt
    )


def test_prompt_includes_custom_guidelines():
    changed_file = ChangedFile(
        file_path="src/app.js",
        status="modified",
    )

    context = RepositoryContext(
        languages={"javascript"},
    )

    prompt = ReviewPromptBuilder.build(
        changed_file=changed_file,
        repository_context=context,
        custom_guidelines=(
            "All API calls must go through ApiService."
        ),
    )

    assert (
        "All API calls must go through ApiService."
        in prompt
    )


def test_prompt_uses_actual_source_line_numbers():
    changed_file = ChangedFile(
        file_path="src/app.js",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app.js",
                line_number=100,
                content='console.log("debug");',
            ),
            ChangedLine(
                file_path="src/app.js",
                line_number=101,
                content="const unused = 10;",
            ),
        ],
    )

    context = RepositoryContext(
        languages={"javascript"},
    )

    prompt = ReviewPromptBuilder.build(
        changed_file=changed_file,
        repository_context=context,
    )

    assert (
        '100 | console.log("debug");'
        in prompt
    )

    assert (
        "101 | const unused = 10;"
        in prompt
    )

    assert "[100, 101]" in prompt


def test_small_file_uses_full_file_context():
    changed_file = ChangedFile(
        file_path="src/app.js",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app.js",
                line_number=3,
                content="const abc = 123;",
            )
        ],
        full_content=(
            "const value = 10;\n"
            "console.log(value);\n"
            "const abc = 123;\n"
        ),
    )

    context = RepositoryContext(
        languages={"javascript"},
    )

    prompt = ReviewPromptBuilder.build(
        changed_file=changed_file,
        repository_context=context,
    )

    assert "Context mode:" in prompt
    assert "FULL FILE" in prompt

    assert (
        "1 | const value = 10;"
        in prompt
    )

    assert (
        "2 | console.log(value);"
        in prompt
    )

    assert (
        "3 | const abc = 123;"
        in prompt
    )


def test_large_file_uses_relevant_context():
    full_content = "\n".join(
        (
            f"const value{index} = "
            f'"{"x" * 100}";'
        )
        for index in range(
            1,
            151,
        )
    )

    changed_file = ChangedFile(
        file_path="src/large.js",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/large.js",
                line_number=100,
                content='console.log("debug");',
            )
        ],
        full_content=full_content,
    )

    context = RepositoryContext(
        languages={"javascript"},
    )

    prompt = ReviewPromptBuilder.build(
        changed_file=changed_file,
        repository_context=context,
    )

    assert "Context mode:" in prompt
    assert "RELEVANT CONTEXT" in prompt

    assert (
        "100 | const value100"
        in prompt
    )

    assert (
        "99 | const value99"
        in prompt
    )

    assert (
        "101 | const value101"
        in prompt
    )

    assert (
        "\n1 | const value1 ="
        not in prompt
    )

    assert (
        "\n2 | const value2 ="
        not in prompt
    )


def test_prompt_contains_estimated_context_tokens():
    changed_file = ChangedFile(
        file_path="src/app.js",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app.js",
                line_number=1,
                content="const value = 10;",
            )
        ],
        full_content=(
            "const value = 10;\n"
        ),
    )

    context = RepositoryContext(
        languages={"javascript"},
    )

    prompt = ReviewPromptBuilder.build(
        changed_file=changed_file,
        repository_context=context,
    )

    assert (
        "Estimated code-context tokens:"
        in prompt
    )


def test_prompt_restricts_comments_to_changed_lines():
    changed_file = ChangedFile(
        file_path="src/app.js",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app.js",
                line_number=50,
                content="const abc = 123;",
            )
        ],
        full_content=(
            "const used = 10;\n"
            "console.log(used);\n"
            + "\n" * 47
            + "const abc = 123;\n"
        ),
    )

    context = RepositoryContext(
        languages={"javascript"},
    )

    prompt = ReviewPromptBuilder.build(
        changed_file=changed_file,
        repository_context=context,
    )

    assert (
        "Only these source lines may "
        "receive findings"
        in prompt
    )

    assert "[50]" in prompt


def test_prompt_focuses_on_semantic_review():
    changed_file = ChangedFile(
        file_path="src/service.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/service.ts",
                line_number=20,
                content=(
                    "await processPayment(order);"
                ),
            )
        ],
    )

    context = RepositoryContext(
        languages={"typescript"},
    )

    prompt = ReviewPromptBuilder.build(
        changed_file=changed_file,
        repository_context=context,
    )

    assert "SEMANTIC REVIEW" in prompt

    assert (
        "incorrect async or concurrency behavior"
        in prompt
    )

    assert (
        "real security vulnerabilities"
        in prompt
    )

    assert (
        "cross-function behavioral problems"
        in prompt
    )


def test_prompt_warns_about_cross_file_claims():
    changed_file = ChangedFile(
        file_path="src/index.html",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/index.html",
                line_number=10,
                content=(
                    '<div id="strength-meter"></div>'
                ),
            )
        ],
    )

    context = RepositoryContext(
        languages={"html"},
    )

    prompt = ReviewPromptBuilder.build(
        changed_file=changed_file,
        repository_context=context,
    )

    assert "CROSS-FILE CAUTION" in prompt

    assert (
        "Do not claim functionality is missing"
        in prompt
    )

    assert (
        "HTML behavior may be implemented in"
        in prompt
    )


def test_prompt_keeps_framework_review():
    changed_file = ChangedFile(
        file_path="src/app.component.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app.component.ts",
                line_number=25,
                content=(
                    "this.service.data$.subscribe("
                    "value => this.value = value);"
                ),
            )
        ],
    )

    context = RepositoryContext(
        languages={"typescript"},
        framework="angular",
    )

    prompt = ReviewPromptBuilder.build(
        changed_file=changed_file,
        repository_context=context,
    )

    assert "FRAMEWORK REVIEW" in prompt
    assert "RxJS" in prompt
    assert "signal" in prompt.lower()
    assert "change-detection" in prompt


def test_source_file_uses_semantic_strategy():
    changed_file = ChangedFile(
        file_path="src/app/app.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app/app.ts",
                line_number=10,
                content="loadUsers();",
            )
        ],
    )

    context = RepositoryContext(
        languages={"typescript"},
        framework="angular",
    )

    prompt = ReviewPromptBuilder.build(
        changed_file=changed_file,
        repository_context=context,
    )

    assert (
        "Review strategy: SEMANTIC"
        in prompt
    )

    assert (
        "SOURCE-CODE SEMANTIC REVIEW"
        in prompt
    )


def test_test_file_uses_test_strategy():
    changed_file = ChangedFile(
        file_path="src/app/app.spec.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app/app.spec.ts",
                line_number=8,
                content="imports: [App],",
            )
        ],
    )

    context = RepositoryContext(
        languages={"typescript"},
        framework="angular",
    )

    prompt = ReviewPromptBuilder.build(
        changed_file=changed_file,
        repository_context=context,
    )

    assert (
        "Review strategy: TEST"
        in prompt
    )

    assert (
        "TEST-CODE REVIEW"
        in prompt
    )

    assert (
        "ANGULAR TEST-SPECIFIC CAUTION"
        in prompt
    )


def test_angular_test_prompt_allows_standalone_component_import():
    changed_file = ChangedFile(
        file_path="src/app/app.spec.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app/app.spec.ts",
                line_number=8,
                content="imports: [App],",
            )
        ],
        full_content=(
            "await TestBed.configureTestingModule({\n"
            "  imports: [App],\n"
            "}).compileComponents();\n"
        ),
    )

    context = RepositoryContext(
        languages={"typescript"},
        framework="angular",
    )

    prompt = ReviewPromptBuilder.build(
        changed_file=changed_file,
        repository_context=context,
    )

    assert (
        "standalone Angular component"
        in prompt
    )

    assert (
        "imports: [ComponentName]"
        in prompt
    )

    assert (
        "Do NOT require AppModule"
        in prompt
    )


def test_template_file_uses_template_strategy():
    changed_file = ChangedFile(
        file_path="src/app/app.html",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app/app.html",
                line_number=12,
                content=(
                    '<button (click)="save()">Save</button>'
                ),
            )
        ],
    )

    context = RepositoryContext(
        languages={"html"},
        framework="angular",
    )

    prompt = ReviewPromptBuilder.build(
        changed_file=changed_file,
        repository_context=context,
    )

    assert (
        "Review strategy: TEMPLATE"
        in prompt
    )

    assert (
        "TEMPLATE / VIEW REVIEW"
        in prompt
    )


def test_stylesheet_file_uses_stylesheet_strategy():
    changed_file = ChangedFile(
        file_path="src/app/app.css",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app/app.css",
                line_number=5,
                content="display: none;",
            )
        ],
    )

    context = RepositoryContext(
        languages={"css"},
        framework="angular",
    )

    prompt = ReviewPromptBuilder.build(
        changed_file=changed_file,
        repository_context=context,
    )

    assert (
        "Review strategy: STYLESHEET"
        in prompt
    )

    assert (
        "STYLESHEET REVIEW"
        in prompt
    )


def test_batch_schema_uses_a_real_allowed_file_path():
    changed_file = ChangedFile(
        file_path="src/app/service.js",
        status="modified",
        changed_lines=[ChangedLine(
            file_path="src/app/service.js",
            line_number=4,
            content="return load();",
        )],
    )
    prompt = ReviewPromptBuilder.build_batch(
        [changed_file],
        RepositoryContext(languages={"javascript"}),
    )

    assert '"file_path": "src/app/service.js"' in prompt
    assert "exact/path/from/FILE" not in prompt


def test_tsconfig_uses_configuration_strategy():
    changed_file = ChangedFile(
        file_path="tsconfig.json",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="tsconfig.json",
                line_number=10,
                content='"strict": true',
            )
        ],
    )

    context = RepositoryContext(
        languages={"typescript"},
        framework="angular",
    )

    prompt = ReviewPromptBuilder.build(
        changed_file=changed_file,
        repository_context=context,
    )

    assert (
        "Review strategy: CONFIGURATION"
        in prompt
    )

    assert (
        "PROJECT-CONFIGURATION REVIEW"
        in prompt
    )

    assert (
        "ANGULAR CONFIGURATION REVIEW"
        in prompt
    )


def test_tsconfig_spec_is_configuration_not_test():
    changed_file = ChangedFile(
        file_path="tsconfig.spec.json",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="tsconfig.spec.json",
                line_number=5,
                content='"types": ["jasmine"]',
            )
        ],
    )

    context = RepositoryContext(
        languages={"typescript"},
        framework="angular",
    )

    prompt = ReviewPromptBuilder.build(
        changed_file=changed_file,
        repository_context=context,
    )

    assert (
        "Review strategy: CONFIGURATION"
        in prompt
    )

    assert (
        "PROJECT-CONFIGURATION REVIEW"
        in prompt
    )


def test_build_gradle_kts_is_configuration_not_source():
    changed_file = ChangedFile(
        file_path="build.gradle.kts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="build.gradle.kts",
                line_number=5,
                content=(
                    'implementation("org.example:test:1.0")'
                ),
            )
        ],
    )

    context = RepositoryContext(
        languages={"kotlin"},
    )

    prompt = ReviewPromptBuilder.build(
        changed_file=changed_file,
        repository_context=context,
    )

    assert (
        "Review strategy: CONFIGURATION"
        in prompt
    )


def test_explicit_review_strategy_can_be_supplied():
    changed_file = ChangedFile(
        file_path="src/custom.futurelang",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/custom.futurelang",
                line_number=1,
                content="custom syntax",
            )
        ],
    )

    context = RepositoryContext()

    prompt = ReviewPromptBuilder.build(
        changed_file=changed_file,
        repository_context=context,
        review_strategy=(
            ReviewStrategy.CONFIGURATION
        ),
    )

    assert (
        "Review strategy: CONFIGURATION"
        in prompt
    )

    assert (
        "PROJECT-CONFIGURATION REVIEW"
        in prompt
    )


def test_configuration_prompt_does_not_treat_keys_as_source_variables():
    changed_file = ChangedFile(
        file_path="angular.json",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="angular.json",
                line_number=20,
                content='"builder": "@angular/build:application"',
            )
        ],
    )

    context = RepositoryContext(
        framework="angular",
    )

    prompt = ReviewPromptBuilder.build(
        changed_file=changed_file,
        repository_context=context,
    )

    assert (
        "Do not interpret configuration keys "
        "as application"
        in prompt
    )

    assert (
        "Do not treat configuration keys "
        "as source-code"
        in prompt
    )


def test_prompt_warns_not_to_invent_framework_modules():
    changed_file = ChangedFile(
        file_path="src/app/app.spec.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app/app.spec.ts",
                line_number=8,
                content="imports: [App],",
            )
        ],
    )

    context = RepositoryContext(
        framework="angular",
    )

    prompt = ReviewPromptBuilder.build(
        changed_file=changed_file,
        repository_context=context,
    )

    assert (
        "Do not invent framework modules"
        in prompt
    )


def test_prompt_warns_against_high_severity_for_style():
    changed_file = ChangedFile(
        file_path="angular.json",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="angular.json",
                line_number=5,
                content='"version": 1',
            )
        ],
    )

    context = RepositoryContext(
        framework="angular",
    )

    prompt = ReviewPromptBuilder.build(
        changed_file=changed_file,
        repository_context=context,
    )

    assert (
        "Do not assign HIGH or CRITICAL severity"
        in prompt
    )

def test_prompt_uses_project_framework_for_angular_project():
    changed_file = ChangedFile(
        file_path="apps/web/src/app/app.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="apps/web/src/app/app.ts",
                line_number=10,
                content="this.loadUsers();",
            )
        ],
    )

    context = RepositoryContext(
        languages={
            "typescript",
            "javascript",
        },
        framework="react",
        project_type="frontend-web",
        workspace="nx",
        projects=[
            ProjectContext(
                name="web",
                root="apps/web",
                languages=frozenset(
                    {
                        "typescript",
                    }
                ),
                framework="angular",
                project_type="frontend-web",
                build_tools=frozenset(),
            ),
        ],
    )

    prompt = ReviewPromptBuilder.build(
        changed_file=changed_file,
        repository_context=context,
    )

    assert "Framework: angular" in prompt

    assert (
        "Project type: frontend-web"
        in prompt
    )

    assert "RxJS" in prompt


def test_prompt_uses_project_framework_for_react_project():
    changed_file = ChangedFile(
        file_path="apps/admin/src/App.tsx",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="apps/admin/src/App.tsx",
                line_number=10,
                content="const value = useMemo(() => 1, []);",
            )
        ],
    )

    context = RepositoryContext(
        languages={
            "typescript",
        },
        framework="angular",
        project_type="frontend-web",
        workspace="nx",
        projects=[
            ProjectContext(
                name="admin",
                root="apps/admin",
                languages=frozenset(
                    {
                        "typescript",
                    }
                ),
                framework="react",
                project_type="frontend-web",
                build_tools=frozenset(
                    {
                        "vite",
                    }
                ),
            ),
        ],
    )

    prompt = ReviewPromptBuilder.build(
        changed_file=changed_file,
        repository_context=context,
    )

    assert "Framework: react" in prompt

    assert (
        "Project type: frontend-web"
        in prompt
    )

    # Repository-level Angular must not leak into
    # this React project's file review.
    assert "Framework: angular" not in prompt


def test_prompt_uses_project_framework_for_express_project():
    changed_file = ChangedFile(
        file_path="services/api/src/server.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="services/api/src/server.ts",
                line_number=20,
                content=(
                    "app.get('/users', handler);"
                ),
            )
        ],
    )

    context = RepositoryContext(
        languages={
            "typescript",
        },
        framework="angular",
        project_type="frontend-web",
        workspace="nx",
        projects=[
            ProjectContext(
                name="api",
                root="services/api",
                languages=frozenset(
                    {
                        "typescript",
                    }
                ),
                framework="express",
                project_type="backend-api",
                build_tools=frozenset(),
            ),
        ],
    )

    prompt = ReviewPromptBuilder.build(
        changed_file=changed_file,
        repository_context=context,
    )

    assert "Framework: express" in prompt

    assert (
        "Project type: backend-api"
        in prompt
    )

    assert "Framework: angular" not in prompt


def test_prompt_resolves_correct_project_in_multi_framework_repository():
    changed_file = ChangedFile(
        file_path="apps/admin/src/App.tsx",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="apps/admin/src/App.tsx",
                line_number=15,
                content="return <Dashboard />;",
            )
        ],
    )

    context = RepositoryContext(
        languages={
            "typescript",
        },
        framework="angular",
        project_type="frontend-web",
        workspace="nx",
        projects=[
            ProjectContext(
                name="web",
                root="apps/web",
                languages=frozenset(
                    {
                        "typescript",
                    }
                ),
                framework="angular",
                project_type="frontend-web",
            ),
            ProjectContext(
                name="admin",
                root="apps/admin",
                languages=frozenset(
                    {
                        "typescript",
                    }
                ),
                framework="react",
                project_type="frontend-web",
                build_tools=frozenset(
                    {
                        "vite",
                    }
                ),
            ),
            ProjectContext(
                name="api",
                root="services/api",
                languages=frozenset(
                    {
                        "typescript",
                    }
                ),
                framework="express",
                project_type="backend-api",
            ),
        ],
    )

    prompt = ReviewPromptBuilder.build(
        changed_file=changed_file,
        repository_context=context,
    )

    assert "Framework: react" in prompt

    assert "Framework: angular" not in prompt

    assert "Framework: express" not in prompt


def test_prompt_falls_back_to_repository_context_when_project_not_found():
    changed_file = ChangedFile(
        file_path="scripts/build.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="scripts/build.ts",
                line_number=5,
                content="runBuild();",
            )
        ],
    )

    context = RepositoryContext(
        languages={
            "typescript",
        },
        framework="angular",
        project_type="frontend-web",
        workspace="nx",
        projects=[
            ProjectContext(
                name="web",
                root="apps/web",
                languages=frozenset(
                    {
                        "typescript",
                    }
                ),
                framework="angular",
                project_type="frontend-web",
            ),
        ],
    )

    prompt = ReviewPromptBuilder.build(
        changed_file=changed_file,
        repository_context=context,
    )

    assert "Framework: angular" in prompt

    assert (
        "Project type: frontend-web"
        in prompt
    )


def test_prompt_uses_root_project_as_fallback():
    changed_file = ChangedFile(
        file_path="scripts/build.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="scripts/build.ts",
                line_number=5,
                content="runBuild();",
            )
        ],
    )

    context = RepositoryContext(
        framework="angular",
        project_type="frontend-web",
        projects=[
            ProjectContext(
                name="root",
                root=".",
                languages=frozenset(
                    {
                        "typescript",
                    }
                ),
                framework="unknown",
                project_type="unknown",
            ),
            ProjectContext(
                name="web",
                root="apps/web",
                languages=frozenset(
                    {
                        "typescript",
                    }
                ),
                framework="angular",
                project_type="frontend-web",
            ),
        ],
    )

    prompt = ReviewPromptBuilder.build(
        changed_file=changed_file,
        repository_context=context,
    )

    assert "Framework: unknown" in prompt

    assert "Project type: unknown" in prompt


def test_prompt_prefers_deepest_matching_project():
    changed_file = ChangedFile(
        file_path=(
            "apps/web/admin/src/App.tsx"
        ),
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path=(
                    "apps/web/admin/src/App.tsx"
                ),
                line_number=5,
                content="return <Admin />;",
            )
        ],
    )

    context = RepositoryContext(
        framework="unknown",
        projects=[
            ProjectContext(
                name="web",
                root="apps/web",
                framework="angular",
                project_type="frontend-web",
            ),
            ProjectContext(
                name="admin",
                root="apps/web/admin",
                framework="react",
                project_type="frontend-web",
            ),
        ],
    )

    prompt = ReviewPromptBuilder.build(
        changed_file=changed_file,
        repository_context=context,
    )

    assert "Framework: react" in prompt

    assert "Framework: angular" not in prompt


def test_prompt_resolves_project_with_windows_path():
    changed_file = ChangedFile(
        file_path=(
            "apps\\admin\\src\\App.tsx"
        ),
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path=(
                    "apps\\admin\\src\\App.tsx"
                ),
                line_number=10,
                content="return <Dashboard />;",
            )
        ],
    )

    context = RepositoryContext(
        framework="angular",
        workspace="nx",
        projects=[
            ProjectContext(
                name="admin",
                root="apps/admin",
                languages=frozenset(
                    {
                        "typescript",
                    }
                ),
                framework="react",
                project_type="frontend-web",
                build_tools=frozenset(
                    {
                        "vite",
                    }
                ),
            ),
        ],
    )

    prompt = ReviewPromptBuilder.build(
        changed_file=changed_file,
        repository_context=context,
    )

    assert "Framework: react" in prompt

    assert "Framework: angular" not in prompt
