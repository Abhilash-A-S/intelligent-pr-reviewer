import re

from pr_reviewer.review.models import Finding
from pr_reviewer.review.rules import DEFAULT_RULE_REGISTRY, RuleRegistry


class RootCauseMatcher:
    """
    Technology-agnostic semantic bridge between AI wording and authoritative rules.

    The matcher does not convert arbitrary AI rule IDs into new product rules. It
    only answers a narrower question: "does this AI finding describe the same
    concrete root cause as an already-proven authoritative finding nearby?"

    This lets deterministic/framework/compiler findings remain authoritative even
    when the LLM labels the same defect with a broad semantic category such as
    `duplicate-logic`, `maintainability`, or `logic-error`.
    """

    DEFAULT_LINE_DISTANCE = 5

    # Canonical root-cause concepts. These are intentionally expressed as
    # language-neutral defect semantics or source constructs, not framework names.
    _CONCEPT_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
        "unreachable-code": (
            re.compile(r"\bunreachable\b", re.I),
            re.compile(r"\b(?:never|cannot|can't|will not|won't)\s+(?:be\s+)?execut(?:e|ed)\b", re.I),
            re.compile(r"\bdead\s+code\b", re.I),
            re.compile(r"\bafter\s+(?:a\s+)?(?:return|throw|break|continue)\b", re.I),
        ),
        "loose-equality": (
            re.compile(r"\bloose\s+equal(?:ity)?\b", re.I),
            re.compile(r"\bnon[-\s]?strict\s+(?:equality|comparison)\b", re.I),
            re.compile(r"\bstrict\s+equal(?:ity)?\b", re.I),
            re.compile(r"\btype\s+coercion\b", re.I),
        ),
        "empty-catch-block": (
            re.compile(r"\bempty\s+catch\b", re.I),
            re.compile(r"\bswallow(?:ed|ing)?\s+(?:an?\s+)?(?:error|exception)\b", re.I),
            re.compile(r"\bsilent(?:ly)?\s+(?:ignore|ignored|ignores)\b", re.I),
            re.compile(r"\b(?:error|exception)[-\s]?handling\b", re.I),
            re.compile(r"\b(?:unhandled|caught)\s+exception\b", re.I),
            re.compile(r"\bpass\b", re.I),
        ),
        "jwt-signature-verification-disabled": (
            re.compile(r"\bjwt\b.*\b(?:verif|signature|decode|token|options)\b", re.I),
            re.compile(r"\bverify_signature\b", re.I),
            re.compile(r"\b(?:security|data-validation)\b", re.I),
            re.compile(r"\binsecure\s+jwt\b", re.I),
        ),
        "authorization": (
            re.compile(r"\b(?:authoriz|permission|access\s+control|role|admin)\b", re.I),
            re.compile(r"\b(?:privilege|validate.*role|user.*role|api[-\s]?misuse)\b", re.I),
        ),
        "json-parse-without-error-handling": (
            re.compile(r"\bjson\.parse\b", re.I),
            re.compile(r"\bjson\s+pars(?:e|ing)\b", re.I),
        ),
        "setinterval-without-timer-reference": (
            re.compile(r"\bsetinterval\b", re.I),
            re.compile(r"\bclearinterval\b", re.I),
            re.compile(r"\btimer\s+(?:handle|reference|ref)\b", re.I),
        ),
        "global-event-listener-without-removal": (
            re.compile(r"\baddEventListener\b", re.I),
            re.compile(r"\bremoveEventListener\b", re.I),
            re.compile(r"\bevent\s+listener\b", re.I),
        ),
        "unsafe-inner-html": (
            re.compile(r"\binnerhtml\b", re.I),
            re.compile(r"\bhtml\s+injection\b", re.I),
            re.compile(r"\bdom\s+xss\b", re.I),
        ),
        "hardcoded-secret": (
            re.compile(r"\bhard[-\s]?coded\s+(?:secret|credential|password|token|api\s*key)\b", re.I),
            re.compile(r"\bembedded\s+(?:secret|credential)\b", re.I),
            re.compile(r"\bexposed\s+(?:secret|credential)\b", re.I),
        ),
        "unused-variable": (
            re.compile(r"\bunused\s+(?:variable|value|constant|local)\b", re.I),
            re.compile(r"\bdeclared\s+but\s+never\s+used\b", re.I),
        ),
        "unused-parameter": (
            re.compile(r"\bunused\s+(?:parameter|argument)\b", re.I),
            re.compile(r"\bparameter\b.*\bnever\s+used\b", re.I),
        ),
        "no-console": (
            re.compile(r"\bconsole\.(?:log|debug|info|warn|error)\b", re.I),
            re.compile(r"\bconsole\s+log(?:ging)?\b", re.I),
        ),
        "debugger": (
            re.compile(r"\bdebugger\s+statement\b", re.I),
        ),
        "fetch-status-not-checked": (
            re.compile(r"\bfetch\b.*\b(?:status|ok|response)\b", re.I),
            re.compile(r"\bresponse\.(?:ok|status)\b", re.I),
        ),
        "effect-cleanup": (
            re.compile(r"\beffect\s+cleanup\b", re.I),
            re.compile(r"\buseeffect\b.*\bcleanup\b", re.I),
        ),
        "effect-dependency": (
            re.compile(r"\buseeffect\b.*\bdependenc(?:y|ies)\b", re.I),
            re.compile(r"\bmissing\s+(?:hook|effect)?\s*dependenc(?:y|ies)\b", re.I),
        ),
        "direct-dom-manipulation": (
            re.compile(r"\bdirect\s+dom\b", re.I),
            re.compile(r"\bgetelementbyid\b", re.I),
            re.compile(r"\bqueryselector\b", re.I),
        ),
        "insufficient-test-assertion": (
            re.compile(r"\b(?:weak|insufficient|narrow)\s+(?:test|assertion)\b", re.I),
            re.compile(r"\btest\b.*\b(?:only|accepts?)\b.*\b(?:status|success|result|metadata)\b", re.I),
            re.compile(r"\b(?:does not|doesn't|fails to)\s+(?:verify|assert|validate)\b", re.I),
            re.compile(r"\bassert(?:ion)?\b.*\bincorrect\s+(?:success|behavior|behaviour|result)\b", re.I),
        ),
        "sql-injection": (
            re.compile(r"\bsql\s+injection\b", re.I),
            re.compile(r"\b(?:interpolated|dynamic|concatenated)\s+sql\b", re.I),
        ),
        "path-traversal": (
            re.compile(r"\b(?:path|directory)\s+traversal\b", re.I),
            re.compile(r"\bfile\s+path\b.*\b(?:escape|root|unvalidated)\b", re.I),
        ),
        "unsafe-deserialization": (
            re.compile(r"\bunsafe\s+deserial", re.I),
            re.compile(r"\b(?:pickle|yaml|dill)\.(?:load|loads)\b", re.I),
        ),
        "weak-cryptography": (
            re.compile(r"\b(?:weak|broken|insecure)\s+(?:hash|cryptography|crypto)\b", re.I),
            re.compile(r"\b(?:md5|sha1)\b", re.I),
        ),
        "resource-cleanup": (
            re.compile(r"\b(?:resource|file|session|response)\s+leak\b", re.I),
            re.compile(r"\b(?:unclosed|not closed|without.*clos)\b", re.I),
        ),
        "unowned-background-task": (
            re.compile(r"\b(?:unowned|discarded|fire.and.forget)\s+(?:background\s+)?task\b", re.I),
            re.compile(r"\bcreate_task\b.*\b(?:discard|retain|await|exception)\b", re.I),
        ),
        "exception-detail-exposure": (
            re.compile(r"\b(?:exception|internal error)\s+(?:detail|message|information).*\b(?:expos|return|leak)\b", re.I),
            re.compile(r"\bstr\s*\(\s*(?:error|exception|exc)\s*\)", re.I),
        ),
        "sync-over-async": (
            re.compile(r"\b(?:sync(?:hronous)?[-\s]?over[-\s]?async|blocking.*async|deadlock)\b", re.I),
            re.compile(r"\.(?:result|wait)\b", re.I),
        ),
        "null-forgiving-nullable": (
            re.compile(r"\bnull[-\s]?forgiving\b", re.I),
            re.compile(r"\bnullable\b.*\b(?:suppress|dereferenc|null)\b", re.I),
        ),
        "async-void": (re.compile(r"\basync\s+void\b", re.I),),
        "missing-cancellation-propagation": (
            re.compile(r"\bcancellation\s+token\b.*\b(?:ignore|missing|not\s+(?:pass|forward)|propagat)", re.I),
            re.compile(r"\b(?:shutdown|request)\s+cancellation\b", re.I),
        ),
        "pagination-offset": (re.compile(r"\b(?:page|pagination)\b.*\b(?:offset|off[-\s]?by[-\s]?one|skip)\b", re.I),),
        "predictable-random-token": (re.compile(r"\b(?:predictable|insecure|pseudo.?random)\b.*\b(?:token|code|random)", re.I),),
        "weak-encryption": (re.compile(r"\b(?:ecb|weak encryption|unauthenticated encryption)\b", re.I),),
        "httpclient-lifetime": (re.compile(r"\bhttpclient\b.*\b(?:lifetime|socket|per[-\s]?(?:call|request)|reuse)", re.I),),
        "tenant-isolation": (re.compile(r"\btenant\b.*\b(?:filter|isolation|scope|predicate|leak)", re.I),),
        "ef-tracking-read": (re.compile(r"\b(?:tracking|asnotracking)\b.*\b(?:query|read|entity)", re.I),),
        "n-plus-one-query": (re.compile(r"\bn\s*\+\s*1|n[-\s]?plus[-\s]?one|query.*(?:each|loop)", re.I),),
        "missing-save-changes": (re.compile(r"\b(?:savechanges|persist)\b.*\b(?:missing|never|not|without)", re.I),),
        "unstable-pagination": (re.compile(r"\b(?:pagination|skip|take)\b.*\b(?:order|deterministic|unstable)", re.I),),
        "dbcontext-concurrency": (re.compile(r"\bdbcontext\b.*\b(?:concurr|parallel|thread)", re.I),),
        "cors-misconfiguration": (re.compile(r"\bcors\b.*\b(?:origin|credential|allow)", re.I),),
        "dependency-lifetime": (re.compile(r"\b(?:singleton|hosted service)\b.*\b(?:scoped|dbcontext|lifetime)", re.I),),
        "background-cancellation": (re.compile(r"\b(?:background|worker|loop)\b.*\b(?:cancell|shutdown|stoppingtoken)", re.I),),
        "unrestricted-file-upload": (re.compile(r"\bfile upload\b.*\b(?:unrestricted|size|type|extension|validat)", re.I),),
        "ssrf": (re.compile(r"\bssrf|server[-\s]?side request forgery|user[-\s]?(?:controlled|supplied).*url", re.I),),
        "open-redirect": (re.compile(r"\bopen redirect|unvalidated redirect", re.I),),
        "mass-assignment": (re.compile(r"\bmass assignment|over[-\s]?posting|domain model.*request", re.I),),
        "sensitive-data-logging": (re.compile(r"\b(?:password|credential|secret|sensitive)\b.*\blog", re.I),),
        "missing-endpoint-authorization": (re.compile(r"\bendpoint\b.*\b(?:missing|without|lacks?)\b.*\bauthoriz", re.I),),
        "wildcard-postmessage": (re.compile(r"\bpostmessage\b.*\b(?:wildcard|any origin|target origin)", re.I),),
        "browser-token-storage": (re.compile(r"\b(?:localstorage|script-readable storage)\b.*\b(?:token|session|credential)", re.I),),
    }

    def __init__(self, registry: RuleRegistry | None = None):
        self.registry = registry or DEFAULT_RULE_REGISTRY

    def same_root_cause(
        self,
        ai_finding: Finding,
        authoritative: Finding,
        changed_file_map: dict | None = None,
    ) -> bool:
        canonical = self.registry.resolve(authoritative.rule_id)
        patterns = self._CONCEPT_PATTERNS.get(canonical)
        if not patterns:
            return False

        if ai_finding.file_path != authoritative.file_path:
            ai_text = self._finding_text(ai_finding).lower()
            enclosing = self._enclosing_function_for(authoritative, changed_file_map)
            if enclosing and enclosing.lower() in ai_text:
                if any(pattern.search(ai_text) for pattern in patterns):
                    return True
            return False

        if abs(ai_finding.line_number - authoritative.line_number) > self.DEFAULT_LINE_DISTANCE:
            return False

        text = self._finding_text(ai_finding)
        if not any(pattern.search(text) for pattern in patterns):
            return False

        # Subject-sensitive families must still describe the same named subject
        # when both findings expose one. This prevents adjacent secrets/variables
        # from collapsing merely because their root-cause semantics are alike.
        if canonical in {"hardcoded-secret", "unused-variable", "unused-parameter"}:
            ai_subject = self._subject(ai_finding)
            authoritative_subject = self._subject(authoritative)
            if ai_subject and authoritative_subject and ai_subject != authoritative_subject:
                return False

        return True

    @staticmethod
    def _finding_text(finding: Finding) -> str:
        return " ".join(
            part
            for part in (
                finding.rule_id,
                finding.message,
                finding.issue,
                finding.impact,
                finding.evidence,
                finding.suggestion,
            )
            if part
        )

    @staticmethod
    def _subject(finding: Finding) -> str | None:
        text = RootCauseMatcher._finding_text(finding)
        quoted = re.findall(r"[`'\"]([A-Za-z_$][\w$.-]*)[`'\"]", text)
        return quoted[0].lower() if quoted else None

    @classmethod
    def _enclosing_function_for(
        cls,
        finding: Finding,
        changed_file_map: dict | None = None,
    ) -> str | None:
        if not changed_file_map:
            return None
        cf = changed_file_map.get(finding.file_path)
        if not cf or not getattr(cf, "full_content", None):
            return None
        lines = cf.full_content.splitlines()
        for idx in range(min(finding.line_number - 1, len(lines) - 1), -1, -1):
            m = re.match(r"^\s*(?:async\s+)?def\s+([A-Za-z0-9_]+)", lines[idx])
            if m:
                return m.group(1)
        return None
