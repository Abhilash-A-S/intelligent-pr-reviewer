from unittest.mock import Mock

from pr_reviewer.review.models import (
    ChangedFile,
    PullRequest,
)
from pr_reviewer.review.orchestrator import (
    ReviewOrchestrator,
)
from pr_reviewer.review.quality_gate import (
    QualityGateDecision,
)


def test_orchestrator_runs_complete_review():
    provider = Mock()
    llm_provider = Mock()

    provider.get_pull_request.return_value = (
        PullRequest(
            provider="github",
            repository="example/repository",
            number=10,
            title="Test PR",
            author="developer",
            state="open",
            base_branch="main",
            head_branch="feature/test",
            head_commit="abc123",
        )
    )

    provider.get_changed_files.return_value = [
        ChangedFile(
            file_path="src/app.js",
            status="modified",
            patch="""@@ -1,1 +1,3 @@
 const value = 1;
+console.log("debug");
+const unused = 10;
""",
        )
    ]

    provider.get_file_content.return_value = (
        "const value = 1;\n"
        'console.log("debug");\n'
        "const unused = 10;\n"
    )

    llm_provider.review.return_value = """
    {
      "findings": []
    }
    """

    provider.get_existing_comments.return_value = []

    provider.publish_inline_comment.side_effect = [
        {"id": 1},
        {"id": 2},
    ]

    provider.get_summary_comments.return_value = []

    provider.publish_summary_comment.return_value = {
        "id": 100,
    }

    orchestrator = ReviewOrchestrator(
        provider=provider,
        llm_provider=llm_provider,
    )

    result = orchestrator.run(
        repository="example/repository",
        pull_number=10,
    )

    assert len(result.findings) == 2

    rule_ids = {
        finding.rule_id
        for finding in result.findings
    }

    assert rule_ids == {
        "no-console",
        "unused-variable",
    }

    assert (
        result.quality_gate.decision
        == QualityGateDecision.NON_BLOCKING
    )

    assert (
        result.publishing.published_count
        == 2
    )

    assert (
        result.summary_publishing.comment_id
        == 100
    )

    assert (
        provider.publish_inline_comment.call_count
        == 2
    )

    provider.publish_summary_comment.assert_called_once()


def test_orchestrator_returns_partial_success_when_summary_is_rate_limited():
    provider = Mock()
    llm_provider = Mock()
    provider.get_pull_request.return_value = PullRequest(
        provider="github", repository="example/repository", number=10,
        title="Test", author="developer", state="open", base_branch="main",
        head_branch="feature", head_commit="abc123",
    )
    provider.get_changed_files.return_value = [ChangedFile(
        file_path="src/app.js", status="modified",
        patch='@@ -0,0 +1 @@\n+console.log("debug");',
    )]
    provider.get_file_content.return_value = 'console.log("debug");\n'
    provider.get_existing_comments.return_value = []
    provider.publish_inline_comment.return_value = {"id": 1}
    provider.get_summary_comments.side_effect = RuntimeError("secondary rate limit")
    llm_provider.review.return_value = '{"findings": []}'

    result = ReviewOrchestrator(provider=provider, llm_provider=llm_provider).run(
        repository="example/repository", pull_number=10,
    )

    assert result.publishing.published_count == 1
    assert result.summary_publishing is None
    assert "secondary rate limit" in result.summary_publishing_failure


def test_orchestrator_handles_clean_review():
    provider = Mock()
    llm_provider = Mock()

    provider.get_pull_request.return_value = (
        PullRequest(
            provider="github",
            repository="example/repository",
            number=10,
            title="Clean PR",
            author="developer",
            state="open",
            base_branch="main",
            head_branch="feature/clean",
            head_commit="abc123",
        )
    )

    provider.get_changed_files.return_value = [
        ChangedFile(
            file_path="src/app.js",
            status="modified",
            patch="""@@ -1 +1 @@
-const value = 1;
+const value = 2;
""",
        )
    ]

    provider.get_file_content.return_value = (
        "const value = 2;\n"
        "console.log(value);\n"
    )

    llm_provider.review.return_value = (
        '{"findings": []}'
    )

    provider.get_existing_comments.return_value = []

    provider.get_summary_comments.return_value = []

    provider.publish_summary_comment.return_value = {
        "id": 200,
    }

    orchestrator = ReviewOrchestrator(
        provider=provider,
        llm_provider=llm_provider,
    )

    result = orchestrator.run(
        repository="example/repository",
        pull_number=10,
    )

    assert result.findings == []

    assert (
        result.quality_gate.decision
        == QualityGateDecision.PASS
    )

    assert (
        result.publishing.published_count
        == 0
    )

    provider.publish_inline_comment.assert_not_called()

    provider.publish_summary_comment.assert_called_once()


def test_orchestrator_dry_run_does_not_publish():
    provider = Mock()
    llm_provider = Mock()

    provider.get_pull_request.return_value = (
        PullRequest(
            provider="github",
            repository="example/repository",
            number=10,
            title="Dry Run PR",
            author="developer",
            state="open",
            base_branch="main",
            head_branch="feature/test",
            head_commit="abc123",
        )
    )

    provider.get_changed_files.return_value = [
        ChangedFile(
            file_path="src/app.js",
            status="modified",
            patch="""@@ -1,1 +1,2 @@
 const value = 1;
+console.log("debug");
""",
        )
    ]

    provider.get_file_content.return_value = (
        "const value = 1;\n"
        'console.log("debug");\n'
    )

    llm_provider.review.return_value = """
    {
      "findings": []
    }
    """

    orchestrator = ReviewOrchestrator(
        provider=provider,
        llm_provider=llm_provider,
    )

    result = orchestrator.run(
        repository="example/repository",
        pull_number=10,
        publish=False,
    )

    assert len(result.findings) == 1

    assert (
        result.findings[0].rule_id
        == "no-console"
    )

    assert result.dry_run is True

    assert (
        result.publishing.published_count
        == 0
    )

    assert result.summary_publishing is None

    provider.get_existing_comments.assert_not_called()

    provider.publish_inline_comment.assert_not_called()

    provider.get_summary_comments.assert_not_called()

    provider.publish_summary_comment.assert_not_called()

    provider.update_summary_comment.assert_not_called()


def test_orchestrator_rejects_false_angular_standalone_finding():
    provider = Mock()
    llm_provider = Mock()

    provider.get_pull_request.return_value = (
        PullRequest(
            provider="github",
            repository="example/angular-app",
            number=20,
            title="Angular test",
            author="developer",
            state="open",
            base_branch="main",
            head_branch="feature/angular",
            head_commit="angular123",
        )
    )

    provider.get_changed_files.return_value = [
        ChangedFile(
            file_path="angular.json",
            status="modified",
            patch="""@@ -1 +1 @@
+{"version": 1}
""",
        ),
        ChangedFile(
            file_path="package.json",
            status="modified",
            patch="""@@ -1 +1,5 @@
+{
+  "dependencies": {
+    "@angular/core": "^20.0.0"
+  }
+}
""",
        ),
        ChangedFile(
            file_path="src/app/app.ts",
            status="modified",
            patch="""@@ -1,1 +1,8 @@
+import { Component } from '@angular/core';
+import { RouterOutlet } from '@angular/router';
+
+@Component({
+  selector: 'app-root',
+  imports: [RouterOutlet],
+})
+export class App {}
""",
        ),
        ChangedFile(
            file_path="src/app/app.spec.ts",
            status="modified",
            patch="""@@ -1,1 +1,8 @@
+import { TestBed } from '@angular/core/testing';
+import { App } from './app';
+
+describe('App', () => {
+  beforeEach(async () => {
+    await TestBed.configureTestingModule({
+      imports: [App],
+    }).compileComponents();
""",
        ),
    ]

    def get_file_content(
        repository,
        file_path,
        ref,
    ):
        contents = {
            "angular.json": (
                '{"version": 1}'
            ),
            "package.json": (
                "{\n"
                '  "dependencies": {\n'
                '    "@angular/core": "^20.0.0"\n'
                "  }\n"
                "}\n"
            ),
            "src/app/app.ts": (
                "import { Component } "
                "from '@angular/core';\n"
                "import { RouterOutlet } "
                "from '@angular/router';\n"
                "\n"
                "@Component({\n"
                "  selector: 'app-root',\n"
                "  imports: [RouterOutlet],\n"
                "})\n"
                "export class App {}\n"
            ),
            "src/app/app.spec.ts": (
                "import { TestBed } "
                "from '@angular/core/testing';\n"
                "import { App } from './app';\n"
                "\n"
                "describe('App', () => {\n"
                "  beforeEach(async () => {\n"
                "    await TestBed.configureTestingModule({\n"
                "      imports: [App],\n"
                "    }).compileComponents();\n"
                "  });\n"
                "});\n"
            ),
        }

        return contents[
            file_path
        ]

    provider.get_file_content.side_effect = (
        get_file_content
    )

    def review(
        changed_file,
        repository_context,
    ):
        if (
            changed_file.file_path
            == "src/app/app.spec.ts"
        ):
            return """
            {
              "findings": [
                {
                  "line_number": 7,
                  "severity": "medium",
                  "rule_id": "standalone-component-import",
                  "message": "Using the component itself as an import in TestBed configuration is not recommended.",
                  "suggestion": "Use a standalone component or a module."
                }
              ]
            }
            """

        return """
        {
          "findings": []
        }
        """

    llm_provider.review.side_effect = review

    orchestrator = ReviewOrchestrator(
        provider=provider,
        llm_provider=llm_provider,
    )

    result = orchestrator.run(
        repository="example/angular-app",
        pull_number=20,
        publish=False,
    )

    assert result.findings == []

    assert (
        result.quality_gate.decision
        == QualityGateDecision.PASS
    )

    assert result.dry_run is True

def test_orchestrator_reviews_independent_files_concurrently():
    import threading
    import time

    provider = Mock()
    provider.get_pull_request.return_value = PullRequest(
        provider="github",
        repository="example/repository",
        number=11,
        title="Concurrent review",
        author="developer",
        state="open",
        base_branch="main",
        head_branch="feature/concurrent",
        head_commit="abc123",
    )
    provider.get_changed_files.return_value = [
        ChangedFile(
            file_path=f"src/file{index}.ts",
            status="modified",
            patch=f"@@ -0,0 +1 @@\n+const value{index} = doWork();\n",
        )
        for index in range(3)
    ]
    provider.get_file_content.side_effect = lambda **kwargs: "const value = doWork();\n"
    provider.get_repository_tree.return_value = []
    provider.get_existing_comments.return_value = []
    provider.get_summary_comments.return_value = []

    class ConcurrentLLMProvider:
        def __init__(self):
            self.active = 0
            self.max_active = 0
            self.lock = threading.Lock()
            self.release = threading.Event()
            self.started = threading.Event()

        def review(self, changed_file, repository_context):
            with self.lock:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
                if self.max_active >= 2:
                    self.started.set()
            self.started.wait(timeout=1.0)
            time.sleep(0.02)
            with self.lock:
                self.active -= 1
            return '{"findings": []}'

    llm_provider = ConcurrentLLMProvider()
    orchestrator = ReviewOrchestrator(
        provider=provider,
        llm_provider=llm_provider,
        max_llm_workers=3,
    )

    result = orchestrator.run(
        repository="example/repository",
        pull_number=11,
        publish=False,
    )

    assert result.findings == []
    assert llm_provider.max_active >= 2


def test_orchestrator_llm_worker_count_is_bounded(monkeypatch):
    monkeypatch.setenv("PR_REVIEW_LLM_MAX_WORKERS", "99")
    orchestrator = ReviewOrchestrator(
        provider=Mock(),
        llm_provider=Mock(),
    )
    assert orchestrator.max_llm_workers == 8


def test_orchestrator_uses_provider_concurrency_recommendation(monkeypatch):
    monkeypatch.delenv("PR_REVIEW_LLM_MAX_WORKERS", raising=False)
    llm_provider = Mock()
    llm_provider.recommended_concurrency = 1

    orchestrator = ReviewOrchestrator(
        provider=Mock(),
        llm_provider=llm_provider,
    )

    assert orchestrator.max_llm_workers == 1
