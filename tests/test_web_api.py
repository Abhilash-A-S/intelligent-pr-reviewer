from unittest.mock import Mock

from fastapi.testclient import TestClient

from pr_reviewer.providers.models import PullRequestSummary
from pr_reviewer.review.models import ChangedFile, ChangedLine
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


def test_pull_request_listing_uses_provider_neutral_summary(monkeypatch):
    provider = Mock()
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
    provider.list_pull_requests.assert_called_once_with("acme/store", state="open")


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
