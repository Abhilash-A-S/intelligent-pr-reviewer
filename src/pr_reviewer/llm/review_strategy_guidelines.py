from pr_reviewer.review.review_strategy import (
    ReviewStrategy,
)


class ReviewStrategyGuidelines:
    """
    Returns focused instructions for the type of file
    currently being reviewed.

    File classification and review strategy are already
    determined before the LLM is asked to reason about
    the code.

    These guidelines prevent source code, tests,
    templates, stylesheets, and project configuration
    from being reviewed as if they were the same kind
    of artifact.
    """

    SEMANTIC = """
SOURCE-CODE SEMANTIC REVIEW

Review this file as application/source code.

Focus on concrete behavior such as:

- correctness
- control flow
- runtime failures
- null/undefined/None risks
- incorrect API usage
- async/concurrency behavior
- security vulnerabilities
- authentication and authorization
- error handling
- resource lifecycle
- data integrity
- meaningful performance problems
- framework lifecycle problems

Do not report style preferences.

Do not recommend refactoring unless the current design
creates a concrete engineering problem.
""".strip()

    TEST = """
TEST-CODE REVIEW

Review this file as test code.

Focus on concrete test-quality problems such as:

- tests that do not actually verify the intended behavior
- assertions that can pass for the wrong reason
- incorrect mocks, spies, stubs, or fixtures
- missing async waiting when it causes unreliable tests
- race conditions or timing-dependent tests
- tests that leak timers, subscriptions, listeners,
  resources, or state
- incorrect test setup or teardown
- shared mutable state between tests
- incorrect framework testing APIs
- tests that exercise the wrong object or code path
- assertions that contradict the implementation contract

Do NOT report:

- missing tests merely because another test could be added
- test naming preferences
- formatting preferences
- stylistic test organization
- speculative test coverage suggestions

Framework-specific test APIs must be interpreted using
the detected framework.

If the framework supports standalone components,
modules, functions, providers, or equivalent constructs,
do not invent a wrapper/module requirement that the
framework does not require.
""".strip()

    TEMPLATE = """
TEMPLATE / VIEW REVIEW

Review this file as a template or view.

Focus on concrete problems such as:

- incorrect bindings
- invalid framework template syntax
- incorrect event/property binding
- unsafe rendering of untrusted content
- accessibility problems that are directly visible
- broken form/control relationships
- incorrect conditional or repeated rendering
- framework-specific template misuse
- template expressions that create a demonstrated
  correctness or serious performance problem

Do NOT:

- invent behavior that may exist in a component,
  controller, script, service, hook, or other file
- treat ids/classes/tags as programming-language variables
- report cosmetic HTML preferences
- report purely stylistic markup changes
""".strip()

    STYLESHEET = """
STYLESHEET REVIEW

Review this file as a stylesheet.

Report only concrete problems such as:

- CSS that clearly breaks interaction or usability
- accessibility-impacting styling
- invalid or contradictory declarations that cause
  incorrect behavior
- layout behavior that demonstrably breaks functionality
- framework-specific stylesheet misuse when directly
  supported by the code
- severe performance problems when clearly demonstrated

Do NOT report:

- color preferences
- font preferences
- spacing preferences
- border-radius preferences
- naming conventions
- selector-style preferences
- repeated values by themselves
- minification suggestions
- formatting
- cosmetic cleanup
""".strip()

    CONFIGURATION = """
PROJECT-CONFIGURATION REVIEW

Review this file as project/build/runtime configuration,
not as ordinary application source code.

Focus only on configuration changes that can materially
affect:

- compilation
- build behavior
- framework behavior
- runtime behavior
- dependency resolution
- module resolution
- deployment
- security
- environment configuration
- test execution
- package scripts
- compiler settings
- path aliases
- include/exclude behavior
- framework compiler configuration

Examples of meaningful issues include:

- broken compiler options
- invalid path mappings
- incompatible framework/compiler settings
- broken build targets
- unsafe runtime configuration
- dependency configuration that creates a concrete
  compatibility or security problem
- project configuration that prevents intended files
  from compiling or being included

Do NOT report:

- formatting
- property ordering
- indentation
- editor preferences
- stylistic configuration preferences
- optional settings merely because they could be added
- recommendations without a concrete behavioral impact

Do not interpret configuration keys as application
variables, methods, classes, or runtime statements.
""".strip()

    SKIP = """
NO SEMANTIC REVIEW

This file should not receive normal semantic LLM review.
""".strip()

    STRATEGY_MAP = {
        ReviewStrategy.SEMANTIC: SEMANTIC,
        ReviewStrategy.TEST: TEST,
        ReviewStrategy.TEMPLATE: TEMPLATE,
        ReviewStrategy.STYLESHEET: STYLESHEET,
        ReviewStrategy.CONFIGURATION: CONFIGURATION,
        ReviewStrategy.SKIP: SKIP,
    }

    @classmethod
    def get(
        cls,
        strategy: ReviewStrategy,
        framework: str | None = None,
    ) -> str:
        """
        Return strategy-specific review guidance.

        Small framework-specific additions can be appended
        where the interaction between file type and framework
        is especially important.
        """

        guidance = cls.STRATEGY_MAP.get(
            strategy,
            cls.SEMANTIC,
        )

        framework_guidance = (
            cls._framework_strategy_guidance(
                strategy=strategy,
                framework=framework,
            )
        )

        if not framework_guidance:
            return guidance

        return (
            f"{guidance}\n\n"
            f"{framework_guidance}"
        )

    @staticmethod
    def _framework_strategy_guidance(
        strategy: ReviewStrategy,
        framework: str | None,
    ) -> str:

        if not framework:
            return ""

        normalized_framework = (
            framework
            .strip()
            .lower()
        )

        if (
            strategy == ReviewStrategy.TEST
            and normalized_framework == "angular"
        ):
            return """
ANGULAR TEST-SPECIFIC CAUTION

Modern Angular applications may use standalone
components.

A standalone Angular component can be placed directly in:

TestBed.configureTestingModule({
  imports: [ComponentName]
})

Do NOT require AppModule, another NgModule, or
declarations merely because a standalone component is
imported directly.

Only report Angular TestBed configuration as incorrect
when the supplied code provides concrete evidence that
the tested component/directive/pipe/provider is configured
incorrectly.
""".strip()

        if (
            strategy == ReviewStrategy.CONFIGURATION
            and normalized_framework == "angular"
        ):
            return """
ANGULAR CONFIGURATION REVIEW

For Angular project configuration, pay particular
attention to concrete problems involving:

- angular.json build/test/serve targets
- builder configuration
- assets and styles configuration
- file replacements
- SSR/server configuration
- TypeScript compiler options
- Angular compiler options
- strictTemplates
- path aliases
- include/exclude/files settings

Do not report optional Angular settings merely because
another configuration is possible.
""".strip()

        return ""