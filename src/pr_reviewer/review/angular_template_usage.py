from __future__ import annotations

import re
from pathlib import PurePosixPath

from pr_reviewer.review.models import ChangedFile


class AngularTemplateUsageResolver:
    """Resolve Angular component-member usage across TS + template files.

    The resolver is intentionally syntax-version tolerant. It understands both
    legacy structural-directive expressions (for example ``*ngIf``/``*ngFor``)
    and modern Angular control-flow blocks such as ``@if``/``@for``/``@switch``.
    It does not attempt to compile Angular templates; it only extracts expression
    regions where component members can legitimately be referenced.
    """

    TEMPLATE_URL_PATTERN = re.compile(
        r"\btemplateUrl\s*:\s*['\"]([^'\"]+)['\"]",
        re.MULTILINE,
    )
    INLINE_TEMPLATE_PATTERN = re.compile(
        r"\btemplate\s*:\s*`(?P<template>.*?)`",
        re.DOTALL,
    )
    INTERPOLATION_PATTERN = re.compile(r"{{(?P<expr>.*?)}}", re.DOTALL)
    ANGULAR_BINDING_PATTERN = re.compile(
        r"(?:"
        r"\[\([^\]]+\)\]"  # [(ngModel)]
        r"|\[[^\]]+\]"      # [value], [class.active], [attr.aria-label]
        r"|\([^\)]+\)"      # (click), (submit)
        r"|\*[A-Za-z_][\w.-]*"  # *ngIf, *ngFor, custom structural directives
        r")\s*=\s*(?P<quote>['\"])(?P<expr>.*?)(?P=quote)",
        re.DOTALL,
    )
    CONTROL_FLOW_PATTERN = re.compile(
        r"@(if|for|switch|case|defer)\s*\((?P<expr>.*?)\)",
        re.DOTALL,
    )
    LET_PATTERN = re.compile(
        r"@let\s+[A-Za-z_$][\w$]*\s*=\s*(?P<expr>.*?);",
        re.DOTALL,
    )

    def suppress_template_used_unused_findings(
        self,
        changed_files: list[ChangedFile],
        findings,
    ):
        files_by_path = {f.file_path: f for f in changed_files}
        result = []

        for finding in findings:
            if finding.rule_id != "unused-variable":
                result.append(finding)
                continue

            component = files_by_path.get(finding.file_path)
            if component is None or not self._is_angular_component(component):
                result.append(finding)
                continue

            symbol = self._symbol_from_message(finding.message)
            if not symbol:
                result.append(finding)
                continue

            template = self._resolve_template(component, files_by_path)
            if template and self._template_uses_symbol(template, symbol):
                continue

            result.append(finding)

        return result

    def _is_angular_component(self, changed_file: ChangedFile) -> bool:
        content = changed_file.full_content or ""
        return changed_file.file_path.lower().endswith(".ts") and "@Component" in content

    def _symbol_from_message(self, message: str) -> str | None:
        match = re.search(r"Variable '([A-Za-z_$][\w$]*)'", message)
        return match.group(1) if match else None

    def _resolve_template(
        self,
        component: ChangedFile,
        files_by_path: dict[str, ChangedFile],
    ) -> str | None:
        source = component.full_content or ""

        inline = self.INLINE_TEMPLATE_PATTERN.search(source)
        if inline:
            return inline.group("template")

        external = self.TEMPLATE_URL_PATTERN.search(source)
        if not external:
            return None

        component_path = PurePosixPath(component.file_path.replace("\\", "/"))
        template_path = str(component_path.parent / external.group(1))
        template_file = files_by_path.get(template_path)
        if template_file and template_file.full_content is not None:
            return template_file.full_content

        return component.related_file_contents.get(template_path)

    def _template_uses_symbol(self, template: str, symbol: str) -> bool:
        identifier = re.compile(rf"(?<![\w$]){re.escape(symbol)}(?![\w$])")

        expressions: list[str] = []
        expressions.extend(
            match.group("expr") for match in self.INTERPOLATION_PATTERN.finditer(template)
        )
        expressions.extend(
            match.group("expr") for match in self.ANGULAR_BINDING_PATTERN.finditer(template)
        )
        expressions.extend(
            match.group("expr") for match in self.CONTROL_FLOW_PATTERN.finditer(template)
        )
        expressions.extend(
            match.group("expr") for match in self.LET_PATTERN.finditer(template)
        )

        return any(identifier.search(expression) for expression in expressions)
