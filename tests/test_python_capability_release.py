from pr_reviewer.review.file_classifier import FileCategory, FileClassifier
from pr_reviewer.review.framework_fact_validator import FrameworkFactValidator
from pr_reviewer.review.models import ChangedFile, ChangedLine, Finding, FindingSource, Severity
from pr_reviewer.review.processor import FindingProcessor
from pr_reviewer.review.professionalizer import FindingProfessionalizer
from pr_reviewer.review.semantic_routing import AdaptiveSemanticRouter, ReviewDepth
from pr_reviewer.review.static_analyzer import StaticAnalyzer


def python_file(path: str, content: str) -> ChangedFile:
    lines = content.splitlines()
    return ChangedFile(
        file_path=path,
        status="modified",
        language="python",
        full_content=content,
        changed_lines=[
            ChangedLine(path, number, line, number)
            for number, line in enumerate(lines, start=1)
        ],
    )


def ai(path: str, line: int, rule: str, message: str) -> Finding:
    return Finding(
        file_path=path,
        line_number=line,
        severity=Severity.MEDIUM,
        rule_id=rule,
        message=message,
        source=FindingSource.LLM,
    )


def test_python_ast_capability_detects_high_confidence_fixture_defects():
    changed = python_file(
        "src/application.py",
        '''api_secret: str = "production-secret-123"
def append_item(item, items=[]):
    items.append(item)
    return items
def compare(value):
    return value is "admin"
def parse(value):
    try:
        return int(value)
    except:
        pass
async def delayed():
    time.sleep(1)
def execute(command):
    return subprocess.check_output(command, shell=True)
def dynamic(expression):
    return eval(expression)
def debug(value):
    print(value)
def converted_success():
    try:
        raise RuntimeError()
    except RuntimeError:
        return {"success": True}
def require_admin(x_role):
    if not x_role:
        raise PermissionError()
    return True
''',
    )

    rules = {finding.rule_id for finding in StaticAnalyzer().analyze(changed)}

    assert {
        "hardcoded-secret",
        "mutable-default-argument",
        "identity-comparison-literal",
        "bare-except",
        "async-blocking-operation",
        "command-injection",
        "unsafe-code-execution",
        "debug-print",
        "incorrect-result-handling",
        "authorization",
    } <= rules


def test_python_ast_capability_keeps_clean_controls_clean():
    changed = python_file(
        "tests/test_clean.py",
        '''from pydantic import Field
def create(items=None):
    values = [] if items is None else items
    return values
async def delayed():
    await asyncio.sleep(0)
def compare(value):
    return value == "admin"
def require_admin(x_role):
    if x_role != "admin":
        raise PermissionError()
    return True
def expected_failure():
    with pytest.raises(ValueError):
        raise ValueError()
''',
    )

    assert StaticAnalyzer().analyze(changed) == []


def test_httpx_default_timeout_claim_is_rejected_but_disabled_timeout_is_not():
    default = python_file(
        "src/client.py",
        'async with httpx.AsyncClient() as client:\n    response = await client.get("https://example.com")',
    )
    disabled = python_file(
        "src/client.py",
        'async with httpx.AsyncClient(timeout=None) as client:\n    response = await client.get("https://example.com")',
    )
    finding = ai(default.file_path, 2, "missing-timeout", "The external request has no timeout.")
    validator = FrameworkFactValidator()

    rejected = validator.validate(finding, default, [default], None)
    accepted = validator.validate(finding, disabled, [disabled], None)

    assert rejected.accepted is False
    assert any("finite default timeout" in reason for reason in rejected.reasons)
    assert accepted.accepted is True


def test_status_only_test_finding_survives_and_gets_precise_professional_wording():
    changed = python_file(
        "tests/test_routes.py",
        "def test_route():\n    response = client.get('/products')\n    assert response.status_code == 200",
    )
    finding = ai(
        changed.file_path,
        3,
        "weak-test",
        "This assertion does not validate the returned response behavior.",
    )

    processed = FindingProcessor().process([finding], [changed])
    assert len(processed) == 1
    enriched = FindingProfessionalizer.enrich(processed[0], changed)
    assert enriched.rule_id == "insufficient-test-assertion"
    assert enriched.category == "test-quality"
    assert "response status" in enriched.issue.lower()
    assert "response body" in enriched.suggestion.lower()


def test_python_metadata_and_lock_files_do_not_consume_semantic_review_calls():
    classifier = FileClassifier()

    for path in ("pyproject.toml", ".python-version", "requirements.txt", "setup.cfg"):
        result = classifier.classify(path)
        assert result.category == FileCategory.PROJECT_CONFIGURATION
        assert result.reviewable is False

    lock = classifier.classify("uv.lock")
    assert lock.category == FileCategory.LOCK_FILE
    assert lock.reviewable is False


def test_python_semantic_static_patterns_find_production_root_causes():
    changed = python_file(
        "src/service.py",
        '''class Service:
    def get_required(self, item_id: int) -> Item:
        return self.repository.get(item_id)  # type: ignore[return-value]
    def update(self, item_id: int, data: Update) -> bool:
        self.repository.update(item_id, data)
        return True
    def list_page(self, page: int, page_size: int):
        start = page * page_size
        return self.items[start:start + page_size]
    def search(self, query: str, category: str | None = None):
        cache_key = query.lower()
        if cache_key in self._cache:
            return self._cache[cache_key]
        result = [item for item in self.items if category is None or item.category == category]
        self._cache[cache_key] = result
        return result
''',
    )

    rules = {finding.rule_id for finding in StaticAnalyzer().analyze(changed)}
    assert {"null-safety", "incorrect-result-handling", "logic-error", "cache-consistency"} <= rules


def test_typed_identity_comparison_is_detected_without_flagging_none_identity():
    changed = python_file(
        "src/repository.py",
        '''def get(product_id: int):
    for product in products:
        if product.id is product_id:
            return product
    if product is None:
        return None
''',
    )

    findings = StaticAnalyzer().analyze(changed)
    identity = [finding for finding in findings if finding.rule_id == "identity-comparison-literal"]
    assert [finding.line_number for finding in identity] == [3]


def test_python_weak_tests_are_deterministic_and_clean_controls_remain_clean():
    changed = python_file(
        "tests/test_service.py",
        '''def test_status_only():
    response = client.get("/items")
    assert response.status_code == 200
def test_first_page(service):
    page = service.list_page(page=1, page_size=10)
    assert page.page == 1
def test_update_missing(service):
    assert service.update(999, {}) is True
def test_complete_response():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
def test_clean_exception():
    with pytest.raises(ValueError):
        raise ValueError()
''',
    )

    weak = [
        finding for finding in StaticAnalyzer().analyze(changed)
        if finding.rule_id == "insufficient-test-assertion"
    ]
    assert [finding.line_number for finding in weak] == [3, 6, 8]


def test_bare_silent_exception_is_one_root_cause():
    changed = python_file(
        "src/repository.py",
        '''def delete(item):
    try:
        remove(item)
    except:
        pass
''',
    )

    findings = StaticAnalyzer().analyze(changed)
    exception_rules = {
        finding.rule_id for finding in findings
        if finding.rule_id in {"bare-except", "empty-catch-block"}
    }
    assert exception_rules == {"bare-except"}


def test_docstring_only_python_module_is_value_gated():
    changed = python_file("src/package/__init__.py", '"""Package documentation."""')
    retained, skipped = AdaptiveSemanticRouter().partition([changed], [], ReviewDepth.STANDARD)
    assert retained == []
    assert len(skipped) == 1
    assert "docstring-only" in skipped[0].reason


def test_authoritative_nullable_finding_is_not_rejected_as_speculative():
    changed = python_file(
        "src/service.py",
        "def get_required(item_id: int) -> Item:\n    return repository.get(item_id)  # type: ignore[return-value]",
    )
    static = StaticAnalyzer().analyze(changed)
    static = [
        Finding(**{**finding.__dict__, "source": FindingSource.STATIC})
        for finding in static
    ]

    processed = FindingProcessor().process(static, [changed])

    assert [finding.rule_id for finding in processed] == ["null-safety"]


def test_authoritative_test_rule_is_stable_and_ai_duplicate_is_suppressed():
    changed = python_file(
        "tests/test_service.py",
        "def test_update_missing(service):\n    assert service.update(999, {}) is True",
    )
    static = StaticAnalyzer().analyze(changed)[0]
    static.source = FindingSource.STATIC
    duplicate_ai = ai(
        changed.file_path,
        2,
        "logic-error",
        "The test accepts the incorrect success behavior for a missing record.",
    )

    processed = FindingProcessor().process([static, duplicate_ai], [changed])

    assert len(processed) == 1
    assert processed[0].source is FindingSource.STATIC
    assert processed[0].rule_id == "insufficient-test-assertion"
    assert processed[0].category == "test-quality"


def test_authoritative_pagination_test_rule_is_not_reclassified_by_message():
    changed = python_file(
        "tests/test_service.py",
        "def test_first_page(service):\n    page = service.list_page(1, 10)\n    assert page.page == 1",
    )
    static = StaticAnalyzer().analyze(changed)[0]
    static.source = FindingSource.STATIC

    processed = FindingProcessor().process([static], [changed])

    assert len(processed) == 1
    assert processed[0].rule_id == "insufficient-test-assertion"
    assert processed[0].category == "test-quality"
