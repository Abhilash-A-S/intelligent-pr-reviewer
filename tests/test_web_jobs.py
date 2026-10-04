import time

from pr_reviewer.web.jobs import ReviewCommand, ReviewJobManager


class SuccessfulOrchestrator:
    def __init__(self, **_kwargs):
        pass

    def run(self, *, progress_callback, **_kwargs):
        progress_callback("static_analysis", 54, "Static analysis complete")
        progress_callback("ai_review", 79, "Semantic review complete")
        progress_callback("validation", 92, "Validation complete")
        return {"quality_gate": {"decision": "pass"}, "findings": []}


class FailingOrchestrator:
    def __init__(self, **_kwargs):
        pass

    def run(self, **_kwargs):
        raise RuntimeError("token=must-not-leak")


def wait_for_terminal_job(manager, job_id):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        job = manager.get(job_id)
        if job["status"] in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(0.01)
    raise AssertionError("review job did not reach a terminal state")


def test_job_manager_reports_structured_progress_and_result():
    manager = ReviewJobManager(
        provider_factory=lambda _name: object(),
        llm_factory=lambda: object(),
        orchestrator_factory=SuccessfulOrchestrator,
        max_parallel_jobs=1,
    )
    submitted = manager.submit(
        ReviewCommand(provider="github", repository="acme/store", pull_number=3)
    )

    job = wait_for_terminal_job(manager, submitted["id"])
    manager.close()

    assert job["status"] == "completed"
    assert job["progress"] == 100
    assert job["result"]["quality_gate"]["decision"] == "pass"
    assert job["result_summary"]["decision"] == "pass"
    assert job["result_summary"]["findings"] == 0
    assert all(step["state"] == "complete" for step in job["steps"])

    listed = manager.list()
    assert "result" not in listed[0]
    assert listed[0]["result_summary"]["decision"] == "pass"


def test_job_manager_redacts_sensitive_values_from_failures():
    manager = ReviewJobManager(
        provider_factory=lambda _name: object(),
        llm_factory=lambda: object(),
        orchestrator_factory=FailingOrchestrator,
        max_parallel_jobs=1,
    )
    submitted = manager.submit(
        ReviewCommand(provider="github", repository="acme/store", pull_number=3)
    )

    job = wait_for_terminal_job(manager, submitted["id"])
    manager.close()

    assert job["status"] == "failed"
    assert "must-not-leak" not in job["error"]
    assert "[redacted]" in job["error"]
