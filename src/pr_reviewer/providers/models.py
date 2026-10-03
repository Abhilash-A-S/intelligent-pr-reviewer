from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PullRequestSummary:
    """Provider-neutral pull-request data used by selection UIs."""

    number: int
    title: str
    author: str
    base_branch: str
    head_branch: str
    state: str
