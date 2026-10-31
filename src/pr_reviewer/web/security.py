"""OIDC server-side sessions and deny-by-default repository authorization.

Identity-provider tokens never enter the Angular application. There is no local
password store, development identity header or authentication-disable switch.
"""

from __future__ import annotations

from dataclasses import dataclass
import base64
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from urllib.parse import urlencode, urlparse, unquote

import httpx
import jwt
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

ROLES = {"viewer": 1, "reviewer": 2, "publisher": 3, "administrator": 4}


def log_sign_in_failure(provider, stage, exc, request=None):
    """Log only diagnostic categories; never exception text or OAuth payloads."""
    status = "-"
    details = {}
    if isinstance(exc, httpx.HTTPStatusError):
        status = str(exc.response.status_code)
        try:
            if len(exc.response.content) <= 65536:
                value = exc.response.json()
                if isinstance(value, dict):
                    details = value
        except (ValueError, UnicodeError):
            pass
    if request is not None and request.query_params.get("error"):
        details = {
            "error": request.query_params.get("error"),
            "error_description": request.query_params.get("error_description", "")[
                :4096
            ],
        }
    known_errors = {
        "access_denied",
        "invalid_client",
        "invalid_grant",
        "invalid_scope",
        "unauthorized_client",
        "invalid_request",
        "interaction_required",
        "consent_required",
        "login_required",
        "temporarily_unavailable",
        "server_error",
        "redirect_uri_mismatch",
        "bad_verification_code",
        "incorrect_client_credentials",
    }
    error = details.get("error")
    error = error if isinstance(error, str) and error in known_errors else "-"
    codes = details.get("error_codes", [])
    codes = codes if isinstance(codes, list) else []
    codes = [str(v) for v in codes[:8] if type(v) is int and 0 <= v <= 999999999]
    description = details.get("error_description")
    if isinstance(description, str):
        codes.extend(re.findall(r"\bAADSTS([0-9]{1,9})\b", description[:4096])[:8])
    missing = "-"
    if (
        isinstance(exc, KeyError)
        and exc.args
        and isinstance(exc.args[0], str)
        and exc.args[0]
        in {
            "code",
            "id_token",
            "access_token",
            "expires_in",
            "sub",
            "exp",
        }
    ):
        missing = exc.args[0]
    logging.getLogger("uvicorn.error").warning(
        "Sign-in failed: provider=%s stage=%s category=%s http_status=%s "
        "oauth_error=%s provider_codes=%s missing_field=%s",
        provider,
        stage,
        type(exc).__name__,
        status,
        error,
        ",".join(dict.fromkeys(codes)) or "-",
        missing,
    )


def canonical_repository(provider: str, repository: str) -> str:
    from pr_reviewer.providers.factory import normalize_provider_name

    provider = normalize_provider_name(provider)
    value = repository.strip()
    if provider == "azure-devops" and value.startswith("https://"):
        parsed = urlparse(value)
        parts = [unquote(p) for p in parsed.path.split("/") if p]
        if parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ValueError("Invalid repository identifier")
        if (
            parsed.hostname == "dev.azure.com"
            and len(parts) == 4
            and parts[2] == "_git"
        ):
            value = "/".join([parts[0], parts[1], parts[3]])
        elif (
            (parsed.hostname or "").endswith(".visualstudio.com")
            and len(parts) == 3
            and parts[1] == "_git"
        ):
            value = "/".join([parsed.hostname.split(".")[0], parts[0], parts[2]])
        else:
            raise ValueError("Invalid Azure repository URL")
    parts = value.split("/")
    count = 2 if provider == "github" else 3 if provider == "azure-devops" else 0
    if (
        not count
        or len(parts) != count
        or any(p != p.strip() or not p or p in {".", ".."} for p in parts)
    ):
        raise ValueError("Use owner/repository or organization/project/repository")
    pattern = r"[A-Za-z0-9_.-]+" if provider == "github" else r"[\w .-]+"
    if any(not re.fullmatch(pattern, p, re.UNICODE) for p in parts):
        raise ValueError("Invalid repository identifier")
    return "/".join(parts).casefold()


@dataclass(frozen=True)
class Principal:
    id: str
    name: str
    groups: tuple[str, ...] = ()
    provider: str = ""


class AccessPolicy:
    def __init__(self, path: str):
        self.path = path

    def permissions(self, user: Principal) -> dict[tuple[str, str], int]:
        try:
            raw = json.loads(Path(self.path).read_text())
            if (
                not isinstance(raw, dict)
                or set(raw) != {"grants"}
                or not isinstance(raw["grants"], list)
            ):
                raise ValueError()
            result: dict[tuple[str, str], int] = {}
            for grant in raw["grants"]:
                if not isinstance(grant, dict) or set(grant) - {
                    "subjects",
                    "groups",
                    "role",
                    "repositories",
                }:
                    raise ValueError()
                role = ROLES[grant["role"]]
                subjects, groups = grant.get("subjects", []), grant.get("groups", [])
                if not all(
                    isinstance(a, list)
                    and all(isinstance(v, str) and v and v != "*" for v in a)
                    for a in [subjects, groups]
                ):
                    raise ValueError()
                repositories = grant["repositories"]
                if not isinstance(repositories, dict):
                    raise ValueError()
                for provider, values in repositories.items():
                    if provider not in {"github", "azure-devops"} or not isinstance(
                        values, list
                    ):
                        raise ValueError()
                    for repo in values:
                        canonical = canonical_repository(provider, repo)
                        if user.id in subjects or set(user.groups).intersection(groups):
                            result[(provider, canonical)] = max(
                                role, result.get((provider, canonical), 0)
                            )
            return result
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            raise HTTPException(
                503, "Access policy is unavailable or invalid"
            ) from None

    def require(
        self, user: Principal, provider: str, repository: str, level: int = 1
    ) -> str:
        try:
            canonical = canonical_repository(provider, repository)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        if self.permissions(user).get((provider, canonical), 0) < level:
            raise HTTPException(
                403, "You do not have permission for this repository or action"
            )
        return canonical


@dataclass(frozen=True)
class AuthSettings:
    issuer: str = ""
    client_id: str = ""
    client_secret: str = ""
    public_url: str = "http://127.0.0.1:8000"
    policy_file: str = ""
    database: str = "data/auth.sqlite3"
    label: str = "Microsoft"
    access_mode: str = "policy"
    github_client_id: str = ""
    github_client_secret: str = ""

    @classmethod
    def from_env(cls):
        tenant = os.getenv("PR_REVIEW_ENTRA_TENANT_ID", "").strip()
        issuer = os.getenv("PR_REVIEW_OIDC_ISSUER", "").strip().rstrip("/")
        if not issuer and tenant:
            if not re.fullmatch(r"[0-9a-fA-F-]{36}", tenant):
                tenant = ""  # No broad common/organizations tenant fallback.
            if tenant:
                issuer = f"https://login.microsoftonline.com/{tenant}/v2.0"
        return cls(
            issuer,
            os.getenv("PR_REVIEW_OIDC_CLIENT_ID", ""),
            os.getenv("PR_REVIEW_OIDC_CLIENT_SECRET", ""),
            os.getenv("PR_REVIEW_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/"),
            os.getenv("PR_REVIEW_ACCESS_POLICY", ""),
            os.getenv("PR_REVIEW_AUTH_DB", "data/auth.sqlite3"),
            os.getenv("PR_REVIEW_SIGN_IN_LABEL", "Microsoft"),
            os.getenv("PR_REVIEW_ACCESS_MODE", "provider"),
            os.getenv("PR_REVIEW_GITHUB_CLIENT_ID", ""),
            os.getenv("PR_REVIEW_GITHUB_CLIENT_SECRET", ""),
        )

    @property
    def secure(self):
        return self.public_url.startswith("https://")

    @property
    def microsoft_configured(self):
        return bool(
            self.issuer.startswith("https://") and self.client_id and self.client_secret
        )

    @property
    def configured(self):
        parsed = urlparse(self.public_url)
        origin_valid = parsed.scheme == "https" or (
            parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}
        )
        return bool(
            (
                self.microsoft_configured
                or (
                    self.access_mode == "provider"
                    and self.github_client_id
                    and self.github_client_secret
                )
            )
            and (self.policy_file or self.access_mode == "provider")
            and self.access_mode in {"policy", "provider"}
            and origin_valid
            and parsed.netloc
            and parsed.path in {"", "/"}
            and not parsed.query
            and not parsed.fragment
            and not parsed.username
            and not parsed.password
        )


class AuthService:
    SESSION = "ipr_session"
    LOGIN = "ipr_login"

    def __init__(self, settings: AuthSettings | None = None):
        self.settings = settings or AuthSettings.from_env()
        self.policy = AccessPolicy(self.settings.policy_file)
        if self.settings.secure:
            self.SESSION = "__Host-ipr_session"
            self.LOGIN = "__Secure-ipr_login"
        self._metadata = None
        self._keys = None
        if self.settings.configured:
            path = Path(self.settings.database).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
            os.close(fd)
            os.chmod(path, 0o600)
            with self._db() as db:
                db.execute(
                    "CREATE TABLE IF NOT EXISTS auth_state (kind TEXT, key TEXT, payload TEXT NOT NULL, expires REAL NOT NULL, PRIMARY KEY(kind,key))"
                )
                if self.settings.access_mode == "provider":
                    db.execute("BEGIN IMMEDIATE")
                    db.execute(
                        "CREATE TABLE IF NOT EXISTS auth_migrations (name TEXT PRIMARY KEY)"
                    )
                    if not db.execute(
                        "SELECT 1 FROM auth_migrations WHERE name=?",
                        ("organizational-login-v2",),
                    ).fetchone():
                        # Old sessions could represent both providers. Require a fresh,
                        # provider-scoped login once; encrypted connections are retained.
                        db.execute("DELETE FROM auth_state")
                        db.execute(
                            "INSERT INTO auth_migrations VALUES (?)",
                            ("organizational-login-v2",),
                        )

        self.connections = None
        if self.settings.access_mode == "provider" and self.settings.configured:
            from pr_reviewer.web.provider_access import ProviderAccess

            self.connections = ProviderAccess(self)
            self.policy = self.connections

    def adapter(self, user, provider, repository=None):
        if self.connections is not None:
            return self.connections.adapter(user, provider, repository)
        from pr_reviewer.providers.factory import create_pull_request_provider

        return create_pull_request_provider(provider)

    def _db(self):
        return sqlite3.connect(
            str(Path(self.settings.database).expanduser()), timeout=10
        )

    @staticmethod
    def _digest(value):
        return hashlib.sha256(value.encode()).hexdigest()

    def _save(self, kind, key, payload, expires):
        with self._db() as db:
            db.execute("DELETE FROM auth_state WHERE expires < ?", (time.time(),))
            if db.execute("SELECT COUNT(*) FROM auth_state").fetchone()[0] >= 10000:
                raise RuntimeError("Session capacity reached")
            db.execute(
                "INSERT INTO auth_state VALUES (?,?,?,?)",
                (kind, self._digest(key), json.dumps(payload), expires),
            )

    def _load(self, kind, key, consume=False):
        if not key or len(key) > 256:
            return None
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT payload,expires FROM auth_state WHERE kind=? AND key=?",
                (kind, self._digest(key)),
            ).fetchone()
            if consume:
                db.execute(
                    "DELETE FROM auth_state WHERE kind=? AND key=?",
                    (kind, self._digest(key)),
                )
        if not row or row[1] <= time.time():
            return None
        payload = json.loads(row[0])
        payload["_expires_at"] = row[1]
        return payload

    def current(self, request: Request) -> Principal:
        if not self.settings.configured:
            raise HTTPException(
                503, "Company sign-in is not configured. Contact your administrator."
            )
        try:
            session = self._load("session", request.cookies.get(self.SESSION, ""))
        except sqlite3.Error:
            raise HTTPException(503, "Session service is unavailable") from None
        if not session:
            raise HTTPException(401, "Sign in to continue")
        request.state.session = session
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin and origin.rstrip("/") != self.settings.public_url:
                raise HTTPException(403, "Request origin is not allowed")
            csrf = request.headers.get("x-csrf-token", "")
            if not secrets.compare_digest(csrf.encode(), session["csrf"].encode()):
                raise HTTPException(403, "Request verification failed")
        return Principal(
            session["id"],
            session["name"],
            tuple(session["groups"]),
            session.get("provider", ""),
        )

    def profile(self, request):
        user = self.current(request)
        access_error = ""
        try:
            allowed = self.policy.permissions(user)
        except HTTPException as exc:
            if not self.connections:
                raise
            allowed = {}
            access_error = exc.detail
        return {
            "active_provider": user.provider or None,
            "connection_fallback": False,
            "access_error": access_error,
            "id": user.id,
            "name": user.name,
            "csrf_token": request.state.session["csrf"],
            "access_mode": self.settings.access_mode,
            "enabled_providers": list(self.connections.providers(user))
            if self.connections
            else ["github", "azure-devops"],
            "connections": self.connections.status(user) if self.connections else [],
            "repositories": [
                {
                    "provider": p,
                    "repository": r,
                    "role": next(k for k, v in ROLES.items() if v == level),
                    "can_review": level >= 2,
                    "can_publish": level >= 3,
                    "can_admin": level >= 4,
                }
                for (p, r), level in sorted(allowed.items())
            ],
        }

    def metadata(self):
        if self._metadata is None:
            with httpx.Client(timeout=10) as client:
                response = client.get(
                    self.settings.issuer + "/.well-known/openid-configuration"
                )
                response.raise_for_status()
                data = response.json()
            if data.get("issuer") != self.settings.issuer:
                raise ValueError("Issuer mismatch")
            if any(
                not str(data.get(k, "")).startswith("https://")
                for k in ["authorization_endpoint", "token_endpoint", "jwks_uri"]
            ):
                raise ValueError("HTTPS identity endpoints are required")
            self._metadata = data
            self._keys = jwt.PyJWKClient(
                data["jwks_uri"], cache_jwk_set=True, lifespan=300, timeout=10
            )
        return self._metadata

    def verify_id_token(self, token, nonce):
        self.metadata()
        if jwt.get_unverified_header(token).get("alg") != "RS256":
            raise ValueError("Unexpected signing algorithm")
        key = self._keys.get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=self.settings.client_id,
            issuer=self.settings.issuer,
            options={"require": ["exp", "iat", "iss", "aud", "sub", "nonce"]},
        )
        if not secrets.compare_digest(str(claims["nonce"]), nonce):
            raise ValueError("Nonce mismatch")
        if (
            isinstance(claims["aud"], list)
            and len(claims["aud"]) > 1
            and claims.get("azp") != self.settings.client_id
        ):
            raise ValueError("Authorized party mismatch")
        if claims.get("azp", self.settings.client_id) != self.settings.client_id:
            raise ValueError("Authorized party mismatch")
        if not isinstance(claims["sub"], str) or not claims["sub"]:
            raise ValueError("Missing subject")
        groups = claims.get("groups", [])
        if not isinstance(groups, list) or any(not isinstance(g, str) for g in groups):
            raise ValueError("Invalid groups")
        return claims

    def finish_login(self, request, payload, expires):
        previous = request.cookies.get(self.SESSION, "")
        if previous:
            self._load("session", previous, consume=True)
        session = secrets.token_urlsafe(48)
        payload["csrf"] = secrets.token_urlsafe(48)
        self._save("session", session, payload, expires)
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(
            self.SESSION,
            session,
            max_age=max(1, int(expires - time.time())),
            httponly=True,
            secure=self.settings.secure,
            samesite="lax",
            path="/",
        )
        response.delete_cookie(self.LOGIN, path="/api/auth")
        return response

    def login_transaction(self, request, provider):
        transaction = self._load(
            "login", request.query_params.get("state", ""), consume=True
        )
        binding = request.cookies.get(self.LOGIN, "")
        if (
            not transaction
            or transaction.get("provider", "microsoft") != provider
            or not binding
            or not secrets.compare_digest(transaction["binding"], self._digest(binding))
        ):
            raise ValueError("Invalid sign-in state")
        if not request.query_params.get("code") or request.query_params.get("error"):
            raise ValueError("Authorization declined")
        return transaction

    def login_failure(self):
        response = RedirectResponse("/login?error=sign_in_failed", status_code=303)
        response.delete_cookie(self.LOGIN, path="/api/auth")
        return response

    def mount(self, app):
        if self.connections:
            self.connections.mount(app)

        @app.get("/api/auth/config")
        def config():
            ready = bool(self.settings.configured)
            if ready:
                try:
                    if self.connections:
                        self.connections.ready()
                    else:
                        self.policy.permissions(
                            Principal("__configuration_probe__", "")
                        )
                except HTTPException:
                    ready = False
            return {
                "configured": ready,
                "enabled_providers": list(self.connections.enabled)
                if self.connections else ["azure-devops"],
                "provider_label": self.settings.label,
                "microsoft_configured": ready
                and self.settings.microsoft_configured
                and (
                    not self.connections or "azure-devops" in self.connections.enabled
                ),
                "github_configured": ready
                and bool(
                    self.connections
                    and self.connections.github_id
                    and self.connections.github_secret
                    and "github" in self.connections.enabled
                ),
                "microsoft_repository_auth": self.connections.microsoft_mode
                if self.connections
                else "policy",
            }

        @app.get("/api/auth/me")
        def me(request: Request):
            return self.profile(request)

        @app.get("/api/auth/login")
        def login(provider: str = "microsoft"):
            if provider not in {"microsoft", "github"}:
                raise HTTPException(400, "Unsupported sign-in provider")
            if not self.settings.configured:
                raise HTTPException(503, "Sign-in is not configured")
            if provider == "github":
                if not self.connections or not (
                    self.connections.github_id and self.connections.github_secret
                ):
                    raise HTTPException(503, "GitHub sign-in is not configured")
                self.connections._check("github")
            elif not self.settings.microsoft_configured:
                raise HTTPException(503, "Microsoft sign-in is not configured")
            elif self.connections:
                self.connections._check("azure-devops")
            stage = "connection_configuration"
            try:
                if self.connections:
                    self.connections.ready()
                state, nonce, verifier, binding = [
                    secrets.token_urlsafe(48) for _ in range(4)
                ]
                delegated = bool(provider == "microsoft" and self.connections)
                stage = "login_transaction_storage"
                self._save(
                    "login",
                    state,
                    {
                        "provider": provider,
                        "delegated": delegated,
                        "nonce": nonce,
                        "verifier": verifier,
                        "binding": self._digest(binding),
                    },
                    time.time() + 600,
                )
                challenge = (
                    base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
                    .rstrip(b"=")
                    .decode()
                )
                callback = (
                    "/api/auth/github/callback"
                    if provider == "github"
                    else "/api/auth/callback"
                )
                query = {
                    "client_id": self.connections.github_id
                    if provider == "github"
                    else self.settings.client_id,
                    "redirect_uri": self.settings.public_url + callback,
                    "state": state,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                }
                if provider == "github":
                    query.update(scope="repo read:user", allow_signup="false")
                    endpoint = "https://github.com/login/oauth/authorize"
                else:
                    from .provider_access import AZURE_SCOPE

                    query.update(
                        response_type="code",
                        response_mode="query",
                        scope="openid profile"
                        + (" " + AZURE_SCOPE if delegated else ""),
                        nonce=nonce,
                    )
                    stage = "identity_discovery"
                    endpoint = self.metadata()["authorization_endpoint"]
                response = RedirectResponse(
                    endpoint + "?" + urlencode(query), status_code=302
                )
                response.set_cookie(
                    self.LOGIN,
                    binding,
                    max_age=600,
                    httponly=True,
                    secure=self.settings.secure,
                    samesite="lax",
                    path="/api/auth",
                )
                return response
            except Exception as exc:
                log_sign_in_failure(provider, stage, exc)
                raise HTTPException(503, "Identity service is unavailable") from None

        @app.get("/api/auth/callback")
        def callback(request: Request):
            if not self.settings.configured or not self.settings.microsoft_configured:
                raise HTTPException(503, "Sign-in is not configured")
            stage = "callback_validation"
            try:
                transaction = self.login_transaction(request, "microsoft")
                stage = "token_exchange"
                with httpx.Client(timeout=10) as client:
                    result = client.post(
                        self.metadata()["token_endpoint"],
                        data={
                            "grant_type": "authorization_code",
                            "code": request.query_params["code"],
                            "redirect_uri": self.settings.public_url
                            + "/api/auth/callback",
                            "client_id": self.settings.client_id,
                            "client_secret": self.settings.client_secret,
                            "code_verifier": transaction["verifier"],
                        },
                    )
                    result.raise_for_status()
                    tokens = result.json()
                stage = "id_token_validation"
                claims = self.verify_id_token(tokens["id_token"], transaction["nonce"])
                payload = {
                    "id": self.settings.issuer + "|" + claims["sub"],
                    "name": str(claims.get("name") or "Team member")[:200],
                    "groups": claims.get("groups", []),
                }
                if self.connections:
                    stage = "azure_delegated_token"
                    if not transaction.get("delegated"):
                        raise ValueError(
                            "Organizational sign-in requires delegated authorization"
                        )
                    self.connections._check("azure-devops")
                    payload["provider"] = "azure-devops"
                    if transaction.get("delegated"):
                        token = tokens["access_token"]
                        if (
                            not isinstance(token, str)
                            or not token
                            or tokens.get("token_type", "").casefold() != "bearer"
                        ):
                            raise ValueError("Missing Azure delegated token")
                        expires = time.time() + min(
                            float(tokens["expires_in"]), 30 * 86400
                        )
                        if expires <= time.time():
                            raise ValueError("Expired delegated token")
                        stage = "credential_storage"
                        self.connections._save(
                            Principal(
                                payload["id"], payload["name"], provider="azure-devops"
                            ),
                            "azure-devops",
                            "",
                            token,
                            "entra:" + str(claims.get("oid") or claims["sub"]),
                            expires,
                            replace_all=True,
                        )
                stage = "session_storage"
                return self.finish_login(
                    request, payload, min(float(claims["exp"]), time.time() + 8 * 3600)
                )
            except Exception as exc:
                log_sign_in_failure("microsoft", stage, exc, request)
                return self.login_failure()

        @app.get("/api/auth/github/callback")
        def github_callback(request: Request):
            if not self.settings.configured or not self.connections:
                raise HTTPException(503, "GitHub sign-in is not configured")
            stage = "callback_validation"
            try:
                self.connections._check("github")
                transaction = self.login_transaction(request, "github")
                stage = "token_exchange"
                with httpx.Client(timeout=15, follow_redirects=False) as client:
                    result = client.post(
                        "https://github.com/login/oauth/access_token",
                        headers={"Accept": "application/json"},
                        data={
                            "client_id": self.connections.github_id,
                            "client_secret": self.connections.github_secret,
                            "redirect_uri": self.settings.public_url
                            + "/api/auth/github/callback",
                            "code": request.query_params["code"],
                            "code_verifier": transaction["verifier"],
                        },
                    )
                    result.raise_for_status()
                    tokens = result.json()
                    token = tokens["access_token"]
                    if (
                        not isinstance(token, str)
                        or not token
                        or tokens.get("token_type", "").casefold() != "bearer"
                    ):
                        raise ValueError("Invalid GitHub token")
                    stage = "github_identity"
                    identity = self.connections.fetch(
                        client,
                        "https://api.github.com/user",
                        headers={"Authorization": "Bearer " + token},
                    ).json()
                if (
                    type(identity.get("id")) is not int
                    or identity["id"] <= 0
                    or not identity.get("login")
                ):
                    raise ValueError("Missing GitHub user identity")
                user = Principal(
                    "https://github.com|" + str(identity["id"]),
                    str(identity.get("name") or identity["login"])[:200],
                    provider="github",
                )
                expires = time.time() + min(
                    float(tokens.get("expires_in", 30 * 86400)), 30 * 86400
                )
                if expires <= time.time():
                    raise ValueError("Expired GitHub token")
                scopes = set(str(tokens.get("scope", "")).replace(",", " ").split())
                stage = "credential_storage"
                self.connections._save(
                    user,
                    "github",
                    "",
                    token,
                    "github:" + str(identity["id"]),
                    expires,
                    bool(scopes.intersection({"repo", "public_repo"})),
                )
                stage = "session_storage"
                return self.finish_login(
                    request,
                    {
                        "id": user.id,
                        "name": user.name,
                        "groups": [],
                        "provider": "github",
                    },
                    min(expires, time.time() + 8 * 3600),
                )
            except Exception as exc:
                log_sign_in_failure("github", stage, exc, request)
                return self.login_failure()

        @app.post("/api/auth/logout")
        def logout(request: Request):
            self.current(request)
            self._load("session", request.cookies.get(self.SESSION, ""), consume=True)
            response = JSONResponse({"signed_out": True})
            response.delete_cookie(self.SESSION, path="/")
            response.delete_cookie(self.LOGIN, path="/api/auth")
            return response
