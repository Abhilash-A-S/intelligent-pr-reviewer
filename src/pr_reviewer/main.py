import argparse
import sys

from pr_reviewer.llm.ollama import OllamaProvider
from pr_reviewer.providers.base import PullRequestProvider
from pr_reviewer.providers.factory import (
    PROVIDER_NAMES,
    create_pull_request_provider,
    provider_display_name,
)
from pr_reviewer.review.orchestrator import ReviewOrchestrator
from pr_reviewer.review.semantic_routing import ReviewDepth


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="intelligent-pr-reviewer",
        description=(
            "AI-powered Pull Request review system."
        ),
    )

    parser.add_argument(
        "--repository",
        required=True,
        help=(
            "Provider-specific repository identifier. Use owner/name for "
            "GitHub or organization/project/repository for Azure DevOps."
        ),
    )

    parser.add_argument(
        "--pull-number",
        required=False,
        default=None,
        type=int,
        help=(
            "Pull Request number. "
            "Required unless --select-pr is used."
        ),
    )

    parser.add_argument(
        "--provider",
        choices=PROVIDER_NAMES,
        default="github",
        help=(
            "Pull request platform provider. "
            "'github' (default): requires GITHUB_TOKEN in .env. "
            "'azure-devops': requires AZURE_DEVOPS_PAT and "
            "--repository as org/project/repo."
        ),
    )

    parser.add_argument(
        "--select-pr",
        action="store_true",
        help=(
            "Interactively list open pull requests for the repository "
            "and prompt you to select one. Ignores --pull-number when set."
        ),
    )

    mode_group = parser.add_mutually_exclusive_group()

    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Review the Pull Request without publishing "
            "comments. This is the default behavior."
        ),
    )

    parser.add_argument(
        "--review-depth",
        choices=[depth.value for depth in ReviewDepth],
        default=ReviewDepth.STANDARD.value,
        help=(
            "Semantic review depth: fast minimizes local LLM calls, "
            "standard balances coverage and performance (default), and "
            "deep reviews every otherwise eligible file."
        ),
    )

    mode_group.add_argument(
        "--publish",
        action="store_true",
        help=(
            "Publish inline findings and the review summary "
            "to the Pull Request."
        ),
    )

    parser.add_argument(
        "--max-workers",
        type=int,
        default=None,
        help=(
            "Maximum concurrent LLM review workers. "
            "Defaults to provider recommended concurrency (e.g. 2 for local Ollama)."
        ),
    )

    return parser


def _select_pull_request(
    provider: PullRequestProvider,
    repository: str,
) -> int:
    """List open PRs and interactively prompt the user to pick one."""
    if not getattr(provider, "supports_pull_request_listing", False):
        raise ValueError(
            f"The provider '{type(provider).__name__}' does not support "
            "pull request listing. Please supply --pull-number directly."
        )
    prs = provider.list_pull_requests(repository, state="open")
    if not prs:
        raise ValueError(
            f"No open pull requests found in '{repository}'."
        )
    print()
    print("📋 Open Pull Requests")
    print("-" * 55)
    for idx, pr in enumerate(prs, start=1):
        print(
            f"  [{idx:2d}] PR #{pr.number:4d}  {pr.title[:60]}"
            f"  ({pr.author})"
        )
    print()
    while True:
        raw = input("Select a list index, or enter # followed by a PR ID: ").strip()
        if not raw:
            continue
        direct_pr_id = raw.startswith("#")
        raw = raw.removeprefix("#")
        try:
            value = int(raw)
        except ValueError:
            print("  Please enter a valid integer.")
            continue
        if not direct_pr_id and 1 <= value <= len(prs):
            return prs[value - 1].number
        match = next((p for p in prs if p.number == value), None)
        if match:
            return match.number
        print(f"  PR #{value} not found in the list above. Try again.")


def main() -> None:
    parser = build_parser()

    args = parser.parse_args()

    # --------------------------------------------------
    # Safe default:
    #
    # Unless --publish is explicitly supplied,
    # the application runs in dry-run mode.
    # --------------------------------------------------

    publish = args.publish
    dry_run = not publish
    provider_label = provider_display_name(args.provider)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    # --------------------------------------------------
    # Validate: must have either --pull-number or --select-pr
    # --------------------------------------------------
    if not args.select_pr and args.pull_number is None:
        parser.error("--pull-number is required unless --select-pr is used.")

    print()
    print("🤖 Intelligent PR Reviewer")
    print("=" * 55)

    print(
        f"Repository   : {args.repository}"
    )

    print(f"Provider     : {provider_label}")

    if not args.select_pr:
        print(
            f"Pull Request : #{args.pull_number}"
        )

    print(
        f"Mode         : "
        f"{'PUBLISH' if publish else 'DRY RUN'}"
    )
    print(f"Review depth : {args.review_depth.upper()}")

    if dry_run:
        print()
        print(
            "🛡️ Dry-run mode: "
            "no pull request comments will be published."
        )

    else:
        print()
        print(
            "⚠️ Publish mode: "
            f"review comments will be written to {provider_label}."
        )

    try:
        provider = create_pull_request_provider(args.provider)

        # --------------------------------------------------
        # Manual PR selection (--select-pr)
        # --------------------------------------------------
        pull_number = args.pull_number
        if getattr(args, "select_pr", False):
            pull_number = _select_pull_request(provider, args.repository)
            print(f"Pull Request : #{pull_number}")

        llm_provider = OllamaProvider()

        orchestrator = ReviewOrchestrator(
            provider=provider,
            llm_provider=llm_provider,
            review_depth=args.review_depth,
            max_llm_workers=args.max_workers,
        )

        print()
        print("🔍 Starting AI review...")

        result = orchestrator.run(
            repository=args.repository,
            pull_number=pull_number,
            publish=publish,
        )

    except KeyboardInterrupt:
        print()
        print("⚠️ Review cancelled.")

        sys.exit(130)

    except Exception as exc:
        print()
        print("❌ Review failed")
        print("-" * 55)

        print(
            f"{type(exc).__name__}: {exc}"
        )

        sys.exit(1)

    # --------------------------------------------------
    # Pull Request information
    # --------------------------------------------------

    print()
    print("📋 Pull Request")
    print("-" * 55)

    print(
        f"Title       : "
        f"{result.pull_request.title}"
    )

    print(
        f"Author      : "
        f"{result.pull_request.author}"
    )

    print(
        f"State       : "
        f"{result.pull_request.state}"
    )

    print(
        f"Branch      : "
        f"{result.pull_request.head_branch} "
        f"→ "
        f"{result.pull_request.base_branch}"
    )

    # --------------------------------------------------
    # Findings
    # --------------------------------------------------

    print()
    print("🔎 Findings")
    print("-" * 55)

    if not result.findings:

        print(
            "✅ No meaningful issues found."
        )

    else:

        for finding in result.findings:

            print()

            print(
                f"{finding.severity.value.upper()} "
                f"| "
                f"{finding.file_path}:"
                f"{finding.line_number}"
            )

            print(
                f"Category   : "
                f"{finding.category or 'General'}"
            )

            print(
                f"Rule       : "
                f"{finding.rule_id}"
            )

            print(
                f"Issue      : "
                f"{finding.issue or finding.message}"
            )

            if finding.impact:
                print(
                    f"Impact     : "
                    f"{finding.impact}"
                )

            if finding.evidence:
                print(
                    f"Evidence   : "
                    f"{finding.evidence}"
                )

            if finding.suggestion:

                print(
                    f"Suggestion : "
                    f"{finding.suggestion}"
                )

    # --------------------------------------------------
    # Quality Gate
    # --------------------------------------------------

    quality = result.quality_gate

    print()
    print("🚦 Quality Gate")
    print("-" * 55)

    print(
        f"Decision    : "
        f"{quality.decision.value.upper()}"
    )

    print(
        f"🔴 Critical : "
        f"{quality.critical_count}"
    )

    print(
        f"🟠 High     : "
        f"{quality.high_count}"
    )

    print(
        f"🟡 Medium   : "
        f"{quality.medium_count}"
    )

    print(
        f"🔵 Low      : "
        f"{quality.low_count}"
    )

    print(
        f"🟢 Suggest. : "
        f"{quality.suggestion_count}"
    )

    print(
        f"Total       : "
        f"{quality.total_findings}"
    )

    # --------------------------------------------------
    # Publishing information
    # --------------------------------------------------

    print()
    print("💬 Publishing")
    print("-" * 55)

    if result.dry_run:

        print(
            "Mode                      : DRY RUN"
        )

        print(
            "Inline comments published : 0"
        )

        print(
            "Summary comments published: 0"
        )

        print()
        print(
            f"🛡️ Nothing was written to {provider_label}."
        )

    else:

        print(
            "Mode                      : PUBLISH"
        )

        print(
            f"Inline comments published : "
            f"{result.publishing.published_count}"
        )

        print(
            f"Duplicates skipped        : "
            f"{result.publishing.skipped_duplicates}"
        )

        print(
            f"Inline placement failures : "
            f"{result.publishing.failed_count}"
        )

        print(
            f"Findings grouped          : "
            f"{result.publishing.grouped_findings}"
        )

        print(
            f"Summary-only findings     : "
            f"{result.publishing.summary_only_findings}"
        )

        print(
            f"Rate limited              : "
            f"{'yes' if result.publishing.rate_limited else 'no'}"
        )

        if result.summary_publishing:

            print(
                f"Summary action            : "
                f"{result.summary_publishing.action.value}"
            )

            if (
                result
                .summary_publishing
                .comment_id
            ):

                print(
                    f"Summary comment ID        : "
                    f"{result.summary_publishing.comment_id}"
                )

        if result.summary_publishing_failure:
            print("Summary publishing        : failed")
            print(
                f"Summary failure           : "
                f"{result.summary_publishing_failure}"
            )

    print()
    print("=" * 55)

    if result.dry_run:

        print(
            "✅ Dry-run review completed."
        )

    else:

        print(
            "✅ Review completed and published."
        )


if __name__ == "__main__":
    main()
