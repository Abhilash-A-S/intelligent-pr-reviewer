import base64
import os

import httpx
from dotenv import load_dotenv

from pr_reviewer.providers.base import PullRequestProvider
from pr_reviewer.providers.models import (
    OrganizationSummary,
    PullRequestSummary,
    RepositorySummary,
)
from pr_reviewer.review.models import ChangedFile, PullRequest

load_dotenv()


class GitHubProvider(PullRequestProvider):
    BASE_URL = "https://api.github.com"
    supports_batch_inline_comments = True
    supports_pull_request_listing = True
    supports_repository_discovery = True
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
                        updated_at=pr.get("updated_at"),
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
        self._viewer_data: dict | None = None
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

    def _authenticated_user(self) -> dict:
        if self._viewer_data is not None:
            return self._viewer_data
        response = self.client.get("/user")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not payload.get("login"):
            raise ValueError("GitHub did not return the authenticated account.")
        self._viewer_data = payload
        return payload

    def list_organizations(self) -> list[OrganizationSummary]:
        """List the authenticated account and organizations visible to it."""
        viewer = self._authenticated_user()
        organizations = [
            OrganizationSummary(
                id=str(viewer.get("id", viewer["login"])),
                name=viewer["login"],
                display_name=viewer.get("name") or viewer["login"],
                description=viewer.get("bio") or None,
            )
        ]
        page = 1
        while True:
            response = self.client.get(
                "/user/orgs",
                params={"per_page": 100, "page": page},
            )
            response.raise_for_status()
            batch = response.json()
            if not isinstance(batch, list):
                raise ValueError("GitHub organizations response was not a list.")
            for item in batch:
                if not isinstance(item, dict) or not item.get("login"):
                    continue
                organizations.append(
                    OrganizationSummary(
                        id=str(item.get("id", item["login"])),
                        name=item["login"],
                        display_name=item.get("name") or item["login"],
                        description=item.get("description") or None,
                    )
                )
            if len(batch) < 100:
                break
            page += 1

        unique = {item.name.casefold(): item for item in organizations}
        return sorted(unique.values(), key=lambda item: item.display_name.casefold())

    def list_repositories(
        self,
        organization: str,
        project: str | None = None,
    ) -> list[RepositorySummary]:
        """List repositories owned by the selected user or organization."""
        del project
        owner = organization.strip()
        if not owner:
            raise ValueError("GitHub owner or organization is required.")
        viewer = self._authenticated_user()
        is_viewer = owner.casefold() == str(viewer["login"]).casefold()
        endpoint = "/user/repos" if is_viewer else f"/orgs/{owner}/repos"
        repositories: list[RepositorySummary] = []
        page = 1
        while True:
            params: dict[str, object] = {"per_page": 100, "page": page, "sort": "full_name"}
            if is_viewer:
                params.update({"affiliation": "owner", "visibility": "all"})
            else:
                params["type"] = "all"
            response = self.client.get(endpoint, params=params)
            response.raise_for_status()
            batch = response.json()
            if not isinstance(batch, list):
                raise ValueError("GitHub repositories response was not a list.")
            for item in batch:
                if not isinstance(item, dict) or not item.get("name"):
                    continue
                visibility = item.get("visibility")
                if not visibility:
                    visibility = "private" if item.get("private") else "public"
                repositories.append(
                    RepositorySummary(
                        id=str(item.get("id", item["name"])),
                        name=item["name"],
                        organization=owner,
                        full_name=item.get("full_name") or f"{owner}/{item['name']}",
                        description=item.get("description") or None,
                        default_branch=item.get("default_branch") or None,
                        visibility=str(visibility),
                    )
                )
            if len(batch) < 100:
                break
            page += 1
        return sorted(repositories, key=lambda item: item.name.casefold())

    def validate_connection(self) -> None:
        self._authenticated_user()

    def get_changed_file_count(
        self,
        repository: str,
        pull_number: int,
    ) -> int | None:
        response = self.client.get(f"/repos/{repository}/pulls/{pull_number}")
        response.raise_for_status()
        payload = response.json()
        value = payload.get("changed_files") if isinstance(payload, dict) else None
        return value if isinstance(value, int) and value >= 0 else None

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
            description=data.get("body") or None,
            commit_count=data.get("commits"),
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
