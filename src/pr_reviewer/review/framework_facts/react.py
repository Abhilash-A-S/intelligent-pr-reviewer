import re

from pr_reviewer.context.models import RepositoryContext
from pr_reviewer.review.models import ChangedFile, Finding


class ReactFactValidator:
    """
    Deterministic React facts.

    The validator is conservative: it rejects only claims
    that are contradicted by source-level React semantics.

    It does NOT try to replace ESLint/react-hooks rules.
    """

    JS_TS_EXTENSIONS = (
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".mjs",
        ".cjs",
    )

    def validate(
        self,
        finding: Finding,
        changed_file: ChangedFile,
        changed_files: list[ChangedFile],
        repository_context: RepositoryContext | None,
    ) -> list[str]:
        reasons: list[str] = []

        if not self._is_react_context(
            changed_file,
            repository_context,
        ):
            return reasons

        reason = self._validate_empty_dependency_semantics(
            finding,
            changed_file,
        )
        if reason:
            reasons.append(reason)

        reason = self._validate_hook_construct_presence(
            finding,
            changed_file,
        )
        if reason:
            reasons.append(reason)

        return reasons

    def _validate_empty_dependency_semantics(
        self,
        finding: Finding,
        changed_file: ChangedFile,
    ) -> str | None:
        """
        Reject the specific false claim that useEffect(..., [])
        runs on every render.

        Empty dependency arrays do not mean "every render".
        They mean the effect runs after the initial mount
        (with development Strict Mode caveats).

        A real missing-dependency finding using correct stale
        closure semantics is preserved.
        """

        text = self._text(finding)

        if "useeffect" not in text.replace(" ", ""):
            return None

        incorrect_every_render_claim = (
            "every render" in text
            or "on every render" in text
            or "each render" in text
        )

        if not incorrect_every_render_claim:
            return None

        content = changed_file.full_content or ""

        # Only reject when source actually contains a useEffect
        # with an empty dependency array, making the semantic
        # contradiction deterministic.
        if re.search(
            r"useEffect\s*\(\s*.*?,\s*\[\s*\]\s*\)",
            content,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            return (
                "Finding contradicts React effect semantics: "
                "an empty dependency array does not make "
                "useEffect run on every render."
            )

        return None

    def _validate_hook_construct_presence(
        self,
        finding: Finding,
        changed_file: ChangedFile,
    ) -> str | None:
        text = self._text(finding)
        content = changed_file.full_content or ""

        hooks = (
            "useEffect",
            "useLayoutEffect",
            "useState",
            "useMemo",
            "useCallback",
            "useRef",
        )

        for hook in hooks:
            if hook.lower() not in text:
                continue

            if not re.search(
                rf"\b{re.escape(hook)}\s*\(",
                content,
                flags=re.IGNORECASE,
            ):
                return (
                    "Finding is not supported by React source "
                    f"evidence: `{hook}` is absent from the file."
                )

        return None

    @classmethod
    def _is_react_context(
        cls,
        changed_file: ChangedFile,
        repository_context: RepositoryContext | None,
    ) -> bool:
        path = (
            changed_file.file_path
            .strip()
            .lower()
            .replace("\\", "/")
        )

        if not path.endswith(
            cls.JS_TS_EXTENSIONS
        ):
            return False

        if repository_context is not None:
            framework = (
                repository_context.framework
                or ""
            ).strip().lower()

            if framework == "react":
                return True

            resolved = repository_context.resolve_file_context(
                changed_file.file_path
            )
            if resolved.framework.strip().lower() == "react":
                return True

        content = (
            changed_file.full_content
            or ""
        ).lower()

        return (
            "from 'react'" in content
            or 'from "react"' in content
            or "react-dom" in content
        )

    @staticmethod
    def _text(
        finding: Finding,
    ) -> str:
        return " ".join(
            part.strip().lower()
            for part in (
                finding.rule_id,
                finding.message,
                finding.suggestion or "",
            )
            if part
        )
