from dataclasses import replace

from pr_reviewer.context.builder import RepositoryContextBuilder
from pr_reviewer.llm.batch_planner import ProjectAwareBatchPlanner
from pr_reviewer.review.framework_fact_validator import FrameworkFactValidator
from pr_reviewer.review.models import ChangedFile, ChangedLine, Finding, FindingSource, Severity
from pr_reviewer.review.processor import FindingProcessor
from pr_reviewer.review.rules import DEFAULT_RULE_REGISTRY
from pr_reviewer.review.semantic_evidence_validator import UniversalSemanticEvidenceValidator
from pr_reviewer.review.static_analyzer import StaticAnalyzer


def py(path: str, content: str) -> ChangedFile:
    return ChangedFile(
        file_path=path,
        status="added",
        language="python",
        full_content=content,
        changed_lines=[
            ChangedLine(path, number, line, number)
            for number, line in enumerate(content.splitlines(), 1)
        ],
    )


def rules(changed: ChangedFile) -> list[str]:
    return [finding.rule_id for finding in StaticAnalyzer().analyze(changed)]


def test_python_security_sinks_are_deterministic():
    changed = py(
        "src/security_cases.py",
        '''def sql(cursor, name):
    cursor.execute(f"SELECT * FROM users WHERE name='{name}'")
def path(root, filename):
    return (root / filename).read_text()
def binary(payload):
    return pickle.loads(payload)
def yaml_data(payload):
    return yaml.load(payload, Loader=yaml.Loader)
def token(email):
    return hashlib.md5(email.encode()).hexdigest()
''',
    )

    assert rules(changed) == [
        "sql-injection",
        "path-traversal",
        "unsafe-deserialization",
        "unsafe-deserialization",
        "weak-cryptography",
    ]


def test_python_safe_security_controls_are_clean():
    changed = py(
        "src/safe_controls.py",
        '''def sql(session, email):
    return session.execute(text("SELECT * FROM users WHERE email=:email"), {"email": email})
def path(root, filename):
    candidate = (root.resolve() / filename).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise ValueError("outside root")
    return candidate.read_text()
def yaml_data(payload):
    return yaml.safe_load(payload)
def token():
    return secrets.token_urlsafe(32)
''',
    )

    assert StaticAnalyzer().analyze(changed) == []


def test_python_resource_and_task_lifecycle_with_clean_controls():
    defective = py(
        "src/async_cases.py",
        '''async def fetch():
    client = aiohttp.ClientSession()
    response = await client.get("https://example.com")
    return await response.json()
async def audit(event):
    asyncio.create_task(send(event))
def report(path):
    handle = path.open("r")
    return handle.read()
''',
    )
    safe = py(
        "src/safe_async.py",
        '''async def fetch():
    async with aiohttp.ClientSession() as client:
        async with client.get("https://example.com") as response:
            return await response.json()
async def audit(event):
    task = asyncio.create_task(send(event))
    await task
def report(path):
    with path.open("r") as handle:
        return handle.read()
''',
    )

    assert rules(defective) == ["resource-cleanup", "resource-cleanup", "unowned-background-task"]
    assert StaticAnalyzer().analyze(safe) == []


def test_python_api_and_database_flow_findings():
    changed = py(
        "src/service.py",
        '''def update(item_id, data):
    session.execute(text("UPDATE items SET name=:name"), {"name": data["name"]})
    return True
def endpoint(payload):
    try:
        process(payload)
    except Exception as error:
        return jsonify({"error": str(error)}), 500
def delete_user(request):
    if not request.headers.get("X-Role"):
        return {"error": "unauthorized"}, 401
    return {"success": True}
''',
    )

    assert rules(changed) == [
        "incorrect-result-handling",
        "exception-detail-exposure",
        "authorization",
    ]


def test_new_universal_security_rules_are_registered_and_ai_admissible():
    for rule in (
        "sql-injection", "path-traversal", "unsafe-deserialization",
        "weak-cryptography", "unowned-background-task", "exception-detail-exposure",
    ):
        definition = DEFAULT_RULE_REGISTRY.get(rule)
        assert definition is not None
        assert definition.ai_policy.value == "validate"


def test_ai_sql_injection_has_exact_evidence_contract():
    changed = py(
        "src/flask_app.py",
        'def search(name):\n    return connection.execute(f"SELECT * FROM users WHERE name={name}")',
    )
    finding = Finding(
        file_path=changed.file_path,
        line_number=2,
        severity=Severity.HIGH,
        rule_id="sql-injection",
        message="Interpolated SQL reaches the execution sink.",
        source=FindingSource.LLM,
    )

    assert UniversalSemanticEvidenceValidator().validate(finding, changed).accepted is True


def test_python_explicit_validation_exception_rejects_false_ai_claim():
    changed = py(
        "src/flask_app.py",
        'def validate(payload):\n    raise ValueError(f"invalid payload: {payload}")',
    )
    finding = Finding(
        file_path=changed.file_path,
        line_number=2,
        severity=Severity.MEDIUM,
        rule_id="data-validation",
        message="The payload is not validated.",
        source=FindingSource.LLM,
    )

    result = FrameworkFactValidator().validate(finding, changed, [changed], None)
    assert result.accepted is False
    assert "explicit validation exception" in result.reasons[0]


def test_mixed_python_framework_context_is_backend_and_batches_compatibly():
    files = [
        py("src/pkg/django_service.py", "from django.db import connection"),
        py("src/pkg/flask_app.py", "from flask import Flask\napp = Flask(__name__)"),
        py("src/pkg/plain.py", "def value():\n    return 1"),
        py("tests/test_flask_app.py", "from pkg.flask_app import app"),
    ]
    context = RepositoryContextBuilder().build(files)

    assert context.framework == "mixed"
    assert context.project_type == "backend"
    assert context.resolve_file_context(files[0].file_path).framework == "django"
    assert context.resolve_file_context(files[1].file_path).framework == "flask"
    assert context.resolve_file_context(files[2].file_path).framework == "python"
    assert context.resolve_file_context(files[3].file_path).framework == "flask"
    assert len(ProjectAwareBatchPlanner().plan(files, context)) == 1


def test_all_new_authoritative_findings_survive_processing_without_ai_filters():
    changed = py(
        "src/security.py",
        'def restore(payload):\n    return pickle.loads(payload)',
    )
    static = [replace(item, source=FindingSource.STATIC) for item in StaticAnalyzer().analyze(changed)]
    final = FindingProcessor().process(static, [changed])
    assert [item.rule_id for item in final] == ["unsafe-deserialization"]
