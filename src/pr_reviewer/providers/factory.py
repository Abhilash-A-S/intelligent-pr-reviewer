from collections.abc import Callable
from typing import Final

from pr_reviewer.providers.azure_devops import AzureDevOpsProvider
from pr_reviewer.providers.base import PullRequestProvider
from pr_reviewer.providers.github import GitHubProvider


ProviderBuilder = Callable[..., PullRequestProvider]

_PROVIDER_BUILDERS: Final[dict[str, ProviderBuilder]] = {
    "github": GitHubProvider,
    "azure-devops": AzureDevOpsProvider,
}

_PROVIDER_ALIASES: Final[dict[str, str]] = {
    "azure": "azure-devops",
    "azure_devops": "azure-devops",
}

PROVIDER_NAMES: Final[tuple[str, ...]] = tuple(_PROVIDER_BUILDERS)


def normalize_provider_name(name: str) -> str:
    normalized = name.strip().lower()
    return _PROVIDER_ALIASES.get(normalized, normalized)


def create_pull_request_provider(
    name: str,
    **kwargs,
) -> PullRequestProvider:
    """Create one source-control provider from its stable public name."""

    normalized = normalize_provider_name(name)
    builder = _PROVIDER_BUILDERS.get(normalized)
    if builder is None:
        supported = ", ".join(PROVIDER_NAMES)
        raise ValueError(
            f"Unsupported pull request provider {name!r}. "
            f"Supported providers: {supported}."
        )
    return builder(**kwargs)


def provider_display_name(name: str) -> str:
    normalized = normalize_provider_name(name)
    if normalized == "github":
        return "GitHub"
    if normalized == "azure-devops":
        return "Azure DevOps"
    return name
