from dataclasses import replace

from pr_reviewer.review.models import ChangedFile, Finding
from pr_reviewer.review.rules import DEFAULT_RULE_REGISTRY


class FindingProfessionalizer:
    """Enrich final findings for professional developer-facing presentation.

    The review engine remains technology-agnostic. This layer derives human-facing
    metadata from the canonical rule registry and concrete changed-line evidence.
    """

    RULE_IMPACTS = {
        "hardcoded-secret": "Exposed credentials can be copied from source control and used to access protected systems or data.",
        "unused-variable": "Dead declarations add noise and can hide stale or incomplete logic.",
        "unused-import": "Unused imports increase noise and can make dependencies harder to understand.",
        "unused-parameter": "Unused parameters make the API contract misleading and may indicate incomplete implementation.",
        "no-console": "Debug logging can leak internal details and add unnecessary production noise.",
        "debugger": "A debugger statement can interrupt normal execution when developer tools are attached.",
        "explicit-any": "Using 'any' bypasses compile-time type safety and can allow invalid values to propagate unnoticed.",
        "loose-equality": "Implicit type coercion can make comparisons behave differently from what the surrounding logic expects.",
        "unreachable-code": "The affected code can never execute, which usually indicates dead logic or an incorrect control-flow path.",
        "empty-catch-block": "The failure is silently ignored, so callers may continue without knowing the operation failed.",
        "json-parse-without-error-handling": "Invalid JSON can throw at runtime and unexpectedly interrupt the current operation.",
        "setinterval-without-timer-reference": "Without retaining the timer handle, the interval cannot be reliably stopped and may keep work running after it is no longer needed.",
        "global-event-listener-without-removal": "The listener can remain active beyond its intended lifetime, causing duplicate handlers, memory retention, or stale behavior.",
        "unsafe-inner-html": "If untrusted content reaches this sink, it can be interpreted as HTML and may enable script injection.",
        "effect-cleanup": "Resources created by the effect can remain active after the component lifecycle changes, causing stale work or leaks.",
        "effect-dependency": "The effect may use stale values and fail to rerun when one of its actual dependencies changes.",
        "direct-dom-manipulation": "Direct DOM mutation can bypass the framework rendering model and produce state/UI inconsistencies.",
        "fetch-status-not-checked": "HTTP error responses may be treated as successful application responses and propagate invalid state.",
        "mutable-default-argument": "The same mutable object is reused across calls, so state can leak between otherwise independent requests.",
        "identity-comparison-literal": "Identity is implementation-dependent for ordinary values and can make a valid value compare unexpectedly.",
        "bare-except": "Catching every exception can hide shutdown signals and unrelated failures that the code cannot safely recover from.",
        "async-blocking-operation": "Blocking an async execution thread delays unrelated requests and reduces throughput under concurrency.",
        "incorrect-result-handling": "Callers can receive a successful result even though the requested operation failed.",
        "insufficient-test-assertion": "The test can pass while the response or domain behavior is incorrect, reducing regression protection.",
        "command-injection": "Attackers can execute arbitrary operating-system commands under the application process account.",
        "upload-security": "Unrestricted uploads can consume storage or introduce executable and malicious content.",
        "missing-input-validation": "Unvalidated request payloads can propagate invalid state or trigger runtime failures in downstream logic.",
        "sql-injection": "Attackers may alter the executed query to read or modify data outside the intended operation.",
        "path-traversal": "A crafted path can escape the configured directory and expose unintended files.",
        "unsafe-deserialization": "A crafted payload can construct unexpected objects and may execute attacker-controlled behavior.",
        "weak-cryptography": "Broken hash primitives do not provide suitable security guarantees for tokens or credentials.",
        "resource-cleanup": "Unclosed resources can exhaust file descriptors, sockets, or connection pools under sustained load.",
        "unowned-background-task": "Failures can become unobserved and work may outlive the request or shutdown lifecycle.",
        "exception-detail-exposure": "Internal exception details can disclose implementation data useful to an attacker.",
        "sync-over-async": "Blocking on asynchronous work can exhaust request threads or deadlock under a synchronization context.",
        "null-forgiving-nullable": "Suppressing nullability hides a real missing-value path that can fail at runtime.",
        "async-void": "Callers cannot await completion or reliably observe exceptions from an async void method.",
        "missing-cancellation-propagation": "Work can continue after the request or application shutdown has been cancelled, wasting resources and delaying termination.",
        "pagination-offset": "The requested page can skip or duplicate records because its index is translated incorrectly.",
        "predictable-random-token": "An attacker may predict verification codes or tokens generated by a non-cryptographic random source.",
        "weak-encryption": "ECB mode preserves plaintext patterns and does not provide authenticated encryption.",
        "httpclient-lifetime": "Repeated HttpClient construction can churn connections and contribute to socket exhaustion.",
        "tenant-isolation": "Records belonging to another tenant can cross the application's authorization boundary.",
        "ef-tracking-read": "Tracking read-only entities adds avoidable memory and change-tracking overhead.",
        "n-plus-one-query": "Database round trips grow with the number of returned records and can severely degrade request latency.",
        "missing-save-changes": "The method can report completion while the intended database mutation was never persisted.",
        "unstable-pagination": "Without stable ordering, records can be duplicated or omitted between pages.",
        "dbcontext-concurrency": "DbContext does not support parallel operations and may throw or corrupt unit-of-work behavior.",
        "singleton-mutable-state": "Request or tenant data can leak between users when stored in shared singleton state.",
        "cors-misconfiguration": "An attacker-controlled origin may issue credentialed cross-origin requests as the signed-in user.",
        "developer-exception-page": "Detailed exceptions can expose stack traces, paths, queries, and internal implementation data.",
        "dependency-lifetime": "A long-lived service can retain a disposed scoped dependency or reuse request state across operations.",
        "background-cancellation": "The hosted service may prevent graceful shutdown and continue work after cancellation.",
        "unrestricted-file-upload": "Unrestricted uploads can consume storage or introduce executable and malicious content.",
        "ssrf": "Attackers may make the server access internal services, cloud metadata endpoints, or restricted networks.",
        "open-redirect": "Attackers can redirect trusted-site users to a malicious destination.",
        "jwt-signature-verification-disabled": "Forged tokens can be accepted as authenticated credentials when their signatures are not verified.",
        "untrusted-identity-header": "A caller can impersonate another identity or privilege level by supplying a trusted-looking header.",
        "http-status-not-checked": "Error responses may be processed as valid dependency data and corrupt downstream behavior.",
        "response-contract-mismatch": "The endpoint can fail response validation or return a payload that does not satisfy its published API contract.",
        "unvalidated-external-data": "Unexpected dependency data can propagate into application logic and cause incorrect or unsafe behavior.",
        "mass-assignment": "Callers may set privileged or server-owned fields that were not intended to be editable.",
        "sensitive-data-logging": "Credentials written to logs can be exposed to operators, log processors, or compromised monitoring systems.",
        "wildcard-postmessage": "A wildcard destination can disclose cross-window data to an untrusted origin.",
        "browser-token-storage": "Script-readable token storage allows any successful script injection to steal the session credential.",
        "missing-endpoint-authorization": "Unauthenticated or unprivileged callers may invoke a state-changing administrative operation.",
        "debug-logging": "Verbose production logs can disclose internal and request data while increasing log volume.",
    }

    CATEGORY_IMPACTS = {
        "security": "This change can weaken the security boundary or expose sensitive behavior.",
        "correctness": "This can produce incorrect behavior for a valid execution path.",
        "framework-correctness": "This can conflict with the framework lifecycle or rendering model and produce inconsistent behavior.",
        "reliability": "This can cause failures to be missed, mishandled, or surfaced unpredictably at runtime.",
        "resource-lifecycle": "This can leave resources active beyond their intended lifetime and create leaks or duplicate work.",
        "performance": "This can increase unnecessary work or resource usage on an affected execution path.",
        "maintainability": "This makes the changed code harder to understand, evolve, or safely modify.",
        "code-quality": "This adds avoidable noise or ambiguity that makes the changed code harder to maintain.",
        "type-safety": "This weakens static guarantees and increases the chance of invalid values reaching runtime logic.",
        "testing": "This can reduce confidence that the changed behavior is correctly covered by automated tests.",
        "test-quality": "This can reduce confidence that the changed behavior is correctly covered by automated tests.",
    }

    @classmethod
    def enrich(
        cls,
        finding: Finding,
        changed_file: ChangedFile | None,
    ) -> Finding:
        definition = DEFAULT_RULE_REGISTRY.get(finding.rule_id)
        category = (
            definition.category
            if definition is not None
            else finding.category or "general"
        )

        evidence = finding.evidence or cls._source_evidence(
            finding=finding,
            changed_file=changed_file,
        )

        impact = finding.impact or cls.RULE_IMPACTS.get(
            finding.rule_id,
            cls.CATEGORY_IMPACTS.get(
                category,
                "This issue can negatively affect the correctness, reliability, or maintainability of the changed code.",
            ),
        )

        issue = finding.issue or finding.message.strip()
        suggestion = finding.suggestion
        if finding.rule_id == "insufficient-test-assertion" and evidence:
            evidence_lower = evidence.lower()
            if "status_code" in evidence_lower or "status code" in evidence_lower:
                issue = "The test verifies only the response status and does not validate the response data or behavior."
                suggestion = "Assert the relevant response body fields or observable domain behavior in addition to the status code."
            elif ".page" in evidence_lower:
                issue = "The pagination test verifies page metadata but does not validate which records were returned."
                suggestion = "Assert the expected page items or record boundaries so skipped and duplicated records fail the test."
            elif " is true" in evidence_lower or "== true" in evidence_lower:
                issue = "The test accepts a successful result without verifying the required failure behavior for this scenario."
                suggestion = "Assert the expected failure result or exception and verify that no invalid state change occurred."
            else:
                issue = "The test asserts only the current result without verifying the expected domain behavior for this scenario."
                suggestion = "Assert the scenario-specific state, error, or returned value that proves the behavior is correct."

        return replace(
            finding,
            category=finding.category or category,
            issue=issue,
            impact=impact,
            evidence=evidence,
            suggestion=suggestion,
        )

    @staticmethod
    def _source_evidence(
        finding: Finding,
        changed_file: ChangedFile | None,
    ) -> str | None:
        if changed_file is None:
            return None

        lines_by_number = {
            line.line_number: line
            for line in changed_file.changed_lines
        }

        primary = lines_by_number.get(finding.line_number)
        if primary is None:
            return None

        primary_code = primary.content.strip()
        if not primary_code:
            return None

        # For construct-level evidence: include up to 2 additional consecutive
        # changed lines that continue the same expression (line ends with a
        # continuation character).
        CONTINUATION_ENDINGS = ("(", ",", "\\", "->", ":", "=", "+", "-")

        evidence_parts = [f"Changed line {finding.line_number}: {primary_code}"]
        current_line_num = finding.line_number
        primary_stripped = primary_code.rstrip()

        for _ in range(2):
            # Only extend if this line clearly continues on the next.
            is_continuation = any(
                primary_stripped.endswith(token)
                for token in CONTINUATION_ENDINGS
            )
            if not is_continuation:
                break
            next_line = lines_by_number.get(current_line_num + 1)
            if next_line is None:
                break
            next_code = next_line.content.strip()
            if not next_code:
                break
            evidence_parts.append(f"  line {current_line_num + 1}: {next_code}")
            current_line_num += 1
            primary_stripped = next_code.rstrip()

        return "\n".join(evidence_parts)
