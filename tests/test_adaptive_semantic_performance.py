from unittest.mock import Mock, patch

from pr_reviewer.context.models import RepositoryContext
from pr_reviewer.llm.ollama import OllamaProvider
from pr_reviewer.llm.batch_planner import ProjectAwareBatchPlanner
from pr_reviewer.main import build_parser
from pr_reviewer.review.models import ChangedFile, ChangedLine, Finding, Severity
from pr_reviewer.review.semantic_routing import AdaptiveSemanticRouter, ReviewDepth


def file(path: str, lines: list[str]) -> ChangedFile:
    return ChangedFile(
        file_path=path,
        status="modified",
        changed_lines=[
            ChangedLine(path, index, content, index)
            for index, content in enumerate(lines, start=1)
        ],
        full_content="\n".join(lines),
    )


def finding(path: str, line: int) -> Finding:
    return Finding(
        file_path=path,
        line_number=line,
        severity=Severity.MEDIUM,
        rule_id="no-console",
        message="Debug output.",
    )


def test_standard_skips_simple_styles_and_setup_but_keeps_business_logic():
    styles = file("src/app.css", [".card { color: red; }"])
    setup = file("src/test-setup.ts", ["import 'zone.js/testing';"])
    service = file(
        "src/payment.service.ts",
        ["return await this.http.post('/payment', request);"],
    )

    retained, skipped = AdaptiveSemanticRouter().partition(
        [styles, setup, service], [], ReviewDepth.STANDARD
    )

    assert retained == [service]
    assert {item.file.file_path for item in skipped} == {
        "src/app.css",
        "src/test-setup.ts",
    }


def test_deep_preserves_every_normally_reviewable_file():
    styles = file("src/app.css", [".card { color: red; }"])
    setup = file("src/test-setup.ts", ["import 'zone.js/testing';"])

    retained, skipped = AdaptiveSemanticRouter().partition(
        [styles, setup], [], ReviewDepth.DEEP
    )

    assert retained == [styles, setup]
    assert skipped == []


def test_standard_skips_layout_only_styles_but_keeps_external_resource_css():
    layout = file(
        "src/auth.css",
        [".toast { position: fixed; z-index: 10; }", ".hidden { display: none; }"],
    )
    external = file(
        "src/theme.css",
        [".hero { background-image: url(https://cdn.example.test/hero.png); }"],
    )

    retained, skipped = AdaptiveSemanticRouter().partition(
        [layout, external], [], ReviewDepth.STANDARD
    )

    assert retained == [external]
    assert [item.file for item in skipped] == [layout]


def test_standard_can_skip_deterministically_saturated_trivial_file():
    trivial = file(
        "src/debug.ts",
        ["console.log('one');", "console.log('two');"],
    )

    retained, skipped = AdaptiveSemanticRouter().partition(
        [trivial],
        [finding("src/debug.ts", 1), finding("src/debug.ts", 2)],
        ReviewDepth.STANDARD,
    )

    assert retained == []
    assert "deterministic" in skipped[0].reason


def test_cli_defaults_to_standard_and_accepts_fast_or_deep():
    parser = build_parser()
    standard = parser.parse_args(["--repository", "a/b", "--pull-number", "1"])
    fast = parser.parse_args([
        "--repository", "a/b", "--pull-number", "1", "--review-depth", "fast"
    ])
    deep = parser.parse_args([
        "--repository", "a/b", "--pull-number", "1", "--review-depth", "deep"
    ])

    assert standard.review_depth == "standard"
    assert fast.review_depth == "fast"
    assert deep.review_depth == "deep"


def test_ollama_records_native_token_and_timing_metrics():
    with patch("pr_reviewer.llm.ollama.httpx.Client") as client_class:
        client = Mock()
        client_class.return_value = client
        response = Mock()
        response.json.return_value = {
            "response": '{"findings": []}',
            "prompt_eval_count": 120,
            "eval_count": 30,
            "prompt_eval_duration": 2_000_000_000,
            "eval_duration": 3_000_000_000,
        }
        client.post.return_value = response
        provider = OllamaProvider()
        changed = file("src/service.ts", ["return await load();"])

        provider.review(changed, RepositoryContext(languages={"typescript"}))

    metric = provider.call_metrics()[0]
    assert metric.files == ("src/service.ts",)
    assert metric.prompt_tokens == 120
    assert metric.generated_tokens == 30
    assert metric.prompt_eval_seconds == 2.0
    assert metric.generation_seconds == 3.0
    assert metric.raw_findings == 0


def test_same_framework_source_and_test_share_batch_with_per_file_strategy():
    source = file("src/orders.service.ts", ["return await loadOrders();"])
    test = file("src/orders.service.spec.ts", ["expect(loadOrders).toHaveBeenCalled();"])

    batches = ProjectAwareBatchPlanner().plan(
        [source, test],
        RepositoryContext(languages={"typescript"}, framework="angular"),
    )

    assert len(batches) == 1
    assert batches[0].files == (source, test)
