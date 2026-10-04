from pr_reviewer.review.models import Severity
from pr_reviewer.review.rules.models import (
    AIPolicy,
    RuleDefinition,
    RuleOwner,
)
from pr_reviewer.review.rules.registry import RuleRegistry


# The catalog is intentionally technology-agnostic. Capabilities describe the
# evidence needed; adapters decide whether a given file/project can provide it.
DEFAULT_RULE_DEFINITIONS = (
    RuleDefinition(
        "hardcoded-secret", "security", RuleOwner.STATIC, AIPolicy.BLOCK,
        minimum_severity=Severity.CRITICAL,
        aliases=(
            "security-101", "password-hardcoded", "hardcoded-password",
            "hardcoded-credential", "hardcoded-credentials", "embedded-secret",
            "embedded-credential", "security-hardcoded-secret", "exposed-secret",
            "credential-hardcoded", "hardcoded-token", "hardcoded-api-key",
            "hardcoded-jwt-secret",
        ),
        capabilities=("secret-detection",),
    ),
    RuleDefinition(
        "unused-variable", "code-quality", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.LOW,
        aliases=(
            "unused-var", "unused-constant", "unused-variable-declaration",
            "unused-local-variable", "unused-local", "unnecessary-variable",
            "unnecessary-constant", "unnecessary-variable-declaration",
            "dead-variable", "dead-local-variable", "unused-code",
        ),
        capabilities=("symbol-analysis",),
    ),
    RuleDefinition(
        "unused-import", "code-quality", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.LOW,
        aliases=("unused-import-statement", "unnecessary-import", "redundant-import"),
        capabilities=("symbol-analysis",),
    ),
    RuleDefinition(
        "unused-parameter", "code-quality", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.LOW,
        aliases=(
            "unused-argument", "unused-function-argument",
            "unused-function-parameter", "unused-method-parameter",
        ),
        capabilities=("symbol-analysis",),
    ),
    RuleDefinition(
        "no-console", "code-quality", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.LOW,
        aliases=(
            "console-log", "console-statement", "console-log-statement",
            "console-logging", "debug-console", "console-debug",
        ),
        capabilities=("debug-artifact-analysis",),
    ),
    RuleDefinition(
        "debugger", "code-quality", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        aliases=("debug-statement", "debugger-statement"),
        capabilities=("debug-artifact-analysis",),
    ),
    RuleDefinition(
        "debug-print", "code-quality", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.LOW,
        aliases=("print-statement", "debug-print-statement"),
        capabilities=("debug-artifact-analysis",),
    ),
    RuleDefinition(
        "mutable-default-argument", "correctness", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        aliases=("mutable-default", "shared-mutable-default"),
        capabilities=("syntax-tree-analysis",),
    ),
    RuleDefinition(
        "identity-comparison-literal", "correctness", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        aliases=("literal-identity-comparison", "incorrect-identity-comparison"),
        capabilities=("operator-analysis",),
    ),
    RuleDefinition(
        "bare-except", "reliability", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        aliases=("bare-exception-handler", "catch-all-exception"),
        capabilities=("exception-flow-analysis",),
    ),
    RuleDefinition(
        "sql-injection", "security", RuleOwner.AI, AIPolicy.VALIDATE,
        aliases=("unsafe-sql", "dynamic-sql-injection"),
        capabilities=("security-sink-analysis", "data-flow-analysis"),
    ),
    RuleDefinition(
        "path-traversal", "security", RuleOwner.AI, AIPolicy.VALIDATE,
        aliases=("directory-traversal", "unsafe-file-path"),
        capabilities=("path-boundary-analysis", "data-flow-analysis"),
    ),
    RuleDefinition(
        "unsafe-deserialization", "security", RuleOwner.AI, AIPolicy.VALIDATE,
        aliases=("insecure-deserialization", "unsafe-pickle", "unsafe-yaml-load"),
        capabilities=("deserialization-analysis", "security-sink-analysis"),
    ),
    RuleDefinition(
        "weak-cryptography", "security", RuleOwner.AI, AIPolicy.VALIDATE,
        aliases=("weak-hash", "insecure-hash", "weak-crypto"),
        max_severity=Severity.HIGH,
        capabilities=("cryptography-analysis",),
    ),
    RuleDefinition(
        "unowned-background-task", "resource-lifecycle", RuleOwner.AI, AIPolicy.VALIDATE,
        aliases=("fire-and-forget-task", "discarded-background-task"),
        max_severity=Severity.MEDIUM,
        capabilities=("async-analysis", "resource-lifecycle-analysis"),
    ),
    RuleDefinition(
        "exception-detail-exposure", "security", RuleOwner.AI, AIPolicy.VALIDATE,
        aliases=("exception-information-disclosure", "internal-error-exposure"),
        max_severity=Severity.MEDIUM,
        capabilities=("exception-flow-analysis", "api-boundary-analysis"),
    ),
    RuleDefinition(
        "explicit-any", "type-safety", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.LOW,
        aliases=("typescript-explicit-any", "no-explicit-any"),
        capabilities=("type-analysis",),
    ),
    RuleDefinition(
        "typescript-null-dereference", "type-safety", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        aliases=("typescript-possibly-null",),
        capabilities=("type-analysis", "nullability-analysis"),
    ),
    RuleDefinition(
        "typescript-optional-property", "type-safety", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        capabilities=("type-analysis", "nullability-analysis"),
    ),
    RuleDefinition(
        "typescript-optional-operand", "type-safety", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        capabilities=("type-analysis",),
    ),
    RuleDefinition(
        "typescript-possibly-undefined-result", "correctness", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        capabilities=("type-analysis", "control-flow-analysis"),
    ),
    RuleDefinition(
        "typescript-use-before-assignment", "correctness", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        capabilities=("type-analysis", "control-flow-analysis"),
    ),
    RuleDefinition(
        "unsafe-type-assertion", "type-safety", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        capabilities=("type-analysis", "data-validation"),
    ),
    RuleDefinition(
        "unsafe-indexed-access", "type-safety", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        capabilities=("type-analysis",),
    ),
    RuleDefinition(
        "broad-function-type", "type-safety", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        capabilities=("type-analysis",),
    ),
    RuleDefinition(
        "non-error-throw", "reliability", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        capabilities=("exception-flow-analysis",),
    ),
    RuleDefinition(
        "unobserved-promise-rejection", "reliability", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        capabilities=("async-analysis",),
    ),
    RuleDefinition(
        "timer-without-cleanup", "resource-lifecycle", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        capabilities=("resource-lifecycle-analysis",),
    ),
    RuleDefinition(
        "unvalidated-external-data", "type-safety", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        capabilities=("type-analysis", "data-validation", "api-boundary-analysis"),
    ),
    RuleDefinition(
        "jwt-signature-verification-disabled", "security", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.HIGH,
        capabilities=("authentication-analysis", "security-analysis"),
    ),
    RuleDefinition(
        "untrusted-identity-header", "security", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.HIGH,
        capabilities=("authentication-analysis", "authorization-flow-analysis"),
    ),
    RuleDefinition(
        "http-status-not-checked", "reliability", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        capabilities=("api-pattern-analysis",),
    ),
    RuleDefinition(
        "response-contract-mismatch", "correctness", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        capabilities=("api-boundary-analysis", "type-analysis"),
    ),
    RuleDefinition(
        "sequential-await-in-loop", "performance", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        capabilities=("async-analysis", "performance-analysis"),
    ),
    RuleDefinition(
        "observer-without-cleanup", "resource-lifecycle", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        capabilities=("resource-lifecycle-analysis",),
    ),
    RuleDefinition(
        "prototype-pollution", "security", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.HIGH,
        capabilities=("security-analysis", "data-flow-analysis"),
    ),
    RuleDefinition(
        "always-truthy-condition", "correctness", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        capabilities=("control-flow-analysis",),
    ),
    RuleDefinition(
        "non-exhaustive-union", "correctness", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        capabilities=("type-analysis", "control-flow-analysis"),
    ),
    RuleDefinition(
        "loose-equality", "correctness", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        aliases=(
            "javascript-loose-equality", "typescript-loose-equality",
            "non-strict-equality", "non-strict-comparison", "eqeqeq",
            "loose-equality-check", "loose-equality-operator",
            "equality-comparison", "comparison-operator",
        ),
        capabilities=("operator-analysis",),
    ),
    RuleDefinition(
        "unreachable-code", "correctness", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        aliases=("dead-code-after-return", "unreachable-statement"),
        capabilities=("control-flow-analysis",),
    ),
    RuleDefinition(
        "empty-catch-block", "reliability", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        aliases=("no-empty-catch", "empty-catch", "swallowed-exception"),
        capabilities=("exception-flow-analysis",),
    ),
    RuleDefinition(
        "json-parse-without-error-handling", "reliability",
        RuleOwner.STATIC, AIPolicy.BLOCK, max_severity=Severity.MEDIUM,
        aliases=(
            "json-parse", "json-parse-error", "json-parsing-error",
            "unsafe-json-parse", "unsafe-json-parsing", "insecure-json-parse",
            "insecure-json-parsing", "json-parse-security", "json-security",
            "json-injection",
        ),
        capabilities=("api-pattern-analysis",),
    ),
    RuleDefinition(
        "setinterval-without-timer-reference", "resource-lifecycle",
        RuleOwner.STATIC, AIPolicy.BLOCK, max_severity=Severity.MEDIUM,
        aliases=(
            "setinterval", "set-interval",
            "setinterval-without-retaining-timer-reference",
            "set-interval-without-retaining-timer-reference",
            "setinterval-without-referencing-timer",
            "set-interval-without-referencing-timer", "unhandled-interval",
            "interval-not-cleared", "timer-not-cleared",
        ),
        capabilities=("resource-lifecycle-analysis",),
    ),
    RuleDefinition(
        "rxjs-subscription-without-cleanup", "resource-lifecycle",
        RuleOwner.STATIC, AIPolicy.BLOCK, max_severity=Severity.MEDIUM,
        aliases=(
            "angular-subscription-without-cleanup",
            "rxjs-missing-unsubscribe",
            "rxjs-subscription-leak",
        ),
        capabilities=("framework-lifecycle-analysis", "resource-lifecycle-analysis"),
    ),
    RuleDefinition(
        "global-event-listener-without-removal", "resource-lifecycle",
        RuleOwner.STATIC, AIPolicy.BLOCK, max_severity=Severity.MEDIUM,
        aliases=(
            "global-event-listener", "global-listener", "window-event-listener",
            "unhandled-event-listener", "event-listener-without-removal",
        ),
        capabilities=("resource-lifecycle-analysis",),
    ),
    RuleDefinition(
        "unsafe-inner-html", "security", RuleOwner.STATIC, AIPolicy.BLOCK,
        aliases=("xss-vulnerability", "dom-xss", "unsafe-html", "unsanitized-html"),
        capabilities=("security-sink-analysis",),
    ),
    RuleDefinition(
        "effect-cleanup", "resource-lifecycle", RuleOwner.FRAMEWORK, AIPolicy.BLOCK,
        aliases=(
            "missing-effect-cleanup", "missing-cleanup", "react-use-effect-cleanup",
            "react-missing-effect-cleanup", "react-effect-cleanup", "hook-cleanup",
        ),
        capabilities=("framework-lifecycle-analysis",),
    ),
    RuleDefinition(
        "effect-dependency", "correctness", RuleOwner.FRAMEWORK, AIPolicy.BLOCK,
        aliases=(
            "react-use-effect-dependency", "react-hooks-missing-dependency",
            "react-empty-dependency-array", "missing-hook-dependency", "hook-dependency",
        ),
        capabilities=("framework-lifecycle-analysis",),
    ),
    RuleDefinition(
        "direct-dom-manipulation", "framework-correctness",
        RuleOwner.FRAMEWORK, AIPolicy.BLOCK,
        aliases=("react-direct-dom-manipulation", "direct-dom-access"),
        capabilities=("framework-dom-analysis",),
    ),
    RuleDefinition(
        "fetch-status-not-checked", "reliability", RuleOwner.STATIC, AIPolicy.BLOCK,
        aliases=("missing-response-status-check", "fetch-response-status"),
        capabilities=("api-pattern-analysis",),
    ),
    # Universal semantic categories. These are the categories the LLM may
    # create after source/framework/test evidence validation.
    RuleDefinition(
        "logic-error", "correctness", RuleOwner.AI, AIPolicy.VALIDATE,
        capabilities=("semantic-reasoning",),
    ),
    RuleDefinition(
        "error-handling", "reliability", RuleOwner.AI, AIPolicy.VALIDATE,
        max_severity=Severity.MEDIUM,
        aliases=(
            "missing-error-handling", "unhandled-error", "unhandled-exception",
            "missing-exception-handling", "exception-not-handled",
            "fetch-error-handling", "missing-fetch-error-handling",
        ),
        capabilities=("semantic-reasoning",),
    ),
    RuleDefinition(
        "async-issue", "reliability", RuleOwner.AI, AIPolicy.VALIDATE,
        aliases=(
            "unhandled-promise", "missing-await", "missing-async-await",
            "async-await-issue", "async-error",
        ),
        capabilities=("async-analysis", "semantic-reasoning"),
    ),
    RuleDefinition(
        "null-safety", "correctness", RuleOwner.AI, AIPolicy.VALIDATE,
        aliases=(
            "null-reference", "null-dereference", "possible-null-reference",
            "none-dereference", "nil-dereference",
        ),
        capabilities=("nullability-analysis", "semantic-reasoning"),
    ),
    RuleDefinition(
        "resource-cleanup", "resource-lifecycle", RuleOwner.AI, AIPolicy.VALIDATE,
        aliases=("resource-leak", "missing-resource-cleanup", "resource-not-closed", "unclosed-resource"),
        capabilities=("resource-lifecycle-analysis", "semantic-reasoning"),
    ),
    RuleDefinition(
        "subscription-cleanup", "resource-lifecycle", RuleOwner.AI, AIPolicy.VALIDATE,
        aliases=("missing-unsubscribe", "subscription-leak", "unclosed-subscription"),
        capabilities=("framework-lifecycle-analysis", "semantic-reasoning"),
    ),
    RuleDefinition(
        "listener-cleanup", "resource-lifecycle", RuleOwner.AI, AIPolicy.VALIDATE,
        aliases=("event-listener-leak", "missing-listener-cleanup"),
        capabilities=("resource-lifecycle-analysis", "semantic-reasoning"),
    ),
    RuleDefinition(
        "api-misuse", "correctness", RuleOwner.AI, AIPolicy.VALIDATE,
        capabilities=("semantic-reasoning",),
    ),
    RuleDefinition(
        "data-validation", "correctness", RuleOwner.AI, AIPolicy.VALIDATE,
        capabilities=("semantic-reasoning",),
    ),
    RuleDefinition(
        "concurrency", "reliability", RuleOwner.AI, AIPolicy.VALIDATE,
        capabilities=("concurrency-analysis", "semantic-reasoning"),
    ),
    RuleDefinition(
        "security", "security", RuleOwner.AI, AIPolicy.VALIDATE,
        capabilities=("semantic-reasoning",),
    ),
    RuleDefinition(
        "duplicate-logic", "maintainability", RuleOwner.AI, AIPolicy.VALIDATE,
        max_severity=Severity.MEDIUM,
        aliases=("duplicated-code", "duplicate-code", "duplicated-logic", "code-duplication"),
        capabilities=("semantic-reasoning",),
    ),
    RuleDefinition(
        "performance", "performance", RuleOwner.AI, AIPolicy.VALIDATE,
        max_severity=Severity.MEDIUM,
        aliases=("performance-issue", "performance-problem", "performance-concern"),
        capabilities=("semantic-reasoning",),
    ),
    RuleDefinition(
        "maintainability", "maintainability", RuleOwner.AI, AIPolicy.VALIDATE,
        max_severity=Severity.MEDIUM,
        aliases=("code-maintainability", "maintainability-issue", "maintainability-problem"),
        capabilities=("semantic-reasoning",),
    ),
    RuleDefinition(
        "accessibility", "accessibility", RuleOwner.AI, AIPolicy.VALIDATE,
        max_severity=Severity.MEDIUM,
        aliases=("accessibility-issue", "accessibility-problem", "a11y", "a11y-issue"),
        capabilities=("semantic-reasoning",),
    ),
    RuleDefinition(
        "return-value-handling", "correctness", RuleOwner.AI, AIPolicy.VALIDATE,
        max_severity=Severity.LOW,
        capabilities=("semantic-reasoning",),
    ),
    RuleDefinition(
        "incorrect-result-handling", "correctness", RuleOwner.AI, AIPolicy.VALIDATE,
        capabilities=("semantic-reasoning", "return-flow-analysis"),
    ),
    RuleDefinition(
        "async-blocking-operation", "reliability", RuleOwner.AI, AIPolicy.VALIDATE,
        max_severity=Severity.MEDIUM,
        capabilities=("async-analysis", "call-analysis"),
    ),
    RuleDefinition(
        "missing-timeout", "reliability", RuleOwner.AI, AIPolicy.VALIDATE,
        max_severity=Severity.MEDIUM,
        capabilities=("external-call-analysis",),
    ),
    RuleDefinition(
        "authorization", "security", RuleOwner.AI, AIPolicy.VALIDATE,
        capabilities=("authorization-flow-analysis",),
    ),
    RuleDefinition(
        "command-injection", "security", RuleOwner.AI, AIPolicy.VALIDATE,
        capabilities=("security-sink-analysis",),
    ),
    RuleDefinition(
        "unsafe-code-execution", "security", RuleOwner.AI, AIPolicy.VALIDATE,
        capabilities=("security-sink-analysis",),
    ),
    RuleDefinition(
        "cache-consistency", "correctness", RuleOwner.AI, AIPolicy.VALIDATE,
        max_severity=Severity.MEDIUM,
        capabilities=("state-analysis", "semantic-reasoning"),
    ),
    RuleDefinition(
        "insufficient-test-assertion", "test-quality", RuleOwner.AI, AIPolicy.VALIDATE,
        max_severity=Severity.LOW,
        capabilities=("test-evidence-analysis",),
    ),
    RuleDefinition(
        "sync-over-async", "reliability", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        aliases=("blocking-on-task", "task-result-blocking", "task-wait-blocking"),
        capabilities=("async-analysis", "call-analysis"),
    ),
    RuleDefinition(
        "null-forgiving-nullable", "correctness", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        aliases=("unsafe-null-forgiving", "suppressed-nullability"),
        capabilities=("nullability-analysis",),
    ),
    RuleDefinition(
        "async-void", "reliability", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        aliases=("async-void-method",), capabilities=("async-analysis",),
    ),
    RuleDefinition(
        "missing-cancellation-propagation", "reliability", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        aliases=("cancellation-token-not-propagated", "ignored-cancellation-token"),
        capabilities=("async-analysis", "call-analysis"),
    ),
    RuleDefinition(
        "pagination-offset", "correctness", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        aliases=("incorrect-pagination-offset", "one-based-pagination"),
        capabilities=("data-flow-analysis",),
    ),
    RuleDefinition(
        "predictable-random-token", "security", RuleOwner.STATIC, AIPolicy.BLOCK,
        minimum_severity=Severity.HIGH,
        aliases=("insecure-random", "weak-random-token", "weak-randomness", "predictable-token"),
        capabilities=("cryptography-analysis",),
    ),
    RuleDefinition(
        "weak-encryption", "security", RuleOwner.STATIC, AIPolicy.BLOCK,
        minimum_severity=Severity.HIGH,
        aliases=("ecb-mode", "insecure-cipher-mode", "aes-ecb"),
        capabilities=("cryptography-analysis",),
    ),
    RuleDefinition(
        "httpclient-lifetime", "resource-lifecycle", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        aliases=("httpclient-per-request", "new-httpclient-per-call"),
        capabilities=("resource-lifecycle-analysis",),
    ),
    RuleDefinition(
        "tenant-isolation", "security", RuleOwner.STATIC, AIPolicy.BLOCK,
        minimum_severity=Severity.HIGH,
        aliases=("missing-tenant-filter", "cross-tenant-data-access"),
        capabilities=("data-flow-analysis", "authorization-flow-analysis"),
    ),
    RuleDefinition(
        "ef-tracking-read", "performance", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.LOW,
        aliases=("missing-as-no-tracking", "unnecessary-entity-tracking"),
        capabilities=("api-pattern-analysis",),
    ),
    RuleDefinition(
        "n-plus-one-query", "performance", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        aliases=("n+1-query", "query-in-loop"),
        capabilities=("data-flow-analysis", "performance-analysis"),
    ),
    RuleDefinition(
        "missing-save-changes", "correctness", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        aliases=("missing-savechanges", "entity-not-persisted"),
        capabilities=("state-analysis", "call-analysis"),
    ),
    RuleDefinition(
        "unstable-pagination", "correctness", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        aliases=("pagination-without-order", "unordered-pagination"),
        capabilities=("data-flow-analysis",),
    ),
    RuleDefinition(
        "dbcontext-concurrency", "reliability", RuleOwner.STATIC, AIPolicy.BLOCK,
        minimum_severity=Severity.HIGH,
        aliases=("concurrent-dbcontext-use", "parallel-dbcontext-operations"),
        capabilities=("concurrency-analysis", "resource-lifecycle-analysis"),
    ),
    RuleDefinition(
        "singleton-mutable-state", "security", RuleOwner.STATIC, AIPolicy.BLOCK,
        minimum_severity=Severity.HIGH,
        aliases=("mutable-singleton-state", "singleton-request-state"),
        capabilities=("state-analysis", "dependency-lifetime-analysis"),
    ),
    RuleDefinition(
        "cors-misconfiguration", "security", RuleOwner.STATIC, AIPolicy.BLOCK,
        minimum_severity=Severity.HIGH,
        aliases=("permissive-cors", "cors-any-origin-credentials"),
        capabilities=("configuration-analysis", "security-sink-analysis"),
    ),
    RuleDefinition(
        "developer-exception-page", "security", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        aliases=("developer-errors-production", "detailed-errors-enabled"),
        capabilities=("configuration-analysis",),
    ),
    RuleDefinition(
        "dependency-lifetime", "reliability", RuleOwner.STATIC, AIPolicy.BLOCK,
        minimum_severity=Severity.HIGH,
        aliases=("captive-dependency", "scoped-service-in-singleton"),
        capabilities=("dependency-lifetime-analysis",),
    ),
    RuleDefinition(
        "background-cancellation", "resource-lifecycle", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        aliases=("background-service-ignores-stop", "infinite-background-loop"),
        capabilities=("async-analysis", "resource-lifecycle-analysis"),
    ),
    RuleDefinition(
        "unrestricted-file-upload", "security", RuleOwner.STATIC, AIPolicy.BLOCK,
        minimum_severity=Severity.HIGH,
        aliases=("unsafe-file-upload", "missing-upload-validation", "upload-security"),
        capabilities=("api-boundary-analysis", "security-sink-analysis"),
    ),
    RuleDefinition(
        "missing-input-validation", "reliability", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        aliases=("request-validation-missing", "missing-validation", "unvalidated-request-body"),
        capabilities=("api-boundary-analysis", "data-validation"),
    ),
    RuleDefinition(
        "sequential-io-operations", "performance", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        aliases=("sequential-network-calls", "blocking-sequential-http", "unparallelized-outbound-calls"),
        capabilities=("async-analysis", "performance-analysis"),
    ),
    RuleDefinition(
        "ssrf", "security", RuleOwner.STATIC, AIPolicy.BLOCK,
        minimum_severity=Severity.HIGH,
        aliases=("server-side-request-forgery", "unsafe-outbound-url"),
        capabilities=("security-sink-analysis", "data-flow-analysis"),
    ),
    RuleDefinition(
        "open-redirect", "security", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.MEDIUM,
        aliases=("unsafe-redirect", "unvalidated-redirect"),
        capabilities=("api-boundary-analysis", "data-flow-analysis"),
    ),
    RuleDefinition(
        "mass-assignment", "security", RuleOwner.STATIC, AIPolicy.BLOCK,
        minimum_severity=Severity.HIGH,
        aliases=("over-posting", "overposting", "unsafe-model-binding"),
        capabilities=("api-boundary-analysis", "data-flow-analysis"),
    ),
    RuleDefinition(
        "sensitive-data-logging", "security", RuleOwner.STATIC, AIPolicy.BLOCK,
        minimum_severity=Severity.HIGH,
        aliases=("password-logging", "credential-logging", "secret-logging", "log-sensitive-data"),
        capabilities=("security-sink-analysis",),
    ),
    RuleDefinition(
        "missing-endpoint-authorization", "security", RuleOwner.STATIC, AIPolicy.BLOCK,
        minimum_severity=Severity.HIGH,
        aliases=("missing-authorize", "unprotected-endpoint", "missing-authorization"),
        capabilities=("authorization-flow-analysis",),
    ),
    RuleDefinition(
        "insecure-cookie", "security", RuleOwner.STATIC, AIPolicy.BLOCK,
        minimum_severity=Severity.HIGH,
        aliases=("missing-httponly-cookie", "missing-secure-cookie", "insecure-cookie-header"),
        capabilities=("security-sink-analysis", "configuration-analysis"),
    ),
    RuleDefinition(
        "debug-logging", "security", RuleOwner.STATIC, AIPolicy.BLOCK,
        max_severity=Severity.LOW,
        aliases=("production-debug-logging", "verbose-production-logging"),
        capabilities=("configuration-analysis",),
    ),
    RuleDefinition(
        "wildcard-postmessage", "security", RuleOwner.STATIC, AIPolicy.BLOCK,
        minimum_severity=Severity.HIGH,
        aliases=("postmessage-wildcard-origin", "unsafe-postmessage-origin"),
        capabilities=("browser-security-analysis", "data-flow-analysis"),
    ),
    RuleDefinition(
        "browser-token-storage", "security", RuleOwner.STATIC, AIPolicy.BLOCK,
        minimum_severity=Severity.HIGH,
        aliases=("localstorage-token", "script-readable-token-storage"),
        capabilities=("browser-security-analysis", "data-flow-analysis"),
    ),
)


DEFAULT_RULE_REGISTRY = RuleRegistry(DEFAULT_RULE_DEFINITIONS)
