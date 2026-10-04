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
    updated_at: str | None = None
    changed_files: int | None = None


@dataclass(frozen=True, slots=True)
class OrganizationSummary:
    """Provider-neutral account or organization available to the token."""

    id: str
    name: str
    display_name: str
    description: str | None = None


@dataclass(frozen=True, slots=True)
class ProjectSummary:
    """Provider-neutral project within a source-control organization."""

    id: str
    name: str
    organization: str
    description: str | None = None


@dataclass(frozen=True, slots=True)
class RepositorySummary:
    """Provider-neutral repository option used by discovery UIs."""

    id: str
    name: str
    organization: str
    project: str | None = None
    full_name: str | None = None
    description: str | None = None
    default_branch: str | None = None
    visibility: str | None = None
