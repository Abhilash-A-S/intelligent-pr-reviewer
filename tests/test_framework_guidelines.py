from pr_reviewer.llm.framework_guidelines import (
    FrameworkGuidelines,
)


# =========================================================
# Frontend frameworks
# =========================================================


def test_angular_guidelines():
    result = FrameworkGuidelines.get(
        "angular"
    )

    assert "ANGULAR-SPECIFIC REVIEW" in result
    assert "RxJS" in result
    assert "signal" in result
    assert "change-detection" in result
    assert "dependency-injection" in result


def test_react_guidelines():
    result = FrameworkGuidelines.get(
        "react"
    )

    assert "REACT-SPECIFIC REVIEW" in result
    assert "Hook" in result
    assert "useEffect" in result
    assert "state mutation" in result
    assert "stale closures" in result.lower()


def test_react_native_guidelines():
    result = FrameworkGuidelines.get(
        "react-native"
    )

    assert (
        "REACT-NATIVE-SPECIFIC REVIEW"
        in result
    )

    assert "Hook" in result
    assert "FlatList" in result
    assert "navigation" in result.lower()
    assert "timer cleanup" in result.lower()


def test_vue_guidelines():
    result = FrameworkGuidelines.get(
        "vue"
    )

    assert "VUE-SPECIFIC REVIEW" in result
    assert "reactivity" in result
    assert "prop mutation" in result
    assert "computed" in result


def test_nuxt_guidelines():
    result = FrameworkGuidelines.get(
        "nuxt"
    )

    assert "NUXT-SPECIFIC REVIEW" in result
    assert "server/client" in result.lower()
    assert "ssr" in result.lower()
    assert "hydration" in result.lower()


def test_nextjs_guidelines():
    result = FrameworkGuidelines.get(
        "nextjs"
    )

    assert "NEXT.JS-SPECIFIC REVIEW" in result
    assert "server/client" in result.lower()
    assert "hydration" in result.lower()
    assert "revalidation" in result.lower()


# =========================================================
# JavaScript backend frameworks
# =========================================================


def test_node_guidelines():
    result = FrameworkGuidelines.get(
        "node"
    )

    assert "NODE.JS-SPECIFIC REVIEW" in result
    assert "Async/promise" in result
    assert "Unhandled promise" in result
    assert "Path traversal" in result
    assert "Command injection" in result


def test_express_guidelines():
    result = FrameworkGuidelines.get(
        "express"
    )

    assert "EXPRESS-SPECIFIC REVIEW" in result
    assert "error middleware" in result
    assert "Middleware ordering" in result
    assert "request validation" in result
    assert "authorization" in result


def test_nestjs_guidelines():
    result = FrameworkGuidelines.get(
        "nestjs"
    )

    assert "NESTJS-SPECIFIC REVIEW" in result
    assert "dependency-injection" in result
    assert "provider" in result.lower()
    assert "Guard" in result
    assert "DTO" in result


# =========================================================
# Java / Spring
# =========================================================


def test_spring_guidelines():
    result = FrameworkGuidelines.get(
        "spring"
    )

    assert "SPRING-SPECIFIC REVIEW" in result
    assert "Dependency-injection" in result
    assert "Transaction" in result
    assert "bean lifecycle" in result
    assert "singleton" in result


def test_spring_boot_guidelines():
    result = FrameworkGuidelines.get(
        "spring-boot"
    )

    assert (
        "SPRING-BOOT-SPECIFIC REVIEW"
        in result
    )

    assert "Spring Boot configuration" in result
    assert "Transaction" in result
    assert "authorization" in result
    assert "Spring Data" in result


# =========================================================
# .NET
# =========================================================


def test_aspnet_core_guidelines():
    result = FrameworkGuidelines.get(
        "aspnet-core"
    )

    assert (
        "ASP.NET-CORE-SPECIFIC REVIEW"
        in result
    )

    assert "Dependency-injection" in result
    assert "Async/await" in result
    assert "Nullable-reference" in result
    assert "Entity Framework Core" in result


# =========================================================
# Python frameworks
# =========================================================


def test_django_guidelines():
    result = FrameworkGuidelines.get(
        "django"
    )

    assert "DJANGO-SPECIFIC REVIEW" in result
    assert "ORM" in result
    assert "N+1" in result
    assert "transaction" in result
    assert "authorization" in result


def test_fastapi_guidelines():
    result = FrameworkGuidelines.get(
        "fastapi"
    )

    assert "FASTAPI-SPECIFIC REVIEW" in result
    assert "Async/sync" in result
    assert "Pydantic" in result
    assert "authorization" in result
    assert "Database session cleanup" in result


def test_flask_guidelines():
    result = FrameworkGuidelines.get(
        "flask"
    )

    assert "FLASK-SPECIFIC REVIEW" in result
    assert "request validation" in result
    assert "application/request context" in result
    assert "global mutable state" in result
    assert "Thread-safety" in result


# =========================================================
# PHP
# =========================================================


def test_laravel_guidelines():
    result = FrameworkGuidelines.get(
        "laravel"
    )

    assert "LARAVEL-SPECIFIC REVIEW" in result
    assert "Mass-assignment" in result
    assert "Eloquent" in result
    assert "N+1" in result
    assert "middleware" in result


# =========================================================
# Ruby
# =========================================================


def test_rails_guidelines():
    result = FrameworkGuidelines.get(
        "rails"
    )

    assert "RAILS-SPECIFIC REVIEW" in result
    assert "ActiveRecord" in result
    assert "N+1" in result
    assert "strong-parameter" in result
    assert "mass assignment" in result


# =========================================================
# Framework isolation
# =========================================================


def test_angular_does_not_include_react_guidelines():
    result = FrameworkGuidelines.get(
        "angular"
    )

    assert "ANGULAR-SPECIFIC REVIEW" in result

    assert (
        "REACT-SPECIFIC REVIEW"
        not in result
    )


def test_react_does_not_include_angular_guidelines():
    result = FrameworkGuidelines.get(
        "react"
    )

    assert "REACT-SPECIFIC REVIEW" in result

    assert (
        "ANGULAR-SPECIFIC REVIEW"
        not in result
    )


def test_spring_boot_does_not_include_frontend_guidelines():
    result = FrameworkGuidelines.get(
        "spring-boot"
    )

    assert (
        "SPRING-BOOT-SPECIFIC REVIEW"
        in result
    )

    assert (
        "ANGULAR-SPECIFIC REVIEW"
        not in result
    )

    assert (
        "REACT-SPECIFIC REVIEW"
        not in result
    )

    assert (
        "VUE-SPECIFIC REVIEW"
        not in result
    )


def test_django_does_not_include_other_backend_guidelines():
    result = FrameworkGuidelines.get(
        "django"
    )

    assert "DJANGO-SPECIFIC REVIEW" in result

    assert (
        "SPRING-BOOT-SPECIFIC REVIEW"
        not in result
    )

    assert (
        "ASP.NET-CORE-SPECIFIC REVIEW"
        not in result
    )

    assert (
        "LARAVEL-SPECIFIC REVIEW"
        not in result
    )


# =========================================================
# Input normalization
# =========================================================


def test_framework_name_is_case_insensitive():
    result = FrameworkGuidelines.get(
        "ANGULAR"
    )

    assert "ANGULAR-SPECIFIC REVIEW" in result
    assert "RxJS" in result


def test_framework_name_with_spaces_is_normalized():
    result = FrameworkGuidelines.get(
        "  spring-boot  "
    )

    assert (
        "SPRING-BOOT-SPECIFIC REVIEW"
        in result
    )


def test_mixed_case_framework_name():
    result = FrameworkGuidelines.get(
        "FastAPI"
    )

    assert (
        "FASTAPI-SPECIFIC REVIEW"
        in result
    )


# =========================================================
# Unknown / missing framework
# =========================================================


def test_unknown_framework():
    result = FrameworkGuidelines.get(
        "unknown"
    )

    assert (
        result
        ==
        "No framework-specific review is required."
    )


def test_none_framework():
    result = FrameworkGuidelines.get(
        None
    )

    assert (
        result
        ==
        "No framework-specific review is required."
    )


def test_empty_framework():
    result = FrameworkGuidelines.get(
        ""
    )

    assert (
        result
        ==
        "No framework-specific review is required."
    )


def test_whitespace_framework():
    result = FrameworkGuidelines.get(
        "   "
    )

    assert (
        result
        ==
        "No framework-specific review is required."
    )


# =========================================================
# Framework map integrity
# =========================================================


def test_all_supported_frameworks_have_guidelines():
    frameworks = [
        "angular",
        "react",
        "react-native",
        "vue",
        "nuxt",
        "nextjs",
        "node",
        "express",
        "nestjs",
        "spring",
        "spring-boot",
        "aspnet-core",
        "django",
        "fastapi",
        "flask",
        "laravel",
        "rails",
    ]

    no_guidelines = (
        "No framework-specific review is required."
    )

    for framework in frameworks:
        result = FrameworkGuidelines.get(
            framework
        )

        assert result != no_guidelines
        assert result.strip()


def test_framework_map_contains_expected_frameworks():
    expected = {
        "angular",
        "react",
        "react-native",
        "vue",
        "nuxt",
        "nextjs",
        "node",
        "express",
        "nestjs",
        "spring",
        "spring-boot",
        "aspnet-core",
        "django",
        "fastapi",
        "flask",
        "laravel",
        "rails",
    }

    assert (
        set(
            FrameworkGuidelines
            .FRAMEWORK_MAP
            .keys()
        )
        ==
        expected
    )