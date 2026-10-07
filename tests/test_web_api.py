from unittest.mock import Mock

import httpx

from fastapi.testclient import TestClient

from pr_reviewer.providers.models import (
    OrganizationSummary,
    ProjectSummary,
    PullRequestSummary,
    RepositorySummary,
)
from pr_reviewer.review.models import ChangedFile, ChangedLine, PullRequest
from pr_reviewer.web import api as web_api


class StubJobManager:
    def __init__(self):
        self.submitted = None

    def submit(self, command):
        self.submitted = command
        return {"id": "job-1", "status": "queued"}

    def list(self, limit=50):
        return [{"id": "job-1", "status": "completed"}][:limit]

    def get(self, job_id, include_result=True):
        if job_id != "job-1":
            return None
        return {"id": job_id, "status": "completed", "result": {} if include_result else None}

    def cancel(self, job_id):
        return None if job_id != "job-1" else True


def test_health_reports_connections_without_exposing_credentials(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "github-secret-value")
    monkeypatch.setenv("AZURE_DEVOPS_PAT", "azure-secret-value")
    client = TestClient(web_api.create_app(job_manager=StubJobManager()))

    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert all(provider["connected"] for provider in payload["providers"])
    rendered = response.text
    assert "github-secret-value" not in rendered
    assert "azure-secret-value" not in rendered


def test_health_reports_runtime_configuration_without_exposing_credentials(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "review-model")
    monkeypatch.setenv("OLLAMA_READ_TIMEOUT", "180")
    monkeypatch.setenv("PR_REVIEW_MAX_INLINE_COMMENTS", "27")
    client = TestClient(web_api.create_app(job_manager=StubJobManager()))

    payload = client.get("/api/health").json()

    assert payload["ollama"]["model"] == "review-model"
    assert payload["ollama"]["read_timeout_seconds"] == 180
    assert payload["review_policy"] == {
        "max_inline_comments": 27,
        "confirmation_before_publish": True,
        "duplicate_prevention": True,
        "summary_comment": True,
    }


def test_pull_request_listing_uses_provider_neutral_summary(monkeypatch):
    provider = Mock()
    provider.get_changed_file_count.return_value = 6
    provider.list_pull_requests.return_value = [
        PullRequestSummary(
            number=14,
            title="Improve checkout validation",
            author="reviewer",
            base_branch="main",
            head_branch="feature/checkout",
            state="open",
        )
    ]
    monkeypatch.setattr(web_api, "create_pull_request_provider", lambda _name: provider)
    client = TestClient(web_api.create_app(job_manager=StubJobManager()))

    response = client.get(
        "/api/pull-requests",
        params={"provider": "github", "repository": "acme/store"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["number"] == 14
    assert payload["items"][0]["changed_files"] == 6
    provider.list_pull_requests.assert_called_once_with("acme/store", state="open")
    provider.get_changed_file_count.assert_called_once_with("acme/store", 14)


def test_health_provider_probe_reports_authentication_failure(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "configured-but-invalid")
    monkeypatch.delenv("AZURE_DEVOPS_PAT", raising=False)
    provider = Mock()
    request = httpx.Request("GET", "https://api.github.com/user")
    response = httpx.Response(401, request=request)
    provider.validate_connection.side_effect = httpx.HTTPStatusError(
        "unauthorized",
        request=request,
        response=response,
    )
    monkeypatch.setattr(web_api, "create_pull_request_provider", lambda _name: provider)
    client = TestClient(web_api.create_app(job_manager=StubJobManager()))

    payload = client.get("/api/health", params={"probe_providers": True}).json()

    github = next(item for item in payload["providers"] if item["id"] == "github")
    assert github["configured"] is True
    assert github["connected"] is False
    assert github["state"] == "authentication-failed"
    assert "configured-but-invalid" not in str(payload)


def test_repository_discovery_endpoints_return_filtered_provider_data(monkeypatch):
    provider = Mock()
    provider.list_organizations.return_value = [
        OrganizationSummary(id="1", name="acme", display_name="Acme"),
        OrganizationSummary(id="2", name="other", display_name="Other"),
    ]
    provider.list_projects.return_value = [
        ProjectSummary(id="p1", name="Platform", organization="acme")
    ]
    provider.list_repositories.return_value = [
        RepositorySummary(
            id="r1",
            name="reviewer",
            organization="acme",
            project="Platform",
            full_name="acme/Platform/reviewer",
            default_branch="main",
        )
    ]
    monkeypatch.setattr(web_api, "create_pull_request_provider", lambda _name: provider)
    client = TestClient(web_api.create_app(job_manager=StubJobManager()))

    organizations = client.get(
        "/api/repository-discovery/organizations",
        params={"provider": "github", "query": "acme"},
    )
    projects = client.get(
        "/api/repository-discovery/projects",
        params={"provider": "azure-devops", "organization": "acme"},
    )
    repositories = client.get(
        "/api/repository-discovery/repositories",
        params={
            "provider": "azure-devops",
            "organization": "acme",
            "project": "Platform",
        },
    )

    assert organizations.status_code == 200
    assert organizations.json()["items"] == [
        {
            "id": "1",
            "name": "acme",
            "display_name": "Acme",
            "description": None,
        }
    ]
    assert projects.json()["items"][0]["name"] == "Platform"
    assert repositories.json()["items"][0]["full_name"] == "acme/Platform/reviewer"
    provider.list_projects.assert_called_once_with("acme")
    provider.list_repositories.assert_called_once_with("acme", "Platform")


def test_pull_request_detail_returns_live_provider_metadata(monkeypatch):
    provider = Mock()
    provider.get_pull_request.return_value = PullRequest(
        provider="github",
        repository="acme/store",
        number=14,
        title="Use live UI data",
        author="reviewer",
        base_branch="main",
        head_branch="feature/live-data",
        state="open",
        head_commit="abc123",
        description="Removes preview fixtures from the product UI.",
        commit_count=3,
    )
    monkeypatch.setattr(web_api, "create_pull_request_provider", lambda _name: provider)
    client = TestClient(web_api.create_app(job_manager=StubJobManager()))

    response = client.get(
        "/api/pull-requests/14",
        params={"provider": "github", "repository": "acme/store"},
    )

    assert response.status_code == 200
    assert response.json()["description"] == "Removes preview fixtures from the product UI."
    assert response.json()["commit_count"] == 3


def test_changed_files_include_diff_statistics_without_counting_headers(monkeypatch):
    provider = Mock()
    provider.get_changed_files.return_value = [
        ChangedFile(
            file_path="src/app.py",
            status="modified",
            language="python",
            patch=(
                "--- a/src/app.py\n"
                "+++ b/src/app.py\n"
                "@@ -1,2 +1,3 @@\n"
                "-old_value = 1\n"
                "+new_value = 2\n"
                "+enabled = True\n"
            ),
            changed_lines=[
                ChangedLine(file_path="src/app.py", line_number=1, content="new_value = 2"),
                ChangedLine(file_path="src/app.py", line_number=2, content="enabled = True"),
            ],
        )
    ]
    monkeypatch.setattr(web_api, "create_pull_request_provider", lambda _name: provider)
    client = TestClient(web_api.create_app(job_manager=StubJobManager()))

    response = client.get(
        "/api/pull-requests/7/files",
        params={"provider": "github", "repository": "acme/store"},
    )

    assert response.status_code == 200
    assert response.json()["items"][0] == {
        "file_path": "src/app.py",
        "status": "modified",
        "language": "python",
        "changed_line_count": 2,
        "additions": 2,
        "deletions": 1,
    }


def test_create_review_requires_server_side_provider_credentials(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    manager = StubJobManager()
    client = TestClient(web_api.create_app(job_manager=manager))

    response = client.post(
        "/api/reviews",
        json={
            "provider": "github",
            "repository": "acme/store",
            "pull_number": 7,
            "review_depth": "standard",
            "publish": False,
        },
    )

    assert response.status_code == 503
    assert "GITHUB_TOKEN" in response.json()["detail"]
    assert manager.submitted is None


def test_create_review_submits_provider_neutral_command(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "configured")
    manager = StubJobManager()
    client = TestClient(web_api.create_app(job_manager=manager))

    response = client.post(
        "/api/reviews",
        json={
            "provider": "github",
            "repository": "acme/store",
            "pull_number": 7,
            "review_depth": "deep",
            "publish": True,
            "max_workers": 2,
        },
    )

    assert response.status_code == 202
    assert manager.submitted.provider == "github"
    assert manager.submitted.repository == "acme/store"
    assert manager.submitted.publish is True
    assert manager.submitted.review_depth == "deep"


def test_unknown_review_job_returns_not_found():
    client = TestClient(web_api.create_app(job_manager=StubJobManager()))

    response = client.get("/api/reviews/missing")

    assert response.status_code == 404


def test_embedded_angular_shell_supports_deep_links():
    client = TestClient(web_api.create_app(job_manager=StubJobManager()))

    response = client.get("/history")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<app-root>" in response.text


def test_azure_file_statistics_hydrate_metadata_before_counting(monkeypatch):
    provider = Mock(supports_deferred_patch_hydration=True)
    metadata = [ChangedFile(file_path="src/app.js", status="added")]
    provider.get_changed_files.return_value = metadata
    provider.hydrate_changed_files.return_value = [
        ChangedFile(file_path="src/app.js", status="added",
                    patch="--- /dev/null\n+++ b/src/app.js\n@@ -0,0 +1,2 @@\n+first\n+++second\n")
    ]
    monkeypatch.setattr(web_api, "create_pull_request_provider", lambda _name: provider)
    client = TestClient(web_api.create_app(job_manager=StubJobManager()))
    response = client.get("/api/pull-requests/1/files", params={
        "provider": "azure-devops", "repository": "org/project/repo"})
    assert response.status_code == 200
    provider.hydrate_changed_files.assert_called_once_with("org/project/repo", 1, metadata)
    assert response.json()["items"][0]["additions"] == 2
    assert response.json()["items"][0]["deletions"] == 0


def test_file_statistics_preserve_unknown_binary_and_zero_text_counts(monkeypatch):
    provider = Mock(supports_deferred_patch_hydration=True)
    provider.get_changed_files.return_value = [ChangedFile(file_path="image.png", status="added")]
    provider.hydrate_changed_files.return_value = [
        ChangedFile(file_path="image.png", status="added", patch=None),
        ChangedFile(file_path="empty.txt", status="added", patch=""),
        ChangedFile(file_path="removed.txt", status="removed", patch="--- a/removed.txt\n+++ /dev/null\n@@ -1,2 +0,0 @@\n-line\n---source\n"),
    ]
    monkeypatch.setattr(web_api, "create_pull_request_provider", lambda _name: provider)
    client = TestClient(web_api.create_app(job_manager=StubJobManager()))
    response = client.get("/api/pull-requests/1/files", params={
        "provider": "azure-devops", "repository": "org/project/repo"})
    items = response.json()["items"]
    assert [(i["additions"], i["deletions"]) for i in items] == [(None, None), (0, 0), (0, 2)]
