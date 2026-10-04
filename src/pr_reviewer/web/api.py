from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
import os
from pathlib import Path
from typing import Annotated, Literal

import httpx
from fastapi import FastAPI, HTTPException, Query, status
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


def _provider_status() -> list[dict]:
    return [
        {
            "id": "github",
            "name": "GitHub",
            "connected": bool(os.getenv("GITHUB_TOKEN")),
            "repository_format": "owner/repository",
        },
        {
            "id": "azure-devops",
            "name": "Azure DevOps",
            "connected": bool(os.getenv("AZURE_DEVOPS_PAT")),
            "repository_format": "organization/project/repository",
        },
    ]


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
        if code in {401, 403, 404, 422}:
            return HTTPException(status_code=code, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=502, detail=f"Provider request failed: {exc}")


def _diff_counts(patch: str | None) -> tuple[int | None, int | None]:
    """Return source additions/deletions without counting unified-diff headers."""
    if patch is None:
        return None, None
    additions = 0
    deletions = 0
    for line in patch.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            additions += 1
        elif line.startswith("-"):
            deletions += 1
    return additions, deletions


def _ui_static_root() -> Path:
    configured = os.getenv("PR_REVIEW_UI_DIST")
    if configured:
        return Path(configured).expanduser().resolve()

    packaged = Path(__file__).resolve().parent / "static"
    if packaged.is_dir():
        return packaged

    project_root = Path(__file__).resolve().parents[3]
    return project_root / "web" / "dist" / "reviewer-ui" / "browser"


def create_app(*, job_manager: ReviewJobManager | None = None) -> FastAPI:
    manager = job_manager or ReviewJobManager()

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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_configured_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    @app.get("/api/health")
    def health(probe_ollama: bool = False) -> dict:
        try:
            max_inline_comments = int(
                os.getenv("PR_REVIEW_MAX_INLINE_COMMENTS", "40")
            )
        except ValueError:
            max_inline_comments = 40
        return {
            "status": "ok",
            "version": __version__,
            "providers": _provider_status(),
            "ollama": _ollama_status(probe_ollama),
            "review_policy": {
                "max_inline_comments": max(0, min(max_inline_comments, 200)),
                "confirmation_before_publish": True,
                "duplicate_prevention": True,
                "summary_comment": True,
            },
        }

    @app.get("/api/providers")
    def providers() -> dict:
        return {"items": _provider_status()}

    @app.get("/api/pull-requests")
    def pull_requests(
        provider: str,
        repository: Annotated[str, Query(min_length=1, max_length=500)],
        state: Literal["open", "closed", "all"] = "open",
    ) -> dict:
        adapter = _provider_or_http_error(provider)
        try:
            items = adapter.list_pull_requests(repository, state=state)
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
        pull_number: int,
        provider: str,
        repository: Annotated[str, Query(min_length=1, max_length=500)],
    ) -> dict:
        adapter = _provider_or_http_error(provider)
        try:
            item = adapter.get_pull_request(repository, pull_number)
        except Exception as exc:
            raise _provider_failure(exc) from exc
        return asdict(item)

    @app.get("/api/pull-requests/{pull_number}/files")
    def changed_files(
        pull_number: int,
        provider: str,
        repository: Annotated[str, Query(min_length=1, max_length=500)],
    ) -> dict:
        adapter = _provider_or_http_error(provider)
        try:
            files = adapter.get_changed_files(repository, pull_number)
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
    def create_review(request: ReviewCreateRequest) -> dict:
        normalized = normalize_provider_name(request.provider)
        if normalized not in PROVIDER_NAMES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported provider: {request.provider}",
            )
        connected = next(
            item["connected"]
            for item in _provider_status()
            if item["id"] == normalized
        )
        if not connected:
            env_name = "GITHUB_TOKEN" if normalized == "github" else "AZURE_DEVOPS_PAT"
            raise HTTPException(
                status_code=503,
                detail=f"{env_name} is not configured on the API server.",
            )
        return manager.submit(
            ReviewCommand(
                provider=normalized,
                repository=request.repository,
                pull_number=request.pull_number,
                review_depth=request.review_depth,
                publish=request.publish,
                max_workers=request.max_workers,
            )
        )

    @app.get("/api/reviews")
    def reviews(limit: Annotated[int, Query(ge=1, le=200)] = 50) -> dict:
        items = manager.list(limit=limit)
        return {"items": items, "total": len(items)}

    @app.get("/api/reviews/{job_id}")
    def review(job_id: str, include_result: bool = True) -> dict:
        item = manager.get(job_id, include_result=include_result)
        if item is None:
            raise HTTPException(status_code=404, detail="Review job not found")
        return item

    @app.delete("/api/reviews/{job_id}")
    def cancel_review(job_id: str) -> dict:
        cancelled = manager.cancel(job_id)
        if cancelled is None:
            raise HTTPException(status_code=404, detail="Review job not found")
        if not cancelled:
            raise HTTPException(
                status_code=409,
                detail="A running review cannot be interrupted safely.",
            )
        return {"id": job_id, "status": "cancelled"}

    static_root = _ui_static_root()

    @app.get("/{full_path:path}", include_in_schema=False)
    def angular_app(full_path: str):
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
