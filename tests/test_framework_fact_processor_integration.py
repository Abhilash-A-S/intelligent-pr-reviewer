from pr_reviewer.context.models import (
    RepositoryContext,
)
from pr_reviewer.review.models import (
    ChangedFile,
    ChangedLine,
    Finding,
    Severity,
)
from pr_reviewer.review.processor import (
    FindingProcessor,
)


def angular_context() -> RepositoryContext:

    return RepositoryContext(
        languages={
            "typescript",
            "json",
        },
        framework="angular",
        project_type="frontend-web",
    )


def test_processor_rejects_proven_framework_fact_hallucination():
    processor = FindingProcessor()

    changed_file = ChangedFile(
        file_path="src/app/app.config.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app/app.config.ts",
                line_number=11,
                content="provideRouter(routes),",
                diff_position=11,
            )
        ],
        full_content=(
            "import { ApplicationConfig } "
            "from '@angular/core';\n"
            "import { provideRouter } "
            "from '@angular/router';\n"
            "\n"
            "export const appConfig: "
            "ApplicationConfig = {\n"
            "  providers: [\n"
            "    provideRouter(routes),\n"
            "  ],\n"
            "};\n"
        ),
    )

    finding = Finding(
        file_path="src/app/app.config.ts",
        line_number=11,
        severity=Severity.HIGH,
        rule_id=(
            "angular-router-provide-router-misuse"
        ),
        message=(
            "The provideRouter provider should be "
            "used outside of the providers array."
        ),
        suggestion=(
            "Move provideRouter(routes) outside "
            "the providers array."
        ),
        diff_position=11,
    )

    result = processor.process(
        findings=[
            finding
        ],
        changed_files=[
            changed_file
        ],
        repository_context=angular_context(),
    )

    assert result == []


def test_processor_rejects_false_angular_typescript_incompatibility():
    processor = FindingProcessor()

    package_file = ChangedFile(
        file_path="package.json",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="package.json",
                line_number=41,
                content='"typescript": "~5.8.2"',
                diff_position=41,
            )
        ],
        full_content=(
            "{\n"
            '  "dependencies": {\n'
            '    "@angular/core": "^20.0.0"\n'
            "  },\n"
            '  "devDependencies": {\n'
            '    "typescript": "~5.8.2"\n'
            "  }\n"
            "}\n"
        ),
    )

    finding = Finding(
        file_path="package.json",
        line_number=41,
        severity=Severity.HIGH,
        rule_id=(
            "typescript-version-incompatibility"
        ),
        message=(
            "TypeScript version ~5.8.2 is not "
            "compatible with Angular ^20.0.0."
        ),
        suggestion=(
            "Change TypeScript to another version."
        ),
        diff_position=41,
    )

    result = processor.process(
        findings=[
            finding
        ],
        changed_files=[
            package_file
        ],
        repository_context=angular_context(),
    )

    assert result == []


def test_processor_rejects_empty_routes_false_positive():
    processor = FindingProcessor()

    changed_file = ChangedFile(
        file_path="src/app/app.routes.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app/app.routes.ts",
                line_number=3,
                content=(
                    "export const routes: Routes = [];"
                ),
                diff_position=3,
            )
        ],
        full_content=(
            "import { Routes } "
            "from '@angular/router';\n"
            "\n"
            "export const routes: Routes = [];\n"
        ),
    )

    finding = Finding(
        file_path="src/app/app.routes.ts",
        line_number=3,
        severity=Severity.LOW,
        rule_id="empty-routes-array",
        message=(
            "The routes array is empty."
        ),
        suggestion=(
            "Add at least one route."
        ),
        diff_position=3,
    )

    result = processor.process(
        findings=[
            finding
        ],
        changed_files=[
            changed_file
        ],
        repository_context=angular_context(),
    )

    assert result == []


def test_processor_rejects_false_express_catch_next_finding():
    processor = FindingProcessor()

    changed_file = ChangedFile(
        file_path="src/server.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/server.ts",
                line_number=38,
                content=".catch(next);",
                diff_position=38,
            )
        ],
        full_content=(
            "import express from 'express';\n"
            "\n"
            "const app = express();\n"
            "\n"
            "app.get('*', (req, res, next) => {\n"
            "  angularApp.handle(req)\n"
            "    .then(response => {\n"
            "      res.send(response);\n"
            "    })\n"
            "    .catch(next);\n"
            "});\n"
        ),
    )

    finding = Finding(
        file_path="src/server.ts",
        line_number=38,
        severity=Severity.MEDIUM,
        rule_id="async-catch-all-error",
        message=(
            "The .catch(next) method may mask errors "
            "and make debugging harder."
        ),
        suggestion=(
            "Use a different error handler."
        ),
        diff_position=38,
    )

    result = processor.process(
        findings=[
            finding
        ],
        changed_files=[
            changed_file
        ],
        repository_context=angular_context(),
    )

    assert result == []


def test_processor_preserves_real_framework_finding():
    processor = FindingProcessor()

    changed_file = ChangedFile(
        file_path="src/app/app.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app/app.ts",
                line_number=28,
                content=(
                    "interval(1000).subscribe("
                    "value => this.value = value);"
                ),
                diff_position=28,
            )
        ],
        full_content=(
            "interval(1000).subscribe("
            "value => this.value = value);"
        ),
    )

    finding = Finding(
        file_path="src/app/app.ts",
        line_number=28,
        severity=Severity.MEDIUM,
        rule_id=(
            "angular-rxjs-subscription-lifecycle"
        ),
        message=(
            "The interval subscription is not cleaned "
            "up when the component is destroyed."
        ),
        suggestion=(
            "Clean up the subscription when the "
            "component is destroyed."
        ),
        diff_position=28,
    )

    result = processor.process(
        findings=[
            finding
        ],
        changed_files=[
            changed_file
        ],
        repository_context=angular_context(),
    )

    assert len(result) == 1

    assert (
        result[0].rule_id
        == "angular-rxjs-subscription-lifecycle"
    )