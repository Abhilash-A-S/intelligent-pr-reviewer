import json
import time

import httpx
import pytest
from fastapi import HTTPException
from pr_reviewer.web.security import AuthService, Principal, AuthSettings
from test_provider_access import (
    setup as provider_fixture,
    ALICE,
    TOKEN,
    install_remote,
    azure_response,
    save_github,
)
from test_provider_login import start

setup = provider_fixture


def test_organization_mode_ignores_previous_pat_setting(setup, monkeypatch):
    auth, client, _ = setup
    monkeypatch.setenv("PR_REVIEW_MICROSOFT_REPOSITORY_AUTH", "pat")
    fresh = AuthService(auth.settings)
    assert fresh.connections.microsoft_mode == "delegated"
    assert (
        client.get("/api/auth/config").json()["microsoft_repository_auth"]
        == "delegated"
    )
    monkeypatch.setattr(
        auth,
        "metadata",
        lambda: {
            "authorization_endpoint": "https://login.microsoftonline.com/tenant/authorize",
            "token_endpoint": "https://login.microsoftonline.com/tenant/token",
        },
    )
    _, query = start(client, "microsoft")
    assert "499b84ac-1321-427f-aa17-267ca6975798/.default" in query["scope"][0]


@pytest.mark.parametrize(
    "path",
    [
        "/api/connections/azure-devops",
        "/api/connections/github/authorize",
        "/api/connections/azure-devops/authorize",
    ],
)
def test_manual_credential_endpoints_are_not_exposed(setup, path):
    auth, client, _ = setup
    result = client.post(
        path,
        json={"token": TOKEN, "organization": "acme"},
        headers={"X-CSRF-Token": "csrf"},
    )
    assert result.status_code in {404, 405}
    assert TOKEN not in result.text
    assert auth.connections._rows(ALICE) == []


@pytest.mark.parametrize("provider", ["github", "azure-devops"])
def test_retired_connection_callback_cannot_create_credentials(setup, provider):
    auth, client, _ = setup
    assert (
        client.get(
            "/api/connections/" + provider + "/callback?code=unused&state=unused"
        ).status_code
        == 404
    )
    assert auth.connections._rows(ALICE) == []


def test_saved_personal_pat_is_never_reused_for_company_access(setup, monkeypatch):
    auth, client, _ = setup
    auth.connections._save(
        ALICE, "azure-devops", "acme", TOKEN, "pat:alice", time.time() + 3600
    )
    monkeypatch.setenv("AZURE_DEVOPS_PAT", "server-admin-token")
    monkeypatch.setattr(
        auth.connections,
        "client",
        lambda *_: pytest.fail("Legacy PAT must not reach an HTTP client"),
    )
    assert auth.connections.permissions(ALICE) == {}
    assert client.get("/api/auth/me").json()["repositories"] == []
    with pytest.raises(HTTPException):
        auth.connections.row(ALICE, "azure-devops", "acme/platform/reviewer")


@pytest.mark.parametrize("owner_type", [None, "Unknown"])
def test_unknown_github_owner_types_are_not_access_grants(
    setup, monkeypatch, owner_type
):
    auth, client, _ = setup
    save_github(auth)

    def remote(request):
        data = {
            "full_name": "acme/store",
            "permissions": {"pull": True, "push": True},
            "owner": {"type": owner_type},
        }
        return httpx.Response(
            200, json=[data] if request.url.path == "/user/repos" else data
        )

    install_remote(monkeypatch, auth, remote)
    assert auth.connections.permissions(ALICE) == {}
    with pytest.raises(HTTPException):
        auth.connections.require(ALICE, "github", "acme/store")


def test_github_sso_error_explains_org_authorization_without_returning_tokens(
    setup, monkeypatch
):
    auth, client, _ = setup
    save_github(auth)
    auth._save(
        "session",
        "scoped",
        {
            "id": ALICE.id,
            "name": "Alice",
            "groups": [],
            "csrf": "csrf",
            "provider": "github",
        },
        time.time() + 600,
    )
    client.cookies.set(auth.SESSION, "scoped")
    install_remote(
        monkeypatch,
        auth,
        lambda r: httpx.Response(
            403,
            headers={"X-GitHub-SSO": "required; url=https://github.com/orgs/acme/sso"},
            json={},
        ),
    )
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    profile = response.json()
    assert profile["repositories"] == [] and "SSO" in profile["access_error"]
    assert not profile["connection_fallback"] and TOKEN not in json.dumps(profile)


def test_github_rate_limit_is_not_reported_as_bad_identity(setup, monkeypatch):
    auth, _, _ = setup
    save_github(auth)
    install_remote(
        monkeypatch,
        auth,
        lambda r: httpx.Response(403, headers={"X-RateLimit-Remaining": "0"}, json={}),
    )
    with pytest.raises(HTTPException) as error:
        auth.connections.require(ALICE, "github", "acme/store")
    assert error.value.status_code == 503 and "rate limit" in error.value.detail


def test_a_denied_azure_organization_does_not_hide_an_accessible_one(
    setup, monkeypatch
):
    auth, _, _ = setup
    user = Principal(ALICE.id, "Alice", provider="azure-devops")
    auth.connections._save(
        user, "azure-devops", "", TOKEN, "entra:alice", time.time() + 600
    )

    def remote(request):
        if request.url.path.endswith("/profiles/me"):
            return httpx.Response(200, json={"id": "member"})
        if request.url.path.endswith("/accounts"):
            return httpx.Response(
                200, json={"value": [{"accountName": "acme"}, {"accountName": "other"}]}
            )
        if request.url.path.startswith("/other/"):
            return httpx.Response(403, json={})
        return azure_response(request)

    install_remote(monkeypatch, auth, remote)
    assert auth.connections.permissions(user) == {
        ("azure-devops", "acme/platform/reviewer"): 3
    }


def test_missing_delegated_access_token_cannot_create_identity_only_company_session(
    setup, monkeypatch
):
    import pr_reviewer.web.security as module

    auth, client, _ = setup
    monkeypatch.setattr(
        auth,
        "metadata",
        lambda: {
            "authorization_endpoint": "https://login.microsoftonline.com/tenant/authorize",
            "token_endpoint": "https://login.microsoftonline.com/tenant/token",
        },
    )
    state, _ = start(client, "microsoft")
    monkeypatch.setattr(
        auth,
        "verify_id_token",
        lambda *_: {"sub": "alice", "name": "Alice", "exp": time.time() + 600},
    )
    original = httpx.Client

    class Client:
        def __enter__(self):
            return original(
                transport=httpx.MockTransport(
                    lambda r: httpx.Response(200, json={"id_token": "signed"})
                )
            )

        def __exit__(self, *_):
            pass

        def __init__(self, *_, **__):
            pass

    monkeypatch.setattr(module.httpx, "Client", Client)
    response = client.get(
        "/api/auth/callback",
        params={"state": state, "code": "code"},
        follow_redirects=False,
    )
    assert response.headers["location"] == "/login?error=sign_in_failed"
    assert auth.connections._rows(ALICE) == []


def test_new_deployment_defaults_to_provider_authorization(monkeypatch):
    monkeypatch.delenv("PR_REVIEW_ACCESS_MODE", raising=False)
    assert AuthSettings.from_env().access_mode == "provider"


def test_malformed_provider_json_is_a_service_error_without_session_loss(
    setup, monkeypatch
):
    auth, client, _ = setup
    save_github(auth)
    install_remote(
        monkeypatch,
        auth,
        lambda r: httpx.Response(200, text="<html>upstream gateway error</html>"),
    )
    response = client.get("/api/auth/me")
    assert response.status_code == 200 and response.json()["id"] == ALICE.id
    assert response.json()["access_error"] and "<html>" not in response.text
    with pytest.raises(HTTPException) as error:
        auth.connections.require(ALICE, "github", "acme/store")
    assert error.value.status_code == 503


def test_retired_api_paths_return_json_instead_of_the_spa(setup):
    _, client, _ = setup
    response = client.get(
        "/api/connections/azure-devops/callback?state=old&code=unused"
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "API endpoint not found"
