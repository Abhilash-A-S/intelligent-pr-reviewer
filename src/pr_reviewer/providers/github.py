import base64
import os

import httpx
from dotenv import load_dotenv

from pr_reviewer.providers.base import PullRequestProvider
from pr_reviewer.providers.models import PullRequestSummary
from pr_reviewer.review.models import ChangedFile, PullRequest

load_dotenv()


class GitHubProvider(PullRequestProvider):
    BASE_URL = "https://api.github.com"
    supports_batch_inline_comments = True
    supports_pull_request_listing = True
    provider_name = "github"
    display_name = "GitHub"

    def list_pull_requests(
        self,
        repository: str,
        state: str = "open",
    ) -> list[PullRequestSummary]:
        """List pull requests for the repository."""
        prs: list[PullRequestSummary] = []
        page = 1
        while True:
            response = self.client.get(
                f"/repos/{repository}/pulls",
                params={"state": state, "per_page": 30, "page": page},
            )
            response.raise_for_status()
            batch = response.json()
            if not batch:
                break
            for pr in batch:
                prs.append(
                    PullRequestSummary(
                        number=pr["number"],
                        title=pr["title"],
                        author=pr["user"]["login"],
                        base_branch=pr["base"]["ref"],
                        head_branch=pr["head"]["ref"],
                        state=pr["state"],
                    )
                )
            if len(batch) < 30:
                break
            page += 1
        return prs

    def __init__(
        self,
        token: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        if client is not None:
            self.client = client
            return

        token = token or os.getenv("GITHUB_TOKEN")

        if not token:
            raise ValueError(
                "GITHUB_TOKEN is not configured. "
                "Please add it to your .env file."
            )

        self.client = httpx.Client(
            base_url=self.BASE_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
            },
            timeout=30.0,
        )

    def get_pull_request(
        self,
        repository: str,
        pull_number: int,
    ) -> PullRequest:
        response = self.client.get(
            f"/repos/{repository}/pulls/{pull_number}"
        )

        response.raise_for_status()

        data = response.json()

        return PullRequest(
            provider="github",
            repository=repository,
            number=pull_number,
            title=data["title"],
            author=data["user"]["login"],
            state=data["state"],
            base_branch=data["base"]["ref"],
            head_branch=data["head"]["ref"],
            head_commit=data["head"]["sha"],
        )

    def get_changed_files(
        self,
        repository: str,
        pull_number: int,
    ) -> list[ChangedFile]:
        """Return every changed file in the pull request.

        GitHub paginates the ``pulls/{number}/files`` endpoint and defaults
        to 30 items per page.  A reviewer must never treat that first page as
        the complete PR, otherwise later application files silently disappear
        from analysis.
        """
        files: list[dict] = []
        page = 1
        per_page = 100

        while True:
            response = self.client.get(
                f"/repos/{repository}/pulls/{pull_number}/files",
                params={"per_page": per_page, "page": page},
            )
            response.raise_for_status()
            batch = response.json()

            if not isinstance(batch, list):
                raise ValueError(
                    "GitHub pull-request files response was not a list."
                )

            files.extend(batch)

            if len(batch) < per_page:
                break

            page += 1

        return [
            ChangedFile(
                file_path=file["filename"],
                status=file["status"],
                patch=file.get("patch"),
            )
            for file in files
        ]

    def get_repository_tree(
        self,
        repository: str,
        ref: str,
    ) -> list[str]:
        """Enumerate files at the PR head without depending on the diff."""
        response = self.client.get(
            f"/repos/{repository}/git/trees/{ref}",
            params={"recursive": "1"},
        )
        response.raise_for_status()
        data = response.json()
        return [
            item["path"]
            for item in data.get("tree", [])
            if item.get("type") == "blob" and item.get("path")
        ]

    def get_file_content(
        self,
        repository: str,
        file_path: str,
        ref: str,
    ) -> str:
        """
        Fetch the complete file content from the PR head commit.

        GitHub returns normal repository file contents as base64.
        """

        response = self.client.get(
            f"/repos/{repository}/contents/{file_path}",
            params={
                "ref": ref,
            },
        )

        response.raise_for_status()

        data = response.json()

        content = data.get("content")

        if not content:
            return ""

        encoding = data.get("encoding")

        if encoding == "base64":
            decoded = base64.b64decode(
                content
            )

            return decoded.decode(
                "utf-8",
                errors="replace",
            )

        # Defensive fallback in case another representation
        # is returned in the future.
        return str(content)

    def get_existing_comments(
        self,
        repository: str,
        pull_number: int,
    ) -> list[dict]:
        """
        Return inline PR review comments.
        """

        comments: list[dict] = []
        page = 1
        per_page = 100

        while True:
            response = self.client.get(
                f"/repos/{repository}/pulls/{pull_number}/comments",
                params={"per_page": per_page, "page": page},
            )
            response.raise_for_status()
            batch = response.json()

            if not isinstance(batch, list):
                raise ValueError(
                    "GitHub pull-request comments response was not a list."
                )

            comments.extend(batch)

            if len(batch) < per_page:
                break

            page += 1

        return comments

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
        endpoint = f"/repos/{repository}/pulls/{pull_number}/comments"
        response = self.client.post(endpoint, json={
            "body": body,
            "commit_id": commit_id,
            "path": file_path,
            "line": line_number,
            "side": "RIGHT",
        })
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if (
                exc.response.status_code != 422
                or diff_position is None
                or self._is_secondary_throttle(exc.response)
            ):
                raise self._with_github_details(exc) from exc
            # GitHub can reject a valid right-side line anchor for some diff
            # shapes. The parsed diff position identifies the same verified
            # added line and is used only as a compatibility fallback.
            response = self.client.post(endpoint, json={
                "body": body,
                "commit_id": commit_id,
                "path": file_path,
                "position": diff_position,
            })
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as fallback_exc:
                raise self._with_github_details(fallback_exc) from fallback_exc

        return response.json()

    def publish_inline_comments_batch(
        self,
        repository: str,
        pull_number: int,
        commit_id: str,
        comments: list[dict],
    ) -> dict:
        """Create one GitHub review containing all selected inline comments."""
        if not comments:
            return {"id": None, "comments": []}
        payload_comments = []
        for comment in comments:
            payload_comments.append({
                "path": comment["file_path"],
                "line": comment["line_number"],
                "side": "RIGHT",
                "body": comment["body"],
            })
        response = self.client.post(
            f"/repos/{repository}/pulls/{pull_number}/reviews",
            json={
                "commit_id": commit_id,
                "event": "COMMENT",
                "body": "Intelligent PR Reviewer inline findings",
                "comments": payload_comments,
            },
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._with_github_details(exc) from exc
        return response.json()

    @staticmethod
    def _is_secondary_throttle(response: httpx.Response) -> bool:
        try:
            payload = response.json()
        except (TypeError, ValueError):
            payload = {}
        text = str(payload).lower()
        return any(marker in text for marker in (
            "submitted too quickly",
            "secondary rate limit",
            "abuse detection",
        ))

    @staticmethod
    def _with_github_details(exc: httpx.HTTPStatusError) -> httpx.HTTPStatusError:
        try:
            payload = exc.response.json()
            detail = str(payload)[:1000]
        except (TypeError, ValueError):
            detail = (exc.response.text or "no response body")[:1000]
        return httpx.HTTPStatusError(
            f"{exc}; GitHub response: {detail}",
            request=exc.request,
            response=exc.response,
        )

    def get_summary_comments(
        self,
        repository: str,
        pull_number: int,
    ) -> list[dict]:
        """
        Return PR timeline comments.

        GitHub exposes PR timeline comments through
        the issue comments API.
        """

        comments: list[dict] = []
        page = 1
        per_page = 100
        while True:
            response = self.client.get(
                f"/repos/{repository}/issues/{pull_number}/comments",
                params={"per_page": per_page, "page": page},
            )
            response.raise_for_status()
            batch = response.json()
            if not isinstance(batch, list):
                raise ValueError(
                    "GitHub pull-request summary comments response was not a list."
                )
            comments.extend(batch)
            if len(batch) < per_page:
                break
            page += 1
        return comments

    def publish_summary_comment(
        self,
        repository: str,
        pull_number: int,
        body: str,
    ) -> dict:
        response = self.client.post(
            f"/repos/{repository}/issues/{pull_number}/comments",
            json={
                "body": body,
            },
        )

        response.raise_for_status()

        return response.json()

    def update_summary_comment(
        self,
        repository: str,
        comment_id: int,
        body: str,
        pull_number: int | None = None,
        thread_id: int | None = None,
    ) -> dict:
        response = self.client.patch(
            f"/repos/{repository}/issues/comments/{comment_id}",
            json={
                "body": body,
            },
        )

        response.raise_for_status()

        return response.json()
