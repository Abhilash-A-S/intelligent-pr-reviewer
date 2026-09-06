from unittest.mock import Mock, patch

from pr_reviewer.providers.github import GitHubProvider


@patch("pr_reviewer.providers.github.httpx.Client")
def test_get_summary_comments(
    mock_client_class,
):
    mock_client = Mock()
    mock_client_class.return_value = mock_client

    response = Mock()

    response.json.return_value = [
        {
            "id": 100,
            "body": "Summary",
        }
    ]

    mock_client.get.return_value = response

    provider = GitHubProvider()

    result = provider.get_summary_comments(
        repository="example/repository",
        pull_number=10,
    )

    mock_client.get.assert_called_once_with(
        "/repos/example/repository/issues/10/comments"
    )

    assert len(result) == 1
    assert result[0]["id"] == 100


@patch("pr_reviewer.providers.github.httpx.Client")
def test_publish_summary_comment(
    mock_client_class,
):
    mock_client = Mock()
    mock_client_class.return_value = mock_client

    response = Mock()

    response.json.return_value = {
        "id": 200,
    }

    mock_client.post.return_value = response

    provider = GitHubProvider()

    result = provider.publish_summary_comment(
        repository="example/repository",
        pull_number=10,
        body="AI review summary",
    )

    mock_client.post.assert_called_once_with(
        "/repos/example/repository/issues/10/comments",
        json={
            "body": "AI review summary",
        },
    )

    assert result["id"] == 200


@patch("pr_reviewer.providers.github.httpx.Client")
def test_update_summary_comment(
    mock_client_class,
):
    mock_client = Mock()
    mock_client_class.return_value = mock_client

    response = Mock()

    response.json.return_value = {
        "id": 200,
        "body": "Updated",
    }

    mock_client.patch.return_value = response

    provider = GitHubProvider()

    result = provider.update_summary_comment(
        repository="example/repository",
        comment_id=200,
        body="Updated AI review",
    )

    mock_client.patch.assert_called_once_with(
        "/repos/example/repository/issues/comments/200",
        json={
            "body": "Updated AI review",
        },
    )

    assert result["id"] == 200