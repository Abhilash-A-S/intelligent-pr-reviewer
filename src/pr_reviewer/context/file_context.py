import re

from pr_reviewer.context.models import RepositoryContext, ResolvedFileContext
from pr_reviewer.detection.framework import FrameworkDetector
from pr_reviewer.review.models import ChangedFile


class FileContextResolver:
    """Resolve framework capabilities at file granularity inside a project."""

    SERVER_FILE_NAMES = {
        "server.ts",
        "server.js",
        "main.server.ts",
        "main.server.js",
    }

    def __init__(self, framework_detector: FrameworkDetector | None = None):
        self.framework_detector = framework_detector or FrameworkDetector()

    def resolve_all(
        self,
        changed_files: list[ChangedFile],
        repository_context: RepositoryContext,
    ) -> dict[str, ResolvedFileContext]:
        explicit: dict[str, str] = {}
        frameworks_by_project: dict[str, set[str]] = {}

        for changed_file in changed_files:
            if not changed_file.changed_lines and not changed_file.full_content:
                continue
            detected = self.framework_detector.detect([changed_file])
            if detected.framework == "unknown":
                continue
            path = self._normalize(changed_file.file_path)
            explicit[path] = detected.framework
            project = repository_context.find_project_for_file(path)
            if project is not None:
                frameworks_by_project.setdefault(project.root, set()).add(
                    detected.framework
                )

        # Tests and support files can inherit framework ownership from an
        # explicitly imported changed module without treating every Python file
        # as the repository's first detected framework.
        module_frameworks = {
            self._module_name(path): framework
            for path, framework in explicit.items()
            if path.lower().endswith(".py")
        }

        resolved: dict[str, ResolvedFileContext] = {}
        for changed_file in changed_files:
            if not changed_file.changed_lines:
                continue
            path = self._normalize(changed_file.file_path)
            project = repository_context.find_project_for_file(path)
            signals = (
                frameworks_by_project.get(project.root, set())
                if project is not None
                else set()
            )
            framework, evidence = self._resolve_framework(
                changed_file=changed_file,
                explicit_framework=(
                    explicit.get(path)
                    or self._imported_framework(changed_file.full_content or "", module_frameworks)
                ),
                project_framework=project.framework if project is not None else None,
                project_signals=signals,
                repository_framework=repository_context.framework,
            )
            project_type = self._project_type(framework)
            resolved[path] = ResolvedFileContext(
                project=project,
                framework=framework,
                project_type=project_type,
                evidence=tuple(evidence),
            )

        return resolved

    def _resolve_framework(
        self,
        changed_file: ChangedFile,
        explicit_framework: str | None,
        project_framework: str | None,
        project_signals: set[str],
        repository_framework: str,
    ) -> tuple[str, list[str]]:
        path = self._normalize(changed_file.file_path)
        name = path.rsplit("/", 1)[-1].lower()
        content = changed_file.full_content or ""

        if explicit_framework and explicit_framework != "unknown":
            return explicit_framework, ["file source/framework evidence"]

        if self._is_express_server(name, content) and "express" in project_signals:
            return "express", ["server filename/import evidence"]

        if "angular" in project_signals and self._is_angular_owned_path(path, content):
            return "angular", ["Angular project signal and file ownership path"]

        if self._is_browser_owned_path(path, content):
            return "browser-javascript", ["browser path, asset, or Web API evidence"]

        if len(project_signals) == 1:
            return next(iter(project_signals)), ["single project framework signal"]

        if path.lower().endswith((".py", ".pyw")) and project_signals and project_signals <= {
            "django", "flask", "fastapi", "python"
        }:
            return "python", ["mixed Python backend project; no file-specific framework evidence"]

        if project_framework and project_framework not in {"unknown", "mixed"}:
            return project_framework, ["project framework fallback"]

        return repository_framework or "unknown", ["repository framework fallback"]

    @classmethod
    def _is_express_server(cls, name: str, content: str) -> bool:
        return name in cls.SERVER_FILE_NAMES and (
            "express" in content.lower()
            or "createnoderequesthandler" in content.lower()
        )

    @staticmethod
    def _is_angular_owned_path(path: str, content: str) -> bool:
        lowered = path.lower()
        return (
            "/src/app/" in f"/{lowered}"
            or ".component." in lowered
            or lowered.endswith((".html", ".css", ".scss"))
            or "@angular/" in content
            or "testbed" in content.lower()
            or "bootstrapapplication" in content.lower()
        )

    @staticmethod
    def _is_browser_owned_path(path: str, content: str) -> bool:
        lowered = path.lower()
        padded = f"/{lowered}"
        if "/browser/" in padded:
            return True
        if lowered.endswith((".html", ".css", ".scss", ".sass", ".less")):
            return True
        if not lowered.endswith((".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx")):
            return False
        if re.search(r"(?:from\s+['\"]node:|require\s*\(\s*['\"]node:)", content):
            return False
        return bool(re.search(
            r"\b(?:window|document|HTMLElement|HTMLInputElement|localStorage|sessionStorage)\b",
            content,
        ))

    @staticmethod
    def _project_type(framework: str) -> str:
        if framework in {"angular", "react", "vue", "vite", "browser-javascript"}:
            return "frontend-web"
        if framework in {
            "express", "node", "nestjs", "fastapi", "flask", "django",
            "python", "spring", "spring-boot",
            "aspnet", "aspnet-core", "dotnet",
        }:
            return "backend"
        return "unknown"

    @staticmethod
    def _normalize(path: str) -> str:
        return path.strip().replace("\\", "/").strip("/")

    @staticmethod
    def _module_name(path: str) -> str:
        normalized = path.replace("\\", "/")
        padded = f"/{normalized}"
        if "/src/" in padded:
            normalized = padded.split("/src/", 1)[-1]
        return normalized.removesuffix(".py").replace("/", ".")

    @staticmethod
    def _imported_framework(content: str, module_frameworks: dict[str, str]) -> str | None:
        lowered = content.lower()
        matches = {
            framework
            for module, framework in module_frameworks.items()
            if f"from {module.lower()} import" in lowered
            or f"import {module.lower()}" in lowered
        }
        return next(iter(matches)) if len(matches) == 1 else None
