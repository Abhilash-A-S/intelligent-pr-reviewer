"""Azure DevOps Pull Request provider.

Authentication
--------------
Set the environment variable `AZURE_DEVOPS_PAT` to a Personal Access Token
with **Code (read)** and **Pull Request Threads (read & write)** scopes.

Repository format
-----------------
Pass `--repository` as one of:
    `{organization}/{project}/{repository}`

Example:
    `my-org/my-project/my-repo`

Or supply `AZURE_DEVOPS_ORG`, `AZURE_DEVOPS_PROJECT`, and
`AZURE_DEVOPS_REPO` environment variables and pass just the repo name.

Pull-request number
-------------------
Azure DevOps uses integer pull request IDs identical to GitHub's convention.
Pass `--pull-number` as the PR integer ID.
"""

import base64
import os

import httpx
from dotenv import load_dotenv

from pr_reviewer.providers.base import PullRequestProvider
from pr_reviewer.review.models import ChangedFile, PullRequest

load_dotenv()

_REVIEWER_TAG = "intelligent-pr-reviewer-summary"


class AzureDevOpsProvider(PullRequestProvider):
    """Azure DevOps REST API v7.1 pull-request provider."""

    API_VERSION = "7.1"
    supports_batch_inline_comments = False
    supports_pull_request_listing = True

    def list_pull_requests(
        self,
        repository: str,
        state: str = "open",
    ) -> list[dict]:
        """List pull requests for the repository."""
        org, project, repo = self._parse_repository(repository)
        status = "active" if state == "open" else state
        url = f"{self._base(org, project, repo)}/pullrequests"
        response = self.client.get(
            url, params=self._qs(searchCriteria_status=status, searchCriteria_includeLinks="false")
        )
        response.raise_for_status()
        prs = []
        for pr in response.json().get("value", []):
            prs.append({
                "number": pr.get("pullRequestId"),
                "title": pr.get("title", ""),
                "author": pr.get("createdBy", {}).get("displayName", "unknown"),
                "base": pr.get("targetRefName", "").removeprefix("refs/heads/"),
                "head": pr.get("sourceRefName", "").removeprefix("refs/heads/"),
                "state": pr.get("status", ""),
            })
        return prs

    def __init__(
        self,
        organization: str | None = None,
        project: str | None = None,
    ) -> None:
        pat = os.getenv("AZURE_DEVOPS_PAT")
        if not pat:
            raise ValueError(
                "AZURE_DEVOPS_PAT is not configured. "
                "Please add it to your .env file."
            )

        self._org = organization or os.getenv("AZURE_DEVOPS_ORG", "")
        self._project = project or os.getenv("AZURE_DEVOPS_PROJECT", "")

        token = base64.b64encode(f":{pat}".encode()).decode()
        self.client = httpx.Client(
            headers={
                "Authorization": f"Basic {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=30.0,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_repository(repository: str) -> tuple[str, str, str]:
        """Return (organization, project, repo_name) from a repository string."""
        parts = [p.strip() for p in repository.split("/") if p.strip()]
        if len(parts) == 3:
            return parts[0], parts[1], parts[2]
        if len(parts) == 1:
            org = os.getenv("AZURE_DEVOPS_ORG", "")
            project = os.getenv("AZURE_DEVOPS_PROJECT", "")
            return org, project, parts[0]
        raise ValueError(
            f"Azure DevOps repository must be 'org/project/repo' or "
            f"'repo' (with env vars). Got: {repository!r}"
        )

    def _base(self, org: str, project: str, repo: str) -> str:
        return (
            f"https://dev.azure.com/{org}/{project}/_apis/git/"
            f"repositories/{repo}"
        )

    def _qs(self, **kwargs) -> dict:
        return {"api-version": self.API_VERSION, **kwargs}

    # ------------------------------------------------------------------
    # PullRequestProvider interface
    # ------------------------------------------------------------------

    def get_pull_request(self, repository: str, pull_number: int) -> PullRequest:
        org, project, repo = self._parse_repository(repository)
        url = f"{self._base(org, project, repo)}/pullrequests/{pull_number}"
        response = self.client.get(url, params=self._qs())
        response.raise_for_status()
        data = response.json()
        return PullRequest(
            provider="azure_devops",
            repository=repository,
            number=pull_number,
            title=data.get("title", ""),
            author=data.get("createdBy", {}).get("displayName", "unknown"),
            state=data.get("status", "unknown"),
            base_branch=data.get("targetRefName", "").removeprefix("refs/heads/"),
            head_branch=data.get("sourceRefName", "").removeprefix("refs/heads/"),
            head_commit=data.get("lastMergeSourceCommit", {}).get("commitId", ""),
        )

    def get_changed_files(self, repository: str, pull_number: int) -> list[ChangedFile]:
        org, project, repo = self._parse_repository(repository)
        url = f"{self._base(org, project, repo)}/pullrequests/{pull_number}/iterations"
        response = self.client.get(url, params=self._qs())
        response.raise_for_status()
        iterations = response.json().get("value", [])
        if not iterations:
            return []

        latest_iteration = max(iterations, key=lambda it: it.get("id", 0))
        iteration_id = latest_iteration["id"]

        changes_url = (
            f"{self._base(org, project, repo)}"
            f"/pullrequests/{pull_number}/iterations/{iteration_id}/changes"
        )
        changes_response = self.client.get(changes_url, params=self._qs())
        changes_response.raise_for_status()
        changes_data = changes_response.json().get("changeEntries", [])

        files: list[ChangedFile] = []
        for entry in changes_data:
            item = entry.get("item", {})
            path = item.get("path", "").lstrip("/")
            if not path:
                continue
            change_type = entry.get("changeType", "").lower()
            if change_type in {"none", "delete"}:
                continue
            status = (
                "added" if "add" in change_type
                else "removed" if "delete" in change_type
                else "modified"
            )
            files.append(ChangedFile(file_path=path, status=status, patch=None))
        return files

    def get_file_content(self, repository: str, file_path: str, ref: str) -> str:
        org, project, repo = self._parse_repository(repository)
        url = f"{self._base(org, project, repo)}/items"
        response = self.client.get(
            url,
            params=self._qs(
                path=f"/{file_path}",
                versionDescriptor_version=ref,
                versionDescriptor_versionType="commit",
                **{"$format": "text"},
            ),
        )
        if response.status_code == 404:
            return ""
        response.raise_for_status()
        return response.text

    def get_existing_comments(self, repository: str, pull_number: int) -> list[dict]:
        org, project, repo = self._parse_repository(repository)
        url = f"{self._base(org, project, repo)}/pullrequests/{pull_number}/threads"
        response = self.client.get(url, params=self._qs())
        response.raise_for_status()
        threads = response.json().get("value", [])
        comments: list[dict] = []
        for thread in threads:
            for comment in thread.get("comments", []):
                comments.append(
                    {
                        "id": comment.get("id"),
                        "thread_id": thread.get("id"),
                        "body": comment.get("content", ""),
                        "path": thread.get("threadContext", {})
                        .get("filePath", "")
                        .lstrip("/"),
                        "line": (
                            thread.get("threadContext", {})
                            .get("rightFileEnd", {})
                            .get("line")
                        ),
                    }
                )
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
        org, project, repo = self._parse_repository(repository)
        url = f"{self._base(org, project, repo)}/pullrequests/{pull_number}/threads"
        payload = {
            "comments": [{"parentCommentId": 0, "content": body, "commentType": 1}],
            "status": 1,
            "threadContext": {
                "filePath": f"/{file_path}",
                "rightFileEnd": {"line": line_number, "offset": 1},
                "rightFileStart": {"line": line_number, "offset": 1},
            },
        }
        response = self.client.post(url, params=self._qs(), json=payload)
        response.raise_for_status()
        return response.json()

    def get_summary_comments(self, repository: str, pull_number: int) -> list[dict]:
        org, project, repo = self._parse_repository(repository)
        url = f"{self._base(org, project, repo)}/pullrequests/{pull_number}/threads"
        response = self.client.get(url, params=self._qs())
        response.raise_for_status()
        threads = response.json().get("value", [])
        summary_threads: list[dict] = []
        for thread in threads:
            if thread.get("threadContext") is not None:
                continue
            for comment in thread.get("comments", []):
                content = comment.get("content", "")
                if _REVIEWER_TAG in content:
                    summary_threads.append(
                        {
                            "id": comment.get("id"),
                            "thread_id": thread.get("id"),
                            "body": content,
                        }
                    )
        return summary_threads

    def publish_summary_comment(self, repository: str, pull_number: int, body: str) -> dict:
        org, project, repo = self._parse_repository(repository)
        url = f"{self._base(org, project, repo)}/pullrequests/{pull_number}/threads"
        tagged_body = f"{body}\n\n<!-- {_REVIEWER_TAG} -->"
        payload = {
            "comments": [{"parentCommentId": 0, "content": tagged_body, "commentType": 1}],
            "status": 4,
        }
        response = self.client.post(url, params=self._qs(), json=payload)
        response.raise_for_status()
        return response.json()

    def update_summary_comment(self, repository: str, comment_id: int, body: str) -> dict:
        raise NotImplementedError(
            "Azure DevOps summary comment update requires the thread ID. "
            "Use the SummaryPublishingService which resolves the thread via "
            "get_summary_comments and passes the correct IDs."
        )
