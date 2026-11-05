import time
from dataclasses import replace
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

from pr_reviewer.web.api import create_app
from pr_reviewer.web.security import AuthService, Principal
from test_provider_access import (  # noqa: F401
    setup as provider_fixture,
    ALICE,
    TOKEN,
    install_remote,
    github_response,
    azure_response,
    save_github,
)


setup = provider_fixture


def start(client, provider):
    response = client.get(
        "/api/auth/login", params={"provider": provider}, follow_redirects=False
    )
    assert response.status_code == 302, response.text
    query = parse_qs(urlparse(response.headers["location"]).query)
    return query["state"][0], query


def oauth_transport(monkeypatch, auth, provider, identity=None):
    import pr_reviewer.web.security as module

    original = httpx.Client
    calls = []

    def remote(request):
        calls.append(request)
        if request.url.path.endswith("/access_token") or request.url.path.endswith(
            "/token"
        ):
            return httpx.Response(
                200,
                json={
                    "access_token": TOKEN,
                    "token_type": "bearer",
                    "scope": "repo read:user",
                    "expires_in": 3600,
                    "id_token": "verified-id-token",
                },
            )
        if request.url.path == "/user":
            return httpx.Response(
                200, json=identity or {"id": 101, "login": "alice", "name": "Alice"}
            )
        if request.url.path.endswith("/profiles/me"):
            return httpx.Response(200, json={"id": "member-alice"})
        if request.url.path.endswith("/accounts"):
            return httpx.Response(
                200,
                json={
                    "value": [{"accountName": "acme"}, {"accountName": "other-company"}]
                },
            )
        return (
            azure_response(request)
            if provider == "microsoft"
            else github_response(request)
        )

    class Client:
        def __init__(self, *args, **kwargs):
            self.inner = original(
                transport=httpx.MockTransport(remote), headers=kwargs.get("headers")
            )

        def __enter__(self):
            return self.inner

        def __exit__(self, *args):
            self.inner.close()

    monkeypatch.setattr(module.httpx, "Client", Client)
    return calls


def test_both_buttons_readiness_is_independent(setup):
    _, client, _ = setup
    config = client.get("/api/auth/config").json()
    assert config["microsoft_configured"] and config["github_configured"]
    assert TOKEN not in str(config)


def test_github_sign_in_without_microsoft_configuration(setup):
    auth, _, _ = setup
    settings = replace(
        auth.settings,
        issuer="",
        client_id="",
        client_secret="",
        github_client_id="github-id",
        github_client_secret="github-secret",
    )
    assert settings.configured and not settings.microsoft_configured
    github = AuthService(settings)
    with TestClient(
        create_app(auth_service=github), base_url="https://app.example"
    ) as client:
        config = client.get("/api/auth/config").json()
        assert config["github_configured"] and not config["microsoft_configured"]
        _, query = start(client, "github")
        assert query["redirect_uri"] == ["https://app.example/api/auth/github/callback"]
        assert client.get("/api/auth/login?provider=microsoft").status_code == 503


def test_github_login_pkce_browser_binding_and_stable_verified_identity(
    setup, monkeypatch
):
    auth, client, _ = setup
    state, query = start(client, "github")
    assert query["code_challenge_method"] == ["S256"]
    assert query["scope"] == ["repo read:user"]
    transaction = auth._load("login", state)
    calls = oauth_transport(monkeypatch, auth, "github")
    result = client.get(
        "/api/auth/github/callback",
        params={"state": state, "code": "github-code"},
        follow_redirects=False,
    )
    assert result.status_code == 303 and result.headers["location"] == "/"
    session = auth._load(
        "session", client.cookies.get(auth.SESSION, domain="app.example", path="/")
    )
    assert session["id"] == "https://github.com|101" and session["provider"] == "github"
    assert auth._load("session", "alice") is None  # Previous session rotated.
    user = Principal(session["id"], session["name"], provider="github")
    assert auth.connections.token(auth.connections.row(user, "github")) == TOKEN
    exchanged = parse_qs(calls[0].content.decode())
    assert exchanged["code_verifier"] == [transaction["verifier"]]
    profile = client.get("/api/auth/me").json()
    assert profile["active_provider"] == "github" and profile["enabled_providers"] == [
        "github"
    ]
    assert all(r["provider"] == "github" for r in profile["repositories"])
    assert TOKEN not in str(profile)
    replay = client.get(
        "/api/auth/github/callback",
        params={"state": state, "code": "github-code"},
        follow_redirects=False,
    )
    assert replay.headers["location"] == "/login?error=sign_in_failed"


@pytest.mark.parametrize(
    "bad",
    ["missing-cookie", "wrong-provider", "expired", "provider-error", "missing-code"],
)
def test_github_callback_rejects_unbound_and_invalid_transactions(setup, bad):
    auth, client, _ = setup
    state, _ = start(client, "github")
    query = {"state": state, "code": "code"}
    if bad == "missing-cookie":
        client.cookies.clear()
    elif bad == "wrong-provider":
        with auth._db() as db:
            import json

            row = db.execute(
                "SELECT payload FROM auth_state WHERE kind=? AND key=?",
                ("login", auth._digest(state)),
            ).fetchone()
            payload = json.loads(row[0])
            payload["provider"] = "microsoft"
            db.execute(
                "UPDATE auth_state SET payload=? WHERE kind=? AND key=?",
                (json.dumps(payload), "login", auth._digest(state)),
            )
    elif bad == "expired":
        with auth._db() as db:
            db.execute("UPDATE auth_state SET expires=0 WHERE kind=?", ("login",))
    elif bad == "provider-error":
        query["error"] = "access_denied"
    else:
        query.pop("code")
    result = client.get(
        "/api/auth/github/callback", params=query, follow_redirects=False
    )
    assert result.headers["location"] == "/login?error=sign_in_failed"
    assert auth.connections._rows(Principal("https://github.com|101", "Alice")) == []


@pytest.mark.parametrize(
    "identity",
    [
        {"login": "alice"},
        {"id": True, "login": "alice"},
        {"id": -1, "login": "alice"},
        {"id": 101},
    ],
)
def test_github_login_requires_verified_numeric_account_identity(
    setup, monkeypatch, identity
):
    auth, client, _ = setup
    state, _ = start(client, "github")
    oauth_transport(monkeypatch, auth, "github", identity)
    result = client.get(
        "/api/auth/github/callback",
        params={"state": state, "code": "code"},
        follow_redirects=False,
    )
    assert "error=sign_in_failed" in result.headers["location"]


def test_microsoft_delegated_login_discovers_orgs_repos_without_pat(setup, monkeypatch):
    auth, client, _ = setup
    auth.connections.microsoft_mode = "delegated"
    auth.connections.allowed["azure-devops"] = {"acme"}
    monkeypatch.setattr(
        auth,
        "metadata",
        lambda: {
            "authorization_endpoint": "https://login.microsoftonline.com/tenant/authorize",
            "token_endpoint": "https://login.microsoftonline.com/tenant/token",
        },
    )
    state, query = start(client, "microsoft")
    assert "499b84ac-1321-427f-aa17-267ca6975798/.default" in query["scope"][0]
    nonce = auth._load("login", state)["nonce"]

    def verify(token, expected_nonce):
        assert token == "verified-id-token" and expected_nonce == nonce
        return {
            "sub": "alice",
            "oid": "entra-alice",
            "name": "Alice",
            "exp": time.time() + 3600,
        }

    monkeypatch.setattr(auth, "verify_id_token", verify)
    calls = oauth_transport(monkeypatch, auth, "microsoft")
    result = client.get(
        "/api/auth/callback",
        params={"state": state, "code": "code"},
        follow_redirects=False,
    )
    assert result.headers["location"] == "/"
    profile = client.get("/api/auth/me").json()
    assert (
        profile["active_provider"] == "azure-devops"
        and not profile["connection_fallback"]
    )
    assert profile["enabled_providers"] == ["azure-devops"]
    assert profile["repositories"][0]["repository"] == "acme/platform/reviewer"
    assert not any("other-company" in str(request.url) for request in calls)
    row = auth.connections.row(
        Principal(profile["id"], "Alice", provider="azure-devops"),
        "azure-devops",
        "acme/platform/reviewer",
    )
    assert row["organization"] == "acme"
    assert (
        auth.policy.require(
            Principal(profile["id"], "Alice", provider="azure-devops"),
            "azure-devops",
            "acme/platform/reviewer",
            3,
        )
        == "acme/platform/reviewer"
    )


def test_selected_provider_enforced_on_direct_api_and_mutations(setup, monkeypatch):
    auth, client, jobs = setup
    save_github(auth)
    auth.connections._save(
        ALICE, "azure-devops", "acme", TOKEN, "entra:alice", time.time() + 3600
    )
    auth._save(
        "session",
        "github-session",
        {
            "id": ALICE.id,
            "name": "Alice",
            "groups": [],
            "csrf": "csrf",
            "provider": "github",
        },
        time.time() + 600,
    )
    client.cookies.set(auth.SESSION, "github-session")
    install_remote(monkeypatch, auth, github_response)
    assert client.get("/api/auth/me").json()["enabled_providers"] == ["github"]
    assert (
        client.get(
            "/api/pull-requests",
            params={"provider": "azure-devops", "repository": "acme/platform/reviewer"},
        ).status_code
        == 403
    )
    assert client.post(
        "/api/connections/azure-devops",
        json={"organization": "acme", "token": TOKEN},
        headers={"X-CSRF-Token": "csrf"},
    ).status_code in {404, 405}
    assert (
        client.post(
            "/api/reviews",
            json={
                "provider": "azure-devops",
                "repository": "acme/platform/reviewer",
                "pull_number": 1,
            },
            headers={"X-CSRF-Token": "csrf"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/reviews",
            json={
                "provider": "github",
                "repository": "acme/store",
                "pull_number": 1,
                "owner_login_provider": "azure-devops",
            },
            headers={"X-CSRF-Token": "csrf"},
        ).status_code
        == 202
    )
    assert jobs.commands[0].owner_login_provider == "github"


def test_microsoft_callback_cannot_consume_github_login_state(setup):
    _, client, _ = setup
    state, _ = start(client, "github")
    result = client.get(
        "/api/auth/callback",
        params={"state": state, "code": "code"},
        follow_redirects=False,
    )
    assert result.headers["location"] == "/login?error=sign_in_failed"


def test_disabled_login_is_visible_but_backend_rejects_its_flow(setup):
    auth, client, _ = setup
    auth.connections.enabled = ("azure-devops",)
    config = client.get("/api/auth/config").json()
    assert config["microsoft_configured"] and not config["github_configured"]
    assert (
        client.get(
            "/api/auth/login?provider=github", follow_redirects=False
        ).status_code
        == 403
    )


def test_unknown_login_provider_rejected(setup):
    _, client, _ = setup
    assert client.get("/api/auth/login?provider=unknown").status_code == 400


def test_upgrade_expires_combined_sessions_once_but_keeps_encrypted_connections(setup):
    auth, _, _ = setup
    save_github(auth)
    with auth._db() as db:
        db.execute("DELETE FROM auth_migrations")
    upgraded = AuthService(auth.settings)
    assert upgraded._load("session", "alice") is None
    assert (
        upgraded.connections.token(upgraded.connections.row(ALICE, "github")) == TOKEN
    )
    upgraded._save(
        "session",
        "new-login",
        {
            "id": ALICE.id,
            "name": "Alice",
            "groups": [],
            "csrf": "csrf",
            "provider": "github",
        },
        time.time() + 600,
    )
    again = AuthService(auth.settings)
    assert again._load("session", "new-login")["provider"] == "github"
