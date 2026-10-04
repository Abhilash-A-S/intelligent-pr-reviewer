from dataclasses import dataclass

from pr_reviewer.review.models import ChangedFile


@dataclass(frozen=True)
class ProjectContext:
    framework: str
    project_type: str


class FrameworkDetector:
    """
    Detects the primary framework/application type using
    repository evidence.

    Evidence can come from:

    - well-known configuration filenames
    - source-file extensions
    - package/dependency manifests
    - imports/usings/package declarations
    - framework-specific source patterns

    Detection precedence matters.

    Strong repository markers such as:

        angular.json
        next.config.*
        nuxt.config.*
        metro.config.*

    are evaluated before weaker dependency/content signals.

    This prevents cases such as an Angular workspace being
    incorrectly classified as Express merely because Express
    appears in package.json.

    The detector is intentionally conservative.

    If there is not enough evidence to identify a framework
    confidently, it returns "unknown" rather than guessing.

    Nx is intentionally NOT treated as Angular.

    Nx/multi-framework/monorepo detection belongs to the
    next architecture phase, where repository-level and
    per-project framework context can be represented
    separately.
    """

    def detect(
        self,
        changed_files: list[ChangedFile],
    ) -> ProjectContext:

        normalized_paths = [
            self._normalize_path(
                changed_file.file_path
            )
            for changed_file in changed_files
        ]

        combined_content = self._combine_content(
            changed_files
        )

        # ==================================================
        # 1. Strong repository/framework markers
        # ==================================================
        #
        # These markers are much stronger evidence than
        # generic package dependencies.
        #
        # Example:
        #
        # angular.json + Express dependency
        #
        # should still identify the repository as Angular
        # for the current single-framework context model.
        # ==================================================

        if self._has_angular_marker(
            normalized_paths
        ):
            return ProjectContext(
                framework="angular",
                project_type="frontend-web",
            )

        if self._has_nextjs_marker(
            normalized_paths
        ):
            return ProjectContext(
                framework="nextjs",
                project_type="fullstack-web",
            )

        if self._has_nuxt_marker(
            normalized_paths
        ):
            return ProjectContext(
                framework="nuxt",
                project_type="fullstack-web",
            )

        if self._has_react_native_marker(
            normalized_paths
        ):
            return ProjectContext(
                framework="react-native",
                project_type="mobile",
            )

        # ==================================================
        # 2. Java / JVM
        # ==================================================

        if self._is_spring_boot(
            normalized_paths=normalized_paths,
            combined_content=combined_content,
        ):
            return ProjectContext(
                framework="spring-boot",
                project_type="backend",
            )

        if self._is_spring(
            normalized_paths=normalized_paths,
            combined_content=combined_content,
        ):
            return ProjectContext(
                framework="spring",
                project_type="backend",
            )

        # ==================================================
        # 3. .NET
        # ==================================================

        if self._is_aspnet_core(
            normalized_paths=normalized_paths,
            combined_content=combined_content,
        ):
            return ProjectContext(
                framework="aspnet-core",
                project_type="backend",
            )

        # ==================================================
        # 4. Python
        # ==================================================

        if self._is_django(
            normalized_paths=normalized_paths,
            combined_content=combined_content,
        ):
            return ProjectContext(
                framework="django",
                project_type="backend",
            )

        if self._is_fastapi(
            normalized_paths=normalized_paths,
            combined_content=combined_content,
        ):
            return ProjectContext(
                framework="fastapi",
                project_type="backend",
            )

        if self._is_flask(
            normalized_paths=normalized_paths,
            combined_content=combined_content,
        ):
            return ProjectContext(
                framework="flask",
                project_type="backend",
            )

        # ==================================================
        # 5. PHP
        # ==================================================

        if self._is_laravel(
            normalized_paths=normalized_paths,
            combined_content=combined_content,
        ):
            return ProjectContext(
                framework="laravel",
                project_type="backend",
            )

        # ==================================================
        # 6. Ruby
        # ==================================================

        if self._is_rails(
            normalized_paths=normalized_paths,
            combined_content=combined_content,
        ):
            return ProjectContext(
                framework="rails",
                project_type="backend",
            )

        # ==================================================
        # 7. JavaScript / TypeScript backend frameworks
        # ==================================================
        #
        # NestJS must come before generic Express.
        # ==================================================

        if self._is_nestjs(
            normalized_paths=normalized_paths,
            combined_content=combined_content,
        ):
            return ProjectContext(
                framework="nestjs",
                project_type="backend",
            )

        if self._is_express(
            normalized_paths=normalized_paths,
            combined_content=combined_content,
        ):
            return ProjectContext(
                framework="express",
                project_type="backend",
            )

        # ==================================================
        # 8. Frontend / universal framework evidence
        # ==================================================
        #
        # Marker-based checks already happened above.
        #
        # These methods can still identify frameworks from
        # imports/dependencies when their config file is not
        # present in the changed-file set.
        # ==================================================

        if self._is_angular(
            normalized_paths=normalized_paths,
            combined_content=combined_content,
        ):
            return ProjectContext(
                framework="angular",
                project_type="frontend-web",
            )

        if self._is_nextjs(
            normalized_paths=normalized_paths,
            combined_content=combined_content,
        ):
            return ProjectContext(
                framework="nextjs",
                project_type="fullstack-web",
            )

        if self._is_nuxt(
            normalized_paths=normalized_paths,
            combined_content=combined_content,
        ):
            return ProjectContext(
                framework="nuxt",
                project_type="fullstack-web",
            )

        if self._is_react_native(
            normalized_paths=normalized_paths,
            combined_content=combined_content,
        ):
            return ProjectContext(
                framework="react-native",
                project_type="mobile",
            )

        if self._is_vue(
            normalized_paths=normalized_paths,
            combined_content=combined_content,
        ):
            return ProjectContext(
                framework="vue",
                project_type="frontend-web",
            )

        if self._is_react(
            normalized_paths=normalized_paths,
            combined_content=combined_content,
        ):
            return ProjectContext(
                framework="react",
                project_type="frontend-web",
            )

        # ==================================================
        # 9. Generic Node.js
        # ==================================================

        if self._is_node(
            normalized_paths=normalized_paths,
            combined_content=combined_content,
        ):
            return ProjectContext(
                framework="node",
                project_type="backend-or-javascript",
            )

        return ProjectContext(
            framework="unknown",
            project_type="unknown",
        )

    def detect_from_files(
        self,
        file_paths: list[str],
    ) -> ProjectContext:
        """
        Backwards-compatible filename-only detection.

        New review code should prefer detect(), because
        detect() can also inspect source/config content.
        """

        changed_files = [
            ChangedFile(
                file_path=file_path,
                status="modified",
            )
            for file_path in file_paths
        ]

        return self.detect(
            changed_files
        )

    # ======================================================
    # Strong repository marker detection
    # ======================================================

    @staticmethod
    def _has_angular_marker(
        normalized_paths: list[str],
    ) -> bool:

        file_names = {
            path.split("/")[-1]
            for path in normalized_paths
        }

        return "angular.json" in file_names

    @staticmethod
    def _has_nextjs_marker(
        normalized_paths: list[str],
    ) -> bool:

        return any(
            path.endswith(
                (
                    "next.config.js",
                    "next.config.mjs",
                    "next.config.ts",
                    "next.config.cjs",
                )
            )
            for path in normalized_paths
        )

    @staticmethod
    def _has_nuxt_marker(
        normalized_paths: list[str],
    ) -> bool:

        return any(
            path.endswith(
                (
                    "nuxt.config.js",
                    "nuxt.config.ts",
                    "nuxt.config.mjs",
                    "nuxt.config.cjs",
                )
            )
            for path in normalized_paths
        )

    @staticmethod
    def _has_react_native_marker(
        normalized_paths: list[str],
    ) -> bool:

        file_names = {
            path.split("/")[-1]
            for path in normalized_paths
        }

        return bool(
            {
                "metro.config.js",
                "metro.config.cjs",
                "metro.config.mjs",
            }
            & file_names
        )

    # ======================================================
    # Java / Spring
    # ======================================================

    def _is_spring_boot(
        self,
        normalized_paths: list[str],
        combined_content: str,
    ) -> bool:

        if (
            not self._has_java_or_jvm_file(
                normalized_paths
            )
            and not self._has_java_build_file(
                normalized_paths
            )
        ):
            return False

        if self._contains_any(
            combined_content,
            (
                "org.springframework.boot",
                "@springbootapplication",
                "spring-boot-starter",
                "springframework.boot",
            ),
        ):
            return True

        has_application_config = any(
            path.endswith(
                (
                    "application.properties",
                    "application.yml",
                    "application.yaml",
                )
            )
            for path in normalized_paths
        )

        if (
            has_application_config
            and self._contains_any(
                combined_content,
                (
                    "spring.",
                    "springframework",
                ),
            )
        ):
            return True

        return False

    def _is_spring(
        self,
        normalized_paths: list[str],
        combined_content: str,
    ) -> bool:

        if not self._has_java_or_jvm_file(
            normalized_paths
        ):
            return False

        if self._contains_any(
            combined_content,
            (
                "org.springframework.",
                "springframework.",
            ),
        ):
            return True

        return self._contains_any(
            combined_content,
            (
                "@restcontroller",
                "@controller",
                "@service",
                "@repository",
                "@autowired",
                "@component",
            ),
        )

    # ======================================================
    # C# / ASP.NET Core
    # ======================================================

    def _is_aspnet_core(
        self,
        normalized_paths: list[str],
        combined_content: str,
    ) -> bool:

        if not self._has_extension(
            normalized_paths,
            (
                ".cs",
                ".csproj",
            ),
        ):
            return False

        if self._contains_any(
            combined_content,
            (
                "microsoft.aspnetcore",
                "webapplication.createbuilder",
                "addcontrollers(",
                "mapcontrollers(",
                "controllerbase",
                "[apicontroller]",
            ),
        ):
            return True

        return (
            any(
                path.endswith(".csproj")
                for path in normalized_paths
            )
            and self._contains_any(
                combined_content,
                (
                    "microsoft.net.sdk.web",
                    "aspnetcore",
                ),
            )
        )

    # ======================================================
    # Python
    # ======================================================

    def _is_django(
        self,
        normalized_paths: list[str],
        combined_content: str,
    ) -> bool:

        if (
            not self._has_extension(
                normalized_paths,
                (".py",),
            )
            and not self._has_python_metadata(
                normalized_paths
            )
        ):
            return False

        if self._contains_any(
            combined_content,
            (
                "from django",
                "import django",
                "django.",
                "django==",
                "django>=",
            ),
        ):
            return True

        file_names = {
            path.split("/")[-1]
            for path in normalized_paths
        }

        return (
            "manage.py" in file_names
            and "settings.py" in file_names
        )

    def _is_fastapi(
        self,
        normalized_paths: list[str],
        combined_content: str,
    ) -> bool:

        if (
            not self._has_extension(
                normalized_paths,
                (".py",),
            )
            and not self._has_python_metadata(
                normalized_paths
            )
        ):
            return False

        return self._contains_any(
            combined_content,
            (
                "from fastapi",
                "import fastapi",
                "fastapi(",
                "fastapi==",
                "fastapi>=",
            ),
        )

    def _is_flask(
        self,
        normalized_paths: list[str],
        combined_content: str,
    ) -> bool:

        if (
            not self._has_extension(
                normalized_paths,
                (".py",),
            )
            and not self._has_python_metadata(
                normalized_paths
            )
        ):
            return False

        return self._contains_any(
            combined_content,
            (
                "from flask",
                "import flask",
                "flask(",
                "flask==",
                "flask>=",
            ),
        )

    # ======================================================
    # PHP / Laravel
    # ======================================================

    def _is_laravel(
        self,
        normalized_paths: list[str],
        combined_content: str,
    ) -> bool:

        if self._contains_any(
            combined_content,
            (
                "illuminate\\",
                "laravel/framework",
            ),
        ):
            return True

        file_names = {
            path.split("/")[-1]
            for path in normalized_paths
        }

        return (
            "artisan" in file_names
            and "composer.json" in file_names
        )

    # ======================================================
    # Ruby / Rails
    # ======================================================

    def _is_rails(
        self,
        normalized_paths: list[str],
        combined_content: str,
    ) -> bool:

        if (
            not self._has_extension(
                normalized_paths,
                (".rb",),
            )
            and not self._has_ruby_metadata(
                normalized_paths
            )
        ):
            return False

        if self._contains_any(
            combined_content,
            (
                "rails::application",
                "rails.application",
                "activerecord::base",
                "actioncontroller::base",
                'gem "rails"',
                "gem 'rails'",
            ),
        ):
            return True

        normalized_set = set(
            normalized_paths
        )

        return (
            "config/routes.rb"
            in normalized_set
        )

    # ======================================================
    # Node.js backend frameworks
    # ======================================================

    def _is_nestjs(
        self,
        normalized_paths: list[str],
        combined_content: str,
    ) -> bool:

        if (
            not self._has_javascript_or_typescript_file(
                normalized_paths
            )
            and not self._has_node_metadata(
                normalized_paths
            )
        ):
            return False

        return self._contains_any(
            combined_content,
            (
                "@nestjs/common",
                "@nestjs/core",
                "nestfactory",
                '"@nestjs/common"',
                '"@nestjs/core"',
                "'@nestjs/common'",
                "'@nestjs/core'",
            ),
        )

    def _is_express(
        self,
        normalized_paths: list[str],
        combined_content: str,
    ) -> bool:

        if (
            not self._has_javascript_or_typescript_file(
                normalized_paths
            )
            and not self._has_node_metadata(
                normalized_paths
            )
        ):
            return False

        return self._contains_any(
            combined_content,
            (
                'from "express"',
                "from 'express'",
                'require("express")',
                "require('express')",
                "express()",
                '"express":',
                "'express':",
            ),
        )

    # ======================================================
    # Frontend frameworks
    # ======================================================

    def _is_angular(
        self,
        normalized_paths: list[str],
        combined_content: str,
    ) -> bool:

        if self._has_angular_marker(
            normalized_paths
        ):
            return True

        # Nx project.json/package metadata can prove Angular ownership even
        # when the representative source file is a barrel with no imports.
        if self._contains_any(
            combined_content,
            (
                "@nx/angular",
                "@angular-devkit/build-angular",
                "@angular/compiler-cli",
            ),
        ):
            return True

        if not self._has_javascript_or_typescript_file(
            normalized_paths
        ):
            return False

        return self._contains_any(
            combined_content,
            (
                "@angular/core",
                "@angular/common",
                "@angular/router",
                "@angular/forms",
                "@angular/platform-browser",
            ),
        )

    def _is_nextjs(
        self,
        normalized_paths: list[str],
        combined_content: str,
    ) -> bool:

        if self._has_nextjs_marker(
            normalized_paths
        ):
            return True

        return self._contains_any(
            combined_content,
            (
                'from "next/',
                "from 'next/",
                '"next":',
                "'next':",
            ),
        )

    def _is_nuxt(
        self,
        normalized_paths: list[str],
        combined_content: str,
    ) -> bool:

        if self._has_nuxt_marker(
            normalized_paths
        ):
            return True

        return self._contains_any(
            combined_content,
            (
                "definenuxtconfig",
                '"nuxt":',
                "'nuxt':",
            ),
        )

    def _is_vue(
        self,
        normalized_paths: list[str],
        combined_content: str,
    ) -> bool:

        if any(
            path.endswith(".vue")
            for path in normalized_paths
        ):
            return True

        return self._contains_any(
            combined_content,
            (
                'from "vue"',
                "from 'vue'",
                "createapp(",
                '"vue":',
                "'vue':",
            ),
        )

    def _is_react_native(
        self,
        normalized_paths: list[str],
        combined_content: str,
    ) -> bool:

        if self._has_react_native_marker(
            normalized_paths
        ):
            return True

        return self._contains_any(
            combined_content,
            (
                'from "react-native"',
                "from 'react-native'",
                '"react-native":',
                "'react-native':",
            ),
        )

    def _is_react(
        self,
        normalized_paths: list[str],
        combined_content: str,
    ) -> bool:

        if self._contains_any(
            combined_content,
            (
                'from "react"',
                "from 'react'",
                "reactdom",
                "usestate(",
                "useeffect(",
                '"react":',
                "'react':",
            ),
        ):
            return True

        return any(
            path.endswith(
                (
                    ".jsx",
                    ".tsx",
                )
            )
            for path in normalized_paths
        )

    # ======================================================
    # Generic Node.js
    # ======================================================

    def _is_node(
        self,
        normalized_paths: list[str],
        combined_content: str,
    ) -> bool:

        file_names = {
            path.split("/")[-1]
            for path in normalized_paths
        }

        if "package.json" in file_names:
            return True

        if not self._has_javascript_or_typescript_file(
            normalized_paths
        ):
            return False

        return self._contains_any(
            combined_content,
            (
                "require(",
                "module.exports",
                "process.env",
                "node:",
            ),
        )

    # ======================================================
    # Language / repository evidence helpers
    # ======================================================

    @classmethod
    def _has_java_or_jvm_file(
        cls,
        normalized_paths: list[str],
    ) -> bool:

        return cls._has_extension(
            normalized_paths,
            (
                ".java",
                ".kt",
                ".kts",
                ".scala",
            ),
        )

    @staticmethod
    def _has_java_build_file(
        normalized_paths: list[str],
    ) -> bool:

        file_names = {
            path.split("/")[-1]
            for path in normalized_paths
        }

        return bool(
            {
                "pom.xml",
                "build.gradle",
                "build.gradle.kts",
            }
            & file_names
        )

    @classmethod
    def _has_javascript_or_typescript_file(
        cls,
        normalized_paths: list[str],
    ) -> bool:

        return cls._has_extension(
            normalized_paths,
            (
                ".js",
                ".jsx",
                ".mjs",
                ".cjs",
                ".ts",
                ".tsx",
            ),
        )

    @staticmethod
    def _has_node_metadata(
        normalized_paths: list[str],
    ) -> bool:

        file_names = {
            path.split("/")[-1]
            for path in normalized_paths
        }

        return "package.json" in file_names

    @staticmethod
    def _has_python_metadata(
        normalized_paths: list[str],
    ) -> bool:

        file_names = {
            path.split("/")[-1]
            for path in normalized_paths
        }

        return bool(
            {
                "requirements.txt",
                "pyproject.toml",
                "poetry.lock",
                "uv.lock",
            }
            & file_names
        )

    @staticmethod
    def _has_ruby_metadata(
        normalized_paths: list[str],
    ) -> bool:

        file_names = {
            path.split("/")[-1]
            for path in normalized_paths
        }

        return (
            "gemfile"
            in file_names
        )

    @staticmethod
    def _has_extension(
        normalized_paths: list[str],
        extensions: tuple[str, ...],
    ) -> bool:

        return any(
            path.endswith(
                extensions
            )
            for path in normalized_paths
        )

    # ======================================================
    # General helpers
    # ======================================================

    @staticmethod
    def _combine_content(
        changed_files: list[ChangedFile],
    ) -> str:

        contents: list[str] = []

        for changed_file in changed_files:

            if changed_file.full_content:
                contents.append(
                    changed_file.full_content
                )
                continue

            if changed_file.changed_lines:
                contents.append(
                    "\n".join(
                        line.content
                        for line
                        in changed_file.changed_lines
                    )
                )

        return "\n".join(
            contents
        ).lower()

    @staticmethod
    def _contains_any(
        content: str,
        patterns: tuple[str, ...],
    ) -> bool:

        return any(
            pattern.lower() in content
            for pattern in patterns
        )

    @staticmethod
    def _normalize_path(
        file_path: str,
    ) -> str:

        return (
            file_path
            .lower()
            .replace("\\", "/")
        )