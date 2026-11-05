from pathlib import Path


class LanguageDetector:
    LANGUAGE_MAP = {
        # JavaScript / TypeScript
        ".js": "javascript",
        ".jsx": "javascript",
        ".mjs": "javascript",
        ".cjs": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",

        # Python
        ".py": "python",

        # Java / JVM
        ".java": "java",
        ".kt": "kotlin",
        ".kts": "kotlin",
        ".scala": "scala",

        # .NET
        ".cs": "csharp",
        ".fs": "fsharp",
        ".vb": "visual-basic",

        # Web
        ".html": "html",
        ".htm": "html",
        ".css": "css",
        ".scss": "scss",
        ".sass": "sass",
        ".less": "less",
        ".vue": "vue",
        ".svelte": "svelte",

        # Systems
        ".c": "c",
        ".h": "c",
        ".cpp": "cpp",
        ".cc": "cpp",
        ".cxx": "cpp",
        ".hpp": "cpp",
        ".rs": "rust",
        ".go": "go",

        # Mobile
        ".swift": "swift",
        ".m": "objective-c",
        ".mm": "objective-cpp",
        ".dart": "dart",

        # Backend / scripting
        ".php": "php",
        ".rb": "ruby",
        ".sh": "shell",
        ".bash": "shell",
        ".ps1": "powershell",

        # Database
        ".sql": "sql",

        # Config / data
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
        ".xml": "xml",

        # Docs / misc
        ".md": "markdown",
    }

    def detect(self, file_path: str) -> str:
        extension = Path(file_path).suffix.lower()

        return self.LANGUAGE_MAP.get(
            extension,
            "unknown",
        )