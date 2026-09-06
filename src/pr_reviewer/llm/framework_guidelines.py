class FrameworkGuidelines:
    """
    Returns focused framework-specific review instructions.

    Only guidance for the detected framework is included
    in the LLM prompt.

    Unrelated framework guidance is never sent.

    The guidance is intentionally concise and
    evidence-oriented so the LLM does not invent framework
    violations.
    """

    # ======================================================
    # Angular
    # ======================================================

    ANGULAR = """
ANGULAR-SPECIFIC REVIEW

Check for concrete Angular issues involving:

- RxJS subscription lifecycle and cleanup.
- Subscriptions that can leak when components/services
  are destroyed.
- Incorrect or unnecessary manual subscriptions.
- RxJS operator misuse.
- Nested subscriptions where composition is required for
  correctness or lifecycle safety.
- async pipe misuse.
- signal, computed, and effect misuse.
- Incorrect signal updates or derived-state handling.
- Lifecycle-hook misuse.
- Angular dependency-injection misuse.
- ChangeDetectorRef misuse.
- Unnecessary or incorrect change-detection behavior.
- Standalone component/provider configuration mistakes.
- Template/component interaction problems.
- Expensive template expressions when they create a real
  performance problem.
- Missing or incorrect track/trackBy behavior when it
  causes rendering problems.
- Unsafe direct DOM manipulation when Angular APIs are
  required.
- Missing cleanup for timers, listeners, observers,
  subscriptions, and streams.

Report only concrete Angular problems supported by the
available code.
""".strip()

    # ======================================================
    # React
    # ======================================================

    REACT = """
REACT-SPECIFIC REVIEW

Check for concrete React issues involving:

- Incorrect Hook usage.
- useEffect dependency problems.
- Missing effect cleanup.
- Direct state mutation.
- Stale closures.
- Incorrect state synchronization.
- Incorrect memoization.
- Unstable dependencies that cause real behavioral issues.
- Missing or unstable keys in rendered collections.
- Incorrect controlled/uncontrolled component behavior.
- Lifecycle behavior implemented incorrectly through
  effects.
- Resource, listener, observer, and timer cleanup.
- Clearly avoidable rerenders when they create a real
  performance problem.

Do not report stylistic Hook preferences or speculative
rerender concerns.

Report only concrete React problems supported by the code.
""".strip()

    # ======================================================
    # React Native
    # ======================================================

    REACT_NATIVE = """
REACT-NATIVE-SPECIFIC REVIEW

Check for concrete React Native issues involving:

- Incorrect Hook usage.
- useEffect dependency and cleanup problems.
- Direct state mutation.
- Stale closures.
- Native event-listener or subscription cleanup.
- Timer cleanup.
- Navigation lifecycle misuse.
- Platform-specific API misuse.
- FlatList/SectionList problems when they create a real
  correctness or performance issue.
- Missing or unstable list keys.
- Expensive work during rendering when clearly harmful.

Report only concrete React Native problems supported by
the code.
""".strip()

    # ======================================================
    # Vue
    # ======================================================

    VUE = """
VUE-SPECIFIC REVIEW

Check for concrete Vue issues involving:

- Incorrect reactivity usage.
- Direct prop mutation.
- ref/reactive misuse.
- computed misuse.
- Watchers that introduce incorrect side effects.
- Lifecycle-hook misuse.
- Incorrect component communication.
- Template/reactivity problems.
- Missing or unstable keys in rendered collections.
- Cleanup for listeners, timers, observers, subscriptions,
  and other resources.
- Unnecessary reactivity work only when it creates a real
  performance problem.

Report only concrete Vue problems supported by the code.
""".strip()

    # ======================================================
    # Nuxt
    # ======================================================

    NUXT = """
NUXT-SPECIFIC REVIEW

Apply relevant Vue checks and also check for:

- Server/client boundary mistakes.
- SSR-unsafe browser API usage.
- Incorrect data-fetching lifecycle usage.
- Hydration problems when supported by the code.
- Runtime configuration misuse.
- Server-only secrets exposed to client code.
- Incorrect composable/reactivity lifecycle behavior.

Report only concrete Nuxt problems supported by the code.
""".strip()

    # ======================================================
    # Next.js
    # ======================================================

    NEXTJS = """
NEXT.JS-SPECIFIC REVIEW

Apply relevant React checks and also check for:

- Server/client component boundary mistakes.
- Browser-only APIs used in server-side code.
- Server-only secrets exposed to client components.
- Incorrect data-fetching behavior.
- Incorrect caching or revalidation behavior when visible
  in the code.
- Hydration problems when clearly supported.
- Incorrect request/response handling in route handlers.
- Missing cleanup or async error handling in client code.

Report only concrete Next.js problems supported by the
code.
""".strip()

    # ======================================================
    # Node.js
    # ======================================================

    NODE = """
NODE.JS-SPECIFIC REVIEW

Check for concrete Node.js issues involving:

- Async/promise handling.
- Missing error propagation.
- Unhandled promise rejections.
- Incorrect callback/promise interactions.
- Blocking synchronous work in request paths when clearly
  problematic.
- Stream, file-handle, socket, and resource cleanup.
- Unsafe input handling.
- Path traversal.
- Command injection.
- Incorrect process/global resource handling.
- Incorrect environment/configuration usage.

Report only concrete Node.js runtime problems supported by
the code.
""".strip()

    # ======================================================
    # Express
    # ======================================================

    EXPRESS = """
EXPRESS-SPECIFIC REVIEW

Apply relevant Node.js checks and also check for:

- Missing error propagation to Express error middleware.
- Async route handlers that can reject without proper
  handling.
- Middleware ordering problems.
- Missing or incorrect request validation.
- Unsafe use of request parameters, query values, headers,
  or body data.
- Authentication or authorization checks placed after
  protected logic.
- Routes that send multiple responses.
- Missing return/flow control after sending a response.
- Incorrect status-code or response handling when it causes
  behavioral problems.
- Resource cleanup in long-running request handlers.

Report only concrete Express problems supported by the
code.
""".strip()

    # ======================================================
    # NestJS
    # ======================================================

    NESTJS = """
NESTJS-SPECIFIC REVIEW

Check for concrete NestJS issues involving:

- Incorrect dependency-injection usage.
- Missing or incorrect provider registration.
- Module/import/export configuration errors.
- Incorrect provider scope or lifecycle behavior.
- Controller/service responsibility mistakes when they
  create concrete coupling or correctness problems.
- Incorrect async/promise handling.
- Missing error/exception handling.
- Guard misuse.
- Authentication or authorization bypasses.
- Interceptor or pipe misuse.
- DTO/validation problems.
- Resource cleanup in providers.
- Incorrect lifecycle-hook usage.
- Circular dependency problems when supported by the code.

Report only concrete NestJS problems supported by the
available code.
""".strip()

    # ======================================================
    # Spring
    # ======================================================

    SPRING = """
SPRING-SPECIFIC REVIEW

Check for concrete Spring issues involving:

- Dependency-injection misuse.
- Incorrect component/service/repository configuration.
- Incorrect bean lifecycle or scope usage.
- Transaction-boundary mistakes.
- Missing transactional behavior when the code clearly
  requires atomicity.
- Incorrect exception handling or exception translation.
- Controller/service/repository boundary problems when
  they create concrete correctness or coupling issues.
- Security or authorization mistakes.
- Resource cleanup.
- Incorrect concurrency assumptions in singleton beans.
- Incorrect persistence/session lifecycle usage.

Do not report framework style preferences.

Report only concrete Spring problems supported by the
available code.
""".strip()

    # ======================================================
    # Spring Boot
    # ======================================================

    SPRING_BOOT = """
SPRING-BOOT-SPECIFIC REVIEW

Apply relevant Spring checks and also check for:

- Incorrect Spring Boot configuration.
- Dependency-injection misuse.
- Bean lifecycle and scope problems.
- Incorrect controller/service/repository interactions.
- Transaction-boundary problems.
- Missing or incorrect exception handling.
- Incorrect configuration-property usage.
- Secrets embedded in source/configuration.
- Security configuration mistakes.
- Missing authentication or authorization.
- Unsafe request input handling.
- Incorrect REST response/status handling when it creates
  a real behavioral problem.
- Resource cleanup.
- Blocking operations in async/reactive flows when clearly
  incorrect.
- Incorrect Spring Data repository assumptions.
- N+1 or excessive database access only when directly
  supported by the code.

Report only concrete Spring Boot problems supported by the
available code.
""".strip()

    # ======================================================
    # ASP.NET Core
    # ======================================================

    ASPNET_CORE = """
ASP.NET-CORE-SPECIFIC REVIEW

Check for concrete ASP.NET Core issues involving:

- Dependency-injection registration or lifetime mistakes.
- Singleton/scoped/transient lifetime misuse.
- Async/await problems.
- Blocking async code with .Result or .Wait() when it can
  cause runtime/threading problems.
- Nullable-reference and null-handling problems.
- Controller/service boundary mistakes when they create
  concrete correctness or coupling issues.
- Missing request validation.
- Authentication or authorization mistakes.
- Middleware ordering problems.
- Incorrect exception handling.
- Incorrect cancellation-token propagation when relevant.
- Disposable/resource cleanup problems.
- Incorrect Entity Framework Core lifetime/tracking usage.
- N+1 or repeated database operations when directly
  supported by the code.
- Incorrect HTTP response/status handling.

Report only concrete ASP.NET Core problems supported by
the available code.
""".strip()

    # ======================================================
    # Django
    # ======================================================

    DJANGO = """
DJANGO-SPECIFIC REVIEW

Check for concrete Django issues involving:

- ORM query mistakes.
- N+1 query problems when directly visible.
- Incorrect transaction handling.
- Incorrect model relationship usage.
- Missing authentication or authorization.
- Unsafe request/input handling.
- Incorrect form/serializer validation.
- Incorrect view or middleware behavior.
- Improper use of raw SQL.
- Security-sensitive configuration mistakes.
- Incorrect queryset evaluation or filtering.
- Incorrect signal usage.
- Resource cleanup where relevant.

Report only concrete Django problems supported by the
available code.
""".strip()

    # ======================================================
    # FastAPI
    # ======================================================

    FASTAPI = """
FASTAPI-SPECIFIC REVIEW

Check for concrete FastAPI issues involving:

- Async/sync misuse.
- Blocking operations inside async request handlers.
- Dependency-injection misuse.
- Incorrect request validation.
- Incorrect Pydantic model usage when it creates a real
  validation or serialization problem.
- Missing authentication or authorization.
- Unsafe request input handling.
- Incorrect exception handling.
- Incorrect response-model/status behavior.
- Resource/session lifecycle problems.
- Database session cleanup.
- Missing cancellation/resource cleanup when relevant.

Report only concrete FastAPI problems supported by the
available code.
""".strip()

    # ======================================================
    # Flask
    # ======================================================

    FLASK = """
FLASK-SPECIFIC REVIEW

Check for concrete Flask issues involving:

- Missing request validation.
- Unsafe request input handling.
- Authentication or authorization mistakes.
- Incorrect application/request context usage.
- Incorrect error handling.
- Blueprint or route registration mistakes.
- Resource/database-session cleanup.
- Unsafe global mutable state.
- Thread-safety problems when clearly supported.
- Incorrect response/status handling.

Report only concrete Flask problems supported by the
available code.
""".strip()

    # ======================================================
    # Laravel
    # ======================================================

    LARAVEL = """
LARAVEL-SPECIFIC REVIEW

Check for concrete Laravel issues involving:

- Authentication or authorization mistakes.
- Missing request validation.
- Mass-assignment vulnerabilities.
- Unsafe raw SQL/query construction.
- Incorrect Eloquent relationship usage.
- N+1 query problems when directly visible.
- Incorrect transaction handling.
- Controller/service/model responsibility problems when
  they create real correctness or coupling issues.
- Incorrect middleware usage.
- Queue/job error-handling problems.
- Resource cleanup where relevant.

Report only concrete Laravel problems supported by the
available code.
""".strip()

    # ======================================================
    # Rails
    # ======================================================

    RAILS = """
RAILS-SPECIFIC REVIEW

Check for concrete Ruby on Rails issues involving:

- ActiveRecord query mistakes.
- N+1 query problems when directly visible.
- Incorrect transaction handling.
- Incorrect model association usage.
- Dangerous callback behavior.
- Authentication or authorization mistakes.
- Missing strong-parameter handling.
- Unsafe mass assignment.
- Unsafe raw SQL.
- Incorrect controller/model responsibility when it
  creates concrete correctness or coupling problems.
- Background-job error handling.
- Resource cleanup where relevant.

Report only concrete Rails problems supported by the
available code.
""".strip()

    # ======================================================
    # Framework mapping
    # ======================================================

    FRAMEWORK_MAP = {
        "angular": ANGULAR,
        "react": REACT,
        "react-native": REACT_NATIVE,
        "vue": VUE,
        "nuxt": NUXT,
        "nextjs": NEXTJS,

        "node": NODE,
        "express": EXPRESS,
        "nestjs": NESTJS,

        "spring": SPRING,
        "spring-boot": SPRING_BOOT,

        "aspnet-core": ASPNET_CORE,

        "django": DJANGO,
        "fastapi": FASTAPI,
        "flask": FLASK,

        "laravel": LARAVEL,
        "rails": RAILS,
    }

    @classmethod
    def get(
        cls,
        framework: str | None,
    ) -> str:
        """
        Return framework-specific guidance.

        Unknown/empty frameworks receive a small neutral
        response rather than unrelated framework rules.
        """

        if not framework:
            return (
                "No framework-specific review is required."
            )

        normalized = (
            framework
            .strip()
            .lower()
        )

        return cls.FRAMEWORK_MAP.get(
            normalized,
            (
                "No framework-specific review is required."
            ),
        )