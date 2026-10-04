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

    provider = GitHubProvider(token="test-token")

    result = provider.get_summary_comments(
        repository="example/repository",
        pull_number=10,
    )

    mock_client.get.assert_called_once_with(
        "/repos/example/repository/issues/10/comments",
        params={"per_page": 100, "page": 1},
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

    provider = GitHubProvider(token="test-token")

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

    provider = GitHubProvider(token="test-token")

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


@patch("pr_reviewer.providers.github.httpx.Client")
def test_get_summary_comments_fetches_all_pages(mock_client_class):
    client = Mock()
    mock_client_class.return_value = client
    first_page = Mock()
    first_page.json.return_value = [{"id": index} for index in range(100)]
    second_page = Mock()
    second_page.json.return_value = [{"id": 100}]
    client.get.side_effect = [first_page, second_page]
    provider = GitHubProvider(token="test-token")

    result = provider.get_summary_comments("example/repository", 10)

    assert len(result) == 101
    assert client.get.call_args_list[1].kwargs["params"] == {
        "per_page": 100,
        "page": 2,
    }
