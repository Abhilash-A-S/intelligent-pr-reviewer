from pr_reviewer.context.models import RepositoryContext
from pr_reviewer.llm.ollama import OllamaProvider
from pr_reviewer.llm.llm_reviewer import LLMReviewer
from pr_reviewer.review.models import ChangedFile, ChangedLine


def main():
    changed_file = ChangedFile(
        file_path="src/app.js",
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path="src/app.js",
                line_number=172,
                content='console.log("Application Load Testing");',
                diff_position=20,
            ),
            ChangedLine(
                file_path="src/app.js",
                line_number=173,
                content="const abc = 12346789;",
                diff_position=21,
            ),
        ],
    )

    repository_context = RepositoryContext(
        languages={"javascript"},
        framework="unknown",
        project_type="frontend-web",
        package_manager="npm",
    )

    provider = OllamaProvider()

    reviewer = LLMReviewer(
        llm_provider=provider
    )

    print()
    print("🤖 Intelligent PR Reviewer")
    print("-------------------------")
    print("Sending changed code to Qwen...")
    print()

    findings = reviewer.review(
        changed_file=changed_file,
        repository_context=repository_context,
    )

    print("Review findings:")
    print("-------------------------")

    if not findings:
        print("✅ No issues found.")
        return

    for finding in findings:
        print()
        print(
            f"{finding.severity.value.upper()} "
            f"| {finding.file_path}:"
            f"{finding.line_number}"
        )
        print(f"Rule: {finding.rule_id}")
        print(f"Message: {finding.message}")

        if finding.suggestion:
            print(
                f"Suggestion: {finding.suggestion}"
            )

        print(
            f"Diff position: "
            f"{finding.diff_position}"
        )


if __name__ == "__main__":
    main()