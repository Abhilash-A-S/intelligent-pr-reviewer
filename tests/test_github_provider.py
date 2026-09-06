from unittest.mock import Mock, patch

import httpx
import pytest

from pr_reviewer.providers.github import GitHubProvider


@patch("pr_reviewer.providers.github.httpx.Client")
def test_get_pull_request(mock_client_class):
    mock_client = Mock()
    mock_client_class.return_value = mock_client

    mock_response = Mock()
    mock_response.json.return_value = {
        "title": "Add authentication",
        "user": {
            "login": "developer",
        },
        "state": "open",
        "base": {
            "ref": "main",
        },
        "head": {
            "ref": "feature/auth",
            "sha": "abc123",
        },
    }

    mock_client.get.return_value = mock_response

    provider = GitHubProvider()

    pull_request = provider.get_pull_request(
        repository="example/repository",
        pull_number=10,
    )

    assert pull_request.provider == "github"
    assert pull_request.repository == "example/repository"
    assert pull_request.number == 10
    assert pull_request.title == "Add authentication"
    assert pull_request.author == "developer"
    assert pull_request.base_branch == "main"
    assert pull_request.head_branch == "feature/auth"
    assert pull_request.head_commit == "abc123"


@patch("pr_reviewer.providers.github.httpx.Client")
def test_get_changed_files(mock_client_class):
    mock_client = Mock()
    mock_client_class.return_value = mock_client

    mock_response = Mock()
    mock_response.json.return_value = [
        {
            "filename": "src/app.js",
            "status": "modified",
            "patch": '@@ -1 +1 @@\n-console.log("old")\n+console.log("new")',
        }
    ]

    mock_client.get.return_value = mock_response

    provider = GitHubProvider()

    files = provider.get_changed_files(
        repository="example/repository",
        pull_number=10,
    )

    assert len(files) == 1

    changed_file = files[0]

    assert changed_file.file_path == "src/app.js"
    assert changed_file.status == "modified"
    assert changed_file.patch is not None
@patch("pr_reviewer.providers.github.httpx.Client")
def test_get_repository_tree_returns_only_blob_paths(mock_client_class):
    mock_client = Mock()
    mock_client_class.return_value = mock_client
    mock_response = Mock()
    mock_response.json.return_value = {
        "tree": [
            {"path": "nx-angular-review/nx.json", "type": "blob"},
            {"path": "nx-angular-review/apps", "type": "tree"},
            {"path": "nx-angular-review/apps/shop/src/main.ts", "type": "blob"},
        ]
    }
    mock_client.get.return_value = mock_response
    provider = GitHubProvider()
    result = provider.get_repository_tree("example/repository", "abc123")
    assert result == [
        "nx-angular-review/nx.json",
        "nx-angular-review/apps/shop/src/main.ts",
    ]

@patch("pr_reviewer.providers.github.httpx.Client")
def test_get_changed_files_fetches_all_github_pages(mock_client_class):
    mock_client = Mock()
    mock_client_class.return_value = mock_client

    first_page = Mock()
    first_page.json.return_value = [
        {"filename": f"src/file-{i}.ts", "status": "modified", "patch": "+x"}
        for i in range(100)
    ]
    second_page = Mock()
    second_page.json.return_value = [
        {"filename": f"src/file-{i}.ts", "status": "added", "patch": "+x"}
        for i in range(100, 135)
    ]
    mock_client.get.side_effect = [first_page, second_page]

    provider = GitHubProvider()
    files = provider.get_changed_files("example/repository", 10)

    assert len(files) == 135
    assert files[0].file_path == "src/file-0.ts"
    assert files[-1].file_path == "src/file-134.ts"
    assert mock_client.get.call_args_list[0].kwargs["params"] == {"per_page": 100, "page": 1}
    assert mock_client.get.call_args_list[1].kwargs["params"] == {"per_page": 100, "page": 2}


@patch("pr_reviewer.providers.github.httpx.Client")
def test_get_existing_comments_fetches_all_github_pages(mock_client_class):
    mock_client = Mock()
    mock_client_class.return_value = mock_client

    first_page = Mock()
    first_page.json.return_value = [{"id": i} for i in range(100)]
    second_page = Mock()
    second_page.json.return_value = [{"id": 100}]
    mock_client.get.side_effect = [first_page, second_page]

    provider = GitHubProvider()
    comments = provider.get_existing_comments("example/repository", 10)

    assert len(comments) == 101
    assert comments[-1]["id"] == 100


@patch("pr_reviewer.providers.github.httpx.Client")
def test_inline_comment_retries_422_with_verified_diff_position(mock_client_class):
    client = Mock()
    mock_client_class.return_value = client
    validation_response = Mock()
    validation_response.status_code = 422
    validation_response.json.return_value = {"message": "Validation Failed"}
    modern = Mock()
    modern.raise_for_status.side_effect = httpx.HTTPStatusError(
        "unprocessable",
        request=Mock(),
        response=validation_response,
    )
    legacy = Mock()
    legacy.json.return_value = {"id": 42}
    client.post.side_effect = [modern, legacy]
    provider = GitHubProvider()

    result = provider.publish_inline_comment(
        repository="example/repository",
        pull_number=10,
        body="Review",
        commit_id="abc123",
        file_path="src/app.js",
        line_number=25,
        diff_position=7,
    )

    assert result == {"id": 42}
    assert client.post.call_count == 2
    assert client.post.call_args_list[0].kwargs["json"]["line"] == 25
    assert client.post.call_args_list[0].kwargs["json"]["side"] == "RIGHT"
    assert client.post.call_args_list[1].kwargs["json"]["position"] == 7
    assert "line" not in client.post.call_args_list[1].kwargs["json"]


@patch("pr_reviewer.providers.github.httpx.Client")
def test_inline_comment_does_not_retry_secondary_throttle(mock_client_class, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    client = Mock()
    mock_client_class.return_value = client
    response = Mock()
    response.status_code = 422
    response.json.return_value = {
        "message": "Validation Failed",
        "errors": [{"message": "was submitted too quickly"}],
    }
    failed = Mock()
    failed.raise_for_status.side_effect = httpx.HTTPStatusError(
        "unprocessable", request=Mock(), response=response,
    )
    client.post.return_value = failed
    provider = GitHubProvider()

    with pytest.raises(httpx.HTTPStatusError):
        provider.publish_inline_comment(
            repository="example/repository", pull_number=1, body="body",
            commit_id="abc", file_path="src/app.ts", line_number=10,
            diff_position=5,
        )

    assert client.post.call_count == 1


@patch("pr_reviewer.providers.github.httpx.Client")
def test_github_batch_review_uses_single_request(mock_client_class, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    client = Mock()
    mock_client_class.return_value = client
    response = Mock()
    response.json.return_value = {"id": 77}
    client.post.return_value = response
    provider = GitHubProvider()

    result = provider.publish_inline_comments_batch(
        repository="example/repository", pull_number=1, commit_id="abc",
        comments=[
            {"file_path": "src/app.ts", "line_number": 10, "body": "one"},
            {"file_path": "src/app.ts", "line_number": 20, "body": "two"},
        ],
    )

    assert result == {"id": 77}
    client.post.assert_called_once()
    call = client.post.call_args
    assert call.args[0] == "/repos/example/repository/pulls/1/reviews"
    assert call.kwargs["json"]["event"] == "COMMENT"
    assert len(call.kwargs["json"]["comments"]) == 2
