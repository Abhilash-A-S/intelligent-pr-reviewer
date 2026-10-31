import json
import time

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi.testclient import TestClient

from pr_reviewer.web.api import create_app
from pr_reviewer.web.security import AuthService, AuthSettings, Principal
from pr_reviewer.web.provider_access import ProviderAccess, GIT_NAMESPACE
from pr_reviewer.web.jobs import ReviewCommand

ALICE = Principal("issuer|alice", "Alice")
BOB = Principal("issuer|bob", "Bob")
TOKEN = "personal-token-that-must-never-leak"


class Jobs:
    def __init__(self):
        self.commands = []

    def submit(self, command):
        self.commands.append(command)
        return {"id": "job", "status": "queued"}

    def list(self, limit=50, predicate=None):
        return []

    def close(self):
        pass


@pytest.fixture
def setup(tmp_path, monkeypatch):
    for name in [
        "ALL_PROXY",
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "all_proxy",
        "https_proxy",
        "http_proxy",
    ]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PR_REVIEW_CONNECTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("PR_REVIEW_ENABLED_PROVIDERS", "github,azure-devops")
    monkeypatch.setenv("PR_REVIEW_GITHUB_CLIENT_ID", "github-client")
    monkeypatch.setenv("PR_REVIEW_GITHUB_CLIENT_SECRET", "github-secret")
    monkeypatch.delenv("PR_REVIEW_GITHUB_ORGANIZATIONS", raising=False)
    monkeypatch.delenv("PR_REVIEW_AZURE_ORGANIZATIONS", raising=False)
    auth = AuthService(
        AuthSettings(
            "https://identity.example/tenant",
            "client",
            "secret",
            "https://app.example",
            "",
            str(tmp_path / "auth.sqlite3"),
            "Microsoft",
            "provider",
        )
    )
    for user in [ALICE, BOB]:
        auth._save(
            "session",
            user.name.lower(),
            {"id": user.id, "name": user.name, "groups": [], "csrf": "csrf"},
            time.time() + 600,
        )
    jobs = Jobs()
    app = create_app(auth_service=auth, job_manager=jobs)
    client = TestClient(app, base_url="https://app.example")
    client.cookies.set(auth.SESSION, "alice")
    yield auth, client, jobs
    client.close()


def install_remote(monkeypatch, auth, handler):
    original = auth.connections.client

    def client(row):
        current = original(row)
        headers = dict(current.headers)
        current.close()
        return httpx.Client(
            headers=headers,
            transport=httpx.MockTransport(handler),
            follow_redirects=False,
        )

    monkeypatch.setattr(auth.connections, "client", client)


def github_response(request, push=True):
    if request.url.path == "/user":
        return httpx.Response(200, json={"id": 100, "login": "alice"})
    repo = {
        "full_name": "acme/store",
        "owner": {"type": "Organization", "login": "acme"},
        "permissions": {"pull": True, "push": push},
    }
    if request.url.path == "/user/repos":
        return httpx.Response(200, json=[repo])
    if request.url.path == "/repos/acme/store":
        return httpx.Response(200, json=repo)
    return httpx.Response(404, json={})


def save_github(auth, user=ALICE, **kwargs):
    auth.connections._save(
        user, "github", "", TOKEN, "github:100", time.time() + 600, **kwargs
    )


def azure_response(request, read=True, publish=True):
    path = request.url.path
    project = {"id": "project-id", "name": "Platform"}
    repo = {"id": "repo-id", "name": "Reviewer", "project": project}
    if path.endswith("/connectionData"):
        return httpx.Response(
            200, json={"authenticatedUser": {"id": "azure-alice", "isActive": True}}
        )
    if path.endswith("/projects"):
        return httpx.Response(200, json={"value": [project]})
    if path.endswith("/git/repositories"):
        return httpx.Response(200, json={"value": [repo]})
    if "/git/repositories/" in path:
        return httpx.Response(200, json=repo)
    if "/securitynamespaces/" in path:
        return httpx.Response(
            200,
            json={
                "value": [
                    {
                        "namespaceId": GIT_NAMESPACE,
                        "actions": [
                            {"name": "GenericRead", "bit": 2},
                            {"name": "PullRequestContribute", "bit": 16384},
                        ],
                    }
                ]
            },
        )
    if path.endswith("/permissionevaluationbatch"):
        evaluations = json.loads(request.content)["evaluations"]
        return httpx.Response(
            200,
            json={
                "evaluations": [
                    {**e, "value": read if e["permissions"] == 2 else publish}
                    for e in evaluations
                ]
            },
        )
    return httpx.Response(404, json={})


def test_empty_new_user_can_sign_in_and_connect_without_policy(setup):
    auth, client, _ = setup
    assert client.get("/api/auth/config").json()["configured"]
    profile = client.get("/api/auth/me").json()
    assert profile["repositories"] == [] and profile["access_mode"] == "provider"
    assert len(profile["connections"]) == 2


def test_vault_encrypted_persistent_and_user_isolated(setup):
    auth, _, _ = setup
    save_github(auth)
    assert TOKEN.encode() not in open(auth.settings.database, "rb").read()
    with auth._db() as db:
        assert TOKEN not in str(
            db.execute("SELECT * FROM provider_connections").fetchall()
        )
    restored = AuthService(auth.settings)
    assert (
        restored.connections.token(restored.connections.row(ALICE, "github")) == TOKEN
    )
    with pytest.raises(HTTPException):
        auth.connections.row(BOB, "github")


@pytest.mark.parametrize("push,level", [(True, 3), (False, 2)])
def test_github_permissions_and_separate_publishing(setup, monkeypatch, push, level):
    auth, client, _ = setup
    save_github(auth)
    install_remote(monkeypatch, auth, lambda r: github_response(r, push))
    assert auth.policy.permissions(ALICE) == {("github", "acme/store"): level}
    assert auth.policy.require(ALICE, "github", "acme/store", 2) == "acme/store"
    if not push:
        with pytest.raises(HTTPException):
            auth.policy.require(ALICE, "github", "acme/store", 3)
    profile = client.get("/api/auth/me").json()
    assert profile["repositories"][0]["can_publish"] == push
    assert TOKEN not in json.dumps(profile)


def test_provider_requests_use_user_token_not_server_admin(setup, monkeypatch):
    auth, _, _ = setup
    save_github(auth)
    monkeypatch.setenv("GITHUB_TOKEN", "admin-token")
    adapter = auth.adapter(ALICE, "github", "acme/store")
    assert adapter.client.headers["authorization"] == "Bearer " + TOKEN
    adapter.client.close()
    with pytest.raises(HTTPException):
        auth.adapter(BOB, "github", "acme/store")


def test_github_pagination_and_company_filter(setup, monkeypatch):
    auth, _, _ = setup
    save_github(auth)
    auth.connections.allowed["github"] = {"acme"}

    def remote(r):
        if r.url.params["page"] == "1":
            return httpx.Response(
                200,
                json=[
                    {
                        "full_name": "outside/private",
                        "permissions": {"pull": True, "push": True},
                    }
                ],
                headers={
                    "Link": '<https://api.github.com/user/repos?page=2>; rel="next"'
                },
            )
        return github_response(r)

    install_remote(monkeypatch, auth, remote)
    assert list(auth.policy.permissions(ALICE)) == [("github", "acme/store")]
    with pytest.raises(HTTPException):
        auth.policy.require(ALICE, "github", "outside/private")


def test_revoked_token_never_falls_back_to_policy_or_admin(setup, monkeypatch):
    auth, client, _ = setup
    save_github(auth)
    monkeypatch.setenv("GITHUB_TOKEN", "admin-token")
    install_remote(monkeypatch, auth, lambda r: httpx.Response(401, json={}))
    assert auth.policy.permissions(ALICE) == {}
    assert (
        client.get(
            "/api/pull-requests",
            params={"provider": "github", "repository": "acme/store"},
        ).status_code
        == 403
    )
    profile = client.get("/api/auth/me").json()
    assert not profile["connections"][0]["connected"]


def test_expired_connection_denies_without_remote_request(setup, monkeypatch):
    auth, _, _ = setup
    auth.connections._save(ALICE, "github", "", TOKEN, "github:100", time.time() - 1)
    assert auth.policy.permissions(ALICE) == {}
    with pytest.raises(HTTPException):
        auth.policy.require(ALICE, "github", "acme/store")


@pytest.mark.parametrize(
    "endpoint,body",
    [
        ("/api/connections/azure-devops", {"organization": "acme", "token": TOKEN}),
        ("/api/connections/github/authorize", {}),
    ],
)
def test_retired_connection_mutations_still_require_csrf(setup, endpoint, body):
    _, client, _ = setup
    assert client.post(endpoint, json=body).status_code == 403


@pytest.mark.parametrize(
    "org",
    [
        "https://dev.azure.com/acme",
        "../private",
        "acme?x=1",
        "acme/other",
        "localhost",
        "",
    ],
)
def test_azure_organization_validation_has_no_arbitrary_url(setup, org):
    _, client, _ = setup
    # localhost is a valid organization slug, but still cannot become a host.
    if org == "localhost":
        assert ProviderAccess.organization(org) == "localhost"
    else:
        with pytest.raises(HTTPException) as error:
            ProviderAccess.organization(org)
        assert error.value.status_code == 400


@pytest.mark.parametrize(
    "read,publish,allow,expected",
    [
        (True, True, True, 3),
        (True, True, False, 2),
        (True, False, True, 2),
        (False, True, True, 0),
    ],
)
def test_azure_effective_permissions_do_not_inherit_admin(
    setup, monkeypatch, read, publish, allow, expected
):
    auth, _, _ = setup
    auth.connections._save(
        ALICE, "azure-devops", "acme", TOKEN, "entra:alice", time.time() + 600, allow
    )
    install_remote(monkeypatch, auth, lambda r: azure_response(r, read, publish))
    assert (
        auth.policy.permissions(ALICE).get(
            ("azure-devops", "acme/platform/reviewer"), 0
        )
        == expected
    )


def test_error_response_never_echoes_pat(setup):
    _, client, _ = setup
    r = client.post(
        "/api/connections/azure-devops", json=[TOKEN], headers={"X-CSRF-Token": "csrf"}
    )
    assert r.status_code in {404, 405} and TOKEN not in r.text


def test_discovery_uses_connected_users_repository_owners(setup, monkeypatch):
    auth, client, _ = setup
    save_github(auth)
    install_remote(monkeypatch, auth, github_response)
    response = client.get(
        "/api/repository-discovery/organizations", params={"provider": "github"}
    )
    assert response.status_code == 200 and response.json()["items"][0]["name"] == "acme"
    response = client.get(
        "/api/repository-discovery/repositories",
        params={"provider": "github", "organization": "acme"},
    )
    assert response.json()["items"][0]["name"] == "store"


def test_publishing_and_job_version_are_server_assigned(setup, monkeypatch):
    auth, client, jobs = setup
    save_github(auth)
    install_remote(monkeypatch, auth, github_response)
    r = client.post(
        "/api/reviews",
        json={
            "provider": "github",
            "repository": "acme/store",
            "pull_number": 1,
            "publish": True,
            "owner_connection_version": "attacker",
        },
        headers={"X-CSRF-Token": "csrf"},
    )
    assert r.status_code == 202
    command = jobs.commands[0]
    assert (
        command.owner_id == ALICE.id
        and command.owner_connection_version
        == auth.connections.row(ALICE, "github")["version"]
    )
    old = command.owner_connection_version
    save_github(auth)
    assert auth.connections.row(ALICE, "github")["version"] != old


def test_disconnect_cannot_delete_another_users_connection(setup, monkeypatch):
    auth, client, _ = setup
    save_github(auth)
    save_github(auth, BOB)
    r = client.delete("/api/connections/github", headers={"X-CSRF-Token": "csrf"})
    assert r.status_code == 200
    with pytest.raises(HTTPException):
        auth.connections.row(ALICE, "github")
    assert auth.connections.row(BOB, "github")


def test_encryption_key_rotation_fails_closed(setup, monkeypatch):
    auth, _, _ = setup
    save_github(auth)
    auth.connections.key = Fernet.generate_key().decode()
    with pytest.raises(HTTPException) as exc:
        auth.connections.token(auth.connections.row(ALICE, "github"))
    assert exc.value.status_code == 503


def test_provider_outage_does_not_destroy_signed_in_identity(setup, monkeypatch):
    auth, client, _ = setup
    save_github(auth)
    install_remote(monkeypatch, auth, lambda r: httpx.Response(503, json={}))
    profile = client.get("/api/auth/me")
    assert profile.status_code == 200 and profile.json()["id"] == ALICE.id
    assert profile.json()["access_error"] and profile.json()["repositories"] == []
    assert (
        client.get(
            "/api/pull-requests",
            params={"provider": "github", "repository": "acme/store"},
        ).status_code
        == 503
    )


@pytest.mark.parametrize("mutation", ["disconnect", "replace", "disable"])
def test_real_worker_authorization_guard_rechecks_connection_version(
    setup, monkeypatch, mutation
):
    import pr_reviewer.web.api as module

    auth, _, _ = setup
    save_github(auth)
    install_remote(monkeypatch, auth, github_response)
    captured = []

    class Manager:
        def __init__(self, **kwargs):
            captured.append(kwargs)

        def close(self):
            pass

    monkeypatch.setattr(module, "ReviewJobManager", Manager)
    module.create_app(auth_service=auth)
    command = ReviewCommand(
        "github",
        "acme/store",
        1,
        owner_id=ALICE.id,
        owner_auth_expires_at=time.time() + 600,
        owner_connection_version=auth.connections.row(ALICE, "github")["version"],
    )
    captured[0]["execution_guard"](command)
    if mutation == "replace":
        save_github(auth)
    elif mutation == "disable":
        auth.connections.enabled = ("azure-devops",)
    else:
        with auth._db() as db:
            db.execute("DELETE FROM provider_connections WHERE owner=?", (ALICE.id,))
    with pytest.raises((HTTPException, PermissionError)):
        captured[0]["execution_guard"](command)
    with pytest.raises((HTTPException, PermissionError)):
        captured[0]["command_provider_factory"](command)


def test_missing_encryption_key_disables_connection_configuration(setup):
    auth, client, _ = setup
    auth.connections.key = ""
    assert not client.get("/api/auth/config").json()["configured"]
    assert (
        client.get(
            "/api/auth/login?provider=github",
        ).status_code
        == 503
    )


@pytest.mark.parametrize("push,publish,expected", [(False, True, 2), (True, True, 3), (True, False, 2)])
def test_personal_github_repositories_keep_live_permissions(setup, monkeypatch, push, publish, expected):
    auth, client, jobs = setup
    save_github(auth, publish=publish)
    repo = {
        "full_name": "alice/personal-review",
        "owner": {"type": "User", "login": "alice"},
        "permissions": {"pull": True, "push": push},
    }

    def remote(request):
        return httpx.Response(200, json=[repo] if request.url.path == "/user/repos" else repo)

    install_remote(monkeypatch, auth, remote)
    assert auth.policy.permissions(ALICE) == {("github", "alice/personal-review"): expected}
    profile = client.get("/api/auth/me").json()
    assert profile["repositories"][0]["can_publish"] == (expected == 3)
    owners = client.get("/api/repository-discovery/organizations", params={"provider": "github"})
    assert owners.status_code == 200 and owners.json()["items"][0]["name"] == "alice"
    response = client.post("/api/reviews", json={"provider": "github", "repository": "alice/personal-review", "pull_number": 1, "publish": True}, headers={"X-CSRF-Token": "csrf"})
    assert response.status_code == (202 if expected == 3 else 403)
    assert len(jobs.commands) == (1 if expected == 3 else 0)


@pytest.mark.parametrize("owner,pull", [("User", False), ("Unknown", True)])
def test_personal_github_discovery_and_direct_access_fail_closed(setup, monkeypatch, owner, pull):
    auth, _, _ = setup
    save_github(auth)
    repo = {"full_name": "alice/private", "owner": {"type": owner}, "permissions": {"pull": pull, "push": True}}
    install_remote(monkeypatch, auth, lambda request: httpx.Response(200, json=[repo] if request.url.path == "/user/repos" else repo))
    assert auth.policy.permissions(ALICE) == {}
    with pytest.raises(HTTPException) as error:
        auth.policy.require(ALICE, "github", "alice/private", 2)
    assert error.value.status_code == 403


def test_personal_github_repositories_respect_optional_owner_restriction(setup, monkeypatch):
    auth, _, _ = setup
    save_github(auth)
    auth.connections.allowed["github"] = {"acme"}
    repo = {"full_name": "alice/private", "owner": {"type": "User"}, "permissions": {"pull": True, "push": True}}
    install_remote(monkeypatch, auth, lambda request: httpx.Response(200, json=[repo] if request.url.path == "/user/repos" else repo))
    assert auth.policy.permissions(ALICE) == {}
    with pytest.raises(HTTPException):
        auth.policy.require(ALICE, "github", "alice/private", 2)


@pytest.mark.parametrize("enabled", [("github",), ("azure-devops",), ("github", "azure-devops"), ()])
def test_login_configuration_exposes_enabled_providers(setup, enabled):
    auth, client, _ = setup
    auth.connections.enabled = enabled
    config = client.get("/api/auth/config").json()
    assert config["enabled_providers"] == list(enabled)
    assert config["github_configured"] == ("github" in enabled)
    assert config["microsoft_configured"] == ("azure-devops" in enabled)
    if not enabled:
        assert not config["configured"]
