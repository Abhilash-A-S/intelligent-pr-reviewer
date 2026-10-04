from unittest.mock import Mock

import pytest

from pr_reviewer.providers.azure_devops import AzureDevOpsProvider
from pr_reviewer.providers.models import PullRequestSummary


def response_with(payload):
    response = Mock()
    response.json.return_value = payload
    response.status_code = 200
    return response


def test_list_pull_requests_returns_provider_neutral_models():
    client = Mock()
    client.get.return_value = response_with({
        "value": [{
            "pullRequestId": 41,
            "title": "Add reviewer",
            "createdBy": {"displayName": "Developer"},
            "targetRefName": "refs/heads/main",
            "sourceRefName": "refs/heads/feature/reviewer",
            "status": "active",
        }]
    })
    provider = AzureDevOpsProvider(client=client)

    result = provider.list_pull_requests("acme/platform/reviewer")

    assert result == [
        PullRequestSummary(
            number=41,
            title="Add reviewer",
            author="Developer",
            base_branch="main",
            head_branch="feature/reviewer",
            state="active",
        )
    ]
    call = client.get.call_args
    assert call.args[0].endswith(
        "/acme/platform/_apis/git/repositories/reviewer/pullrequests"
    )
    assert call.kwargs["params"]["searchCriteria_status"] == "active"


def test_repository_name_uses_injected_organization_and_project():
    provider = AzureDevOpsProvider(
        organization="acme",
        project="platform",
        client=Mock(),
    )

    assert provider._parse_repository("reviewer") == (
        "acme",
        "platform",
        "reviewer",
    )


def test_repository_name_without_context_is_rejected(monkeypatch):
    monkeypatch.delenv("AZURE_DEVOPS_ORG", raising=False)
    monkeypatch.delenv("AZURE_DEVOPS_PROJECT", raising=False)
    provider = AzureDevOpsProvider(client=Mock())

    with pytest.raises(ValueError, match="organization and project"):
        provider._parse_repository("reviewer")


def test_get_pull_request_maps_azure_metadata():
    client = Mock()
    client.get.return_value = response_with({
        "title": "Review API",
        "createdBy": {"displayName": "Developer"},
        "status": "active",
        "targetRefName": "refs/heads/main",
        "sourceRefName": "refs/heads/feature/api",
        "lastMergeSourceCommit": {"commitId": "abc123"},
    })
    provider = AzureDevOpsProvider(client=client)

    result = provider.get_pull_request("acme/platform/reviewer", 7)

    assert result.provider == "azure-devops"
    assert result.number == 7
    assert result.base_branch == "main"
    assert result.head_branch == "feature/api"
    assert result.head_commit == "abc123"


def test_summary_lookup_preserves_thread_context_for_updates():
    client = Mock()
    client.get.return_value = response_with({
        "value": [{
            "id": 91,
            "threadContext": None,
            "comments": [{
                "id": 3,
                "content": (
                    "<!-- intelligent-pr-reviewer:summary -->\n\nReview"
                ),
            }],
        }]
    })
    provider = AzureDevOpsProvider(client=client)

    result = provider.get_summary_comments("acme/platform/reviewer", 7)

    assert result == [{
        "id": 3,
        "thread_id": 91,
        "body": "<!-- intelligent-pr-reviewer:summary -->\n\nReview",
    }]


def test_publish_summary_uses_service_owned_marker_without_duplication():
    client = Mock()
    client.post.return_value = response_with({"id": 91})
    provider = AzureDevOpsProvider(client=client)
    body = "<!-- intelligent-pr-reviewer:summary -->\n\nReview"

    provider.publish_summary_comment("acme/platform/reviewer", 7, body)

    payload = client.post.call_args.kwargs["json"]
    assert payload["comments"][0]["content"] == body
    assert payload["comments"][0]["content"].count(
        "intelligent-pr-reviewer:summary"
    ) == 1


def test_update_summary_uses_azure_thread_comment_endpoint():
    client = Mock()
    client.patch.return_value = response_with({"id": 3, "content": "New"})
    provider = AzureDevOpsProvider(client=client)

    result = provider.update_summary_comment(
        repository="acme/platform/reviewer",
        comment_id=3,
        body="New",
        pull_number=7,
        thread_id=91,
    )

    call = client.patch.call_args
    assert call.args[0].endswith(
        "/pullrequests/7/threads/91/comments/3"
    )
    assert call.kwargs["json"] == {"content": "New"}
    assert result["id"] == 3


def test_update_summary_fails_closed_without_thread_identity():
    provider = AzureDevOpsProvider(client=Mock())

    with pytest.raises(ValueError, match="pull_number and thread_id"):
        provider.update_summary_comment(
            repository="acme/platform/reviewer",
            comment_id=3,
            body="New",
        )
