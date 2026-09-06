import json
import re
from pathlib import PurePosixPath

from pr_reviewer.context.models import RepositoryContext
from pr_reviewer.review.models import ChangedFile, Finding


class TypeScriptBuildFactValidator:
    """
    Deterministic TypeScript/Vite build and configuration facts.

    This validator rejects AI findings that contradict
    concrete TypeScript/Vite repository evidence.

    Current protections:

    - Vite + `tsc -b` build pipelines
    - TypeScript solution/project-reference configs
    - Intentional `files: []`
    - Non-empty tsconfig detection
    - Vite + `noEmit: true`
    - Solution tsconfig without root `compilerOptions`
    """

    def validate(
        self,
        finding: Finding,
        changed_file: ChangedFile,
        changed_files: list[ChangedFile],
        repository_context: RepositoryContext | None,
    ) -> list[str]:

        reasons: list[str] = []

        # --------------------------------------------------
        # Vite build command
        # --------------------------------------------------

        reason = self._validate_vite_build(
            finding,
            changed_file,
            repository_context,
        )

        if reason:
            reasons.append(reason)

        # --------------------------------------------------
        # TypeScript solution config / files: []
        # --------------------------------------------------

        reason = self._validate_solution_tsconfig(
            finding,
            changed_file,
            changed_files,
            repository_context,
        )

        if reason:
            reasons.append(reason)

        # --------------------------------------------------
        # TypeScript solution config / compilerOptions
        # --------------------------------------------------

        reason = (
            self._validate_solution_tsconfig_compiler_options(
                finding,
                changed_file,
                changed_files,
                repository_context,
            )
        )

        if reason:
            reasons.append(reason)

        # --------------------------------------------------
        # Empty tsconfig claims
        # --------------------------------------------------

        reason = self._validate_non_empty_tsconfig(
            finding,
            changed_file,
        )

        if reason:
            reasons.append(reason)

        # --------------------------------------------------
        # Vite + noEmit
        # --------------------------------------------------

        reason = self._validate_vite_no_emit(
            finding,
            changed_file,
            repository_context,
        )

        if reason:
            reasons.append(reason)

        return reasons

    # ======================================================
    # Vite build validation
    # ======================================================

    def _validate_vite_build(
        self,
        finding: Finding,
        changed_file: ChangedFile,
        repository_context: RepositoryContext | None,
    ) -> str | None:

        if (
            PurePosixPath(
                self._norm(
                    changed_file.file_path
                )
            ).name.lower()
            != "package.json"
        ):
            return None

        text = self._finding_text(
            finding
        )

        rule = (
            finding.rule_id
            .strip()
            .lower()
        )

        if not (
            (
                "tsc" in text
                and (
                    "redundant" in text
                    or "unnecessary" in text
                )
            )
            or (
                "unnecessary" in rule
                and "compilation" in rule
            )
            or "redundant-tsc" in rule
        ):
            return None

        package = self._load_json_like(
            changed_file.full_content
        )

        if not isinstance(
            package,
            dict,
        ):
            return None

        scripts = package.get(
            "scripts"
        )

        build = (
            scripts.get("build")
            if isinstance(
                scripts,
                dict,
            )
            else None
        )

        if not isinstance(
            build,
            str,
        ):
            return None

        command = " ".join(
            build.lower().split()
        )

        has_tsc_build = re.search(
            r"(?:^|&&|;|\|\|)\s*tsc\s+-b(?:\s|$)",
            command,
        )

        has_vite_build = re.search(
            r"(?:^|&&|;|\|\|)\s*(?:npx\s+)?vite\s+build(?:\s|$)",
            command,
        )

        if not (
            has_tsc_build
            and has_vite_build
        ):
            return None

        if not self._has_vite_evidence(
            package=package,
            repository_context=repository_context,
        ):
            return None

        return (
            "Vite/TypeScript evidence shows `tsc -b` "
            "and `vite build` are separate valid "
            "build/type-check steps."
        )

    # ======================================================
    # Solution tsconfig / files: []
    # ======================================================

    def _validate_solution_tsconfig(
        self,
        finding: Finding,
        changed_file: ChangedFile,
        changed_files: list[ChangedFile],
        repository_context: RepositoryContext | None,
    ) -> str | None:

        if not self._is_tsconfig(
            changed_file.file_path
        ):
            return None

        text = self._finding_text(
            finding
        )

        rule = (
            finding.rule_id
            .strip()
            .lower()
        )

        looks_like_empty_files_claim = (
            (
                "files" in text
                and "empty" in text
            )
            or "empty-files" in rule
            or "files-array" in rule
        )

        if not looks_like_empty_files_claim:
            return None

        config = self._load_json_like(
            changed_file.full_content
        )

        if (
            not isinstance(
                config,
                dict,
            )
            or config.get("files") != []
        ):
            return None

        reference_paths = (
            self._extract_reference_paths(
                config
            )
        )

        if reference_paths is None:
            return None

        if not self._references_exist(
            changed_file.file_path,
            reference_paths,
            changed_files,
            repository_context,
        ):
            return None

        return (
            "TypeScript project-reference evidence "
            "shows this is a solution-style tsconfig; "
            "`files: []` is intentional."
        )

    # ======================================================
    # Solution tsconfig / compilerOptions
    # ======================================================

    def _validate_solution_tsconfig_compiler_options(
        self,
        finding: Finding,
        changed_file: ChangedFile,
        changed_files: list[ChangedFile],
        repository_context: RepositoryContext | None,
    ) -> str | None:
        """
        Reject false-positive claims that a solution-style
        TypeScript project-reference tsconfig must define
        compilerOptions itself.

        Example:

            {
                "files": [],
                "references": [
                    {
                        "path": "./tsconfig.app.json"
                    },
                    {
                        "path": "./tsconfig.node.json"
                    }
                ]
            }

        This is a valid TypeScript solution configuration.

        Compiler options may be defined by the referenced
        project configurations rather than the root
        solution configuration.
        """

        if not self._is_tsconfig(
            changed_file.file_path
        ):
            return None

        if not self._looks_like_missing_compiler_options_claim(
            finding
        ):
            return None

        config = self._load_json_like(
            changed_file.full_content
        )

        if not isinstance(
            config,
            dict,
        ):
            return None

        # --------------------------------------------------
        # Case 1:
        # compilerOptions already exists.
        #
        # The finding is directly contradicted by the file.
        # --------------------------------------------------

        if "compilerOptions" in config:
            compiler_options = config.get(
                "compilerOptions"
            )

            if isinstance(
                compiler_options,
                dict,
            ):
                return (
                    "The TypeScript configuration already "
                    "defines `compilerOptions`; the finding "
                    "is contradicted by the file contents."
                )

        # --------------------------------------------------
        # Case 2:
        # Solution-style project-reference config.
        # --------------------------------------------------

        reference_paths = (
            self._extract_reference_paths(
                config
            )
        )

        if reference_paths is None:
            return None

        # Do not trust references merely because they are
        # present in JSON. Require repository evidence that
        # the referenced configurations exist.
        if not self._references_exist(
            changed_file.file_path,
            reference_paths,
            changed_files,
            repository_context,
        ):
            return None

        return (
            "TypeScript project-reference evidence shows "
            "this is a solution-style tsconfig. A solution "
            "config does not need to define "
            "`compilerOptions`; compiler settings may be "
            "defined by the referenced projects."
        )

    def _looks_like_missing_compiler_options_claim(
        self,
        finding: Finding,
    ) -> bool:

        rule = (
            finding.rule_id
            .strip()
            .lower()
        )

        text = self._finding_text(
            finding
        )

        normalized_rule = (
            rule
            .replace("_", "-")
        )

        # --------------------------------------------------
        # Known rule-ID shapes
        # --------------------------------------------------

        if (
            "missing-compileroptions"
            in normalized_rule
        ):
            return True

        if (
            "missing-compiler-options"
            in normalized_rule
        ):
            return True

        if (
            "compileroptions-missing"
            in normalized_rule
        ):
            return True

        if (
            "compiler-options-missing"
            in normalized_rule
        ):
            return True

        # --------------------------------------------------
        # Message/suggestion based detection
        # --------------------------------------------------

        mentions_compiler_options = (
            "compileroptions" in text
            or "compiler options" in text
        )

        if not mentions_compiler_options:
            return False

        missing_language = (
            "missing" in text
            or "required" in text
            or "must define" in text
            or "must include" in text
            or "should define" in text
            or "should include" in text
            or "needs to define" in text
            or "needs to include" in text
            or "essential" in text
            or "not defined" in text
            or "not present" in text
        )

        return missing_language

    # ======================================================
    # Non-empty tsconfig
    # ======================================================

    def _validate_non_empty_tsconfig(
        self,
        finding: Finding,
        changed_file: ChangedFile,
    ) -> str | None:

        if not self._is_tsconfig(
            changed_file.file_path
        ):
            return None

        text = self._finding_text(
            finding
        )

        rule = (
            finding.rule_id
            .strip()
            .lower()
        )

        empty_claim = (
            "empty-config" in rule
            or "empty-tsconfig" in rule
            or (
                (
                    "tsconfig" in text
                    or "configuration file" in text
                )
                and (
                    " empty" in f" {text}"
                    or "blank" in text
                )
            )
        )

        if not empty_claim:
            return None

        config = self._load_json_like(
            changed_file.full_content
        )

        if (
            not isinstance(
                config,
                dict,
            )
            or not config
        ):
            return None

        keys = sorted(
            str(key)
            for key
            in config.keys()
            if str(key).strip()
        )

        if not keys:
            return None

        return (
            "The TypeScript configuration is "
            "demonstrably not empty; it contains: "
            f"{', '.join(keys)}."
        )

    # ======================================================
    # Vite + noEmit
    # ======================================================

    def _validate_vite_no_emit(
        self,
        finding: Finding,
        changed_file: ChangedFile,
        repository_context: RepositoryContext | None,
    ) -> str | None:
        """
        In a Vite application, TypeScript commonly performs
        type checking only while Vite handles transpilation
        and bundling.

        Therefore `compilerOptions.noEmit: true` is not by
        itself a defect.

        Reject only when:

        - the file is a tsconfig,
        - noEmit is explicitly true,
        - the finding actually criticizes noEmit/emission,
        - concrete repository context proves Vite.
        """

        if not self._is_tsconfig(
            changed_file.file_path
        ):
            return None

        if not self._looks_like_no_emit_claim(
            finding
        ):
            return None

        config = self._load_json_like(
            changed_file.full_content
        )

        if not isinstance(
            config,
            dict,
        ):
            return None

        compiler_options = config.get(
            "compilerOptions"
        )

        if not isinstance(
            compiler_options,
            dict,
        ):
            return None

        if (
            compiler_options.get(
                "noEmit"
            )
            is not True
        ):
            return None

        if not self._repository_uses_vite(
            repository_context
        ):
            return None

        return (
            "Vite/TypeScript build evidence shows "
            "`compilerOptions.noEmit: true` is valid: "
            "TypeScript can perform type checking while "
            "Vite handles transpilation and bundling."
        )

    def _looks_like_no_emit_claim(
        self,
        finding: Finding,
    ) -> bool:

        rule = (
            finding.rule_id
            .strip()
            .lower()
        )

        text = self._finding_text(
            finding
        )

        if (
            "noemit" in rule
            or "no-emit" in rule
            or "no_emit" in rule
        ):
            return True

        return bool(
            re.search(
                r"\bno\s*emit\b",
                text,
                flags=re.IGNORECASE,
            )
            or (
                "emit" in text
                and (
                    "debug" in text
                    or "build" in text
                    or "compile" in text
                    or "output" in text
                )
            )
        )

    # ======================================================
    # Project-reference helpers
    # ======================================================

    @staticmethod
    def _extract_reference_paths(
        config: dict,
    ) -> list[str] | None:
        """
        Extract valid TypeScript project-reference paths.

        None means that the config cannot be proven to be
        a valid project-reference/solution configuration.
        """

        references = config.get(
            "references"
        )

        if (
            not isinstance(
                references,
                list,
            )
            or not references
        ):
            return None

        paths: list[str] = []

        for reference in references:

            if not isinstance(
                reference,
                dict,
            ):
                return None

            path = reference.get(
                "path"
            )

            if (
                not isinstance(
                    path,
                    str,
                )
                or not path.strip()
            ):
                return None

            paths.append(
                path.strip()
            )

        if not paths:
            return None

        return paths

    def _references_exist(
        self,
        config_path: str,
        reference_paths: list[str],
        changed_files: list[ChangedFile],
        repository_context: RepositoryContext | None,
    ) -> bool:

        known = {
            self._norm(
                item.file_path
            ).lower()
            for item
            in changed_files
        }

        if (
            repository_context
            is not None
        ):
            known.update(
                self._norm(
                    path
                ).lower()
                for path
                in repository_context.metadata_files
                if path
            )

        parent = PurePosixPath(
            self._norm(
                config_path
            )
        ).parent

        for reference in reference_paths:

            reference = self._norm(
                reference
            )

            candidate = self._norm(
                str(
                    parent
                    / reference
                )
            ).lower()

            candidates = {
                candidate
            }

            candidate_name = (
                PurePosixPath(
                    candidate
                ).name
            )

            # --------------------------------------------------
            # TypeScript references may point directly to:
            #
            # ./tsconfig.app.json
            #
            # or to a project directory:
            #
            # ./packages/shared
            #
            # In the latter case also check:
            #
            # ./packages/shared/tsconfig.json
            # --------------------------------------------------

            if "." not in candidate_name:
                candidates.add(
                    f"{candidate}/tsconfig.json"
                )

            if not candidates.intersection(
                known
            ):
                return False

        return True

    # ======================================================
    # Vite evidence
    # ======================================================

    def _has_vite_evidence(
        self,
        package: dict,
        repository_context: RepositoryContext | None,
    ) -> bool:

        if self._repository_uses_vite(
            repository_context
        ):
            return True

        for section_name in (
            "dependencies",
            "devDependencies",
        ):

            section = package.get(
                section_name
            )

            if (
                isinstance(
                    section,
                    dict,
                )
                and "vite" in section
            ):
                return True

        return False

    def _repository_uses_vite(
        self,
        repository_context: RepositoryContext | None,
    ) -> bool:

        if repository_context is None:
            return False

        for tool in (
            repository_context.build_tools
        ):

            value = getattr(
                tool,
                "value",
                tool,
            )

            if (
                str(value)
                .lower()
                == "vite"
            ):
                return True

        for path in (
            repository_context
            .metadata_files
        ):

            file_name = PurePosixPath(
                self._norm(
                    path
                )
            ).name.lower()

            if file_name.startswith(
                "vite.config."
            ):
                return True

        return False

    # ======================================================
    # General helpers
    # ======================================================

    @staticmethod
    def _finding_text(
        finding: Finding,
    ) -> str:

        return " ".join(
            part.strip().lower()
            for part in (
                finding.message,
                finding.suggestion
                or "",
            )
            if part
        )

    @staticmethod
    def _is_tsconfig(
        file_path: str,
    ) -> bool:

        name = PurePosixPath(
            TypeScriptBuildFactValidator
            ._norm(
                file_path
            )
        ).name.lower()

        return (
            name.startswith(
                "tsconfig"
            )
            and name.endswith(
                ".json"
            )
        )

    @staticmethod
    def _norm(
        path: str,
    ) -> str:

        normalized = (
            path
            .strip()
            .replace(
                "\\",
                "/",
            )
        )

        while normalized.startswith(
            "./"
        ):
            normalized = (
                normalized[2:]
            )

        return (
            normalized.strip(
                "/"
            )
            or "."
        )

    @staticmethod
    def _load_json_like(
        content: str | None,
    ):
        """
        Parse ordinary JSON and common tsconfig JSONC.

        Supports:

        - // comments
        - block comments
        - trailing commas
        """

        if not content:
            return None

        try:
            return json.loads(
                content
            )

        except json.JSONDecodeError:
            pass

        cleaned = re.sub(
            r"/\*.*?\*/",
            "",
            content,
            flags=re.DOTALL,
        )

        cleaned = re.sub(
            r"(^|\s)//.*$",
            r"\1",
            cleaned,
            flags=re.MULTILINE,
        )

        cleaned = re.sub(
            r",\s*([}\]])",
            r"\1",
            cleaned,
        )

        try:
            return json.loads(
                cleaned
            )

        except json.JSONDecodeError:
            return None