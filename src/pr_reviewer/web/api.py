from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import asdict, replace
import os
import logging
import json
import time
from pathlib import Path
from typing import Annotated, Literal

import httpx
from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pr_reviewer.web.security import AuthService, Principal, canonical_repository
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from pr_reviewer import __version__
from pr_reviewer.providers.factory import (
    PROVIDER_NAMES,
    create_pull_request_provider,
    normalize_provider_name,
    provider_display_name,
)
from pr_reviewer.web.jobs import ReviewCommand, ReviewJobManager


class ReviewCreateRequest(BaseModel):
    provider: str
    repository: str = Field(min_length=1, max_length=500)
    pull_number: int = Field(gt=0)
    review_depth: Literal["fast", "standard", "deep"] = "standard"
    publish: bool = False
    max_workers: int | None = Field(default=None, ge=1, le=8)


def _configured_origins() -> list[str]:
    raw = os.getenv(
        "PR_REVIEW_UI_ORIGINS",
        "http://localhost:4200,http://127.0.0.1:4200",
    )
    return [item.strip() for item in raw.split(",") if item.strip()]


def _provider_probe(name: str) -> tuple[bool, str, str | None]:
    try:
        adapter = create_pull_request_provider(name)
        adapter.validate_connection()
        return True, "connected", None
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        if status_code in {401, 403}:
            return (
                False,
                "authentication-failed",
                "Authentication failed. Verify the credential and its provider permissions.",
            )
        return (
            False,
            "unavailable",
            f"Provider validation returned HTTP {status_code}.",
        )
    except Exception:
        return (
            False,
            "unavailable",
            "The provider could not be validated. Check its configuration and availability.",
        )


def _provider_status(*, probe: bool = False) -> list[dict]:
    definitions = (
        ("github", "GitHub", "GITHUB_TOKEN", "owner/repository"),
        (
            "azure-devops",
            "Azure DevOps",
            "AZURE_DEVOPS_PAT",
            "organization/project/repository",
        ),
    )
    statuses = [
        {
            "id": provider_id,
            "name": name,
            "configured": bool(os.getenv(env_name)),
            "connected": bool(os.getenv(env_name)),
            "state": "configured" if os.getenv(env_name) else "not-configured",
            "detail": None,
            "repository_format": repository_format,
        }
        for provider_id, name, env_name, repository_format in definitions
    ]
    if not probe:
        return statuses

    configured = [item for item in statuses if item["configured"]]
    if configured:
        with ThreadPoolExecutor(max_workers=len(configured)) as executor:
            probes = {
                item["id"]: future
                for item, future in (
                    (item, executor.submit(_provider_probe, item["id"]))
                    for item in configured
                )
            }
            for item in configured:
                connected, state, detail = probes[item["id"]].result()
                item["connected"] = connected
                item["state"] = state
                item["detail"] = detail
    return statuses


def _ollama_status(probe: bool) -> dict:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    try:
        read_timeout = float(os.getenv("OLLAMA_READ_TIMEOUT", "300"))
    except ValueError:
        read_timeout = 300.0
    payload = {
        "configured": bool(base_url and os.getenv("OLLAMA_MODEL")),
        "ready": None,
        "model": os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b"),
        "base_url": base_url,
        "read_timeout_seconds": max(0.0, read_timeout),
    }
    if not probe:
        return payload
    try:
        response = httpx.get(f"{base_url}/api/tags", timeout=1.25)
        response.raise_for_status()
        payload["ready"] = True
    except Exception:
        payload["ready"] = False
    return payload


def _provider_or_http_error(name: str):
    normalized = normalize_provider_name(name)
    if normalized not in PROVIDER_NAMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider: {name}",
        )
    try:
        return create_pull_request_provider(normalized)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


def _provider_failure(exc: Exception) -> HTTPException:
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code == 401:
            return HTTPException(
                status_code=code,
                detail="Provider authentication failed. Verify that the token is valid and unexpired.",
            )
        if code == 403:
            return HTTPException(
                status_code=code,
                detail="Provider access was denied. Verify repository and pull-request permissions.",
            )
        if code in {404, 422}:
            return HTTPException(status_code=code, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=502, detail=f"Provider request failed: {exc}")


def _pull_request_summaries_with_counts(
    adapter,
    repository: str,
    items: list,
) -> list:
    """Enrich a bounded dashboard page without downloading full patches."""

    try:
        configured_limit = int(os.getenv("PR_REVIEW_UI_FILE_COUNT_LIMIT", "30"))
    except ValueError:
        configured_limit = 30
    limit = max(0, min(configured_limit, 100))
    candidates = items[:limit]
    if not candidates:
        return items

    def resolve(item):
        if item.changed_files is not None:
            return item
        try:
            value = adapter.get_changed_file_count(repository, item.number)
        except Exception:
            return item
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return item
        return replace(item, changed_files=value)

    workers = min(8, len(candidates))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        enriched = list(executor.map(resolve, candidates))
    return [*enriched, *items[limit:]]


def _diff_counts(patch: str | None) -> tuple[int | None, int | None]:
    """Return source additions/deletions without counting unified-diff headers."""
    if patch is None:
        return None, None
    additions = 0
    deletions = 0
    in_hunk = False
    for line in patch.splitlines():
        if line.startswith("@@"):
            in_hunk = True
            continue
        if not in_hunk:
            continue
        if line.startswith("+"):
            additions += 1
        elif line.startswith("-"):
            deletions += 1
    return additions, deletions


def _discovery_payload(
    provider: str,
    items: list,
    query: str,
    limit: int,
) -> dict:
    serialized = [item if isinstance(item, dict) else asdict(item) for item in items]
    term = query.strip().casefold()
    if term:
        serialized = [
            item
            for item in serialized
            if term
            in " ".join(
                str(value) for value in item.values() if value is not None
            ).casefold()
        ]
    total = len(serialized)
    return {
        "provider": normalize_provider_name(provider),
        "items": serialized[:limit],
        "total": total,
    }


def _ui_static_root() -> Path:
    configured = os.getenv("PR_REVIEW_UI_DIST")
    if configured:
        return Path(configured).expanduser().resolve()

    packaged = Path(__file__).resolve().parent / "static"
    if packaged.is_dir():
        return packaged

    project_root = Path(__file__).resolve().parents[3]
    return project_root / "web" / "dist" / "reviewer-ui" / "browser"


def create_app(
    *,
    job_manager: ReviewJobManager | None = None,
    auth_service: AuthService | None = None,
) -> FastAPI:
    auth = auth_service or AuthService()

    def execution_guard(command):
        if (
            not command.owner_id
            or not command.owner_auth_expires_at
            or command.owner_auth_expires_at <= time.time()
        ):
            raise PermissionError(
                "Review authorization has expired; sign in and start a new review"
            )
        if auth.connections:
            row = auth.connections.row(
                Principal(command.owner_id, "", provider=command.owner_login_provider),
                command.provider,
                command.repository,
            )
            if row["version"] != command.owner_connection_version:
                raise PermissionError("Provider connection changed. Start a new review")
        auth.policy.require(
            Principal(
                command.owner_id,
                command.owner_name or "",
                command.owner_groups,
                command.owner_login_provider,
            ),
            command.provider,
            command.repository,
            3 if command.publish else 2,
        )

    def command_provider(command):
        if auth.connections:
            execution_guard(command)
            return auth.adapter(
                Principal(
                    command.owner_id,
                    command.owner_name or "",
                    provider=command.owner_login_provider,
                ),
                command.provider,
                command.repository,
            )
        return create_pull_request_provider(command.provider)

    manager = job_manager or ReviewJobManager(
        execution_guard=execution_guard, command_provider_factory=command_provider
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        if job_manager is None:
            manager.close()

    app = FastAPI(
        title="Intelligent PR Reviewer API",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.auth = auth
    auth.mount(app)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        if request.url.path.startswith("/api/connections"):
            return JSONResponse(
                {"detail": "Invalid connection request"}, status_code=422
            )
        return JSONResponse(
            {
                "detail": [
                    {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]}
                    for e in exc.errors()
                ]
            },
            status_code=422,
        )

    def user_adapter(request, provider, repository=None):
        if auth.connections:
            return auth.adapter(request.state.user, provider, repository)
        return _provider_or_http_error(provider)

    def connection_status(request, probe=False):
        if auth.connections:
            return auth.connections.status(request.state.user)
        return _provider_status(probe=probe)

    @app.middleware("http")
    async def authenticate(request: Request, call_next):
        protected = (
            request.url.path.startswith("/api/")
            and not request.url.path.startswith("/api/auth/")
        ) or request.url.path in {"/docs", "/redoc", "/openapi.json"}
        if protected and request.method != "OPTIONS":
            try:
                request.state.user = auth.current(request)
            except HTTPException as exc:
                return JSONResponse(
                    {"detail": exc.detail},
                    status_code=exc.status_code,
                    headers={"Cache-Control": "no-store"},
                )
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
            if request.url.path == "/api/auth/callback":
                response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def permissions(request):
        # Cache only within this HTTP request, never across users or requests.
        if not hasattr(request.state, "repository_permissions"):
            request.state.repository_permissions = auth.policy.permissions(
                request.state.user
            )
        return request.state.repository_permissions

    def job_permission(request, item):
        command = item.get("command") or {}
        try:
            repo = canonical_repository(
                command.get("provider", ""), command.get("repository", "")
            )
        except (ValueError, AttributeError):
            return 0
        return permissions(request).get((command.get("provider"), repo), 0)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_configured_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )

    @app.get("/api/health")
    def health(
        http_request: Request,
        probe_ollama: bool = False,
        probe_providers: bool = False,
    ) -> dict:
        try:
            max_inline_comments = int(os.getenv("PR_REVIEW_MAX_INLINE_COMMENTS", "40"))
        except ValueError:
            max_inline_comments = 40
        return {
            "status": "ok",
            "version": __version__,
            "providers": connection_status(http_request, probe_providers),
            "ollama": _ollama_status(probe_ollama),
            "review_policy": {
                "max_inline_comments": max(0, min(max_inline_comments, 200)),
                "confirmation_before_publish": True,
                "duplicate_prevention": True,
                "summary_comment": True,
            },
        }

    @app.get("/api/providers")
    def providers(http_request: Request) -> dict:
        return {"items": connection_status(http_request)}

    @app.get("/api/repository-discovery/organizations")
    def discover_organizations(
        http_request: Request,
        provider: str,
        query: Annotated[str, Query(max_length=200)] = "",
        limit: Annotated[int, Query(ge=1, le=500)] = 200,
    ) -> dict:
        provider = normalize_provider_name(provider)
        allowed = {
            r.split("/")[0] for (p, r) in permissions(http_request) if p == provider
        }
        if not allowed:
            return _discovery_payload(provider, [], query, limit)
        if auth.connections:
            return _discovery_payload(
                provider,
                [
                    {"id": name, "name": name, "display_name": name}
                    for name in sorted(allowed)
                ],
                query,
                limit,
            )
        adapter = user_adapter(http_request, provider)
        try:
            items = [
                i for i in adapter.list_organizations() if i.name.casefold() in allowed
            ]
        except Exception as exc:
            raise _provider_failure(exc) from exc
        return _discovery_payload(provider, items, query, limit)

    @app.get("/api/repository-discovery/projects")
    def discover_projects(
        http_request: Request,
        provider: str,
        organization: Annotated[str, Query(min_length=1, max_length=200)],
        query: Annotated[str, Query(max_length=200)] = "",
        limit: Annotated[int, Query(ge=1, le=500)] = 200,
    ) -> dict:
        provider = normalize_provider_name(provider)
        allowed = {
            r.split("/")[1]
            for (p, r) in permissions(http_request)
            if p == provider and r.split("/")[0] == organization.casefold()
        }
        if not allowed:
            raise HTTPException(403, "Organization access denied")
        if auth.connections:
            return _discovery_payload(
                provider,
                [
                    {"id": name, "name": name, "display_name": name}
                    for name in sorted(allowed)
                ],
                query,
                limit,
            )
        adapter = user_adapter(http_request, provider)
        try:
            items = [
                i
                for i in adapter.list_projects(organization)
                if i.name.casefold() in allowed
            ]
        except Exception as exc:
            raise _provider_failure(exc) from exc
        return _discovery_payload(provider, items, query, limit)

    @app.get("/api/repository-discovery/repositories")
    def discover_repositories(
        http_request: Request,
        provider: str,
        organization: Annotated[str, Query(min_length=1, max_length=200)],
        project: Annotated[str | None, Query(max_length=200)] = None,
        query: Annotated[str, Query(max_length=200)] = "",
        limit: Annotated[int, Query(ge=1, le=500)] = 300,
    ) -> dict:
        provider = normalize_provider_name(provider)
        allowed = {
            r
            for (p, r) in permissions(http_request)
            if p == provider
            and r.split("/")[0] == organization.casefold()
            and (
                provider != "azure-devops"
                or r.split("/")[1] == (project or "").casefold()
            )
        }
        if not allowed:
            raise HTTPException(403, "Repository discovery access denied")
        if auth.connections:
            return _discovery_payload(
                provider,
                [
                    {
                        "id": repo,
                        "name": repo.split("/")[-1],
                        "full_name": repo,
                        "default_branch": None,
                    }
                    for repo in sorted(allowed)
                ],
                query,
                limit,
            )
        adapter = user_adapter(http_request, provider)
        try:
            items = []
            for item in adapter.list_repositories(organization, project):
                identifier = (
                    "/".join([organization, item.name])
                    if provider == "github"
                    else "/".join([organization, project or "", item.name])
                )
                if canonical_repository(provider, identifier) in allowed:
                    items.append(item)
        except Exception as exc:
            raise _provider_failure(exc) from exc
        return _discovery_payload(provider, items, query, limit)

    @app.get("/api/pull-requests")
    def pull_requests(
        http_request: Request,
        provider: str,
        repository: Annotated[str, Query(min_length=1, max_length=500)],
        state: Literal["open", "closed", "all"] = "open",
    ) -> dict:
        provider = normalize_provider_name(provider)
        repository = auth.policy.require(http_request.state.user, provider, repository)
        adapter = user_adapter(http_request, provider, repository)
        try:
            items = adapter.list_pull_requests(repository, state=state)
            items = _pull_request_summaries_with_counts(
                adapter,
                repository,
                items,
            )
        except Exception as exc:
            raise _provider_failure(exc) from exc
        return {
            "provider": normalize_provider_name(provider),
            "repository": repository,
            "items": [asdict(item) for item in items],
            "total": len(items),
        }

    @app.get("/api/pull-requests/{pull_number}")
    def pull_request(
        http_request: Request,
        pull_number: int,
        provider: str,
        repository: Annotated[str, Query(min_length=1, max_length=500)],
    ) -> dict:
        provider = normalize_provider_name(provider)
        repository = auth.policy.require(http_request.state.user, provider, repository)
        adapter = user_adapter(http_request, provider, repository)
        try:
            item = adapter.get_pull_request(repository, pull_number)
        except Exception as exc:
            raise _provider_failure(exc) from exc
        return asdict(item)

    @app.get("/api/pull-requests/{pull_number}/files")
    def changed_files(
        http_request: Request,
        pull_number: int,
        provider: str,
        repository: Annotated[str, Query(min_length=1, max_length=500)],
    ) -> dict:
        provider = normalize_provider_name(provider)
        repository = auth.policy.require(http_request.state.user, provider, repository)
        adapter = user_adapter(http_request, provider, repository)
        try:
            files = adapter.get_changed_files(repository, pull_number)
            # Azure lists metadata first; line statistics require text patches.
            if adapter.supports_deferred_patch_hydration is True and files:
                files = adapter.hydrate_changed_files(repository, pull_number, files)
        except Exception as exc:
            raise _provider_failure(exc) from exc
        items = []
        for item in files:
            additions, deletions = _diff_counts(item.patch)
            items.append(
                {
                    "file_path": item.file_path,
                    "status": item.status,
                    "language": item.language,
                    "changed_line_count": len(item.changed_lines),
                    "additions": additions,
                    "deletions": deletions,
                }
            )
        return {
            "items": items,
            "total": len(files),
        }

    @app.post("/api/reviews", status_code=status.HTTP_202_ACCEPTED)
    def create_review(request: ReviewCreateRequest, http_request: Request) -> dict:
        normalized = normalize_provider_name(request.provider)
        if normalized not in PROVIDER_NAMES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported provider: {request.provider}",
            )
        repository = auth.policy.require(
            http_request.state.user,
            normalized,
            request.repository,
            3 if request.publish else 2,
        )
        connected = bool(auth.connections) or next(
            item["connected"] for item in _provider_status() if item["id"] == normalized
        )
        if not connected:
            env_name = "GITHUB_TOKEN" if normalized == "github" else "AZURE_DEVOPS_PAT"
            raise HTTPException(
                status_code=503,
                detail=f"{env_name} is not configured on the API server.",
            )
        submitted = manager.submit(
            ReviewCommand(
                provider=normalized,
                repository=repository,
                pull_number=request.pull_number,
                review_depth=request.review_depth,
                publish=request.publish,
                max_workers=request.max_workers,
                owner_connection_version=(
                    auth.connections.row(
                        http_request.state.user, normalized, repository
                    )["version"]
                    if auth.connections
                    else None
                ),
                owner_login_provider=http_request.state.user.provider,
                owner_id=http_request.state.user.id,
                owner_name=http_request.state.user.name,
                owner_auth_expires_at=http_request.state.session["_expires_at"],
                owner_groups=http_request.state.user.groups,
            )
        )
        logging.getLogger("pr_reviewer.audit").info(
            json.dumps(
                {
                    "event": "review_requested",
                    "actor": http_request.state.user.id,
                    "repository": repository,
                    "provider": normalized,
                    "publish": request.publish,
                    "job_id": submitted["id"],
                }
            )
        )
        return submitted

    @app.get("/api/reviews")
    def reviews(
        http_request: Request, limit: Annotated[int, Query(ge=1, le=200)] = 50
    ) -> dict:
        items = manager.list(
            limit=limit, predicate=lambda item: job_permission(http_request, item) >= 1
        )
        return {"items": items, "total": len(items)}

    @app.get("/api/reviews/{job_id}")
    def review(job_id: str, http_request: Request, include_result: bool = True) -> dict:
        item = manager.get(job_id, include_result=include_result)
        if item is None or not job_permission(http_request, item):
            raise HTTPException(status_code=404, detail="Review job not found")
        return item

    @app.delete("/api/reviews/{job_id}")
    def cancel_review(job_id: str, http_request: Request) -> dict:
        item = manager.get(job_id, include_result=False)
        level = job_permission(http_request, item) if item else 0
        if not level:
            raise HTTPException(404, "Review job not found")
        if level < 4 and (
            level < 2
            or (item.get("command") or {}).get("owner_id") != http_request.state.user.id
        ):
            raise HTTPException(
                403,
                "Only the job owner or a repository administrator may cancel this review",
            )
        cancelled = manager.cancel(job_id)
        if cancelled is None:
            raise HTTPException(status_code=404, detail="Review job not found")
        if not cancelled:
            raise HTTPException(
                status_code=409,
                detail="A running review cannot be interrupted safely.",
            )
        logging.getLogger("pr_reviewer.audit").info(
            json.dumps(
                {
                    "event": "review_cancelled",
                    "actor": http_request.state.user.id,
                    "job_id": job_id,
                }
            )
        )
        return {"id": job_id, "status": "cancelled"}

    static_root = _ui_static_root()

    @app.get("/{full_path:path}", include_in_schema=False)
    def angular_app(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(404, "API endpoint not found")
        if not static_root.is_dir():
            raise HTTPException(
                status_code=404,
                detail="Angular UI is not built. Run npm run build in web/.",
            )
        requested = (static_root / full_path).resolve()
        if requested.is_relative_to(static_root.resolve()) and requested.is_file():
            return FileResponse(requested)
        return FileResponse(static_root / "index.html")

    return app


app = create_app()
