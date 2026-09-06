from pr_reviewer.context.models import (
    RepositoryContext,
)
from pr_reviewer.review.framework_fact_validator import (
    FrameworkFactValidator,
)
from pr_reviewer.review.models import (
    ChangedFile,
    ChangedLine,
    Finding,
    Severity,
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


def react_context() -> RepositoryContext:

    return RepositoryContext(
        languages={
            "typescript",
            "javascript",
            "json",
        },
        framework="react",
        project_type="frontend-web",
    )


def unknown_context() -> RepositoryContext:

    return RepositoryContext(
        languages={
            "typescript",
            "json",
        },
        framework="unknown",
        project_type="unknown",
    )


def create_finding(
    file_path: str,
    line_number: int,
    rule_id: str,
    message: str,
    suggestion: str | None = None,
    severity: Severity = Severity.MEDIUM,
) -> Finding:

    return Finding(
        file_path=file_path,
        line_number=line_number,
        severity=severity,
        rule_id=rule_id,
        message=message,
        suggestion=suggestion,
    )


# ======================================================
# Angular / TypeScript compatibility
# ======================================================


def test_rejects_false_angular_typescript_incompatibility():
    validator = FrameworkFactValidator()

    package_file = ChangedFile(
        file_path="package.json",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="package.json",
                line_number=41,
                content='"typescript": "~5.8.2"',
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

    finding = create_finding(
        file_path="package.json",
        line_number=41,
        rule_id=(
            "typescript-version-incompatibility"
        ),
        severity=Severity.HIGH,
        message=(
            "TypeScript version ~5.8.2 is not "
            "compatible with Angular ^20.0.0."
        ),
        suggestion=(
            "Change the TypeScript version."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=package_file,
        changed_files=[
            package_file
        ],
        repository_context=angular_context(),
    )

    assert result.accepted is False

    assert (
        "Angular/TypeScript compatibility evidence"
        in result.reasons[0]
    )


def test_preserves_possible_real_typescript_incompatibility():
    validator = FrameworkFactValidator()

    package_file = ChangedFile(
        file_path="package.json",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="package.json",
                line_number=10,
                content='"typescript": "~5.7.3"',
            )
        ],
        full_content=(
            "{\n"
            '  "dependencies": {\n'
            '    "@angular/core": "^20.0.0"\n'
            "  },\n"
            '  "devDependencies": {\n'
            '    "typescript": "~5.7.3"\n'
            "  }\n"
            "}\n"
        ),
    )

    finding = create_finding(
        file_path="package.json",
        line_number=10,
        rule_id=(
            "typescript-version-incompatibility"
        ),
        message=(
            "TypeScript 5.7.3 is incompatible "
            "with Angular 20."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=package_file,
        changed_files=[
            package_file
        ],
        repository_context=angular_context(),
    )

    assert result.accepted is True


# ======================================================
# provideRouter
# ======================================================


def test_rejects_false_provide_router_misuse():
    validator = FrameworkFactValidator()

    changed_file = ChangedFile(
        file_path="src/app/app.config.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app/app.config.ts",
                line_number=11,
                content="provideRouter(routes),",
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

    finding = create_finding(
        file_path="src/app/app.config.ts",
        line_number=11,
        rule_id=(
            "angular-router-provide-router-misuse"
        ),
        severity=Severity.HIGH,
        message=(
            "The provideRouter provider should be "
            "used outside of the providers array."
        ),
        suggestion=(
            "Move provideRouter(routes) outside "
            "the providers array."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
        changed_files=[
            changed_file
        ],
        repository_context=angular_context(),
    )

    assert result.accepted is False

    assert (
        "provideRouter(...) is valid inside "
        "ApplicationConfig.providers"
        in result.reasons[0]
    )


def test_preserves_unrelated_router_finding():
    validator = FrameworkFactValidator()

    changed_file = ChangedFile(
        file_path="src/app/app.config.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app/app.config.ts",
                line_number=10,
                content="someRouterCall();",
            )
        ],
        full_content=(
            "someRouterCall();"
        ),
    )

    finding = create_finding(
        file_path="src/app/app.config.ts",
        line_number=10,
        rule_id="router-runtime-error",
        message=(
            "The router call receives an invalid value."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
        changed_files=[
            changed_file
        ],
        repository_context=angular_context(),
    )

    assert result.accepted is True


# ======================================================
# Empty Angular routes
# ======================================================


def test_rejects_empty_routes_as_automatic_defect():
    validator = FrameworkFactValidator()

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
            )
        ],
        full_content=(
            "import { Routes } "
            "from '@angular/router';\n"
            "\n"
            "export const routes: Routes = [];\n"
        ),
    )

    finding = create_finding(
        file_path="src/app/app.routes.ts",
        line_number=3,
        rule_id="empty-routes-array",
        severity=Severity.LOW,
        message=(
            "The routes array is empty. Ensure that "
            "routes are defined to handle navigation."
        ),
        suggestion=(
            "Add at least one route."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
        changed_files=[
            changed_file
        ],
        repository_context=angular_context(),
    )

    assert result.accepted is False

    assert (
        "empty Angular Routes array"
        in result.reasons[0]
    )


def test_preserves_routes_finding_when_routes_are_not_empty():
    validator = FrameworkFactValidator()

    changed_file = ChangedFile(
        file_path="src/app/app.routes.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app/app.routes.ts",
                line_number=5,
                content=(
                    "{ path: '', component: HomeComponent },"
                ),
            )
        ],
        full_content=(
            "import { Routes } "
            "from '@angular/router';\n"
            "\n"
            "export const routes: Routes = [\n"
            "  {\n"
            "    path: '',\n"
            "    component: HomeComponent,\n"
            "  },\n"
            "];\n"
        ),
    )

    finding = create_finding(
        file_path="src/app/app.routes.ts",
        line_number=5,
        rule_id="invalid-route-component",
        message=(
            "The route points to an invalid component."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
        changed_files=[
            changed_file
        ],
        repository_context=angular_context(),
    )

    assert result.accepted is True


# ======================================================
# Express fact validation
# ======================================================


def test_rejects_false_express_catch_next_finding():
    validator = FrameworkFactValidator()

    changed_file = ChangedFile(
        file_path="src/server.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/server.ts",
                line_number=38,
                content=".catch(next);",
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

    finding = create_finding(
        file_path="src/server.ts",
        line_number=38,
        rule_id="async-catch-all-error",
        message=(
            "The .catch(next) method masks errors "
            "and makes debugging harder."
        ),
        suggestion=(
            "Replace it with a custom error handler."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
        changed_files=[
            changed_file
        ],
        repository_context=angular_context(),
    )

    assert result.accepted is False

    assert (
        "Express error propagation semantics"
        in result.reasons[0]
    )


def test_does_not_assume_catch_next_is_express_without_evidence():
    validator = FrameworkFactValidator()

    changed_file = ChangedFile(
        file_path="src/service.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/service.ts",
                line_number=20,
                content=".catch(next);",
            )
        ],
        full_content=(
            "operation()\n"
            "  .catch(next);\n"
        ),
    )

    finding = create_finding(
        file_path="src/service.ts",
        line_number=20,
        rule_id="async-catch-all-error",
        message=(
            "The .catch(next) call masks an error."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
        changed_files=[
            changed_file
        ],
        repository_context=angular_context(),
    )

    assert result.accepted is True


# ======================================================
# Unrelated Angular semantic findings
# ======================================================


def test_unrelated_rxjs_finding_survives_fact_validation():
    validator = FrameworkFactValidator()

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
            )
        ],
    )

    finding = create_finding(
        file_path="src/app/app.ts",
        line_number=28,
        rule_id=(
            "angular-rxjs-subscription-lifecycle"
        ),
        message=(
            "The subscription is not cleaned up when "
            "the component is destroyed."
        ),
        suggestion=(
            "Clean up the subscription on destroy."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
        changed_files=[
            changed_file
        ],
        repository_context=angular_context(),
    )

    assert result.accepted is True


# ======================================================
# Project/package name vs folder-name regression
# ======================================================


def test_rejects_false_angular_project_name_folder_requirement():
    """
    Regression test for the real LLM false positive:

        angular-project-name-must-match-folder-name

    package.json name does not generally have to match the
    repository directory name.
    """

    validator = FrameworkFactValidator()

    package_file = ChangedFile(
        file_path="package.json",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="package.json",
                line_number=2,
                content='"name": "aitest",',
            )
        ],
        full_content=(
            "{\n"
            '  "name": "aitest",\n'
            '  "version": "0.0.0",\n'
            '  "dependencies": {\n'
            '    "@angular/core": "^20.0.0"\n'
            "  }\n"
            "}\n"
        ),
    )

    finding = create_finding(
        file_path="package.json",
        line_number=2,
        rule_id=(
            "angular-project-name-must-match-folder-name"
        ),
        severity=Severity.HIGH,
        message=(
            "The project name 'aitest' does not match "
            "the folder name 'package.json'. It should "
            "be updated to match the folder name for "
            "consistency."
        ),
        suggestion=(
            "Rename the project name to match the "
            "folder name."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=package_file,
        changed_files=[
            package_file
        ],
        repository_context=angular_context(),
    )

    assert result.accepted is False

    assert result.reasons

    assert (
        "does not impose that requirement"
        in result.reasons[0]
    )


def test_rejects_project_name_folder_mismatch_on_angular_json():
    validator = FrameworkFactValidator()

    changed_file = ChangedFile(
        file_path="angular.json",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="angular.json",
                line_number=5,
                content='"aitest": {',
            )
        ],
        full_content=(
            "{\n"
            '  "projects": {\n'
            '    "aitest": {\n'
            '      "projectType": "application"\n'
            "    }\n"
            "  }\n"
            "}\n"
        ),
    )

    finding = create_finding(
        file_path="angular.json",
        line_number=5,
        rule_id=(
            "project-name-folder-mismatch"
        ),
        severity=Severity.HIGH,
        message=(
            "The Angular project name does not match "
            "the folder name."
        ),
        suggestion=(
            "Rename the Angular project to match "
            "the folder."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
        changed_files=[
            changed_file
        ],
        repository_context=angular_context(),
    )

    assert result.accepted is False

    assert result.reasons

    assert (
        "does not impose that requirement"
        in result.reasons[0]
    )


def test_rejects_project_folder_claim_detected_from_message():
    """
    The protection must not depend on one exact LLM rule ID.

    LLM-generated rule IDs can vary between runs.
    """

    validator = FrameworkFactValidator()

    package_file = ChangedFile(
        file_path="package.json",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="package.json",
                line_number=2,
                content='"name": "dashboard",',
            )
        ],
        full_content=(
            "{\n"
            '  "name": "dashboard",\n'
            '  "dependencies": {\n'
            '    "@angular/core": "^20.0.0"\n'
            "  }\n"
            "}\n"
        ),
    )

    finding = create_finding(
        file_path="package.json",
        line_number=2,
        rule_id="angular-project-structure",
        severity=Severity.HIGH,
        message=(
            "The project name must match the folder "
            "name in an Angular application."
        ),
        suggestion=(
            "Change the project name so that it "
            "matches the folder name."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=package_file,
        changed_files=[
            package_file
        ],
        repository_context=angular_context(),
    )

    assert result.accepted is False

    assert result.reasons


def test_preserves_unrelated_package_json_finding():
    """
    The new Angular fact check must not suppress every
    package.json finding.
    """

    validator = FrameworkFactValidator()

    package_file = ChangedFile(
        file_path="package.json",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="package.json",
                line_number=10,
                content=(
                    '"build": "ng build --configuration production"'
                ),
            )
        ],
        full_content=(
            "{\n"
            '  "name": "aitest",\n'
            '  "scripts": {\n'
            '    "build": '
            '"ng build --configuration production"\n'
            "  }\n"
            "}\n"
        ),
    )

    finding = create_finding(
        file_path="package.json",
        line_number=10,
        rule_id="invalid-build-command",
        severity=Severity.HIGH,
        message=(
            "The build command references an invalid "
            "configuration."
        ),
        suggestion=(
            "Correct the referenced Angular build "
            "configuration."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=package_file,
        changed_files=[
            package_file
        ],
        repository_context=angular_context(),
    )

    assert result.accepted is True


def test_preserves_folder_name_finding_on_source_file():
    """
    The folder-name protection is specifically about
    Angular/package metadata claims.

    It must not suppress an unrelated source-code finding
    simply because its wording contains 'folder name'.
    """

    validator = FrameworkFactValidator()

    changed_file = ChangedFile(
        file_path="src/app/path.service.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app/path.service.ts",
                line_number=20,
                content=(
                    "return folderName;"
                ),
            )
        ],
        full_content=(
            "export class PathService {\n"
            "  getFolderName() {\n"
            "    return folderName;\n"
            "  }\n"
            "}\n"
        ),
    )

    finding = create_finding(
        file_path="src/app/path.service.ts",
        line_number=20,
        rule_id=(
            "project-name-folder-mismatch"
        ),
        message=(
            "The project name does not match the "
            "folder name used by this runtime path."
        ),
        suggestion=(
            "Correct the runtime folder mapping."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=changed_file,
        changed_files=[
            changed_file
        ],
        repository_context=angular_context(),
    )

    assert result.accepted is True


def test_project_name_folder_claim_is_not_rejected_for_react_repository():
    """
    Angular fact validation must not leak into a
    non-Angular repository.
    """

    validator = FrameworkFactValidator()

    package_file = ChangedFile(
        file_path="package.json",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="package.json",
                line_number=2,
                content='"name": "frontend",',
            )
        ],
        full_content=(
            "{\n"
            '  "name": "frontend",\n'
            '  "dependencies": {\n'
            '    "react": "^19.0.0"\n'
            "  }\n"
            "}\n"
        ),
    )

    finding = create_finding(
        file_path="package.json",
        line_number=2,
        rule_id=(
            "angular-project-name-must-match-folder-name"
        ),
        severity=Severity.HIGH,
        message=(
            "The project name does not match "
            "the folder name."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=package_file,
        changed_files=[
            package_file
        ],
        repository_context=react_context(),
    )

    assert result.accepted is True


def test_project_name_folder_claim_is_not_rejected_for_unknown_framework():
    """
    Unknown/custom frameworks should not inherit Angular
    fact assumptions.
    """

    validator = FrameworkFactValidator()

    package_file = ChangedFile(
        file_path="package.json",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="package.json",
                line_number=2,
                content='"name": "custom-app",',
            )
        ],
        full_content=(
            "{\n"
            '  "name": "custom-app"\n'
            "}\n"
        ),
    )

    finding = create_finding(
        file_path="package.json",
        line_number=2,
        rule_id=(
            "project-name-folder-mismatch"
        ),
        severity=Severity.HIGH,
        message=(
            "The project name does not match "
            "the folder name."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=package_file,
        changed_files=[
            package_file
        ],
        repository_context=unknown_context(),
    )

    assert result.accepted is True

def test_rejects_false_selector_instead_of_component_class_for_testbed():
    """
    Regression test for the real Angular LLM false positive:

        angular-standalone-component-configuration

    A standalone Angular component is imported into
    TestBed using its TypeScript component class.

    The component selector is for templates and is not
    a replacement for the class reference.
    """

    validator = FrameworkFactValidator()

    test_file = ChangedFile(
        file_path="src/app/app.spec.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app/app.spec.ts",
                line_number=8,
                content="imports: [App]",
            )
        ],
        full_content=(
            "import { TestBed } "
            "from '@angular/core/testing';\n"
            "import { App } "
            "from './app';\n"
            "\n"
            "describe('App', () => {\n"
            "  beforeEach(async () => {\n"
            "    await TestBed.configureTestingModule({\n"
            "      imports: [App],\n"
            "    }).compileComponents();\n"
            "  });\n"
            "});\n"
        ),
    )

    component_file = ChangedFile(
        file_path="src/app/app.ts",
        status="modified",
        full_content=(
            "import { Component } "
            "from '@angular/core';\n"
            "\n"
            "@Component({\n"
            "  selector: 'app-root',\n"
            "  standalone: true,\n"
            "  template: '<h1>Hello</h1>',\n"
            "})\n"
            "export class App {}\n"
        ),
    )

    finding = create_finding(
        file_path="src/app/app.spec.ts",
        line_number=8,
        rule_id=(
            "angular-standalone-component-configuration"
        ),
        severity=Severity.MEDIUM,
        message=(
            "The component should be imported using "
            "the component's selector instead of the "
            "component's class name."
        ),
        suggestion=(
            "Change `imports: [App]` to "
            "`imports: [AppComponent]`."
        ),
    )

    result = validator.validate(
        finding=finding,
        changed_file=test_file,
        changed_files=[
            test_file,
            component_file,
        ],
        repository_context=angular_context(),
    )

    assert result.accepted is False

    assert result.reasons

    assert (
        "standalone-component evidence"
        in result.reasons[0]
    )

    assert (
        "'App' is valid in TestBed imports"
        in result.reasons[0]
    )

def test_rejects_false_standalone_class_import_claim_disguised_as_api_misuse():
    validator = FrameworkFactValidator()

    test_file = ChangedFile(
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
            "import { TestBed } from '@angular/core/testing';\n"
            "import { App } from './app';\n"
            "describe('App', () => {\n"
            "  beforeEach(async () => {\n"
            "    await TestBed.configureTestingModule({\n"
            "      imports: [App],\n"
            "    }).compileComponents();\n"
            "  });\n"
            "});\n"
        ),
    )
    component_file = ChangedFile(
        file_path="src/app/app.ts",
        status="modified",
        full_content=(
            "import { Component } from '@angular/core';\n"
            "@Component({ selector: 'app-root', standalone: true, template: '' })\n"
            "export class App {}\n"
        ),
    )
    finding = create_finding(
        file_path="src/app/app.spec.ts",
        line_number=8,
        rule_id="api-misuse",
        message=(
            "Using `App` directly in imports is incorrect. Standalone components "
            "should be imported using their names, not the component class."
        ),
        suggestion="Import the component using its name, e.g. imports: [AppComponent].",
    )

    result = validator.validate(
        finding=finding,
        changed_file=test_file,
        changed_files=[test_file, component_file],
        repository_context=angular_context(),
    )

    assert result.accepted is False
    assert any("standalone-component evidence" in reason for reason in result.reasons)


def test_rejects_subscription_cleanup_claim_for_finite_angular_httpclient_request():
    validator = FrameworkFactValidator()
    source_file = ChangedFile(
        file_path="src/app/review-test.ts",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app/review-test.ts",
                line_number=9,
                content="    }).subscribe()",
            )
        ],
        full_content=(
            "import { HttpClient } from '@angular/common/http';\n"
            "export class ReviewTest {\n"
            "  constructor(private http: HttpClient) {}\n"
            "  save(): void {\n"
            "    this.http.post('/api/save', {\n"
            "      username: this.username,\n"
            "    }).subscribe()\n"
            "  }\n"
            "}\n"
        ),
    )
    finding = create_finding(
        file_path="src/app/review-test.ts",
        line_number=9,
        rule_id="subscription-cleanup",
        severity=Severity.HIGH,
        message="Observable subscription is created but never cleaned up, which can lead to memory leaks.",
        suggestion="Unsubscribe when the component is destroyed.",
    )

    result = validator.validate(
        finding=finding,
        changed_file=source_file,
        changed_files=[source_file],
        repository_context=angular_context(),
    )

    assert result.accepted is False
    assert any("HttpClient request Observables are finite" in reason for reason in result.reasons)
