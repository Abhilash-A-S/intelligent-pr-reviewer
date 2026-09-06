import base64
from unittest.mock import Mock, patch

from pr_reviewer.providers.github import GitHubProvider


@patch("pr_reviewer.providers.github.httpx.Client")
def test_get_file_content(
    mock_client_class,
):
    mock_client = Mock()

    mock_client_class.return_value = (
        mock_client
    )

    source_code = (
        'console.log("hello");\n'
        'const value = 10;\n'
    )

    encoded_content = base64.b64encode(
        source_code.encode("utf-8")
    ).decode("utf-8")

    response = Mock()

    response.json.return_value = {
        "content": encoded_content,
        "encoding": "base64",
    }

    mock_client.get.return_value = (
        response
    )

    provider = GitHubProvider()

    result = provider.get_file_content(
        repository="example/repository",
        file_path="src/app.js",
        ref="abc123",
    )

    mock_client.get.assert_called_once_with(
        "/repos/example/repository/contents/src/app.js",
        params={
            "ref": "abc123",
        },
    )

    assert result == source_code


@patch("pr_reviewer.providers.github.httpx.Client")
def test_get_file_content_returns_empty_when_missing(
    mock_client_class,
):
    mock_client = Mock()

    mock_client_class.return_value = (
        mock_client
    )

    response = Mock()

    response.json.return_value = {
        "content": "",
        "encoding": "base64",
    }

    mock_client.get.return_value = (
        response
    )

    provider = GitHubProvider()

    result = provider.get_file_content(
        repository="example/repository",
        file_path="src/empty.js",
        ref="abc123",
    )

    assert result == ""