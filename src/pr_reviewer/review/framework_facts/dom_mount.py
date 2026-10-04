import re

from pr_reviewer.review.models import ChangedFile, Finding


class DomMountEvidenceValidator:
    """Cross-file evidence for browser DOM mount/root element claims."""

    GET_ELEMENT_BY_ID = re.compile(
        r"""document\s*\.\s*getElementById\s*\(\s*["'](?P<id>[^"']+)["']\s*\)""",
        re.IGNORECASE,
    )
    QUERY_SELECTOR_ID = re.compile(
        r"""document\s*\.\s*querySelector\s*\(\s*["']\#(?P<id>[A-Za-z_][A-Za-z0-9_:\-.]*)["']\s*\)""",
        re.IGNORECASE,
    )

    def validate(
        self,
        finding: Finding,
        changed_file: ChangedFile,
        changed_files: list[ChangedFile],
    ) -> list[str]:
        if not self._looks_like_missing_mount_claim(finding):
            return []

        content = changed_file.full_content or "\n".join(
            line.content for line in changed_file.changed_lines
        )
        if not content:
            return []

        ids = self._requested_ids(content)
        for element_id in ids:
            if self._html_contains_id(element_id, changed_files):
                return [
                    "Finding contradicts cross-file DOM evidence: "
                    f"an HTML source contains an element with id '{element_id}'."
                ]

        return []

    @staticmethod
    def _looks_like_missing_mount_claim(finding: Finding) -> bool:
        rule = finding.rule_id.strip().lower()
        text = " ".join(
            part.strip().lower()
            for part in (finding.message, finding.suggestion or "")
            if part
        )

        rule_terms = (
            "root-element",
            "mount-element",
            "mount-point",
            "missing-root",
            "missing-mount",
            "react-root",
        )
        if any(term in rule for term in rule_terms):
            return True

        return (
            ("element" in text or "mount" in text or "root" in text)
            and (
                "must exist" in text
                or "does not exist" in text
                or "missing" in text
            )
        )

    def _requested_ids(self, content: str) -> list[str]:
        result: list[str] = []
        for pattern in (self.GET_ELEMENT_BY_ID, self.QUERY_SELECTOR_ID):
            for match in pattern.finditer(content):
                value = match.group("id").strip()
                if value and value not in result:
                    result.append(value)
        return result

    @staticmethod
    def _html_contains_id(
        element_id: str,
        changed_files: list[ChangedFile],
    ) -> bool:
        pattern = re.compile(
            r"""<[^>]+\bid\s*=\s*["']"""
            + re.escape(element_id)
            + r"""["'][^>]*>""",
            re.IGNORECASE | re.DOTALL,
        )

        for candidate in changed_files:
            path = candidate.file_path.strip().lower().replace("\\", "/")
            if not path.endswith((".html", ".htm")):
                continue

            content = candidate.full_content or "\n".join(
                line.content for line in candidate.changed_lines
            )
            if content and pattern.search(content):
                return True

        return False
