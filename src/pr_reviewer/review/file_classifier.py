from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath


class FileCategory(str, Enum):
    SOURCE_CODE = "source_code"
    TEMPLATE = "template"
    STYLESHEET = "stylesheet"
    PROJECT_CONFIGURATION = "project_configuration"
    TOOL_CONFIGURATION = "tool_configuration"
    DOCUMENTATION = "documentation"
    TEST = "test"
    GENERATED = "generated"
    LOCK_FILE = "lock_file"
    BINARY = "binary"
    UNKNOWN = "unknown"

    # Backward-compatible alias.
    CONFIGURATION = "project_configuration"


@dataclass(frozen=True)
class FileClassification:
    category: FileCategory
    reviewable: bool
    reason: str


class FileClassifier:
    """
    Language-agnostic file classifier.

    Responsibilities:

    - Identify source code.
    - Identify tests.
    - Identify templates and stylesheets.
    - Distinguish meaningful project configuration from
      editor/tool configuration.
    - Exclude generated, binary, lock, and documentation
      files from normal semantic review.
    - Keep unknown text/source types reviewable.

    Important:

    Project configuration can affect build behavior,
    compilation, dependencies, deployment, runtime
    configuration, and security. It remains reviewable.

    Tool/editor configuration is normally not useful for
    semantic PR review and is skipped by default.
    """

    # ======================================================
    # Lock files
    # ======================================================

    LOCK_FILE_NAMES = {
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "npm-shrinkwrap.json",
        "composer.lock",
        "cargo.lock",
        "poetry.lock",
        "pipfile.lock",
        "uv.lock",
        "gemfile.lock",
        "packages.lock.json",
    }

    # ======================================================
    # Generated/build directories
    # ======================================================

    GENERATED_DIRECTORY_NAMES = {
        "dist",
        "build",
        "target",
        "bin",
        "obj",
        "coverage",
        "node_modules",
        "vendor",
        ".angular",
        ".next",
        ".nuxt",
        ".gradle",
        ".idea",
    }

    TOOLING_INSTRUCTION_DIRECTORY_NAMES = {
        ".agents",
        ".cursor",
        ".codex",
        ".claude",
        ".gemini",
        ".opencode",
        ".vscode",
        ".nx",
    }

    # Directories that contain assistant/tool control-plane material.
    # .github is intentionally NOT excluded wholesale because workflows are
    # meaningful CI/CD code. Only the skills subtree is skipped.
    TOOLING_INSTRUCTION_PATH_PREFIXES = (
        ".github/skills/",
    )

    # End-to-end suites are intentionally out of scope for the fast default
    # review path. Unit/integration tests remain reviewable.
    E2E_DIRECTORY_MARKERS = {
        "e2e",
        "e2es",
        "cypress",
    }

    E2E_FILE_MARKERS = (
        ".e2e.",
        "-e2e.",
        "_e2e.",
    )

    GENERATED_FILE_SUFFIXES = (
        ".min.js",
        ".min.css",
        ".bundle.js",
        ".bundle.css",
        ".map",
        ".generated.cs",
        ".g.cs",
        ".designer.cs",
    )

    # ======================================================
    # Binary
    # ======================================================

    # Static visual assets in conventional asset directories can be
    # skipped without treating every text-based SVG as binary.
    STATIC_ASSET_EXTENSIONS = {
        ".svg",
    }

    STATIC_ASSET_DIRECTORY_NAMES = {
        "assets",
        "public",
        "static",
        "images",
        "icons",
    }

    BINARY_EXTENSIONS = {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".webp",
        ".ico",
        ".pdf",
        ".zip",
        ".gz",
        ".tar",
        ".7z",
        ".rar",
        ".jar",
        ".war",
        ".dll",
        ".exe",
        ".so",
        ".dylib",
        ".class",
        ".pyc",
        ".pdb",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".mp3",
        ".mp4",
        ".wav",
        ".avi",
        ".mov",
    }

    # ======================================================
    # Documentation
    # ======================================================

    DOCUMENTATION_EXTENSIONS = {
        ".md",
        ".mdx",
        ".rst",
        ".adoc",
        ".txt",
    }

    # ======================================================
    # Stylesheets
    # ======================================================

    STYLESHEET_EXTENSIONS = {
        ".css",
        ".scss",
        ".sass",
        ".less",
        ".styl",
    }

    # ======================================================
    # Templates / views
    # ======================================================

    TEMPLATE_EXTENSIONS = {
        ".html",
        ".htm",
        ".hbs",
        ".handlebars",
        ".ejs",
        ".jinja",
        ".jinja2",
        ".twig",
        ".mustache",
        ".razor",
        ".cshtml",
    }

    # ======================================================
    # Project configuration
    # ======================================================

    PROJECT_CONFIGURATION_EXTENSIONS = {
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".properties",
        ".xml",
    }

    PROJECT_CONFIGURATION_FILE_NAMES = {
        # JavaScript / TypeScript
        "package.json",
        "angular.json",

        # TypeScript
        "tsconfig.json",
        "tsconfig.app.json",
        "tsconfig.spec.json",
        "jsconfig.json",

        # Python
        "pyproject.toml",
        "requirements.txt",

        # Java / JVM
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",

        # Go
        "go.mod",

        # Rust
        "cargo.toml",

        # PHP
        "composer.json",

        # Ruby
        "gemfile",

        # Container / build / deployment
        "dockerfile",
        ".python-version",
        "pyproject.toml",
        "requirements.txt",
        "setup.py",
        "setup.cfg",
        "pipfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        "makefile",
        "jenkinsfile",
        "procfile",

        # Environment template
        ".env.example",
    }

    PROJECT_CONFIGURATION_SUFFIXES = (
        ".csproj",
        ".fsproj",
        ".vbproj",
    )

    # Repository/workspace metadata that is valuable for context discovery but
    # should not consume an LLM call or create normal PR findings. These files
    # are still hydrated by RepositoryContextBuilder discovery.
    CONTEXT_ONLY_CONFIGURATION_FILE_NAMES = {
        "package.json",
        "nx.json",
        "angular.json",
        "project.json",
        "tsconfig.json",
        "tsconfig.base.json",
        "tsconfig.app.json",
        "tsconfig.spec.json",
        "dockerfile",
        ".python-version",
        "pyproject.toml",
        "requirements.txt",
        "setup.py",
        "setup.cfg",
        "pipfile",
        # .NET workspace selectors. Project files and shared build props remain
        # reviewable because they can change dependencies/compiler behavior.
        "global.json",
    }

    CONTEXT_ONLY_CONFIGURATION_SUFFIXES = (
        ".sln",
    )

    CONTEXT_ONLY_CONFIGURATION_PREFIXES = (
        "tsconfig.",
        "vite.config.",
        "vitest.config.",
        "eslint.config.",
    )

    # ======================================================
    # Tool/editor configuration
    # ======================================================

    TOOL_CONFIGURATION_FILE_NAMES = {
        ".editorconfig",
        ".gitignore",
        ".dockerignore",
        ".prettierignore",
        ".eslintignore",
        ".npmignore",
        ".gitattributes",
        ".prettierrc",
        ".eslintrc",
        ".stylelintrc",
        "opencode.json",
    }

    TOOL_CONFIGURATION_PREFIXES = (
        ".prettierrc.",
        ".eslintrc.",
        ".stylelintrc.",
    )

    # ======================================================
    # Tests
    # ======================================================

    TEST_PATH_MARKERS = {
        "test",
        "tests",
        "__tests__",
        "spec",
        "specs",
    }

    TEST_FILE_MARKERS = (
        ".test.",
        ".spec.",
        "_test.",
        "_tests.",
    )

    # ======================================================
    # Source code
    # ======================================================

    SOURCE_EXTENSIONS = {
        # JavaScript / TypeScript
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".ts",
        ".tsx",

        # JVM
        ".java",
        ".kt",
        ".kts",
        ".scala",
        ".groovy",
        ".clj",
        ".cljs",

        # .NET
        ".cs",
        ".fs",
        ".fsx",
        ".vb",

        # Python
        ".py",
        ".pyw",

        # Go
        ".go",

        # Rust
        ".rs",

        # C / C++
        ".c",
        ".h",
        ".cc",
        ".cpp",
        ".cxx",
        ".hpp",
        ".hxx",

        # Objective-C
        ".m",
        ".mm",

        # Swift
        ".swift",

        # PHP
        ".php",

        # Ruby
        ".rb",

        # Dart
        ".dart",

        # Elixir / Erlang
        ".ex",
        ".exs",
        ".erl",
        ".hrl",

        # Shell
        ".sh",
        ".bash",
        ".zsh",
        ".fish",
        ".ps1",
        ".bat",
        ".cmd",

        # Database / query
        ".sql",
        ".graphql",
        ".gql",

        # Functional languages
        ".hs",
        ".lhs",
        ".ml",
        ".mli",

        # Other languages
        ".lua",
        ".r",
        ".pl",
        ".pm",
        ".sol",
        ".zig",

        # Component / mixed source
        ".vue",
        ".svelte",
        ".astro",
    }

    def classify(
        self,
        file_path: str,
    ) -> FileClassification:
        """
        Classify a repository file.

        Classification precedence matters.

        Known project configuration must be detected
        before generic test/source detection.

        Examples:

        - tsconfig.spec.json contains ".spec." but is
          configuration, not a test source file.

        - build.gradle.kts has a ".kts" extension but is
          Gradle configuration, not normal Kotlin source.
        """

        normalized = self._normalize_path(
            file_path
        )

        path = PurePosixPath(
            normalized
        )

        file_name = path.name.lower()
        suffix = path.suffix.lower()

        # Explicit low-value paths are excluded before extension-based
        # classification. Keep .github/workflows reviewable while suppressing
        # .github/skills and similar tool-control directories.
        if self._is_tooling_instruction_path(path):
            return FileClassification(
                category=FileCategory.TOOL_CONFIGURATION,
                reviewable=False,
                reason=(
                    "Tool/assistant control-plane content is excluded from "
                    "application PR review."
                ),
            )

        # E2E suites are skipped by the fast default review path. Unit and
        # integration tests remain reviewable.
        if self._is_e2e_path(path=path, file_name=file_name):
            return FileClassification(
                category=FileCategory.TEST,
                reviewable=False,
                reason=(
                    "End-to-end test files are excluded from the default "
                    "semantic PR review path."
                ),
            )

        # Workspace/build metadata can be essential for repository context but
        # is intentionally context-only: no LLM call and no normal finding.
        if self._is_context_only_configuration(file_name):
            return FileClassification(
                category=FileCategory.PROJECT_CONFIGURATION,
                reviewable=False,
                reason=(
                    "Repository/build metadata is context-only and is not "
                    "reviewed as a standalone PR target."
                ),
            )

        # AI/editor agent instructions and their helper scripts are tooling
        # control-plane material, not application runtime source. Reviewing
        # them as product code creates false framework/control-flow findings.
        if any(part.lower() in self.TOOLING_INSTRUCTION_DIRECTORY_NAMES for part in path.parts):
            return FileClassification(
                category=FileCategory.TOOL_CONFIGURATION,
                reviewable=False,
                reason="AI/editor agent tooling is excluded from application semantic review.",
            )

        # --------------------------------------------------
        # 1. Lock files
        # --------------------------------------------------

        if self._is_lock_file(
            file_name
        ):
            return FileClassification(
                category=FileCategory.LOCK_FILE,
                reviewable=False,
                reason=(
                    "Dependency lock files are generated "
                    "and do not require normal semantic "
                    "AI review."
                ),
            )

        # --------------------------------------------------
        # 2. Binary files
        # --------------------------------------------------

        if suffix in self.BINARY_EXTENSIONS:
            return FileClassification(
                category=FileCategory.BINARY,
                reviewable=False,
                reason=(
                    "Binary or compiled files cannot be "
                    "meaningfully reviewed as source code."
                ),
            )

        # --------------------------------------------------
        # 3. Conventional static visual assets
        # --------------------------------------------------
        #
        # SVG is text, so it is intentionally NOT added to
        # BINARY_EXTENSIONS. An SVG outside a conventional
        # static-asset directory remains UNKNOWN/reviewable.
        # This skips normal Vite/React visual assets such as:
        #
        #     public/favicon.svg
        #     public/icons.svg
        #     src/assets/react.svg
        #
        # without globally suppressing every SVG file.
        # --------------------------------------------------

        if self._is_static_asset(
            path=path,
            suffix=suffix,
        ):
            return FileClassification(
                category=FileCategory.BINARY,
                reviewable=False,
                reason=(
                    "Static visual assets in conventional "
                    "asset directories are excluded from "
                    "normal semantic AI review."
                ),
            )

        # --------------------------------------------------
        # 4. Generated files
        # --------------------------------------------------

        if self._is_generated(
            path=path,
            file_name=file_name,
        ):
            return FileClassification(
                category=FileCategory.GENERATED,
                reviewable=False,
                reason=(
                    "Generated/build output should not "
                    "receive semantic AI review."
                ),
            )

        # --------------------------------------------------
        # 4. Tool/editor configuration
        # --------------------------------------------------
        #
        # This must run before generic configuration.
        #
        # Example:
        #
        # .eslintrc.json
        #
        # has a JSON extension but should remain tool
        # configuration rather than project configuration.
        # --------------------------------------------------

        if self._is_tool_configuration(
            file_name
        ):
            return FileClassification(
                category=FileCategory.TOOL_CONFIGURATION,
                reviewable=False,
                reason=(
                    "Editor/tool configuration is excluded "
                    "from semantic AI review by default."
                ),
            )

        # --------------------------------------------------
        # 5. Known project configuration
        # --------------------------------------------------
        #
        # IMPORTANT:
        #
        # This check must happen before test and source
        # detection.
        #
        # tsconfig.spec.json would otherwise match ".spec."
        # and become TEST.
        #
        # build.gradle.kts would otherwise match ".kts"
        # and become SOURCE_CODE.
        # --------------------------------------------------

        if self._is_project_configuration(
            file_name=file_name,
            suffix=suffix,
        ):
            return FileClassification(
                category=(
                    FileCategory.PROJECT_CONFIGURATION
                ),
                reviewable=True,
                reason=(
                    "Project configuration can affect "
                    "compilation, build behavior, runtime "
                    "behavior, dependencies, deployment, "
                    "or security."
                ),
            )

        # --------------------------------------------------
        # 6. Test source
        # --------------------------------------------------

        if self._is_test_file(
            path=path,
            file_name=file_name,
        ):
            return FileClassification(
                category=FileCategory.TEST,
                reviewable=True,
                reason=(
                    "Test source should receive "
                    "test-aware semantic review."
                ),
            )

        # --------------------------------------------------
        # 7. Source code
        # --------------------------------------------------

        if suffix in self.SOURCE_EXTENSIONS:
            return FileClassification(
                category=FileCategory.SOURCE_CODE,
                reviewable=True,
                reason=(
                    "Source code should receive semantic "
                    "AI review."
                ),
            )

        # --------------------------------------------------
        # 8. Templates / views
        # --------------------------------------------------

        if suffix in self.TEMPLATE_EXTENSIONS:
            return FileClassification(
                category=FileCategory.TEMPLATE,
                reviewable=True,
                reason=(
                    "Template/view files can contain "
                    "reviewable structure and behavior."
                ),
            )

        # --------------------------------------------------
        # 9. Stylesheets
        # --------------------------------------------------

        if suffix in self.STYLESHEET_EXTENSIONS:
            return FileClassification(
                category=FileCategory.STYLESHEET,
                reviewable=True,
                reason=(
                    "Stylesheets may contain functional, "
                    "accessibility, layout, or behavioral "
                    "issues worth reviewing."
                ),
            )

        # --------------------------------------------------
        # 10. Documentation
        # --------------------------------------------------

        if suffix in self.DOCUMENTATION_EXTENSIONS:
            return FileClassification(
                category=FileCategory.DOCUMENTATION,
                reviewable=False,
                reason=(
                    "Documentation is excluded from code "
                    "review by default."
                ),
            )

        # --------------------------------------------------
        # 11. Unknown
        # --------------------------------------------------

        return FileClassification(
            category=FileCategory.UNKNOWN,
            reviewable=True,
            reason=(
                "Unknown file types remain reviewable so "
                "future or uncommon programming languages "
                "are not silently skipped."
            ),
        )

    def should_review(
        self,
        file_path: str,
    ) -> bool:
        """
        Return whether the file should receive LLM review.
        """

        return self.classify(
            file_path
        ).reviewable

    def _is_lock_file(
        self,
        file_name: str,
    ) -> bool:
        """
        Return True when the file is a dependency lock file.
        """

        return (
            file_name
            in self.LOCK_FILE_NAMES
        )

    def _is_static_asset(
        self,
        path: PurePosixPath,
        suffix: str,
    ) -> bool:
        """
        Detect text-based visual assets in conventional
        static-asset directories.

        The path requirement is deliberate. Unknown SVG files
        elsewhere remain reviewable so the classifier does not
        globally suppress a text-based format that can contain
        meaningful markup or script.
        """

        if suffix not in self.STATIC_ASSET_EXTENSIONS:
            return False

        path_parts = {
            part.lower()
            for part in path.parts[:-1]
        }

        return bool(
            path_parts
            & self.STATIC_ASSET_DIRECTORY_NAMES
        )

    def _is_generated(
        self,
        path: PurePosixPath,
        file_name: str,
    ) -> bool:
        """
        Detect generated/build output.
        """

        path_parts = {
            part.lower()
            for part in path.parts[:-1]
        }

        if (
            path_parts
            & self.GENERATED_DIRECTORY_NAMES
        ):
            return True

        return any(
            file_name.endswith(
                generated_suffix
            )
            for generated_suffix
            in self.GENERATED_FILE_SUFFIXES
        )

    def _is_test_file(
        self,
        path: PurePosixPath,
        file_name: str,
    ) -> bool:
        """
        Detect test source files.

        This method is intentionally called only after
        known project configuration has been checked.
        """

        path_parts = {
            part.lower()
            for part in path.parts[:-1]
        }

        if (
            path_parts
            & self.TEST_PATH_MARKERS
        ):
            return True

        return any(
            marker in file_name
            for marker in self.TEST_FILE_MARKERS
        )

    def _is_tool_configuration(
        self,
        file_name: str,
    ) -> bool:
        """
        Detect editor/linter/formatter/tool configuration.
        """

        if (
            file_name
            in self.TOOL_CONFIGURATION_FILE_NAMES
        ):
            return True

        return any(
            file_name.startswith(
                prefix
            )
            for prefix
            in self.TOOL_CONFIGURATION_PREFIXES
        )

    def _is_project_configuration(
        self,
        file_name: str,
        suffix: str,
    ) -> bool:
        """
        Detect meaningful project/build/runtime
        configuration.

        Exact known filenames are checked first.

        Generic configuration extensions are accepted
        afterwards.
        """

        if (
            file_name
            in self.PROJECT_CONFIGURATION_FILE_NAMES
        ):
            return True

        if any(
            file_name.endswith(
                project_suffix
            )
            for project_suffix
            in self.PROJECT_CONFIGURATION_SUFFIXES
        ):
            return True

        return (
            suffix
            in self.PROJECT_CONFIGURATION_EXTENSIONS
        )

    def _is_tooling_instruction_path(
        self,
        path: PurePosixPath,
    ) -> bool:
        parts = tuple(part.lower() for part in path.parts)
        if any(part in self.TOOLING_INSTRUCTION_DIRECTORY_NAMES for part in parts):
            return True

        normalized = "/".join(parts)
        return any(
            normalized.startswith(prefix) or f"/{prefix}" in f"/{normalized}"
            for prefix in self.TOOLING_INSTRUCTION_PATH_PREFIXES
        )

    def _is_e2e_path(
        self,
        path: PurePosixPath,
        file_name: str,
    ) -> bool:
        parts = tuple(part.lower() for part in path.parts)
        if any(
            part in self.E2E_DIRECTORY_MARKERS or part.endswith("-e2e")
            for part in parts[:-1]
        ):
            return True

        return any(marker in file_name for marker in self.E2E_FILE_MARKERS)

    def _is_context_only_configuration(
        self,
        file_name: str,
    ) -> bool:
        if file_name in self.CONTEXT_ONLY_CONFIGURATION_FILE_NAMES:
            return True

        if any(
            file_name.endswith(suffix)
            for suffix in self.CONTEXT_ONLY_CONFIGURATION_SUFFIXES
        ):
            return True

        return any(
            file_name.startswith(prefix)
            for prefix in self.CONTEXT_ONLY_CONFIGURATION_PREFIXES
        )

    @staticmethod
    def _normalize_path(
        file_path: str,
    ) -> str:
        """
        Normalize Windows and Unix repository paths.
        """

        return (
            file_path
            .strip()
            .replace("\\", "/")
        )
