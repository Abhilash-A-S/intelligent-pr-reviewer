from pr_reviewer.detection.framework import (
    FrameworkDetector,
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
# Frontend / JavaScript ecosystem
# ======================================================


def test_detect_angular():
    detector = FrameworkDetector()

    result = detector.detect_from_files(
        [
            "angular.json",
            "src/app/app.component.ts",
        ]
    )

    assert result.framework == "angular"
    assert result.project_type == "frontend-web"


def test_detect_angular_from_import_without_angular_json():
    detector = FrameworkDetector()

    files = [
        create_changed_file(
            file_path="src/app/app.component.ts",
            content=(
                "import { Component } "
                "from '@angular/core';\n"
                "@Component({})\n"
                "export class AppComponent {}"
            ),
        )
    ]

    result = detector.detect(
        files
    )

    assert result.framework == "angular"
    assert result.project_type == "frontend-web"


def test_angular_marker_has_precedence_over_express_dependency():
    detector = FrameworkDetector()

    files = [
        create_changed_file(
            file_path="angular.json",
            content=(
                '{"version": 1, "projects": {}}'
            ),
        ),
        create_changed_file(
            file_path="package.json",
            content=(
                "{"
                '"dependencies": {'
                '"@angular/core": "^20.0.0",'
                '"express": "^5.0.0"'
                "}"
                "}"
            ),
        ),
        create_changed_file(
            file_path="src/app/app.ts",
            content=(
                "import { Component } "
                "from '@angular/core';"
            ),
        ),
    ]

    result = detector.detect(
        files
    )

    assert result.framework == "angular"
    assert result.project_type == "frontend-web"


def test_angular_marker_has_precedence_over_express_source():
    detector = FrameworkDetector()

    files = [
        create_changed_file(
            file_path="angular.json",
            content=(
                '{"version": 1}'
            ),
        ),
        create_changed_file(
            file_path="src/app/app.ts",
            content=(
                "import { Component } "
                "from '@angular/core';"
            ),
        ),
        create_changed_file(
            file_path="tools/server.js",
            content=(
                "const express = "
                "require('express');\n"
                "const app = express();"
            ),
        ),
    ]

    result = detector.detect(
        files
    )

    assert result.framework == "angular"


def test_angular_marker_has_precedence_over_nestjs_dependency():
    detector = FrameworkDetector()

    files = [
        create_changed_file(
            file_path="angular.json",
            content=(
                '{"version": 1}'
            ),
        ),
        create_changed_file(
            file_path="package.json",
            content=(
                "{"
                '"dependencies": {'
                '"@angular/core": "^20.0.0",'
                '"@nestjs/core": "^11.0.0"'
                "}"
                "}"
            ),
        ),
    ]

    result = detector.detect(
        files
    )

    assert result.framework == "angular"


def test_detect_nextjs():
    detector = FrameworkDetector()

    result = detector.detect_from_files(
        [
            "next.config.js",
            "pages/index.tsx",
        ]
    )

    assert result.framework == "nextjs"
    assert result.project_type == "fullstack-web"


def test_nextjs_marker_has_precedence_over_express_dependency():
    detector = FrameworkDetector()

    files = [
        create_changed_file(
            file_path="next.config.ts",
            content=(
                "export default {};"
            ),
        ),
        create_changed_file(
            file_path="package.json",
            content=(
                "{"
                '"dependencies": {'
                '"next": "^15.0.0",'
                '"express": "^5.0.0"'
                "}"
                "}"
            ),
        ),
    ]

    result = detector.detect(
        files
    )

    assert result.framework == "nextjs"


def test_detect_vue():
    detector = FrameworkDetector()

    result = detector.detect_from_files(
        [
            "src/App.vue",
            "src/main.js",
        ]
    )

    assert result.framework == "vue"
    assert result.project_type == "frontend-web"


def test_detect_nuxt():
    detector = FrameworkDetector()

    result = detector.detect_from_files(
        [
            "nuxt.config.ts",
            "pages/index.vue",
        ]
    )

    assert result.framework == "nuxt"
    assert result.project_type == "fullstack-web"


def test_nuxt_marker_has_precedence_over_express_dependency():
    detector = FrameworkDetector()

    files = [
        create_changed_file(
            file_path="nuxt.config.ts",
            content=(
                "export default defineNuxtConfig({});"
            ),
        ),
        create_changed_file(
            file_path="package.json",
            content=(
                "{"
                '"dependencies": {'
                '"nuxt": "^4.0.0",'
                '"express": "^5.0.0"'
                "}"
                "}"
            ),
        ),
    ]

    result = detector.detect(
        files
    )

    assert result.framework == "nuxt"


def test_detect_react_native():
    detector = FrameworkDetector()

    result = detector.detect_from_files(
        [
            "app.json",
            "metro.config.js",
            "src/App.tsx",
        ]
    )

    assert result.framework == "react-native"
    assert result.project_type == "mobile"


def test_react_native_marker_has_precedence_over_express():
    detector = FrameworkDetector()

    files = [
        create_changed_file(
            file_path="metro.config.js",
            content=(
                "module.exports = {};"
            ),
        ),
        create_changed_file(
            file_path="package.json",
            content=(
                "{"
                '"dependencies": {'
                '"react-native": "^0.80.0",'
                '"express": "^5.0.0"'
                "}"
                "}"
            ),
        ),
    ]

    result = detector.detect(
        files
    )

    assert result.framework == "react-native"
    assert result.project_type == "mobile"


def test_detect_react():
    detector = FrameworkDetector()

    result = detector.detect_from_files(
        [
            "src/App.tsx",
            "src/components/User.tsx",
        ]
    )

    assert result.framework == "react"
    assert result.project_type == "frontend-web"


def test_detect_node():
    detector = FrameworkDetector()

    result = detector.detect_from_files(
        [
            "package.json",
            "src/server.js",
        ]
    )

    assert result.framework == "node"

    assert (
        result.project_type
        == "backend-or-javascript"
    )


# ======================================================
# Java / Spring
# ======================================================


def test_detect_spring_boot_from_import():
    detector = FrameworkDetector()

    files = [
        create_changed_file(
            file_path="src/Application.java",
            content=(
                "import "
                "org.springframework.boot."
                "SpringApplication;\n"
                "import "
                "org.springframework.boot."
                "autoconfigure."
                "SpringBootApplication;\n"
                "@SpringBootApplication\n"
                "public class Application {}"
            ),
        )
    ]

    result = detector.detect(
        files
    )

    assert result.framework == "spring-boot"
    assert result.project_type == "backend"


def test_detect_spring_boot_from_dependency():
    detector = FrameworkDetector()

    files = [
        create_changed_file(
            file_path="pom.xml",
            content=(
                "<dependency>"
                "<groupId>"
                "org.springframework.boot"
                "</groupId>"
                "<artifactId>"
                "spring-boot-starter-web"
                "</artifactId>"
                "</dependency>"
            ),
        )
    ]

    result = detector.detect(
        files
    )

    assert result.framework == "spring-boot"
    assert result.project_type == "backend"


def test_detect_spring_without_boot():
    detector = FrameworkDetector()

    files = [
        create_changed_file(
            file_path="src/UserController.java",
            content=(
                "import "
                "org.springframework.stereotype."
                "Controller;\n"
                "@Controller\n"
                "public class UserController {}"
            ),
        )
    ]

    result = detector.detect(
        files
    )

    assert result.framework == "spring"
    assert result.project_type == "backend"


def test_spring_controller_does_not_conflict_with_nestjs():
    detector = FrameworkDetector()

    files = [
        create_changed_file(
            file_path="src/UserController.java",
            content=(
                "import "
                "org.springframework.web.bind.annotation."
                "RestController;\n"
                "@RestController\n"
                "public class UserController {}"
            ),
        )
    ]

    result = detector.detect(
        files
    )

    assert result.framework == "spring"


# ======================================================
# C# / ASP.NET Core
# ======================================================


def test_detect_aspnet_core_from_using():
    detector = FrameworkDetector()

    files = [
        create_changed_file(
            file_path="Controllers/UserController.cs",
            content=(
                "using Microsoft.AspNetCore.Mvc;\n"
                "[ApiController]\n"
                "public class UserController "
                ": ControllerBase {}"
            ),
        )
    ]

    result = detector.detect(
        files
    )

    assert result.framework == "aspnet-core"
    assert result.project_type == "backend"


def test_detect_aspnet_core_from_program():
    detector = FrameworkDetector()

    files = [
        create_changed_file(
            file_path="Program.cs",
            content=(
                "var builder = "
                "WebApplication.CreateBuilder(args);\n"
                "builder.Services.AddControllers();\n"
                "var app = builder.Build();\n"
                "app.MapControllers();"
            ),
        )
    ]

    result = detector.detect(
        files
    )

    assert result.framework == "aspnet-core"
    assert result.project_type == "backend"


def test_detect_aspnet_core_from_csproj():
    detector = FrameworkDetector()

    files = [
        create_changed_file(
            file_path="SampleApi.csproj",
            content=(
                '<Project '
                'Sdk="Microsoft.NET.Sdk.Web">'
                "</Project>"
            ),
        )
    ]

    result = detector.detect(
        files
    )

    assert result.framework == "aspnet-core"


# ======================================================
# Python frameworks
# ======================================================


def test_detect_django_from_import():
    detector = FrameworkDetector()

    files = [
        create_changed_file(
            file_path="users/models.py",
            content=(
                "from django.db import models\n"
                "class User(models.Model):\n"
                "    pass"
            ),
        )
    ]

    result = detector.detect(
        files
    )

    assert result.framework == "django"
    assert result.project_type == "backend"


def test_detect_django_from_repository_structure():
    detector = FrameworkDetector()

    result = detector.detect_from_files(
        [
            "manage.py",
            "project/settings.py",
            "users/models.py",
        ]
    )

    assert result.framework == "django"


def test_detect_fastapi():
    detector = FrameworkDetector()

    files = [
        create_changed_file(
            file_path="main.py",
            content=(
                "from fastapi import FastAPI\n"
                "app = FastAPI()"
            ),
        )
    ]

    result = detector.detect(
        files
    )

    assert result.framework == "fastapi"
    assert result.project_type == "backend"


def test_detect_flask():
    detector = FrameworkDetector()

    files = [
        create_changed_file(
            file_path="app.py",
            content=(
                "from flask import Flask\n"
                "app = Flask(__name__)"
            ),
        )
    ]

    result = detector.detect(
        files
    )

    assert result.framework == "flask"
    assert result.project_type == "backend"


# ======================================================
# Node.js backend frameworks
# ======================================================


def test_detect_nestjs():
    detector = FrameworkDetector()

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

    result = detector.detect(
        files
    )

    assert result.framework == "nestjs"
    assert result.project_type == "backend"


def test_nestjs_has_precedence_over_generic_node():
    detector = FrameworkDetector()

    files = [
        create_changed_file(
            file_path="package.json",
            content=(
                "{"
                '"dependencies": {'
                '"@nestjs/core": "^11.0.0"'
                "}"
                "}"
            ),
        ),
        create_changed_file(
            file_path="src/main.ts",
            content=(
                "import { NestFactory } "
                "from '@nestjs/core';"
            ),
        ),
    ]

    result = detector.detect(
        files
    )

    assert result.framework == "nestjs"


def test_detect_express():
    detector = FrameworkDetector()

    files = [
        create_changed_file(
            file_path="src/server.js",
            content=(
                "const express = "
                "require('express');\n"
                "const app = express();"
            ),
        )
    ]

    result = detector.detect(
        files
    )

    assert result.framework == "express"
    assert result.project_type == "backend"


def test_pure_express_with_package_json_is_express():
    detector = FrameworkDetector()

    files = [
        create_changed_file(
            file_path="package.json",
            content=(
                "{"
                '"dependencies": {'
                '"express": "^5.0.0"'
                "}"
                "}"
            ),
        ),
        create_changed_file(
            file_path="src/server.js",
            content=(
                "const express = "
                "require('express');\n"
                "const app = express();"
            ),
        ),
    ]

    result = detector.detect(
        files
    )

    assert result.framework == "express"


# ======================================================
# PHP / Laravel
# ======================================================


def test_detect_laravel_from_dependency():
    detector = FrameworkDetector()

    files = [
        create_changed_file(
            file_path="composer.json",
            content=(
                "{"
                '"require": {'
                '"laravel/framework": "^11.0"'
                "}"
                "}"
            ),
        )
    ]

    result = detector.detect(
        files
    )

    assert result.framework == "laravel"
    assert result.project_type == "backend"


def test_detect_laravel_from_structure():
    detector = FrameworkDetector()

    result = detector.detect_from_files(
        [
            "artisan",
            "composer.json",
            "app/Http/Controllers/UserController.php",
        ]
    )

    assert result.framework == "laravel"


# ======================================================
# Ruby / Rails
# ======================================================


def test_detect_rails_from_content():
    detector = FrameworkDetector()

    files = [
        create_changed_file(
            file_path="config/application.rb",
            content=(
                "class Application "
                "< Rails::Application\n"
                "end"
            ),
        )
    ]

    result = detector.detect(
        files
    )

    assert result.framework == "rails"
    assert result.project_type == "backend"


def test_detect_rails_from_routes_file():
    detector = FrameworkDetector()

    result = detector.detect_from_files(
        [
            "config/routes.rb",
            "app/controllers/users_controller.rb",
        ]
    )

    assert result.framework == "rails"


# ======================================================
# Evidence / false-positive behavior
# ======================================================


def test_plain_java_does_not_become_spring():
    detector = FrameworkDetector()

    files = [
        create_changed_file(
            file_path="src/UserService.java",
            content=(
                "public class UserService {}"
            ),
        )
    ]

    result = detector.detect(
        files
    )

    assert result.framework == "unknown"


def test_plain_csharp_does_not_become_aspnet():
    detector = FrameworkDetector()

    files = [
        create_changed_file(
            file_path="src/UserService.cs",
            content=(
                "public class UserService {}"
            ),
        )
    ]

    result = detector.detect(
        files
    )

    assert result.framework == "unknown"


def test_plain_python_does_not_become_framework():
    detector = FrameworkDetector()

    files = [
        create_changed_file(
            file_path="src/service.py",
            content=(
                "def calculate_total():\n"
                "    return 10"
            ),
        )
    ]

    result = detector.detect(
        files
    )

    assert result.framework == "unknown"


def test_plain_typescript_without_framework_is_unknown():
    detector = FrameworkDetector()

    files = [
        create_changed_file(
            file_path="src/utils.ts",
            content=(
                "export function add("
                "a: number, b: number"
                "): number {\n"
                "    return a + b;\n"
                "}"
            ),
        )
    ]

    result = detector.detect(
        files
    )

    assert result.framework == "unknown"


def test_package_json_without_framework_is_node():
    detector = FrameworkDetector()

    files = [
        create_changed_file(
            file_path="package.json",
            content=(
                "{"
                '"name": "sample-project",'
                '"version": "1.0.0"'
                "}"
            ),
        ),
        create_changed_file(
            file_path="src/index.js",
            content=(
                "console.log('hello');"
            ),
        ),
    ]

    result = detector.detect(
        files
    )

    assert result.framework == "node"


def test_unknown_framework():
    detector = FrameworkDetector()

    result = detector.detect_from_files(
        [
            "src/service.py",
            "README.md",
        ]
    )

    assert result.framework == "unknown"
    assert result.project_type == "unknown"


# ======================================================
# Precedence regression coverage
# ======================================================


def test_angular_marker_beats_express_package_dependency():
    detector = FrameworkDetector()

    files = [
        create_changed_file(
            file_path="angular.json",
            content=(
                '{"version": 1}'
            ),
        ),
        create_changed_file(
            file_path="package.json",
            content=(
                "{"
                '"dependencies": {'
                '"express": "^5.0.0"'
                "}"
                "}"
            ),
        ),
    ]

    result = detector.detect(
        files
    )

    assert result.framework == "angular"


def test_angular_marker_beats_nestjs_package_dependency():
    detector = FrameworkDetector()

    files = [
        create_changed_file(
            file_path="angular.json",
            content=(
                '{"version": 1}'
            ),
        ),
        create_changed_file(
            file_path="package.json",
            content=(
                "{"
                '"dependencies": {'
                '"@nestjs/common": "^11.0.0"'
                "}"
                "}"
            ),
        ),
    ]

    result = detector.detect(
        files
    )

    assert result.framework == "angular"


def test_next_marker_beats_express():
    detector = FrameworkDetector()

    files = [
        create_changed_file(
            file_path="next.config.js",
            content=(
                "module.exports = {};"
            ),
        ),
        create_changed_file(
            file_path="package.json",
            content=(
                "{"
                '"dependencies": {'
                '"express": "^5.0.0"'
                "}"
                "}"
            ),
        ),
    ]

    result = detector.detect(
        files
    )

    assert result.framework == "nextjs"


def test_nuxt_marker_beats_express():
    detector = FrameworkDetector()

    files = [
        create_changed_file(
            file_path="nuxt.config.ts",
            content=(
                "export default defineNuxtConfig({});"
            ),
        ),
        create_changed_file(
            file_path="package.json",
            content=(
                "{"
                '"dependencies": {'
                '"express": "^5.0.0"'
                "}"
                "}"
            ),
        ),
    ]

    result = detector.detect(
        files
    )

    assert result.framework == "nuxt"


def test_react_native_marker_beats_express():
    detector = FrameworkDetector()

    files = [
        create_changed_file(
            file_path="metro.config.js",
            content=(
                "module.exports = {};"
            ),
        ),
        create_changed_file(
            file_path="package.json",
            content=(
                "{"
                '"dependencies": {'
                '"express": "^5.0.0"'
                "}"
                "}"
            ),
        ),
    ]

    result = detector.detect(
        files
    )

    assert result.framework == "react-native"


def test_spring_boot_regression_after_precedence_change():
    detector = FrameworkDetector()

    files = [
        create_changed_file(
            file_path="pom.xml",
            content=(
                "<dependency>"
                "<groupId>"
                "org.springframework.boot"
                "</groupId>"
                "<artifactId>"
                "spring-boot-starter-data-jpa"
                "</artifactId>"
                "</dependency>"
            ),
        ),
        create_changed_file(
            file_path="src/AccountService.java",
            content=(
                "import "
                "org.springframework.stereotype.Service;\n"
                "@Service\n"
                "public class AccountService {}"
            ),
        ),
    ]

    result = detector.detect(
        files
    )

    assert result.framework == "spring-boot"


def test_nestjs_regression_after_precedence_change():
    detector = FrameworkDetector()

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

    result = detector.detect(
        files
    )

    assert result.framework == "nestjs"


def test_express_regression_after_precedence_change():
    detector = FrameworkDetector()

    files = [
        create_changed_file(
            file_path="src/server.js",
            content=(
                "const express = "
                "require('express');\n"
                "const app = express();"
            ),
        )
    ]

    result = detector.detect(
        files
    )

    assert result.framework == "express"