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

    changed_lines = []

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
# Existing frontend contexts
# ======================================================


def test_build_angular_context():
    builder = RepositoryContextBuilder()

    files = [
        ChangedFile(
            file_path="angular.json",
            status="modified",
        ),
        ChangedFile(
            file_path="src/app/app.component.ts",
            status="modified",
        ),
        ChangedFile(
            file_path="package-lock.json",
            status="modified",
        ),
    ]

    context = builder.build(
        files
    )

    assert context.framework == "angular"
    assert context.project_type == "frontend-web"
    assert "typescript" in context.languages
    assert context.package_manager == "npm"
    assert (
        "angular.json"
        in context.metadata_files
    )


def test_build_react_context():
    builder = RepositoryContextBuilder()

    files = [
        ChangedFile(
            file_path="src/App.tsx",
            status="modified",
        ),
        ChangedFile(
            file_path="package.json",
            status="modified",
        ),
        ChangedFile(
            file_path="yarn.lock",
            status="modified",
        ),
    ]

    context = builder.build(
        files
    )

    assert context.framework == "react"
    assert "typescript" in context.languages
    assert context.package_manager == "yarn"


# ======================================================
# Python contexts
# ======================================================


def test_build_python_context():
    builder = RepositoryContextBuilder()

    files = [
        ChangedFile(
            file_path="src/service.py",
            status="modified",
        ),
        ChangedFile(
            file_path="pyproject.toml",
            status="modified",
        ),
        ChangedFile(
            file_path="uv.lock",
            status="modified",
        ),
    ]

    context = builder.build(
        files
    )

    assert "python" in context.languages
    assert context.framework == "unknown"
    assert context.package_manager == "uv"

    assert (
        "pyproject.toml"
        in context.metadata_files
    )


def test_build_django_context():
    builder = RepositoryContextBuilder()

    files = [
        create_changed_file(
            file_path="users/models.py",
            content=(
                "from django.db import models\n"
                "class User(models.Model):\n"
                "    pass"
            ),
        ),
        ChangedFile(
            file_path="requirements.txt",
            status="modified",
        ),
    ]

    context = builder.build(
        files
    )

    assert context.framework == "django"
    assert context.project_type == "backend"
    assert "python" in context.languages

    assert (
        context.package_manager
        == "pip"
    )


def test_build_fastapi_context():
    builder = RepositoryContextBuilder()

    files = [
        create_changed_file(
            file_path="main.py",
            content=(
                "from fastapi import FastAPI\n"
                "app = FastAPI()"
            ),
        )
    ]

    context = builder.build(
        files
    )

    assert context.framework == "fastapi"
    assert context.project_type == "backend"
    assert "python" in context.languages


def test_build_flask_context():
    builder = RepositoryContextBuilder()

    files = [
        create_changed_file(
            file_path="app.py",
            content=(
                "from flask import Flask\n"
                "app = Flask(__name__)"
            ),
        )
    ]

    context = builder.build(
        files
    )

    assert context.framework == "flask"
    assert context.project_type == "backend"


# ======================================================
# Java / Spring contexts
# ======================================================


def test_build_spring_boot_context():
    builder = RepositoryContextBuilder()

    files = [
        create_changed_file(
            file_path="src/Application.java",
            content=(
                "import "
                "org.springframework.boot."
                "autoconfigure."
                "SpringBootApplication;\n"
                "@SpringBootApplication\n"
                "public class Application {}"
            ),
        ),
        ChangedFile(
            file_path="pom.xml",
            status="modified",
        ),
    ]

    context = builder.build(
        files
    )

    assert context.framework == "spring-boot"
    assert context.project_type == "backend"
    assert "java" in context.languages
    assert context.package_manager == "maven"

    assert (
        "pom.xml"
        in context.metadata_files
    )


def test_build_gradle_context():
    builder = RepositoryContextBuilder()

    files = [
        ChangedFile(
            file_path="build.gradle.kts",
            status="modified",
        ),
        ChangedFile(
            file_path="src/Main.kt",
            status="modified",
        ),
    ]

    context = builder.build(
        files
    )

    assert "kotlin" in context.languages
    assert context.package_manager == "gradle"

    assert (
        "build.gradle.kts"
        in context.metadata_files
    )


# ======================================================
# .NET / ASP.NET Core contexts
# ======================================================


def test_build_aspnet_core_context():
    builder = RepositoryContextBuilder()

    files = [
        create_changed_file(
            file_path="Program.cs",
            content=(
                "var builder = "
                "WebApplication.CreateBuilder(args);\n"
                "builder.Services.AddControllers();"
            ),
        ),
        create_changed_file(
            file_path="SampleApi.csproj",
            content=(
                '<Project Sdk="Microsoft.NET.Sdk.Web">'
                "</Project>"
            ),
        ),
    ]

    context = builder.build(
        files
    )

    assert context.framework == "aspnet-core"
    assert context.project_type == "backend"
    assert "csharp" in context.languages
    assert context.package_manager == "dotnet"

    assert (
        "SampleApi.csproj"
        in context.metadata_files
    )


# ======================================================
# Node backend contexts
# ======================================================


def test_build_express_context():
    builder = RepositoryContextBuilder()

    files = [
        create_changed_file(
            file_path="src/server.js",
            content=(
                "const express = "
                "require('express');\n"
                "const app = express();"
            ),
        ),
        ChangedFile(
            file_path="package-lock.json",
            status="modified",
        ),
    ]

    context = builder.build(
        files
    )

    assert context.framework == "express"
    assert context.project_type == "backend"
    assert "javascript" in context.languages
    assert context.package_manager == "npm"


def test_build_nestjs_context():
    builder = RepositoryContextBuilder()

    files = [
        create_changed_file(
            file_path="src/app.controller.ts",
            content=(
                "import { Controller } "
                "from '@nestjs/common';\n"
                "@Controller('users')\n"
                "export class AppController {}"
            ),
        )
    ]

    context = builder.build(
        files
    )

    assert context.framework == "nestjs"
    assert context.project_type == "backend"
    assert "typescript" in context.languages


# ======================================================
# PHP / Laravel
# ======================================================


def test_build_laravel_context():
    builder = RepositoryContextBuilder()

    files = [
        create_changed_file(
            file_path="composer.json",
            content=(
                '{'
                '"require": {'
                '"laravel/framework": "^11.0"'
                '}'
                '}'
            ),
        ),
        ChangedFile(
            file_path="app/Http/Controllers/UserController.php",
            status="modified",
        ),
    ]

    context = builder.build(
        files
    )

    assert context.framework == "laravel"
    assert context.project_type == "backend"
    assert "php" in context.languages
    assert context.package_manager == "composer"

    assert (
        "composer.json"
        in context.metadata_files
    )


# ======================================================
# Ruby / Rails
# ======================================================


def test_build_rails_context():
    builder = RepositoryContextBuilder()

    files = [
        create_changed_file(
            file_path="config/application.rb",
            content=(
                "class Application "
                "< Rails::Application\n"
                "end"
            ),
        ),
        ChangedFile(
            file_path="Gemfile",
            status="modified",
        ),
    ]

    context = builder.build(
        files
    )

    assert context.framework == "rails"
    assert context.project_type == "backend"
    assert "ruby" in context.languages
    assert context.package_manager == "bundler"

    assert (
        "Gemfile"
        in context.metadata_files
    )


# ======================================================
# Other package managers
# ======================================================


def test_build_rust_context():
    builder = RepositoryContextBuilder()

    files = [
        ChangedFile(
            file_path="Cargo.toml",
            status="modified",
        ),
        ChangedFile(
            file_path="src/main.rs",
            status="modified",
        ),
    ]

    context = builder.build(
        files
    )

    assert "rust" in context.languages
    assert context.package_manager == "cargo"

    assert (
        "Cargo.toml"
        in context.metadata_files
    )


def test_build_go_context():
    builder = RepositoryContextBuilder()

    files = [
        ChangedFile(
            file_path="go.mod",
            status="modified",
        ),
        ChangedFile(
            file_path="cmd/main.go",
            status="modified",
        ),
    ]

    context = builder.build(
        files
    )

    assert "go" in context.languages

    assert (
        context.package_manager
        == "go-modules"
    )

    assert (
        "go.mod"
        in context.metadata_files
    )


# ======================================================
# Unknown / conservative behavior
# ======================================================


def test_plain_java_context_remains_framework_unknown():
    builder = RepositoryContextBuilder()

    files = [
        create_changed_file(
            file_path="src/UserService.java",
            content=(
                "public class UserService {}"
            ),
        )
    ]

    context = builder.build(
        files
    )

    assert "java" in context.languages
    assert context.framework == "unknown"
    assert context.project_type == "unknown"


def test_plain_python_context_remains_framework_unknown():
    builder = RepositoryContextBuilder()

    files = [
        create_changed_file(
            file_path="src/service.py",
            content=(
                "def calculate_total():\n"
                "    return 10"
            ),
        )
    ]

    context = builder.build(
        files
    )

    assert "python" in context.languages
    assert context.framework == "unknown"


def test_build_unknown_context():
    builder = RepositoryContextBuilder()

    files = [
        ChangedFile(
            file_path="assets/custom.abc",
            status="modified",
        )
    ]

    context = builder.build(
        files
    )

    assert context.languages == set()
    assert context.framework == "unknown"
    assert context.project_type == "unknown"

def test_repository_tree_context_detects_nested_nx_when_diff_has_only_tooling_files():
    changed_files = [
        ChangedFile(file_path="nx-angular-review/.agents/tool.mjs", status="modified")
    ]
    repository_files = [
        ChangedFile(file_path="nx-angular-review/nx.json", status="unchanged"),
        ChangedFile(file_path="nx-angular-review/package-lock.json", status="unchanged"),
        ChangedFile(file_path="nx-angular-review/apps/shop/package.json", status="unchanged"),
        ChangedFile(
            file_path="nx-angular-review/apps/shop/src/main.ts",
            status="unchanged",
            full_content="import { bootstrapApplication } from '@angular/platform-browser';",
        ),
        ChangedFile(file_path="nx-angular-review/packages/shared-ui/package.json", status="unchanged"),
        ChangedFile(
            file_path="nx-angular-review/packages/shared-ui/src/index.ts",
            status="unchanged",
            full_content="export { Component } from '@angular/core';",
        ),
    ]
    context = RepositoryContextBuilder().build(
        changed_files,
        repository_files=repository_files,
    )
    assert context.workspace == "nx"
    assert context.package_manager == "npm"
    roots = {project.root for project in context.projects}
    assert "nx-angular-review/apps/shop" in roots
    assert "nx-angular-review/packages/shared-ui" in roots
    shop = context.find_project_for_file("nx-angular-review/apps/shop/src/main.ts")
    assert shop is not None
    assert shop.framework == "angular"
