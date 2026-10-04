from unittest.mock import Mock, patch

import httpx

from pr_reviewer.context.models import RepositoryContext
from pr_reviewer.llm.ollama import OllamaProvider
from pr_reviewer.review.models import (
    ChangedFile,
    ChangedLine,
)


@patch("pr_reviewer.llm.ollama.httpx.Client")
def test_ollama_provider_review(
    mock_client_class,
):
    mock_client = Mock()
    mock_client_class.return_value = mock_client

    mock_response = Mock()

    mock_response.json.return_value = {
        "response": "Review completed."
    }

    mock_client.post.return_value = (
        mock_response
    )

    provider = OllamaProvider(
        model="qwen2.5-coder:7b",
        base_url="http://localhost:11434",
    )

    changed_file = ChangedFile(
        file_path="src/app.js",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app.js",
                line_number=10,
                content='console.log("debug");',
                diff_position=5,
            ),
        ],
        full_content=(
            'console.log("debug");\n'
        ),
    )

    context = RepositoryContext(
        languages={"javascript"},
        framework="react",
        project_type="frontend-web",
    )

    result = provider.review(
        changed_file=changed_file,
        repository_context=context,
    )

    assert result == "Review completed."

    mock_client.post.assert_called_once()

    request_json = (
        mock_client
        .post
        .call_args
        .kwargs["json"]
    )

    assert (
        request_json["model"]
        == "qwen2.5-coder:7b"
    )

    assert request_json["stream"] is False

    prompt = request_json["prompt"]

    assert "src/app.js" in prompt
    assert "javascript" in prompt
    assert "react" in prompt

    assert (
        '10 | console.log("debug");'
        in prompt
    )


def test_ollama_provider_defaults(
    monkeypatch,
):
    monkeypatch.delenv(
        "OLLAMA_MODEL",
        raising=False,
    )

    monkeypatch.delenv(
        "OLLAMA_BASE_URL",
        raising=False,
    )

    monkeypatch.delenv(
        "OLLAMA_READ_TIMEOUT",
        raising=False,
    )
    monkeypatch.delenv(
        "OLLAMA_MAX_CONCURRENT_REVIEWS",
        raising=False,
    )

    with patch(
        "pr_reviewer.llm.ollama.httpx.Client"
    ):
        provider = OllamaProvider()

    assert (
        provider.model
        == "qwen2.5-coder:7b"
    )

    assert (
        provider.base_url
        == "http://localhost:11434"
    )
    assert provider.recommended_concurrency == 1


def test_ollama_provider_concurrency_can_be_tuned(monkeypatch):
    monkeypatch.setenv("OLLAMA_MAX_CONCURRENT_REVIEWS", "2")

    with patch("pr_reviewer.llm.ollama.httpx.Client"):
        provider = OllamaProvider()

    assert provider.recommended_concurrency == 2

def test_ollama_provider_applies_bounded_generation_settings(monkeypatch):
    monkeypatch.setenv("OLLAMA_NUM_PREDICT", "777")
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "20m")

    with patch("pr_reviewer.llm.ollama.httpx.Client") as client_class:
        client = Mock()
        client_class.return_value = client
        response = Mock()
        response.json.return_value = {"response": '{"findings": []}'}
        client.post.return_value = response

        provider = OllamaProvider()
        provider.review(
            changed_file=ChangedFile(
                file_path="src/app.ts",
                status="modified",
                changed_lines=[
                    ChangedLine(
                        file_path="src/app.ts",
                        line_number=1,
                        content="const value = 1;",
                        diff_position=1,
                    )
                ],
                full_content="const value = 1;",
            ),
            repository_context=RepositoryContext(languages={"typescript"}),
        )

    payload = client.post.call_args.kwargs["json"]
    assert payload["keep_alive"] == "20m"
    assert payload["options"]["temperature"] == 0
    assert payload["options"]["num_predict"] == 777
    assert payload["format"]["type"] == "object"
    assert payload["format"]["properties"]["findings"]["maxItems"] == 5


def test_ollama_default_generation_budget_is_bounded(monkeypatch):
    monkeypatch.delenv("OLLAMA_NUM_PREDICT", raising=False)
    with patch("pr_reviewer.llm.ollama.httpx.Client"):
        provider = OllamaProvider()
    assert provider.num_predict == 512


def test_batch_schema_requires_an_exact_allowed_file_path():
    with patch("pr_reviewer.llm.ollama.httpx.Client") as client_class:
        client = Mock()
        client_class.return_value = client
        response = Mock()
        response.json.return_value = {"response": '{"findings": []}'}
        client.post.return_value = response
        provider = OllamaProvider()
        files = [
            ChangedFile(
                file_path=path,
                status="modified",
                changed_lines=[ChangedLine(path, 1, "run();", 1)],
                full_content="run();",
            )
            for path in ("src/browser.js", "src/server.js")
        ]

        provider.review_batch(files, RepositoryContext(languages={"javascript"}))

    schema = client.post.call_args.kwargs["json"]["format"]
    finding = schema["$defs"]["LLMFinding"]
    assert "file_path" in finding["required"]
    assert finding["properties"]["file_path"]["enum"] == [
        "src/browser.js", "src/server.js",
    ]


def test_single_file_schema_preserves_implicit_path_compatibility():
    schema = OllamaProvider._response_schema(["src/app.js"])
    assert "file_path" not in schema["$defs"]["LLMFinding"]["required"]


def test_ollama_falls_back_to_json_mode_for_older_schema_api():
    with patch("pr_reviewer.llm.ollama.httpx.Client") as client_class:
        client = Mock()
        client_class.return_value = client
        unsupported = Mock()
        unsupported.raise_for_status.side_effect = httpx.HTTPStatusError(
            "schema unsupported",
            request=httpx.Request("POST", "http://localhost:11434/api/generate"),
            response=httpx.Response(400),
        )
        supported = Mock()
        supported.raise_for_status.return_value = None
        supported.json.return_value = {"response": '{"findings": []}'}
        client.post.side_effect = [unsupported, supported]

        provider = OllamaProvider()
        result = provider.review(
            ChangedFile(
                file_path="src/app.js",
                status="modified",
                changed_lines=[ChangedLine("src/app.js", 1, "run();", 1)],
                full_content="run();",
            ),
            RepositoryContext(languages={"javascript"}),
        )

    assert result == '{"findings": []}'
    assert client.post.call_count == 2
    assert client.post.call_args_list[1].kwargs["json"]["format"] == "json"


def test_ollama_defaults_to_one_expensive_attempt(monkeypatch):
    monkeypatch.delenv("OLLAMA_MAX_ATTEMPTS", raising=False)

    with patch("pr_reviewer.llm.ollama.httpx.Client"):
        provider = OllamaProvider()

    assert provider.recommended_max_attempts == 1
