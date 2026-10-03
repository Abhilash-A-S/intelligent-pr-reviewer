from unittest.mock import Mock, patch

from pr_reviewer.main import _select_pull_request, build_parser
from pr_reviewer.providers.models import PullRequestSummary


def summaries():
    return [
        PullRequestSummary(
            number=42,
            title="First PR",
            author="one",
            base_branch="main",
            head_branch="feature/one",
            state="open",
        ),
        PullRequestSummary(
            number=1,
            title="Second PR",
            author="two",
            base_branch="main",
            head_branch="feature/two",
            state="open",
        ),
    ]


def test_parser_defaults_to_github():
    args = build_parser().parse_args([
        "--repository", "owner/repository", "--pull-number", "3"
    ])

    assert args.provider == "github"


def test_select_pull_request_accepts_list_index():
    provider = Mock()
    provider.supports_pull_request_listing = True
    provider.list_pull_requests.return_value = summaries()

    with patch("builtins.input", return_value="1"):
        selected = _select_pull_request(provider, "owner/repository")

    assert selected == 42


def test_select_pull_request_hash_prefix_disambiguates_pr_id():
    provider = Mock()
    provider.supports_pull_request_listing = True
    provider.list_pull_requests.return_value = summaries()

    with patch("builtins.input", return_value="#1"):
        selected = _select_pull_request(provider, "owner/repository")

    assert selected == 1
