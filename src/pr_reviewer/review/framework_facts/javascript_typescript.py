import re
from pr_reviewer.context.models import RepositoryContext
from pr_reviewer.review.models import ChangedFile, Finding


class JavaScriptTypeScriptFactValidator:
    """Reject deterministic JS/TS hallucinations and severity-inflating claims."""

    EXTENSIONS = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")

    def validate(self, finding: Finding, changed_file: ChangedFile,
                 changed_files: list[ChangedFile],
                 repository_context: RepositoryContext | None) -> list[str]:
        path = changed_file.file_path.lower()
        if not path.endswith(self.EXTENSIONS):
            return []
        text = " ".join(x for x in (finding.rule_id, finding.message, finding.suggestion or "") if x).lower()
        content = changed_file.full_content or ""
        reasons: list[str] = []

        # JSON.parse can throw on malformed input, but JSON parsing by itself does
        # not execute JavaScript. Reject RCE/code-execution claims unless the file
        # contains an actual execution primitive.
        json_parse_claim = (
            "json.parse" in text
            or "json-pars" in finding.rule_id.lower()
            or "json_parse" in finding.rule_id.lower()
        )
        if (json_parse_claim and "json.parse" in content.lower()
                and any(term in text for term in (
                    "remote code execution", "code execution",
                    "execute arbitrary", "rce"
                ))):
            if not re.search(r"\b(?:eval|Function)\s*\(", content):
                reasons.append("JSON.parse parses data and does not itself execute code; no execution primitive is present.")

        # Reject claims that password-length validation is missing when the
        # reviewed source already contains an explicit length comparison.
        # This is deliberately narrow: it only disproves missing-length claims
        # and does not infer that the application's overall password policy is
        # sufficient.
        password_length_claim = (
            "password" in text
            and any(term in text for term in (
                "length", "minimum", "min length", "min-length",
                "too short", "short password"
            ))
            and any(term in text for term in (
                "missing", "does not", "doesn't", "no check",
                "not validate", "not enforce", "without"
            ))
        )
        password_length_check = re.search(
            r"\b(?:password|pwd|pass)\w*\s*\.\s*length\s*"
            r"(?:<=|>=|<|>|===|==)\s*\d+",
            content,
            flags=re.IGNORECASE,
        ) or re.search(
            r"\d+\s*(?:<=|>=|<|>)\s*"
            r"(?:password|pwd|pass)\w*\s*\.\s*length\b",
            content,
            flags=re.IGNORECASE,
        )
        if password_length_claim and password_length_check:
            reasons.append(
                "The source already contains an explicit password-length validation check."
            )

        # Password-strength requirements belong to password creation/change
        # flows, not ordinary login credential verification. Reject an LLM
        # finding that demands a strength meter/check for a login form.
        password_strength_claim = (
            "password" in text
            and "strength" in text
            and any(term in text for term in (
                "missing", "verification", "validate", "validation",
                "meter", "check", "should"
            ))
        )
        login_strength_claim = (
            password_strength_claim
            and "login" in text
            and not any(term in text for term in (
                "registration", "register", "sign up", "signup",
                "create account", "change password", "reset password"
            ))
        )
        if login_strength_claim:
            reasons.append(
                "Password-strength validation is not a requirement for an ordinary login form."
            )

        # Reject a missing registration/password-strength claim when the file
        # already contains concrete strength-scoring evidence. We require at
        # least two independent signals so a single incidental length check
        # does not prove a complete strength meter.
        if password_strength_claim and not login_strength_claim:
            strength_signals = 0
            lowered = content.lower()
            if re.search(r"\.length\s*(?:>=|>|<=|<)\s*\d+", content):
                strength_signals += 1
            if "[a-z]" in lowered or "[a-z]" in lowered:
                strength_signals += 1
            if re.search(r"\[0-9\]|\\d", content):
                strength_signals += 1
            if any(token in lowered for token in (
                "strengthbar", "strengthtext", "password strength",
                "weak", "medium", "strong"
            )):
                strength_signals += 1
            if strength_signals >= 2:
                reasons.append(
                    "The source already contains concrete password-strength validation logic."
                )

        # A fallback/default port is a normal server configuration pattern.
        if ("port" in text and any(term in text for term in ("environment", "hardcoded", "config"))
                and re.search(r"process\.env\.PORT\s*(?:\|\||\?\?)\s*\d+", content)):
            reasons.append("The server already uses process.env.PORT with a conventional numeric fallback.")

        return reasons
