from pr_reviewer.context.models import RepositoryContext
from pr_reviewer.review.framework_facts.dom_mount import DomMountEvidenceValidator
from pr_reviewer.review.framework_facts.typescript_build import TypeScriptBuildFactValidator
from pr_reviewer.review.models import ChangedFile, ChangedLine, Finding


def cf(path: str, content: str) -> ChangedFile:
    return ChangedFile(
        file_path=path,
        status="modified",
        language="typescript",
        patch="",
        changed_lines=[
            ChangedLine(
                file_path=path,
                line_number=1,
                content=content.splitlines()[0] if content.splitlines() else "",
            )
        ],
        full_content=content,
    )


def finding(path: str, rule: str, message: str) -> Finding:
    return Finding(
        file_path=path,
        line_number=1,
        severity="HIGH",
        rule_id=rule,
        message=message,
        suggestion=None,
    )


def test_dom_root_existing_is_rejected():
    validator = DomMountEvidenceValidator()
    main = cf("src/main.tsx", 'document.getElementById("root")')
    html = cf("index.html", '<div id="root"></div>')

    reasons = validator.validate(
        finding("src/main.tsx", "react-root-element-must-exist",
                "The element with id root must exist."),
        main,
        [main, html],
    )
    assert reasons


def test_dom_root_genuinely_missing_is_preserved():
    validator = DomMountEvidenceValidator()
    main = cf("src/main.tsx", 'document.getElementById("root")')
    html = cf("index.html", '<div id="app"></div>')

    reasons = validator.validate(
        finding("src/main.tsx", "react-root-element-must-exist",
                "The element with id root must exist."),
        main,
        [main, html],
    )
    assert reasons == []


def test_non_empty_tsconfig_rejects_empty_config_claim():
    validator = TypeScriptBuildFactValidator()
    config = cf(
        "tsconfig.json",
        '{"files":[],"references":[{"path":"./tsconfig.app.json"}]}',
    )
    app = cf("tsconfig.app.json", '{"compilerOptions":{"composite":true}}')

    reasons = validator.validate(
        finding("tsconfig.json", "empty-config",
                "The tsconfig.json file is empty."),
        config,
        [config, app],
        RepositoryContext(
            framework="react",
            build_tools={"vite"},
            metadata_files=["tsconfig.json", "tsconfig.app.json"],
        ),
    )
    assert reasons


def test_genuinely_empty_tsconfig_is_preserved():
    validator = TypeScriptBuildFactValidator()
    config = cf("tsconfig.json", "{}")

    reasons = validator.validate(
        finding("tsconfig.json", "empty-config",
                "The tsconfig.json file is empty."),
        config,
        [config],
        RepositoryContext(framework="react", build_tools={"vite"}),
    )
    assert reasons == []


def test_solution_style_files_array_still_rejected():
    validator = TypeScriptBuildFactValidator()
    config = cf(
        "tsconfig.json",
        '{"files":[],"references":[{"path":"./tsconfig.app.json"}]}',
    )
    app = cf("tsconfig.app.json", '{"compilerOptions":{"composite":true}}')

    reasons = validator.validate(
        finding("tsconfig.json", "empty-files-array",
                "The files array is empty."),
        config,
        [config, app],
        RepositoryContext(
            framework="react",
            build_tools={"vite"},
            metadata_files=["tsconfig.json", "tsconfig.app.json"],
        ),
    )
    assert reasons
