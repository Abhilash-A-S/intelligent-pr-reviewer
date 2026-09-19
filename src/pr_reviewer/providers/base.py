from abc import ABC, abstractmethod

from pr_reviewer.review.models import ChangedFile, PullRequest


class PullRequestProvider(ABC):
    """
    Provider-independent interface for Pull Request platforms.

    Implementations may include:
    - GitHub
    - Azure DevOps
    - GitLab
    - Bitbucket
    """

    supports_batch_inline_comments = False
    supports_pull_request_listing = False

    def list_pull_requests(
        self,
        repository: str,
        state: str = "open",
    ) -> list[dict]:
        """Return a list of pull requests with id, number, title, and author.

        Providers that support listing should override this method and set
        ``supports_pull_request_listing = True``.
        """
        return []

    def publish_inline_comments_batch(
        self,
        repository: str,
        pull_number: int,
        commit_id: str,
        comments: list[dict],
    ) -> dict:
        """Publish one provider-native batch of inline comments when supported."""
        raise NotImplementedError

    @abstractmethod
    def get_pull_request(
        self,
        repository: str,
        pull_number: int,
    ) -> PullRequest:
        """
        Return Pull Request metadata.
        """
        raise NotImplementedError

    @abstractmethod
    def get_changed_files(
        self,
        repository: str,
        pull_number: int,
    ) -> list[ChangedFile]:
        """
        Return files changed by the Pull Request.
        """
        raise NotImplementedError

    def get_repository_tree(
        self,
        repository: str,
        ref: str,
    ) -> list[str]:
        """Return repository file paths at a ref when supported.

        Providers that cannot enumerate a repository may return an empty list.
        Repository discovery is context-only: unchanged files can inform
        workspace/project ownership but can never produce findings.
        """
        return []

    @abstractmethod
    def get_file_content(
        self,
        repository: str,
        file_path: str,
        ref: str,
    ) -> str:
        """
        Return the complete current content of a file
        at the supplied repository reference.

        The review engine will use this as context while
        allowing findings only on newly changed lines.
        """
        raise NotImplementedError

    @abstractmethod
    def get_existing_comments(
        self,
        repository: str,
        pull_number: int,
    ) -> list[dict]:
        """
        Return existing inline Pull Request review comments.
        """
        raise NotImplementedError

    @abstractmethod
    def publish_inline_comment(
        self,
        repository: str,
        pull_number: int,
        body: str,
        commit_id: str,
        file_path: str,
        line_number: int,
        diff_position: int | None = None,
    ) -> dict:
        """
        Publish an inline review comment on a changed line.
        """
        raise NotImplementedError

    @abstractmethod
    def get_summary_comments(
        self,
        repository: str,
        pull_number: int,
    ) -> list[dict]:
        """
        Return existing PR-level summary/timeline comments.
        """
        raise NotImplementedError

    @abstractmethod
    def publish_summary_comment(
        self,
        repository: str,
        pull_number: int,
        body: str,
    ) -> dict:
        """
        Publish the Intelligent PR Reviewer summary.
        """
        raise NotImplementedError

    @abstractmethod
    def update_summary_comment(
        self,
        repository: str,
        comment_id: int,
        body: str,
    ) -> dict:
        """
        Update an existing Intelligent PR Reviewer summary.
        """
        raise NotImplementedError
