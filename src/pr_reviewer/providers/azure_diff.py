"""Pure Azure DevOps change and patch helpers.

Azure DevOps exposes pull-request change metadata, but unlike GitHub it does
not include a unified text patch with every changed file.  The provider uses
these helpers to normalize Azure change flags and reconstruct the patch from
the common/source commit contents without leaking Azure semantics into the
review engine.
"""

from difflib import unified_diff
import re


_NUMERIC_CHANGE_FLAGS = {
    1: "add",
    2: "edit",
    4: "encoding",
    8: "rename",
    16: "delete",
    32: "undelete",
    64: "branch",
    128: "merge",
    256: "lock",
    512: "rollback",
    1024: "sourceRename",
    2048: "targetRename",
    4096: "property",
}


def normalize_change_types(value: object) -> frozenset[str]:
    """Return normalized Azure change flags from string or numeric payloads."""

    if isinstance(value, int):
        return frozenset(
            name.lower()
            for bit, name in _NUMERIC_CHANGE_FLAGS.items()
            if value & bit
        )

    if not isinstance(value, str):
        return frozenset()

    # Azure normally serializes flags as ``"edit, rename"``.  Splitting on
    # non-letters also accepts alternate casing and separators defensively.
    return frozenset(
        token.lower()
        for token in re.findall(r"[A-Za-z]+", value)
        if token.lower() not in {"none", "all"}
    )


def changed_file_status(change_types: frozenset[str]) -> str:
    """Map Azure flags to the provider-neutral ChangedFile status values."""

    if "delete" in change_types:
        return "removed"
    if change_types.intersection({"rename", "sourcerename", "targetrename"}):
        return "renamed"
    if change_types.intersection({"add", "undelete"}):
        return "added"
    return "modified"


def build_unified_patch(
    *,
    old_content: str,
    new_content: str,
    old_path: str,
    new_path: str,
    context_lines: int = 3,
) -> str | None:
    """Build a deterministic unified patch consumable by ``DiffParser``."""

    lines = list(
        unified_diff(
            old_content.splitlines(),
            new_content.splitlines(),
            fromfile=f"a/{old_path}",
            tofile=f"b/{new_path}",
            n=context_lines,
            lineterm="",
        )
    )
    return "\n".join(lines) if lines else None


def added_line_numbers(patch: str | None) -> frozenset[int]:
    """Return right-side line numbers that were added by a unified patch."""

    if not patch:
        return frozenset()

    header = re.compile(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
    current_line = 0
    result: set[int] = set()

    for line in patch.splitlines():
        match = header.match(line)
        if match:
            current_line = int(match.group(1))
            continue
        if line.startswith("+++"):
            continue
        if line.startswith("+"):
            result.add(current_line)
            current_line += 1
            continue
        if line.startswith("-") or line.startswith("\\"):
            continue
        current_line += 1

    return frozenset(result)
