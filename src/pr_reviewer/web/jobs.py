from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import os
import re
from threading import RLock
from typing import Any, Callable
from uuid import uuid4

from fastapi.encoders import jsonable_encoder

from pr_reviewer.llm.ollama import OllamaProvider
from pr_reviewer.providers.base import PullRequestProvider
from pr_reviewer.providers.factory import create_pull_request_provider
from pr_reviewer.review.orchestrator import ReviewOrchestrator, ReviewRunResult


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class ReviewCommand:
    provider: str
    repository: str
    pull_number: int
    review_depth: str = "standard"
    publish: bool = False
    max_workers: int | None = None


@dataclass(slots=True)
class ReviewStep:
    key: str
    label: str
    state: str = "pending"
    message: str | None = None
    updated_at: datetime | None = None


@dataclass(slots=True)
class ReviewJob:
    id: str
    command: ReviewCommand
    status: str = "queued"
    phase: str = "queued"
    progress: int = 0
    message: str = "Waiting for an available review worker"
    created_at: datetime = field(default_factory=_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    result: dict[str, Any] | None = None
    result_summary: dict[str, Any] | None = None
    steps: list[ReviewStep] = field(default_factory=list)

    def snapshot(self, *, include_result: bool = True) -> dict[str, Any]:
        payload = asdict(self)
        if not include_result:
            payload.pop("result", None)
        return jsonable_encoder(payload)


class ReviewJobManager:
    """Runs the synchronous review engine behind a thread-safe job API."""

    STEP_DEFINITIONS = (
        ("queued", "Queued"),
        ("discovery", "Discovery"),
        ("static_analysis", "Static analysis"),
        ("ai_review", "AI review"),
        ("validation", "Validation"),
        ("publishing", "Publishing"),
        ("completed", "Completed"),
    )

    def __init__(
        self,
        *,
        provider_factory: Callable[..., PullRequestProvider] = (
            create_pull_request_provider
        ),
        llm_factory: Callable[[], Any] = OllamaProvider,
        orchestrator_factory: Callable[..., ReviewOrchestrator] = ReviewOrchestrator,
        max_parallel_jobs: int | None = None,
    ) -> None:
        configured = max_parallel_jobs
        if configured is None:
            try:
                configured = int(os.getenv("PR_REVIEW_MAX_JOBS", "1"))
            except ValueError:
                configured = 1
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, min(configured, 4)),
            thread_name_prefix="pr-review",
        )
        self._provider_factory = provider_factory
        self._llm_factory = llm_factory
        self._orchestrator_factory = orchestrator_factory
        self._jobs: dict[str, ReviewJob] = {}
        self._futures: dict[str, Future[None]] = {}
        self._lock = RLock()

    def submit(self, command: ReviewCommand) -> dict[str, Any]:
        job_id = uuid4().hex
        steps = [
            ReviewStep(
                key=key,
                label=label,
                state="active" if key == "queued" else "pending",
                updated_at=_now() if key == "queued" else None,
            )
            for key, label in self.STEP_DEFINITIONS
        ]
        job = ReviewJob(id=job_id, command=command, steps=steps)
        with self._lock:
            self._jobs[job_id] = job
            self._futures[job_id] = self._executor.submit(self._run, job_id)
        return job.snapshot(include_result=False)

    def get(self, job_id: str, *, include_result: bool = True) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.snapshot(include_result=include_result) if job else None

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            ordered = sorted(
                self._jobs.values(),
                key=lambda job: job.created_at,
                reverse=True,
            )
            return [job.snapshot(include_result=False) for job in ordered[:limit]]

    def cancel(self, job_id: str) -> bool | None:
        with self._lock:
            job = self._jobs.get(job_id)
            future = self._futures.get(job_id)
            if job is None or future is None:
                return None
            if not future.cancel():
                return False
            job.status = "cancelled"
            job.phase = "cancelled"
            job.message = "Review cancelled before execution"
            job.completed_at = _now()
            return True

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _run(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "running"
            job.started_at = _now()
            self._apply_progress(job, "discovery", 2, "Preparing review services")
            command = job.command

        try:
            provider = self._provider_factory(command.provider)
            llm_provider = self._llm_factory()
            orchestrator = self._orchestrator_factory(
                provider=provider,
                llm_provider=llm_provider,
                review_depth=command.review_depth,
                max_llm_workers=command.max_workers,
            )

            def report(phase: str, progress: int, message: str) -> None:
                with self._lock:
                    current = self._jobs.get(job_id)
                    if current is not None:
                        self._apply_progress(current, phase, progress, message)

            result = orchestrator.run(
                repository=command.repository,
                pull_number=command.pull_number,
                publish=command.publish,
                progress_callback=report,
            )
            self._complete(job_id, result)
        except Exception as exc:
            self._fail(job_id, exc)

    def _complete(self, job_id: str, result: ReviewRunResult) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "completed"
            job.result = jsonable_encoder(result)
            job.result_summary = self._summarize_result(job.result)
            job.completed_at = _now()
            self._apply_progress(job, "completed", 100, "Review completed")

    def _fail(self, job_id: str, exc: Exception) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "failed"
            job.phase = "failed"
            job.progress = min(job.progress, 99)
            job.message = "Review failed"
            job.error = self._safe_error(exc)
            job.completed_at = _now()
            for step in job.steps:
                if step.state == "active":
                    step.state = "failed"
                    step.message = job.error
                    step.updated_at = job.completed_at

    def _apply_progress(
        self,
        job: ReviewJob,
        phase: str,
        progress: int,
        message: str,
    ) -> None:
        job.phase = phase
        job.progress = max(job.progress, max(0, min(progress, 100)))
        job.message = message
        keys = [key for key, _label in self.STEP_DEFINITIONS]
        if phase not in keys:
            return
        active_index = keys.index(phase)
        timestamp = _now()
        for index, step in enumerate(job.steps):
            if index < active_index:
                step.state = "complete"
            elif index == active_index:
                step.state = "complete" if phase == "completed" else "active"
                step.message = message
                step.updated_at = timestamp
            elif step.state not in {"failed", "cancelled"}:
                step.state = "pending"

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        value = f"{type(exc).__name__}: {exc}"
        value = re.sub(
            r"(?i)(token|pat|authorization|password)(\s*[:=]\s*)[^\s,;]+",
            r"\1\2[redacted]",
            value,
        )
        return value[:2000]

    @staticmethod
    def _summarize_result(result: dict[str, Any]) -> dict[str, Any]:
        pull_request = result.get("pull_request") or {}
        quality_gate = result.get("quality_gate") or {}
        diagnostics = result.get("diagnostics") or {}
        findings = result.get("findings") or []
        severity_total = sum(
            int(quality_gate.get(key) or 0)
            for key in (
                "critical_count",
                "high_count",
                "medium_count",
                "low_count",
                "suggestion_count",
            )
        )
        return {
            "title": pull_request.get("title"),
            "author": pull_request.get("author"),
            "decision": quality_gate.get("decision"),
            "findings": severity_total or len(findings),
            "duration_seconds": diagnostics.get("total_review_seconds"),
            "dry_run": bool(result.get("dry_run", True)),
        }
