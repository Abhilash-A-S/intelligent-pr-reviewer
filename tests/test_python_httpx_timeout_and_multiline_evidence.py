from pr_reviewer.context.models import RepositoryContext
from pr_reviewer.llm.prompt import ReviewPromptBuilder
from pr_reviewer.review.models import ChangedFile, ChangedLine
from pr_reviewer.review.static_analyzer import StaticAnalyzer


def python_file(path: str, content: str) -> ChangedFile:
    return ChangedFile(
        file_path=path,
        status="modified",
        language="python",
        full_content=content,
        changed_lines=[
            ChangedLine(path, number, line, number)
            for number, line in enumerate(content.splitlines(), start=1)
        ],
    )


def rules(content: str, path: str = "src/app.py") -> set[str]:
    return {item.rule_id for item in StaticAnalyzer().analyze(python_file(path, content))}


def findings(content: str, path: str = "src/app.py"):
    return StaticAnalyzer().analyze(python_file(path, content))


def test_httpx_default_timeout_is_safe_in_static_analyzer():
    code = """import httpx

async def fetch(client: httpx.AsyncClient):
    response = await client.get("https://example.com/api")
    response.raise_for_status()
    return response.json()
"""
    assert "missing-timeout" not in rules(code)


def test_httpx_explicit_timeout_none_is_flagged():
    code = """import httpx

async def fetch(client: httpx.AsyncClient):
    response = await client.get("https://example.com/api", timeout=None)
    response.raise_for_status()
    return response.json()
"""
    assert "missing-timeout" in rules(code)


def test_httpx_client_init_timeout_none_is_flagged():
    code = """import httpx

async def fetch():
    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.get("https://example.com/api")
        response.raise_for_status()
        return response.json()
"""
    assert "missing-timeout" in rules(code)


def test_multiline_subprocess_shell_anchors_to_shell_kw():
    code = """import subprocess

def run_task(cmd):
    return subprocess.check_output(
        cmd,
        shell=True,
    )
"""
    items = findings(code)
    ci_findings = [f for f in items if f.rule_id == "command-injection"]
    assert len(ci_findings) == 1
    # Line 6 is "        shell=True,"
    assert ci_findings[0].line_number == 6


def test_multiline_jwt_verify_signature_anchors_to_options():
    code = """import jwt

def get_token(token):
    return jwt.decode(
        token,
        options={"verify_signature": False},
    )
"""
    items = findings(code)
    jwt_findings = [f for f in items if f.rule_id == "jwt-signature-verification-disabled"]
    assert len(jwt_findings) == 1
    # Line 6 is '        options={"verify_signature": False},'
    assert jwt_findings[0].line_number == 6


def test_token_aware_batch_prompt_allocates_adaptive_budget():
    file1 = python_file("src/a.py", "x = 1\n" * 50)
    file2 = python_file("src/b.py", "y = 2\n" * 50)
    context = RepositoryContext(languages={"python"}, framework="fastapi")
    prompt = ReviewPromptBuilder.build_batch([file1, file2], context)
    assert "FILE: src/a.py" in prompt
    assert "FILE: src/b.py" in prompt
    assert "BOUNDED SOURCE CONTEXT:" in prompt
