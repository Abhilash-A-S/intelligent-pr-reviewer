from unittest.mock import Mock

from pr_reviewer.context.builder import (
    RepositoryContextBuilder,
)
from pr_reviewer.review.models import (
    ChangedFile,
    PullRequest,
)
from pr_reviewer.review.orchestrator import (
    ReviewOrchestrator,
)


def test_nx_multi_framework_repository_resolves_correct_project_context():
    """
    Verify that an Nx repository containing multiple
    frameworks creates independent project contexts.

    Repository:

        Nx
        ├── apps/angular-app
        │       Angular
        │
        ├── apps/react-app
        │       React
        │
        └── services/api
                Express

    A framework detected for one project must not leak
    into another project.
    """

    changed_files = [
        ChangedFile(
            file_path="nx.json",
            status="modified",
            patch="""@@ -1 +1,3 @@
 {
+  "defaultBase": "main"
 }
""",
            full_content="""{
  "defaultBase": "main"
}
""",
        ),

        ChangedFile(
            file_path=(
                "apps/angular-app/"
                "src/app/app.component.ts"
            ),
            status="modified",
            language="typescript",
            patch="""@@ -0,0 +1,7 @@
+import { Component } from '@angular/core';
+
+@Component({
+  selector: 'app-root',
+  standalone: true,
+  template: '<h1>Angular</h1>'
+})
+export class AppComponent {}
""",
            full_content="""import { Component } from '@angular/core';

@Component({
  selector: 'app-root',
  standalone: true,
  template: '<h1>Angular</h1>'
})
export class AppComponent {}
""",
        ),

        ChangedFile(
            file_path="apps/react-app/src/App.tsx",
            status="modified",
            language="typescript",
            patch="""@@ -0,0 +1,5 @@
+import React from 'react';
+
+export function App() {
+  return <h1>React</h1>;
+}
""",
            full_content="""import React from 'react';

export function App() {
  return <h1>React</h1>;
}
""",
        ),

        ChangedFile(
            file_path="services/api/src/server.ts",
            status="modified",
            language="typescript",
            patch="""@@ -0,0 +1,6 @@
+import express from 'express';
+
+const app = express();
+app.get('/health', (req, res) => {
+  res.json({ status: 'ok' });
+});
""",
            full_content="""import express from 'express';

const app = express();

app.get('/health', (req, res) => {
  res.json({ status: 'ok' });
});
""",
        ),
    ]

    context = (
        RepositoryContextBuilder().build(
            changed_files
        )
    )

    # --------------------------------------------------
    # Workspace detection
    # --------------------------------------------------

    assert context.workspace == "nx"

    # --------------------------------------------------
    # Resolve project ownership
    # --------------------------------------------------

    angular_project = (
        context.find_project_for_file(
            "apps/angular-app/"
            "src/app/app.component.ts"
        )
    )

    react_project = (
        context.find_project_for_file(
            "apps/react-app/src/App.tsx"
        )
    )

    express_project = (
        context.find_project_for_file(
            "services/api/src/server.ts"
        )
    )

    assert angular_project is not None
    assert react_project is not None
    assert express_project is not None

    # --------------------------------------------------
    # Project roots
    # --------------------------------------------------

    assert (
        angular_project.root
        == "apps/angular-app"
    )

    assert (
        react_project.root
        == "apps/react-app"
    )

    assert (
        express_project.root
        == "services/api"
    )

    # --------------------------------------------------
    # Framework detection
    # --------------------------------------------------

    assert (
        angular_project.framework
        == "angular"
    )

    assert (
        react_project.framework
        == "react"
    )

    assert (
        express_project.framework
        == "express"
    )

    # --------------------------------------------------
    # Framework isolation
    # --------------------------------------------------

    assert (
        angular_project.framework
        != react_project.framework
    )

    assert (
        angular_project.framework
        != express_project.framework
    )

    assert (
        react_project.framework
        != express_project.framework
    )


def test_project_resolution_uses_deepest_matching_root():
    """
    Project resolution must select the most specific
    matching project root.
    """

    changed_files = [
        ChangedFile(
            file_path="nx.json",
            status="modified",
            full_content="{}",
        ),

        ChangedFile(
            file_path="apps/web/src/app.ts",
            status="modified",
            language="typescript",
            full_content=(
                "import { Component } "
                "from '@angular/core';"
            ),
        ),

        ChangedFile(
            file_path=(
                "apps/web-e2e/src/test.ts"
            ),
            status="modified",
            language="typescript",
            full_content=(
                "export const test = true;"
            ),
        ),
    ]

    context = (
        RepositoryContextBuilder().build(
            changed_files
        )
    )

    web_project = (
        context.find_project_for_file(
            "apps/web/src/app.ts"
        )
    )

    e2e_project = (
        context.find_project_for_file(
            "apps/web-e2e/src/test.ts"
        )
    )

    assert web_project is not None
    assert e2e_project is not None

    assert (
        web_project.root
        == "apps/web"
    )

    assert (
        e2e_project.root
        == "apps/web-e2e"
    )


def test_orchestrator_passes_correct_project_context_to_llm():
    """
    Verify the complete orchestration boundary:

        ReviewOrchestrator
            ↓
        RepositoryContextBuilder
            ↓
        ProjectDetector
            ↓
        LLMReviewer
            ↓
        LLMProvider

    Each reviewed file must be able to resolve its own
    project/framework from RepositoryContext.
    """

    provider = Mock()
    llm_provider = Mock()

    provider.get_pull_request.return_value = (
        PullRequest(
            provider="github",
            repository="example/nx-repository",
            number=1,
            title="Multi framework test",
            author="developer",
            state="open",
            base_branch="main",
            head_branch="feature/test",
            head_commit="abc123",
        )
    )

    provider.get_changed_files.return_value = [
        ChangedFile(
            file_path="nx.json",
            status="modified",
            patch="""@@ -1 +1,3 @@
 {
+  "defaultBase": "main"
 }
""",
        ),

        ChangedFile(
            file_path=(
                "apps/angular-app/"
                "src/app/app.component.ts"
            ),
            status="modified",
            patch="""@@ -0,0 +1,7 @@
+import { Component } from '@angular/core';
+
+@Component({
+  standalone: true,
+  template: '<h1>Angular</h1>'
+})
+export class AppComponent {}
""",
        ),

        ChangedFile(
            file_path="apps/react-app/src/App.tsx",
            status="modified",
            patch="""@@ -0,0 +1,5 @@
+import React from 'react';
+
+export function App() {
+  return <h1>React</h1>;
+}
""",
        ),

        ChangedFile(
            file_path="services/api/src/server.ts",
            status="modified",
            patch="""@@ -0,0 +1,6 @@
+import express from 'express';
+
+const app = express();
+app.get('/health', (req, res) => {
+  res.json({ status: 'ok' });
+});
""",
        ),
    ]

    # --------------------------------------------------
    # Simulate provider full-file fetching.
    # --------------------------------------------------

    file_contents = {
        "nx.json": """{
  "defaultBase": "main"
}
""",

        (
            "apps/angular-app/"
            "src/app/app.component.ts"
        ): """import { Component } from '@angular/core';

@Component({
  standalone: true,
  template: '<h1>Angular</h1>'
})
export class AppComponent {}
""",

        "apps/react-app/src/App.tsx": """import React from 'react';

export function App() {
  return <h1>React</h1>;
}
""",

        "services/api/src/server.ts": """import express from 'express';

const app = express();

app.get('/health', (req, res) => {
  res.json({ status: 'ok' });
});
""",
    }

    def get_file_content(
        repository,
        file_path,
        ref,
    ):
        return file_contents[
            file_path
        ]

    provider.get_file_content.side_effect = (
        get_file_content
    )

    # --------------------------------------------------
    # Return valid empty semantic-review results.
    # --------------------------------------------------

    llm_provider.review.return_value = (
        '{"findings": []}'
    )

    orchestrator = ReviewOrchestrator(
        provider=provider,
        llm_provider=llm_provider,
    )

    result = orchestrator.run(
        repository="example/nx-repository",
        pull_number=1,
        publish=False,
    )

    assert result.dry_run is True

    # --------------------------------------------------
    # nx.json remains repository context but is context-only for LLM review.
    # --------------------------------------------------

    assert (
        llm_provider.review.call_count
        == 3
    )

    reviewed_frameworks: dict[
        str,
        str,
    ] = {}

    reviewed_projects: dict[
        str,
        str,
    ] = {}

    # --------------------------------------------------
    # Inspect the actual context passed across the
    # LLMProvider boundary.
    # --------------------------------------------------

    for call in (
        llm_provider.review.call_args_list
    ):

        changed_file = (
            call.kwargs[
                "changed_file"
            ]
        )

        repository_context = (
            call.kwargs[
                "repository_context"
            ]
        )

        project = (
            repository_context
            .find_project_for_file(
                changed_file.file_path
            )
        )

        assert project is not None

        reviewed_frameworks[
            changed_file.file_path
        ] = project.framework

        reviewed_projects[
            changed_file.file_path
        ] = project.root

    # --------------------------------------------------
    # Root workspace metadata remains available in repository context
    # even though it is not sent to the LLM.
    # --------------------------------------------------

    repository_context = llm_provider.review.call_args_list[0].kwargs[
        "repository_context"
    ]
    root_project = repository_context.find_project_for_file("nx.json")
    assert root_project is not None
    assert root_project.framework == "unknown"
    assert root_project.root == "."

    # --------------------------------------------------
    # Angular
    # --------------------------------------------------

    angular_file = (
        "apps/angular-app/"
        "src/app/app.component.ts"
    )

    assert (
        reviewed_frameworks[
            angular_file
        ]
        == "angular"
    )

    assert (
        reviewed_projects[
            angular_file
        ]
        == "apps/angular-app"
    )

    # --------------------------------------------------
    # React
    # --------------------------------------------------

    react_file = (
        "apps/react-app/src/App.tsx"
    )

    assert (
        reviewed_frameworks[
            react_file
        ]
        == "react"
    )

    assert (
        reviewed_projects[
            react_file
        ]
        == "apps/react-app"
    )

    # --------------------------------------------------
    # Express
    # --------------------------------------------------

    express_file = (
        "services/api/src/server.ts"
    )

    assert (
        reviewed_frameworks[
            express_file
        ]
        == "express"
    )

    assert (
        reviewed_projects[
            express_file
        ]
        == "services/api"
    )

    # --------------------------------------------------
    # Critical isolation guarantee
    # --------------------------------------------------

    assert (
        reviewed_frameworks[
            react_file
        ]
        != reviewed_frameworks[
            angular_file
        ]
    )

    assert (
        reviewed_frameworks[
            express_file
        ]
        != reviewed_frameworks[
            angular_file
        ]
    )