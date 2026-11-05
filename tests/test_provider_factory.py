from unittest.mock import Mock

import pytest

from pr_reviewer.providers.azure_devops import AzureDevOpsProvider
from pr_reviewer.providers.factory import (
    PROVIDER_NAMES,
    create_pull_request_provider,
    normalize_provider_name,
    provider_display_name,
)
from pr_reviewer.providers.github import GitHubProvider


def test_factory_exposes_stable_provider_names():
    assert PROVIDER_NAMES == ("github", "azure-devops")


def test_factory_creates_github_with_injected_client(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    provider = create_pull_request_provider("github", client=Mock())

    assert isinstance(provider, GitHubProvider)
    assert provider.provider_name == "github"


def test_factory_creates_azure_alias_with_injected_client(monkeypatch):
    monkeypatch.delenv("AZURE_DEVOPS_PAT", raising=False)

    provider = create_pull_request_provider("azure", client=Mock())

    assert isinstance(provider, AzureDevOpsProvider)
    assert provider.provider_name == "azure-devops"


def test_factory_rejects_unknown_provider():
    with pytest.raises(ValueError, match="Unsupported pull request provider"):
        create_pull_request_provider("git-lab", client=Mock())


@pytest.mark.parametrize(
    ("raw", "normalized", "display"),
    [
        ("github", "github", "GitHub"),
        ("azure", "azure-devops", "Azure DevOps"),
        ("azure_devops", "azure-devops", "Azure DevOps"),
        ("AZURE-DEVOPS", "azure-devops", "Azure DevOps"),
    ],
)
def test_provider_name_normalization(raw, normalized, display):
    assert normalize_provider_name(raw) == normalized
    assert provider_display_name(raw) == display


def test_github_requires_credentials_without_injected_client(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    with pytest.raises(ValueError, match="GITHUB_TOKEN"):
        GitHubProvider()


def test_azure_requires_credentials_without_injected_client(monkeypatch):
    monkeypatch.delenv("AZURE_DEVOPS_PAT", raising=False)

    with pytest.raises(ValueError, match="AZURE_DEVOPS_PAT"):
        AzureDevOpsProvider()
