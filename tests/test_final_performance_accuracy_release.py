from unittest.mock import Mock

from pr_reviewer.context.models import RepositoryContext
from pr_reviewer.context.file_context import FileContextResolver
from pr_reviewer.detection.project import ProjectContext
from pr_reviewer.llm.batch_planner import ProjectAwareBatchPlanner
from pr_reviewer.llm.llm_reviewer import LLMReviewer
from pr_reviewer.review.finding_validator import FindingValidator
from pr_reviewer.review.models import ChangedFile, ChangedLine, Finding, Severity
from pr_reviewer.review.review_router import ReviewRouter
from pr_reviewer.review.static_analyzer import StaticAnalyzer
from pr_reviewer.review.test_evidence_validator import TestEvidenceValidator


def changed_file(path: str, lines: list[str]) -> ChangedFile:
    return ChangedFile(
        file_path=path,
        status="modified",
        changed_lines=[
            ChangedLine(path, index, content, index)
            for index, content in enumerate(lines, start=1)
        ],
        full_content="\n".join(lines),
    )


def finding(path: str, line: int, rule: str, message: str, suggestion: str = "Fix it.") -> Finding:
    return Finding(path, line, Severity.MEDIUM, rule, message, suggestion)


def test_import_only_barrel_is_context_only_but_real_index_logic_is_reviewed():
    router = ReviewRouter()
    barrel = changed_file("packages/data/src/index.ts", ["export * from './lib/data';"])
    logic = changed_file("packages/data/src/index.ts", ["export function load() { return run(); }"])

    assert router.should_review_with_llm(barrel) is False
    assert router.should_review_with_llm(logic) is True


def test_batch_planner_groups_only_compatible_small_files():
    files = [
        changed_file(f"src/file-{index}.ts", [f"const value{index} = work();"])
        for index in range(5)
    ]
    batches = ProjectAwareBatchPlanner(max_files=4).plan(
        files,
        RepositoryContext(languages={"typescript"}, framework="angular"),
    )

    assert [len(batch.files) for batch in batches] == [4, 1]


def test_batch_mapping_rejects_unknown_files_and_unchanged_lines():
    provider = Mock()
    provider.review_batch.return_value = """{
      "findings": [
        {"file_path":"src/a.ts","line_number":1,"severity":"medium","rule_id":"logic-error","message":"Valid issue."},
        {"file_path":"src/missing.ts","line_number":1,"severity":"medium","rule_id":"logic-error","message":"Wrong file."},
        {"file_path":"src/b.ts","line_number":99,"severity":"medium","rule_id":"logic-error","message":"Wrong line."}
      ]
    }"""
    reviewer = LLMReviewer(provider)
    results = reviewer.review_batch(
        [changed_file("src/a.ts", ["run();"]), changed_file("src/b.ts", ["work();"])],
        RepositoryContext(languages={"typescript"}),
    )

    assert [(item.file_path, item.line_number) for item in results] == [("src/a.ts", 1)]


def test_inline_angular_css_is_not_parsed_as_typescript_parameters():
    source = """@Component({
  styles: [`@media (max-width: 768px) { .card { display: block; } }`]
})
export class CardComponent {}
"""
    file = changed_file("card.component.ts", source.splitlines())
    results = StaticAnalyzer().analyze(file)

    assert not any(item.rule_id == "unused-parameter" and "max" in item.message for item in results)


def test_returned_object_properties_are_not_unreachable():
    source = """function result() {
  return {
    items: [],
  };
}
"""
    results = StaticAnalyzer().analyze(changed_file("result.ts", source.splitlines()))
    assert not any(item.rule_id == "unreachable-code" for item in results)


def test_test_title_cannot_prove_null_safety_issue():
    file = changed_file(
        "app.spec.ts",
        ["it('renders title', () => {", "  expect(true).toBe(true);", "});"],
    )
    result = TestEvidenceValidator().validate(
        finding("app.spec.ts", 1, "null-safety", "The queried element can be null."),
        file,
    )
    assert result.accepted is False


def test_query_selector_is_not_itself_an_xss_sink():
    file = changed_file("app.ts", ["const host = document.querySelector('#app');"])
    result = FindingValidator().validate(
        finding("app.ts", 1, "security", "Direct DOM lookup creates an XSS vulnerability."),
        file,
    )
    assert result.accepted is False


def test_angular_bootstrap_does_not_receive_express_middleware_advice():
    file = changed_file(
        "main.ts",
        ["bootstrapApplication(App, appConfig).catch((err) => console.error(err));"],
    )
    result = FindingValidator().validate(
        finding(
            "main.ts",
            1,
            "error-handling",
            "The error should be passed to Express middleware.",
            "Call next(err).",
        ),
        file,
    )
    assert result.accepted is False


def test_multiline_return_chain_is_not_unreachable():
    source = """function load() {
  return this.http
    .get('/products')
    .pipe(map(value => value));
}
"""
    results = StaticAnalyzer().analyze(changed_file("service.ts", source.splitlines()))
    assert not any(item.rule_id == "unreachable-code" for item in results)


def test_exported_declaration_is_not_locally_unused():
    source = "export const reqHandler = createNodeRequestHandler(app);"
    results = StaticAnalyzer().analyze(changed_file("server.ts", [source]))
    assert not any(item.rule_id == "unused-variable" for item in results)


def test_async_test_finding_requires_exact_async_evidence_line():
    file = changed_file(
        "product-list.spec.ts",
        ["expect(service.load).toHaveBeenCalledWith('all');"],
    )
    result = TestEvidenceValidator().validate(
        finding(
            "product-list.spec.ts",
            1,
            "async-issue",
            "The test may not wait for filtering to finish.",
        ),
        file,
    )
    assert result.accepted is False


def test_file_context_resolves_angular_and_express_inside_same_project():
    project = ProjectContext(
        name="shop",
        root="apps/shop",
        framework="express",
        project_type="backend",
    )
    angular = changed_file(
        "apps/shop/src/app/app.component.ts",
        ["import { Component } from '@angular/core';", "@Component({})", "export class App {}"],
    )
    server = changed_file(
        "apps/shop/src/server.ts",
        ["import express from 'express';", "const app = express();"],
    )
    context = RepositoryContext(
        languages={"typescript"},
        framework="mixed",
        project_type="monorepo",
        projects=[project],
    )
    context.file_contexts = FileContextResolver().resolve_all(
        [angular, server],
        context,
    )

    assert context.resolve_file_context(angular.file_path).framework == "angular"
    assert context.resolve_file_context(server.file_path).framework == "express"

    batches = ProjectAwareBatchPlanner().plan([angular, server], context)
    assert len(batches) == 2


def test_compatible_framework_files_batch_across_nx_projects():
    projects = [
        ProjectContext(name="data", root="packages/data", framework="angular"),
        ProjectContext(name="ui", root="packages/ui", framework="angular"),
    ]
    first = changed_file("packages/data/src/data.ts", ["export const load = () => api();"])
    second = changed_file("packages/ui/src/card.ts", ["export const card = render();"])
    context = RepositoryContext(
        languages={"typescript"},
        framework="angular",
        projects=projects,
    )

    batches = ProjectAwareBatchPlanner().plan([first, second], context)

    assert len(batches) == 1
    assert len(batches[0].files) == 2


def test_large_semantic_file_uses_one_bounded_call():
    file = changed_file(
        "src/large.component.ts",
        [f"const value{index} = calculate({index});" for index in range(340)],
    )

    plan = ProjectAwareBatchPlanner().file_planner.plan(file)

    assert plan.llm_call_count == 1
