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


def test_pagination_distinguishes_zero_and_one_based_offsets():
    unsafe = "def page(page, page_size):\n    return items[page * page_size:(page + 1) * page_size]"
    safe = "def page(page, page_size):\n    offset = (page - 1) * page_size\n    return items[offset:offset + page_size]"

    assert "logic-error" in rules(unsafe)
    assert "logic-error" not in rules(safe)


def test_fastapi_identity_and_jwt_verification_are_grounded():
    unsafe = '''def get_current_user(x_user: str = Header()):
    return x_user
def decode_token(token):
    return jwt.decode(token, options={"verify_signature": False})
def require_admin(user):
    if not user.get("role"):
        raise HTTPException(status_code=403)
'''
    safe = '''def get_current_user(authorization: str = Header()):
    token = authorization.removeprefix("Bearer ")
    return jwt.decode(token, SECRET, algorithms=["HS256"])["sub"]
def require_admin(user):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403)
'''

    assert {"untrusted-identity-header", "jwt-signature-verification-disabled", "authorization"} <= rules(unsafe)
    assert not ({"untrusted-identity-header", "jwt-signature-verification-disabled", "authorization"} & rules(safe))


def test_http_client_contracts_and_safe_controls():
    unsafe = '''async def fetch_user(client, user_id):
    response = await client.get(f"https://api/users/{user_id}")
    return response.json()
'''
    safe = '''async def fetch_user(client, user_id):
    response = await client.get(f"https://api/users/{user_id}", timeout=5)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("invalid payload")
    return payload
'''

    assert {"missing-timeout", "http-status-not-checked", "unvalidated-external-data"} <= rules(unsafe)
    assert not ({"missing-timeout", "http-status-not-checked", "unvalidated-external-data"} & rules(safe))


def test_async_batching_and_failure_result_controls():
    unsafe = '''async def load_all(client, ids):
    results = []
    for item_id in ids:
        results.append(await client.get(str(item_id)))
    return results
def save(item):
    try:
        repository.save(item)
    except RuntimeError:
        pass
    return True
'''
    safe = '''async def load_all(client, ids):
    return await asyncio.gather(*(client.get(str(item_id)) for item_id in ids))
def save(item):
    try:
        repository.save(item)
    except RuntimeError:
        return False
    return True
'''

    assert {"sequential-await-in-loop", "incorrect-result-handling"} <= rules(unsafe)
    assert not ({"sequential-await-in-loop", "incorrect-result-handling"} & rules(safe))


def test_upload_redirect_logging_and_mass_assignment_controls():
    unsafe = '''async def upload(file: UploadFile):
    return Path("uploads") / file.filename
def redirect(next_url: str):
    return RedirectResponse(next_url)
def update_user(user, updates):
    user.update(updates)
def inspect(request):
    print(request.headers["authorization"])
'''
    safe = '''async def upload(file: UploadFile):
    if file.content_type not in {"image/png"}:
        raise ValueError("type")
    return Path("uploads") / f"{uuid4()}.png"
def redirect(next_url: str):
    if not next_url.startswith("/"):
        raise ValueError("destination")
    return RedirectResponse(next_url)
def update_user(user, updates):
    user["name"] = updates["name"]
def inspect(request):
    logger.info("request %s", request.method)
'''

    assert {"unrestricted-file-upload", "open-redirect", "mass-assignment", "sensitive-data-logging"} <= rules(unsafe)
    assert not ({"unrestricted-file-upload", "open-redirect", "mass-assignment", "sensitive-data-logging"} & rules(safe))


def test_cross_file_fastapi_response_model_contract():
    models = python_file("src/models.py", '''class UserInput(BaseModel):
    name: str
class UserResponse(BaseModel):
    id: int
    name: str
''')
    unsafe = python_file("src/main.py", '''@app.post("/users", response_model=UserResponse)
def create_user(payload: UserInput):
    return payload.model_dump()
''')
    safe = python_file("src/safe.py", '''@app.post("/users", response_model=UserResponse)
def create_user(payload: UserInput):
    return UserResponse(id=1, name=payload.name)
''')

    unsafe_rules = {item.rule_id for item in StaticAnalyzer().analyze_files([models, unsafe])}
    safe_rules = {item.rule_id for item in StaticAnalyzer().analyze_files([models, safe])}

    assert "response-contract-mismatch" in unsafe_rules
    assert "response-contract-mismatch" not in safe_rules
