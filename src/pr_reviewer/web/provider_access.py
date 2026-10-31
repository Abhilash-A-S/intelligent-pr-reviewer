"""Per-user provider authorization. No shared-token or static-policy fallback."""

from __future__ import annotations

import os
import logging
import re
import secrets
import time
from urllib.parse import quote, urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, Request

from .security import canonical_repository

GIT_NAMESPACE = "2e9eb7ed-3c0a-47d4-87c1-0ffdd275fd87"
AZURE_SCOPE = "499b84ac-1321-427f-aa17-267ca6975798/.default"


def log_provider_failure(url, status, category):
    """Fixed endpoint labels only: no URLs, identities, headers or bodies."""
    parsed = urlsplit(str(url))
    provider, endpoint = "unknown", "other"
    if parsed.hostname in {"dev.azure.com", "app.vssps.visualstudio.com"}:
        provider = "azure-devops"
        path = parsed.path.lower()
        for suffix, label in [
            ("/_apis/profile/profiles/me", "identity_profile"),
            ("/_apis/accounts", "organization_discovery"),
            ("/_apis/projects", "project_discovery"),
            ("/_apis/git/repositories", "repository_discovery"),
            ("/_apis/security/permissionevaluationbatch", "permission_evaluation"),
        ]:
            if path.endswith(suffix):
                endpoint = label
                break
        else:
            if "/_apis/securitynamespaces/" in path:
                endpoint = "security_namespace"
            elif "/_apis/git/repositories/" in path:
                endpoint = "repository_access"
    elif parsed.hostname == "api.github.com":
        provider = "github"
        endpoint = "repository_discovery" if parsed.path == "/user/repos" else "identity_or_repository"
    logging.getLogger("uvicorn.error").warning(
        "Provider request failed: provider=%s endpoint=%s http_status=%s category=%s",
        provider, endpoint, status, category,
    )


class ProviderAccess:
    def __init__(self, auth):
        self.auth = auth
        raw = os.getenv("PR_REVIEW_ENABLED_PROVIDERS", "github,azure-devops")
        self.enabled = tuple(
            dict.fromkeys(v.strip() for v in raw.split(",") if v.strip())
        )
        self.github_id = auth.settings.github_client_id or os.getenv(
            "PR_REVIEW_GITHUB_CLIENT_ID", ""
        )
        self.github_secret = auth.settings.github_client_secret or os.getenv(
            "PR_REVIEW_GITHUB_CLIENT_SECRET", ""
        )
        self.microsoft_mode = "delegated"
        self.key = os.getenv("PR_REVIEW_CONNECTION_KEY", "")
        self.allowed = {
            "github": self._organizations("PR_REVIEW_GITHUB_ORGANIZATIONS"),
            "azure-devops": self._organizations("PR_REVIEW_AZURE_ORGANIZATIONS"),
        }
        with auth._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS provider_connections (
                owner TEXT NOT NULL, provider TEXT NOT NULL, organization TEXT NOT NULL,
                secret TEXT NOT NULL, identity TEXT NOT NULL, expires REAL NOT NULL,
                version TEXT NOT NULL, publish INTEGER NOT NULL,
                PRIMARY KEY(owner,provider,organization))""")

    @staticmethod
    def _organizations(name):
        return {
            v.strip().casefold() for v in os.getenv(name, "").split(",") if v.strip()
        }

    def ready(self):
        try:
            Fernet(self.key.encode())
            if not self.enabled or set(self.enabled) - {"github", "azure-devops"}:
                raise ValueError()
            for values in self.allowed.values():
                if any(
                    not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,199}", v) for v in values
                ):
                    raise ValueError()
        except (ValueError, TypeError):
            raise HTTPException(
                503,
                "Provider connections require a valid encryption key and company configuration",
            ) from None

    def _check(self, provider, organization=""):
        self.ready()
        if provider not in self.enabled:
            raise HTTPException(403, "This provider is not enabled for your company")
        if (
            organization
            and self.allowed[provider]
            and organization.casefold() not in self.allowed[provider]
        ):
            raise HTTPException(
                403, "This organization is not enabled for your company"
            )

    @staticmethod
    def organization(value):
        if not isinstance(value, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9-]{0,99}", value
        ):
            raise HTTPException(
                400, "Enter the Azure DevOps organization name, without a URL"
            )
        return value.casefold()

    def providers(self, user):
        return tuple(p for p in self.enabled if not user.provider or p == user.provider)

    def check_user(self, user, provider):
        self._check(provider)
        if user.provider and provider != user.provider:
            raise HTTPException(
                403, "Sign in with the matching provider to access this dashboard"
            )

    def _rows(self, user, provider=None):
        self.ready()
        with self.auth._db() as db:
            rows = db.execute(
                "SELECT provider,organization,secret,identity,expires,version,publish FROM provider_connections WHERE owner=?",
                (user.id,),
            ).fetchall()
        return [
            dict(
                zip(
                    [
                        "provider",
                        "organization",
                        "secret",
                        "identity",
                        "expires",
                        "version",
                        "publish",
                    ],
                    r,
                )
            )
            for r in rows
            if (
                (r[0] == "github" and r[3].startswith("github:"))
                or (r[0] == "azure-devops" and r[3].startswith("entra:"))
            )
            and r[0] in self.providers(user)
            and (provider is None or r[0] == provider)
            and (not r[1] or not self.allowed[r[0]] or r[1] in self.allowed[r[0]])
        ]

    def _save(
        self,
        user,
        provider,
        organization,
        token,
        identity,
        expires,
        publish=True,
        replace_all=False,
    ):
        self.check_user(user, provider)
        self._check(provider, organization)
        cipher = Fernet(self.key.encode()).encrypt(token.encode()).decode()
        with self.auth._db() as db:
            if replace_all:
                db.execute(
                    "DELETE FROM provider_connections WHERE owner=? AND provider=?",
                    (user.id, provider),
                )
            db.execute(
                "INSERT OR REPLACE INTO provider_connections VALUES (?,?,?,?,?,?,?,?)",
                (
                    user.id,
                    provider,
                    organization,
                    cipher,
                    str(identity)[:200],
                    expires,
                    secrets.token_urlsafe(24),
                    bool(publish),
                ),
            )

    def row(self, user, provider, repository=None):
        self.check_user(user, provider)
        organization = repository.split("/")[0].casefold() if repository else None
        rows = [
            r
            for r in self._rows(user, provider)
            if provider == "github"
            or organization is None
            or r["organization"] == organization
            or (r["organization"] == "" and r["identity"].startswith("entra:"))
        ]
        if len(rows) != 1:
            raise HTTPException(
                403, "Sign in with your company account to access this organization"
            )
        row = rows[0]
        if row["expires"] <= time.time():
            raise HTTPException(
                403, "Provider connection expired. Reconnect your account"
            )
        if provider == "azure-devops" and not row["organization"] and organization:
            self._check(provider, organization)
            row = {**row, "organization": organization}
        return row

    def token(self, row):
        try:
            return Fernet(self.key.encode()).decrypt(row["secret"].encode()).decode()
        except InvalidToken:
            raise HTTPException(
                503,
                "Provider credential could not be decrypted. Contact your administrator",
            ) from None

    def client(self, row):
        token = self.token(row)
        headers = {"Accept": "application/json"}
        if not row["identity"].startswith(("github:", "entra:")):
            raise HTTPException(
                403,
                "Legacy personal credentials are not supported. Sign in with your organization account",
            )
        headers["Authorization"] = "Bearer " + token
        return httpx.Client(headers=headers, timeout=15, follow_redirects=False)

    @staticmethod
    def fetch(client, url, *, method="GET", **kwargs):
        response = None
        try:
            response = client.request(method, url, **kwargs)
            if not 200 <= response.status_code < 300:
                log_provider_failure(url, response.status_code, "http_error")
            if (
                response.status_code == 403
                and response.headers.get("x-ratelimit-remaining") == "0"
            ):
                raise HTTPException(503, "Provider rate limit reached. Retry later")
            if (
                response.status_code == 403
                and "required" in response.headers.get("x-github-sso", "").casefold()
            ):
                raise HTTPException(
                    403,
                    "Your GitHub organization requires SSO authorization. Sign in to your organization in GitHub, then sign in here again",
                )
            if response.status_code in {401, 403}:
                raise HTTPException(
                    403,
                    "Provider access was rejected. Sign in again and check your organization approval and repository permissions",
                )
            if response.status_code == 404:
                raise HTTPException(
                    403,
                    "Repository or organization is not accessible to your connection",
                )
            response.raise_for_status()
            response.json()  # These authorization/discovery endpoints must return JSON.
            return response
        except (httpx.HTTPError, ValueError):
            if response is None:
                log_provider_failure(url, "-", "transport_error")
            elif 200 <= response.status_code < 300:
                log_provider_failure(url, response.status_code, "invalid_response")
            raise HTTPException(
                503, "Provider service is unavailable. Retry later"
            ) from None

    def pages(self, client, url, params=None, github=False):
        params = dict(params or {})
        for page in range(1, 101):
            if github:
                params.update(page=page, per_page=100)
            response = self.fetch(client, url, params=params)
            body = response.json()
            items = body if github else body.get("value", [])
            if not isinstance(items, list):
                raise HTTPException(503, "Provider returned invalid discovery data")
            yield from items
            if github:
                if not response.links.get("next"):
                    return
            else:
                continuation = response.headers.get("x-ms-continuationtoken")
                if not continuation:
                    return
                params["continuationToken"] = continuation
        raise HTTPException(
            503,
            "Provider discovery exceeded its safety limit. Contact your administrator",
        )

    def _github_allowed(self, repo):
        return (
            not self.allowed["github"]
            or repo.split("/")[0].casefold() in self.allowed["github"]
        )

    def _github_level(self, data, row):
        # Owner type is not an authorization grant: both account kinds still
        # require the signed-in user's live repository permissions.
        owner = data.get("owner")
        if not isinstance(owner, dict) or owner.get("type") not in {"Organization", "User"}:
            return 0
        permissions = data.get("permissions", {})
        if not isinstance(permissions, dict):
            return 0
        if permissions.get("pull") is not True:
            return 0
        return 3 if row["publish"] and permissions.get("push") is True else 2

    def _azure_levels(self, client, row, repos):
        org = row["organization"]
        base = f"https://dev.azure.com/{quote(org, safe='')}"
        namespaces = (
            self.fetch(
                client,
                base + "/_apis/securitynamespaces/" + GIT_NAMESPACE,
                params={"api-version": "7.1"},
            )
            .json()
            .get("value", [])
        )
        actions = {
            a["name"]: a["bit"]
            for n in namespaces
            if str(n.get("namespaceId", "")).casefold() == GIT_NAMESPACE
            for a in n.get("actions", [])
        }
        if not isinstance(actions.get("GenericRead"), int) or not isinstance(
            actions.get("PullRequestContribute"), int
        ):
            raise HTTPException(
                503, "Azure repository permissions could not be verified"
            )
        result = {}
        for start in range(0, len(repos), 100):
            batch = repos[start : start + 100]
            checks = []
            for repo in batch:
                token = f"repoV2/{repo['project']['id']}/{repo['id']}"
                checks.extend(
                    {
                        "securityNamespaceId": GIT_NAMESPACE,
                        "token": token,
                        "permissions": actions[name],
                    }
                    for name in ["GenericRead", "PullRequestContribute"]
                )
            values = (
                self.fetch(
                    client,
                    base + "/_apis/security/permissionevaluationbatch",
                    method="POST",
                    params={"api-version": "7.1"},
                    json={"alwaysAllowAdministrators": False, "evaluations": checks},
                )
                .json()
                .get("evaluations", [])
            )
            evaluated = {
                (v.get("token"), v.get("permissions")): v.get("value") is True
                for v in values
                if v.get("securityNamespaceId", "").casefold() == GIT_NAMESPACE
            }
            for repo in batch:
                token = f"repoV2/{repo['project']['id']}/{repo['id']}"
                if evaluated.get((token, actions["GenericRead"]), False):
                    result[repo["id"]] = (
                        3
                        if row["publish"]
                        and evaluated.get(
                            (token, actions["PullRequestContribute"]), False
                        )
                        else 2
                    )
        return result

    def _azure_level(self, client, row, repo):
        return self._azure_levels(client, row, [repo]).get(repo["id"], 0)

    def azure_organizations(self, client, row):
        if row["organization"]:
            return [row["organization"]]
        if not row["identity"].startswith("entra:"):
            raise HTTPException(403, "Organization-scoped connection required")
        profile = self.fetch(
            client,
            "https://app.vssps.visualstudio.com/_apis/profile/profiles/me",
            params={"api-version": "7.1"},
        ).json()
        member_id = profile.get("id")
        if not isinstance(member_id, str) or not member_id:
            raise HTTPException(
                503, "Azure DevOps organization discovery did not return your identity"
            )
        result = []
        for account in self.pages(
            client,
            "https://app.vssps.visualstudio.com/_apis/accounts",
            {"memberId": member_id, "api-version": "7.1"},
        ):
            organization = self.organization(account.get("accountName"))
            if (
                not self.allowed["azure-devops"]
                or organization in self.allowed["azure-devops"]
            ):
                result.append(organization)
        return sorted(set(result))

    def permissions(self, user):
        allowed = {}
        rows = self._rows(user)
        azure_counts = {"connections": 0, "active_connections": 0, "organizations": 0,
                        "projects": 0, "repositories": 0, "readable": 0}
        for row in rows:
            if row["provider"] == "azure-devops":
                azure_counts["connections"] += 1
            if row["expires"] <= time.time():
                continue
            if row["provider"] == "azure-devops":
                azure_counts["active_connections"] += 1
            try:
                with self.client(row) as client:
                    if row["provider"] == "github":
                        for repo in self.pages(
                            client,
                            "https://api.github.com/user/repos",
                            {"affiliation": "owner,collaborator,organization_member"},
                            github=True,
                        ):
                            name = canonical_repository("github", repo["full_name"])
                            level = self._github_level(repo, row)
                            if level and self._github_allowed(name):
                                allowed[("github", name)] = level
                    else:
                        denied_organizations = []
                        organizations = self.azure_organizations(client, row)
                        azure_counts["organizations"] += len(organizations)
                        for organization in organizations:
                            try:
                                scoped_row = {**row, "organization": organization}
                                base = "https://dev.azure.com/" + quote(
                                    organization, safe=""
                                )
                                for project in self.pages(
                                    client,
                                    base + "/_apis/projects",
                                    {"api-version": "7.1", "$top": 100},
                                ):
                                    azure_counts["projects"] += 1
                                    repos = (
                                        self.fetch(
                                            client,
                                            base
                                            + "/"
                                            + quote(project["id"], safe="")
                                            + "/_apis/git/repositories",
                                            params={"api-version": "7.1"},
                                        )
                                        .json()
                                        .get("value", [])
                                    )
                                    azure_counts["repositories"] += len(repos)
                                    levels = (
                                        self._azure_levels(client, scoped_row, repos)
                                        if repos
                                        else {}
                                    )
                                    azure_counts["readable"] += sum(level >= 2 for level in levels.values())
                                    for repo in repos:
                                        name = canonical_repository(
                                            "azure-devops",
                                            f"{organization}/{project['name']}/{repo['name']}",
                                        )
                                        level = levels.get(repo["id"], 0)
                                        if level:
                                            allowed[("azure-devops", name)] = level
                            except HTTPException as exc:
                                if exc.status_code != 403:
                                    raise
                                denied_organizations.append(exc)
                        if denied_organizations and not any(
                            p == "azure-devops" for p, _ in allowed
                        ):
                            raise denied_organizations[0]
            except HTTPException as exc:
                if exc.status_code != 403 or user.provider:
                    raise
                # A revoked connection grants nothing; other connections remain usable.
        if user.provider == "azure-devops" and not allowed:
            if not azure_counts["connections"]:
                reason = "no_connection"
            elif not azure_counts["active_connections"]:
                reason = "expired_connection"
            elif not azure_counts["organizations"]:
                reason = "no_organizations_returned"
            elif not azure_counts["projects"]:
                reason = "no_projects_returned"
            elif not azure_counts["repositories"]:
                reason = "no_repositories_returned"
            else:
                reason = "no_repository_read_permission"
            logging.getLogger("uvicorn.error").warning(
                "Azure discovery empty: reason=%s connections=%s active_connections=%s "
                "organizations=%s projects=%s repositories=%s readable=%s organization_filter=%s",
                reason, azure_counts["connections"], azure_counts["active_connections"],
                azure_counts["organizations"], azure_counts["projects"],
                azure_counts["repositories"], azure_counts["readable"],
                bool(self.allowed["azure-devops"]),
            )
        return allowed

    def require(self, user, provider, repository, level=1):
        try:
            repo = canonical_repository(provider, repository)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        row = self.row(user, provider, repo)
        self._check(provider, repo.split("/")[0])
        with self.client(row) as client:
            if provider == "github":
                data = self.fetch(client, "https://api.github.com/repos/" + repo).json()
                actual = self._github_level(data, row)
            else:
                org, project, name = repo.split("/")
                url = f"https://dev.azure.com/{quote(org, safe='')}/{quote(project, safe='')}/_apis/git/repositories/{quote(name, safe='')}"
                data = self.fetch(client, url, params={"api-version": "7.1"}).json()
                actual = self._azure_level(client, row, data)
        if actual < level:
            raise HTTPException(
                403, "Your provider account does not permit this repository action"
            )
        return repo

    def adapter(self, user, provider, repository=None):
        from pr_reviewer.providers.github import GitHubProvider
        from pr_reviewer.providers.azure_devops import AzureDevOpsProvider

        row = self.row(user, provider, repository)
        client = self.client(row)
        if provider == "github":
            client.base_url = "https://api.github.com"
            return GitHubProvider(client=client)
        return AzureDevOpsProvider(organization=row["organization"], client=client)

    def status(self, user):
        result = []
        for provider in self.providers(user):
            rows = self._rows(user, provider)
            for row in rows or [None]:
                state = "not-configured" if row is None else "configured"
                detail = (
                    "Connect your account"
                    if row is None
                    else "Connection saved; access is checked against your provider"
                )
                if row and row["expires"] <= time.time():
                    state, detail = (
                        "authentication-failed",
                        "Connection expired. Reconnect your account",
                    )
                elif row:
                    try:
                        with self.client(row) as client:
                            endpoint = (
                                "https://api.github.com/user"
                                if provider == "github"
                                else (
                                    f"https://dev.azure.com/{quote(row['organization'], safe='')}/_apis/connectionData"
                                    if row["organization"]
                                    else "https://app.vssps.visualstudio.com/_apis/profile/profiles/me"
                                )
                            )
                            self.fetch(
                                client,
                                endpoint,
                                params={"api-version": "7.1"}
                                if provider == "azure-devops"
                                and not row["organization"]
                                else None,
                            )
                        state, detail = "connected", "Your account is connected"
                    except HTTPException as exc:
                        state = (
                            "authentication-failed"
                            if exc.status_code == 403
                            else "unavailable"
                        )
                        detail = exc.detail
                result.append(
                    {
                        "id": provider,
                        "organization": row["organization"] if row else "",
                        "identity": row["identity"] if row else "",
                        "connected": state == "connected",
                        "configured": row is not None,
                        "state": state,
                        "detail": detail,
                        "github_oauth_ready": bool(
                            self.github_id and self.github_secret
                        ),
                    }
                )
        return result

    def mount(self, app):
        @app.get("/api/connections")
        def connections(request: Request):
            user = self.auth.current(request)
            return {
                "items": self.status(user),
                "enabled_providers": list(self.providers(user)),
            }

        @app.delete("/api/connections/{provider}")
        def disconnect(provider: str, request: Request, organization: str = ""):
            user = self.auth.current(request)
            self.check_user(user, provider)
            with self.auth._db() as db:
                db.execute(
                    "DELETE FROM provider_connections WHERE owner=? AND provider=? AND organization=?",
                    (user.id, provider, organization.casefold()),
                )
            return {"disconnected": True}
