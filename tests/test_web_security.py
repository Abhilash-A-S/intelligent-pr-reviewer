import json
import time
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient

from pr_reviewer.web.api import create_app
from pr_reviewer.web.security import (
    AuthService,
    AuthSettings,
    Principal,
    canonical_repository,
)
from pr_reviewer.web.jobs import ReviewCommand, ReviewJobManager
from pr_reviewer.providers.models import (
    OrganizationSummary,
    ProjectSummary,
    RepositorySummary,
)

ISSUER = "https://identity.example/tenant"
ALICE = ISSUER + "|alice"
BOB = ISSUER + "|bob"


class Jobs:
    def __init__(self):
        self.commands = []
        self.cancelled = []

    def submit(self, command):
        self.commands.append(command)
        return {"id": "new", "status": "queued"}

    def get(self, job_id, include_result=True):
        if job_id == "missing":
            return None
        return {
            "id": job_id,
            "command": {
                "provider": "github",
                "repository": "other/private" if job_id == "hidden" else "acme/store",
                "owner_id": BOB if job_id == "bobs" else ALICE,
            },
            "result": {"private": "code"},
        }

    def list(self, limit=50, predicate=None):
        return [
            i
            for i in [self.get("hidden"), self.get("bobs"), self.get("alice")]
            if predicate is None or predicate(i)
        ][:limit]

    def cancel(self, job_id):
        self.cancelled.append(job_id)
        return True


@pytest.fixture
def setup(tmp_path, monkeypatch):
    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps(
            {
                "grants": [
                    {
                        "subjects": [ALICE],
                        "role": "reviewer",
                        "repositories": {
                            "github": ["acme/store"],
                            "azure-devops": ["acme/platform/reviewer"],
                        },
                    }
                ]
            }
        )
    )
    auth = AuthService(
        AuthSettings(
            ISSUER,
            "client",
            "secret",
            "https://app.example",
            str(policy),
            str(tmp_path / "auth.sqlite3"),
        )
    )
    auth._save(
        "session",
        "alice-session",
        {"id": ALICE, "name": "Alice", "groups": [], "csrf": "alice-csrf"},
        time.time() + 600,
    )
    jobs = Jobs()
    app = create_app(job_manager=jobs, auth_service=auth)
    monkeypatch.setenv("GITHUB_TOKEN", "dummy-provider-token")
    with TestClient(app, base_url="https://app.example") as client:
        yield SimpleNamespace(
            auth=auth, policy=policy, jobs=jobs, app=app, client=client
        )


def signed(s):
    s.client.cookies.set(s.auth.SESSION, "alice-session")
    s.client.headers["X-CSRF-Token"] = "alice-csrf"
    return s.client


def role(s, value):
    data = json.loads(s.policy.read_text())
    data["grants"][0]["role"] = value
    s.policy.write_text(json.dumps(data))


def submit(c, **kwargs):
    body = {"provider": "github", "repository": "acme/store", "pull_number": 1}
    body.update(kwargs)
    return c.post("/api/reviews", json=body)


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/health"),
        ("get", "/api/providers"),
        ("get", "/api/reviews"),
        ("get", "/api/reviews/alice"),
        ("delete", "/api/reviews/alice"),
        ("post", "/api/reviews"),
        ("get", "/api/repository-discovery/organizations?provider=github"),
        ("get", "/api/pull-requests?provider=github&repository=acme/store"),
        ("get", "/api/pull-requests/1?provider=github&repository=acme/store"),
        ("get", "/api/pull-requests/1/files?provider=github&repository=acme/store"),
        ("get", "/openapi.json"),
    ],
)
def test_unauthenticated_denied_without_work(setup, method, path):
    assert getattr(setup.client, method)(path).status_code == 401
    assert not setup.jobs.commands and not setup.jobs.cancelled


@pytest.mark.parametrize("cookie", ["forged", "expired"])
def test_invalid_or_expired_session(setup, cookie):
    if cookie == "expired":
        setup.auth._save("session", cookie, {"id": ALICE}, time.time() - 1)
    setup.client.cookies.set(setup.auth.SESSION, cookie)
    assert setup.client.get("/api/reviews").status_code == 401


def test_fail_closed_without_configuration():
    with TestClient(
        create_app(job_manager=Jobs(), auth_service=AuthService(AuthSettings()))
    ) as c:
        assert c.get("/api/reviews").status_code == 503
        assert not c.get("/api/auth/config").json()["configured"]


def test_reviewer_dry_run_ownership_and_hidden_groups(setup):
    c = signed(setup)
    assert submit(c).status_code == 202
    command = setup.jobs.commands[0]
    assert command.owner_id == ALICE and command.repository == "acme/store"


def test_reviewer_cannot_publish_or_escalate_via_body(setup):
    c = signed(setup)
    assert (
        submit(c, publish=True, role="administrator", owner_id=BOB).status_code == 403
    )
    assert not setup.jobs.commands


@pytest.mark.parametrize("value", ["publisher", "administrator"])
def test_authorized_publishing(setup, value):
    role(setup, value)
    assert submit(signed(setup), publish=True).status_code == 202
    assert setup.jobs.commands[0].publish


def test_viewer_cannot_run_or_cancel(setup):
    role(setup, "viewer")
    c = signed(setup)
    assert (
        submit(c).status_code == 403
        and c.delete("/api/reviews/alice").status_code == 403
    )
    assert not setup.jobs.commands and not setup.jobs.cancelled


@pytest.mark.parametrize(
    "repository", ["other/private", "acme/store/../private", "acme/store?x=1", "   "]
)
def test_forbidden_or_malformed_repository_no_enqueue(setup, repository):
    response = submit(signed(setup), repository=repository)
    assert response.status_code in {400, 403} and not setup.jobs.commands


def test_private_job_not_found_and_filtered_history(setup):
    c = signed(setup)
    assert c.get("/api/reviews/hidden").status_code == 404
    response = c.get("/api/reviews").json()
    assert response["total"] == 2
    assert {j["id"] for j in response["items"]} == {"bobs", "alice"}
    assert (
        c.get("/api/reviews/bobs").status_code == 200
    )  # Team repository visibility is deliberate.


def test_owner_only_cancel_and_repository_admin_override(setup):
    c = signed(setup)
    assert c.delete("/api/reviews/bobs").status_code == 403
    assert c.delete("/api/reviews/alice").status_code == 200
    role(setup, "administrator")
    assert c.delete("/api/reviews/bobs").status_code == 200
    assert c.delete("/api/reviews/hidden").status_code == 404


@pytest.mark.parametrize(
    "csrf,origin",
    [("", None), ("incorrect", None), ("alice-csrf", "https://evil.example")],
)
def test_csrf_and_origin_protection(setup, csrf, origin):
    c = signed(setup)
    c.headers["X-CSRF-Token"] = csrf
    if origin:
        c.headers["Origin"] = origin
    assert submit(c, publish=True).status_code == 403 and not setup.jobs.commands
    assert c.post("/api/auth/logout").status_code == 403


def test_logout_revokes_cookie_and_server_session(setup):
    c = signed(setup)
    assert c.get("/api/auth/me").status_code == 200
    assert c.post("/api/auth/logout").status_code == 200
    c.cookies.set(setup.auth.SESSION, "alice-session")
    assert c.get("/api/auth/me").status_code == 401


def test_policy_changes_take_effect_and_corruption_fails_closed(setup):
    c = signed(setup)
    assert submit(c).status_code == 202
    setup.policy.write_text('{"grants":[]}')
    assert submit(c).status_code == 403
    setup.policy.write_text("{broken")
    assert submit(c).status_code == 503
    assert len(setup.jobs.commands) == 1


def test_group_policy_and_role_scope(setup):
    setup.policy.write_text(
        json.dumps(
            {
                "grants": [
                    {
                        "groups": ["engineers"],
                        "role": "publisher",
                        "repositories": {"github": ["acme/store"]},
                    }
                ]
            }
        )
    )
    assert not setup.auth.policy.permissions(Principal(ALICE, "Alice"))
    assert (
        setup.auth.policy.permissions(Principal(ALICE, "Alice", ("engineers",)))[
            ("github", "acme/store")
        ]
        == 3
    )
    assert not setup.auth.policy.permissions(Principal(ALICE, "Alice", ("different",)))


def test_pr_forbidden_before_provider_construction(setup, monkeypatch):
    provider = Mock()
    monkeypatch.setattr("pr_reviewer.web.api.create_pull_request_provider", provider)
    c = signed(setup)
    for path in [
        "/api/pull-requests",
        "/api/pull-requests/1",
        "/api/pull-requests/1/files",
    ]:
        assert (
            c.get(
                path, params={"provider": "github", "repository": "other/private"}
            ).status_code
            == 403
        )
    provider.assert_not_called()


def test_discovery_filters_names_metadata_and_counts(setup, monkeypatch):
    provider = Mock()
    provider.list_organizations.return_value = [
        OrganizationSummary("1", "acme", "Acme"),
        OrganizationSummary("2", "secret", "Secret"),
    ]
    provider.list_repositories.return_value = [
        RepositorySummary("1", "store", "acme"),
        RepositorySummary("2", "secret", "acme"),
    ]
    provider.list_projects.return_value = [
        ProjectSummary("1", "platform", "acme"),
        ProjectSummary("2", "private", "acme"),
    ]
    monkeypatch.setattr(
        "pr_reviewer.web.api.create_pull_request_provider", lambda _: provider
    )
    c = signed(setup)
    r = c.get(
        "/api/repository-discovery/organizations", params={"provider": "github"}
    ).json()
    assert r["total"] == 1 and r["items"][0]["name"] == "acme"
    r = c.get(
        "/api/repository-discovery/repositories",
        params={"provider": "github", "organization": "acme"},
    ).json()
    assert r["total"] == 1 and r["items"][0]["name"] == "store"
    r = c.get(
        "/api/repository-discovery/projects",
        params={"provider": "azure-devops", "organization": "acme"},
    ).json()
    assert r["total"] == 1 and r["items"][0]["name"] == "platform"
    provider.reset_mock()
    assert (
        c.get(
            "/api/repository-discovery/repositories",
            params={"provider": "github", "organization": "secret"},
        ).status_code
        == 403
    )
    provider.list_repositories.assert_not_called()


def test_no_tokens_in_profile_and_no_cache(setup):
    r = signed(setup).get("/api/auth/me")
    assert r.headers["Cache-Control"] == "no-store"
    assert "dummy-provider-token" not in r.text and "client_secret" not in r.text


def test_sessions_survive_auth_service_recreation(setup):
    another = AuthService(setup.auth.settings)
    assert another._load("session", "alice-session")["id"] == ALICE


@pytest.fixture
def rsa_tokens(setup):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    setup.auth._metadata = {
        "authorization_endpoint": ISSUER + "/authorize",
        "token_endpoint": ISSUER + "/token",
        "jwks_uri": ISSUER + "/keys",
    }
    setup.auth._keys = SimpleNamespace(
        get_signing_key_from_jwt=lambda _: SimpleNamespace(key=private.public_key())
    )

    def token(**overrides):
        claims = {
            "iss": ISSUER,
            "sub": "alice",
            "aud": "client",
            "iat": int(time.time()),
            "exp": int(time.time() + 600),
            "nonce": "expected",
            "name": "Alice",
        }
        claims.update(overrides)
        return jwt.encode(claims, private, algorithm="RS256")

    return token


def test_real_signature_and_claim_validation(setup, rsa_tokens):
    assert setup.auth.verify_id_token(rsa_tokens(), "expected")["sub"] == "alice"


@pytest.mark.parametrize(
    "overrides",
    [
        {"iss": "https://evil.example"},
        {"aud": "other"},
        {"exp": 1},
        {"nonce": "wrong"},
        {"azp": "other"},
        {"groups": "not-a-list"},
    ],
)
def test_reject_invalid_id_token_claims(setup, rsa_tokens, overrides):
    with pytest.raises((ValueError, jwt.PyJWTError)):
        setup.auth.verify_id_token(rsa_tokens(**overrides), "expected")


def test_wrong_signature_and_algorithm_rejected(setup, rsa_tokens):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    claims = {
        "iss": ISSUER,
        "sub": "alice",
        "aud": "client",
        "iat": int(time.time()),
        "exp": time.time() + 600,
        "nonce": "expected",
    }
    for token in [
        jwt.encode(claims, other, algorithm="RS256"),
        jwt.encode(
            claims, "fake-signing-key-for-test-only-32-bytes", algorithm="HS256"
        ),
    ]:
        with pytest.raises((ValueError, jwt.PyJWTError)):
            setup.auth.verify_id_token(token, "expected")


def test_login_pkce_browser_binding_callback_and_replay(setup, rsa_tokens, monkeypatch):
    c = setup.client
    login = c.get("/api/auth/login", follow_redirects=False)
    q = parse_qs(urlparse(login.headers["location"]).query)
    assert q["code_challenge_method"] == ["S256"] and q["response_type"] == ["code"]
    assert (
        "HttpOnly" in login.headers["set-cookie"]
        and "Secure" in login.headers["set-cookie"]
    )
    token = rsa_tokens(nonce=q["nonce"][0])
    response = Mock()
    response.json.return_value = {"id_token": token}
    exchange = Mock()
    exchange.__enter__ = Mock(return_value=exchange)
    exchange.__exit__ = Mock(return_value=False)
    exchange.post.return_value = response
    monkeypatch.setattr("pr_reviewer.web.security.httpx.Client", lambda **kw: exchange)
    callback = c.get(
        "/api/auth/callback",
        params={"state": q["state"][0], "code": "single-use-code"},
        follow_redirects=False,
    )
    assert callback.status_code == 303 and callback.headers["location"] == "/"
    assert c.get("/api/auth/me").json()["id"] == ALICE
    assert exchange.post.call_args.kwargs["data"]["code_verifier"]
    assert "secret" not in callback.headers.get("location", "")
    replay = c.get(
        "/api/auth/callback",
        params={"state": q["state"][0], "code": "single-use-code"},
        follow_redirects=False,
    )
    assert (
        "sign_in_failed" in replay.headers["location"] and exchange.post.call_count == 1
    )


def test_callback_rejects_missing_binding_and_bad_state(setup, rsa_tokens):
    c = setup.client
    login = c.get("/api/auth/login", follow_redirects=False)
    q = parse_qs(urlparse(login.headers["location"]).query)
    c.cookies.clear()
    for state in [q["state"][0], "invented"]:
        r = c.get(
            "/api/auth/callback",
            params={"state": state, "code": "bad"},
            follow_redirects=False,
        )
        assert "sign_in_failed" in r.headers["location"]


def test_canonical_identifiers_and_aliases():
    assert (
        canonical_repository(
            "azure", "https://dev.azure.com/Acme/Platform/_git/Reviewer"
        )
        == "acme/platform/reviewer"
    )
    assert canonical_repository("github", "Acme/Store") == "acme/store"


def test_queued_and_later_provider_calls_recheck_permission(setup):
    from pr_reviewer.web.jobs import AuthorizedProvider

    calls = Mock()

    def authorize():
        setup.auth.policy.require(Principal(ALICE, "Alice"), "github", "acme/store", 3)

    role(setup, "publisher")
    wrapped = AuthorizedProvider(calls, authorize)
    wrapped.publish_inline_comment(repository="acme/store")
    assert calls.publish_inline_comment.call_count == 1
    role(setup, "viewer")
    with pytest.raises(HTTPException):
        wrapped.publish_inline_comment(repository="acme/store")
    assert calls.publish_inline_comment.call_count == 1


def test_owner_groups_never_serialized():
    from pr_reviewer.web.jobs import ReviewJob

    command = ReviewCommand(
        "github", "acme/store", 1, owner_id=ALICE, owner_groups=("private-group-id",)
    )
    assert "owner_groups" not in ReviewJob("job", command).snapshot()["command"]


def test_pending_login_expiry_and_fail_closed_policy(setup):
    setup.auth._save("login", "old-state", {"binding": "x"}, time.time() - 1)
    assert setup.auth._load("login", "old-state", consume=True) is None
    setup.policy.write_text(
        json.dumps(
            {
                "grants": [
                    {
                        "subjects": [ALICE],
                        "role": "root",
                        "repositories": {"github": ["acme/store"]},
                    }
                ]
            }
        )
    )
    assert signed(setup).get("/api/auth/me").status_code == 503


def test_client_cannot_override_owner_or_groups(setup):
    c = signed(setup)
    assert (
        submit(
            c, owner_id=BOB, owner_groups=["administrators"], role="administrator"
        ).status_code
        == 202
    )
    assert setup.jobs.commands[-1].owner_id == ALICE
    assert setup.jobs.commands[-1].owner_groups == ()


def test_login_configuration_reports_invalid_policy(setup):
    setup.policy.write_text("{invalid")
    assert setup.client.get("/api/auth/config").json()["configured"] is False


def test_jwks_discovery_requires_exact_issuer(setup, monkeypatch):
    response = Mock()
    response.json.return_value = {
        "issuer": "https://other.example",
        "authorization_endpoint": "https://other.example/auth",
        "token_endpoint": "https://other.example/token",
        "jwks_uri": "https://other.example/keys",
    }
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    client.get.return_value = response
    monkeypatch.setattr(
        "pr_reviewer.web.security.httpx.Client", lambda **kwargs: client
    )
    with pytest.raises(ValueError):
        setup.auth.metadata()


def test_worker_guard_refuses_ownerless_job_before_provider_construction():
    provider = Mock()
    manager = ReviewJobManager(
        provider_factory=provider,
        llm_factory=Mock(),
        execution_guard=lambda command: (_ for _ in ()).throw(
            PermissionError("Access denied")
        ),
    )
    try:
        submitted = manager.submit(ReviewCommand("github", "acme/store", 1))
        for _ in range(100):
            job = manager.get(submitted["id"])
            if job["status"] == "failed":
                break
            time.sleep(0.01)
        assert job["status"] == "failed"
        provider.assert_not_called()
    finally:
        manager.close()


def test_production_execution_guard_rejects_expired_authorization(setup, monkeypatch):
    import pr_reviewer.web.api as api_module

    managers = []
    provider = Mock()

    def factory(**kwargs):
        manager = ReviewJobManager(
            provider_factory=provider, llm_factory=Mock(), max_parallel_jobs=1, **kwargs
        )
        managers.append(manager)
        return manager

    monkeypatch.setattr(api_module, "ReviewJobManager", factory)
    app = api_module.create_app(auth_service=setup.auth)
    manager = managers[0]
    try:
        job = manager.submit(
            ReviewCommand(
                "github",
                "acme/store",
                1,
                owner_id=ALICE,
                owner_auth_expires_at=time.time() - 1,
            )
        )
        for _ in range(100):
            result = manager.get(job["id"])
            if result["status"] == "failed":
                break
            time.sleep(0.01)
        assert result["status"] == "failed"
        assert "authorization has expired" in result["error"]
        provider.assert_not_called()
    finally:
        manager.close()
