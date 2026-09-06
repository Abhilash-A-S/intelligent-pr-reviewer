from pr_reviewer.context.models import RepositoryContext
from pr_reviewer.review.finding_validator import FindingValidator
from pr_reviewer.review.framework_fact_validator import FrameworkFactValidator
from pr_reviewer.review.models import ChangedFile, ChangedLine, Finding, Severity
from pr_reviewer.review.static_analyzer import StaticAnalyzer


def cf(path: str, content: str, line: int = 1) -> ChangedFile:
    return ChangedFile(file_path=path, status="modified", changed_lines=[ChangedLine(path, line, content)], full_content=content)


def finding(path: str, rule: str, message: str, line: int = 1) -> Finding:
    return Finding(path, line, Severity.HIGH, rule, message)


def test_camel_case_api_key_is_detected():
    rules = StaticAnalyzer().analyze(cf("app.ts", "private apiKey = 'sk_live_123456789';"))
    assert "hardcoded-secret" in {x.rule_id for x in rules}


def test_private_unused_field_is_detected():
    rules = StaticAnalyzer().analyze(cf("app.ts", "private unusedValue = 12345;"))
    assert "unused-variable" in {x.rule_id for x in rules}


def test_loose_equality_is_detected():
    rules = StaticAnalyzer().analyze(cf("app.ts", "if (role == 1) return true;"))
    assert "loose-equality" in {x.rule_id for x in rules}


def test_explicit_any_is_detected():
    rules = StaticAnalyzer().analyze(cf("app.ts", "processUser(user: any): any { return user; }"))
    assert "explicit-any" in {x.rule_id for x in rules}


def test_json_parse_is_not_rce_by_itself():
    changed = cf("src/app/app.ts", "return JSON.parse(settings);")
    result = FrameworkFactValidator().validate(
        finding("src/app/app.ts", "unsafe-json-parsing", "JSON.parse allows remote code execution."),
        changed, [changed], RepositoryContext(languages={"typescript"}, framework="angular", project_type="frontend-web")
    )
    assert result.accepted is False


def test_application_config_does_not_require_generic_error_handling():
    content = "import { ApplicationConfig } from '@angular/core';\nexport const appConfig: ApplicationConfig = { providers: [] };"
    changed = cf("src/app/app.config.ts", content)
    result = FrameworkFactValidator().validate(
        finding("src/app/app.config.ts", "error-handling", "ApplicationConfig has no error handling."),
        changed, [changed], RepositoryContext(languages={"typescript"}, framework="angular", project_type="frontend-web")
    )
    assert result.accepted is False


def test_password_strength_behavior_claim_is_rejected_from_plain_html():
    changed = cf("index.html", '<div id="strengthBar"></div>')
    result = FindingValidator().validate(
        finding("index.html", "password-strength-meter", "The password strength meter should be updated based on the password entered."),
        changed,
    )
    assert result.accepted is False
    assert any("HTML alone" in reason for reason in result.reasons)


def test_hardcoded_secret_is_not_rejected_just_because_file_uses_json_parse():
    content = """const apiKey = 'sk_live_123456789';\nreturn JSON.parse(settings);"""
    changed = ChangedFile(
        file_path="src/app/app.ts",
        status="modified",
        changed_lines=[ChangedLine("src/app/app.ts", 1, "const apiKey = 'sk_live_123456789';")],
        full_content=content,
    )
    secret = Finding(
        "src/app/app.ts", 1, Severity.CRITICAL, "hardcoded-secret",
        "A hardcoded API secret is present.",
        "Move the secret to secure configuration to prevent credential exposure and code execution risks.",
    )
    result = FrameworkFactValidator().validate(
        secret, changed, [changed],
        RepositoryContext(languages={"typescript"}, framework="angular", project_type="frontend-web"),
    )
    assert result.accepted is True


def test_existing_password_length_check_rejects_false_missing_validation_claim():
    content = """function validatePassword(password: string) {\n  if (password.length < 8) return false;\n  return true;\n}"""
    changed = ChangedFile(
        file_path="src/auth.ts",
        status="modified",
        changed_lines=[ChangedLine("src/auth.ts", 2, "  if (password.length < 8) return false;")],
        full_content=content,
    )
    result = FrameworkFactValidator().validate(
        finding(
            "src/auth.ts",
            "missing-password-length-validation",
            "The password does not enforce a minimum length.",
            line=2,
        ),
        changed, [changed],
        RepositoryContext(languages={"typescript"}, framework="unknown", project_type="frontend-web"),
    )
    assert result.accepted is False
    assert any("password-length validation" in reason for reason in result.reasons)


def test_hardcoded_token_alias_normalizes_to_secret():
    from pr_reviewer.review.normalizer import FindingNormalizer
    assert FindingNormalizer.normalize_rule_id("hardcoded-token") == "hardcoded-secret"


def test_login_does_not_require_password_strength_validation():
    content = "loginForm.addEventListener('submit', e => e.preventDefault());"
    changed = cf("script.js", content)
    result = FrameworkFactValidator().validate(
        finding("script.js", "password-strength-verification", "Password strength verification is missing for the login form."),
        changed, [changed], RepositoryContext(languages={"javascript"}, framework="unknown", project_type="unknown")
    )
    assert result.accepted is False


def test_existing_strength_logic_rejects_registration_strength_claim():
    content = """const val = regPassword.value;\nif (val.length >= 8) score++;\nif (/[A-Z]/.test(val)) score++;\nif (/[0-9]/.test(val)) score++;\nstrengthText.textContent = 'Strong';"""
    changed = ChangedFile(
        file_path="script.js", status="modified",
        changed_lines=[ChangedLine("script.js", 1, "const val = regPassword.value;")],
        full_content=content,
    )
    result = FrameworkFactValidator().validate(
        finding("script.js", "password-strength-verification", "Password strength verification is missing for the registration form."),
        changed, [changed], RepositoryContext(languages={"javascript"}, framework="unknown", project_type="unknown")
    )
    assert result.accepted is False


def test_multiline_private_token_is_detected_as_secret():
    content = """class UserService {\n  private token =\n    'private_hardcoded_token_123456789';\n}"""
    changed = ChangedFile(
        file_path="review-test.ts", status="modified",
        changed_lines=[
            ChangedLine("review-test.ts", 2, "  private token ="),
            ChangedLine("review-test.ts", 3, "    'private_hardcoded_token_123456789';"),
        ],
        full_content=content,
    )
    rules = StaticAnalyzer().analyze(changed)
    secrets = [item for item in rules if item.rule_id == "hardcoded-secret"]
    assert len(secrets) == 1
    assert secrets[0].line_number == 2
