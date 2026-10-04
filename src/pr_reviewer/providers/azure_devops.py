"""Azure DevOps implementation of the provider-neutral PR contract.

Azure DevOps supplies pull-request iterations and file-change metadata rather
than the GitHub-style unified patches consumed by the review engine. This
adapter reconstructs those patches from the iteration's common and source
commits, keeps Azure iteration identifiers for inline thread placement, and
leaves the core review pipeline provider agnostic.
"""

import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import os
from threading import RLock
from urllib.parse import quote, unquote, urlparse

import httpx
from dotenv import load_dotenv

from pr_reviewer.providers.azure_diff import (
    added_line_numbers,
    build_unified_patch,
    changed_file_status,
    normalize_change_types,
)
from pr_reviewer.providers.base import PullRequestProvider
from pr_reviewer.providers.models import PullRequestSummary
from pr_reviewer.review.models import ChangedFile, PullRequest


load_dotenv()

_SUMMARY_MARKER = "<!-- intelligent-pr-reviewer:summary -->"
_MARKDOWN_PROPERTIES = {
    "Microsoft.TeamFoundation.Discussion.SupportsMarkdown": {
        "$type": "System.Int32",
        "$value": 1,
    }
}


@dataclass(frozen=True)
class _IterationContext:
    iteration_id: int
    common_commit: str
    source_commit: str
    target_commit: str


@dataclass(frozen=True)
class _PullRequestChange:
    file_path: str
    original_path: str
    status: str
    change_tracking_id: int


@dataclass(frozen=True)
class _InlineContext:
    iteration_id: int
    change_tracking_id: int
    changed_lines: frozenset[int]


class AzureDevOpsProvider(PullRequestProvider):
    """Azure DevOps REST API 7.1 pull-request provider."""

    API_VERSION = "7.1"
    CHANGE_PAGE_SIZE = 2000
    PR_PAGE_SIZE = 100
    supports_batch_inline_comments = False
    supports_pull_request_listing = True
    supports_deferred_patch_hydration = True
    provider_name = "azure-devops"
    display_name = "Azure DevOps"

    def __init__(
        self,
        organization: str | None = None,
        project: str | None = None,
        pat: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._org = organization or os.getenv("AZURE_DEVOPS_ORG", "")
        self._project = project or os.getenv("AZURE_DEVOPS_PROJECT", "")
        self._cache_lock = RLock()
        self._content_cache: dict[tuple[str, str, str], str | None] = {}
        self._tree_cache: dict[tuple[str, str], tuple[str, ...]] = {}
        self._pr_data_cache: dict[tuple[str, int], dict] = {}
        self._iteration_cache: dict[tuple[str, int], _IterationContext] = {}
        self._pending_changes: dict[
            tuple[str, int], dict[str, _PullRequestChange]
        ] = {}
        self._inline_context: dict[
            tuple[str, int, str], _InlineContext
        ] = {}

        if client is not None:
            self.client = client
            return

        pat = pat or os.getenv("AZURE_DEVOPS_PAT")
        if not pat:
            raise ValueError(
                "AZURE_DEVOPS_PAT is not configured. Add it to your local "
                ".env file; never commit the token."
            )

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
    # URL, response, and cache helpers
    # ------------------------------------------------------------------

    def _parse_repository(self, repository: str) -> tuple[str, str, str]:
        """Return ``(organization, project, repository)``."""

        value = repository.strip()
        if value.startswith(("https://", "http://")):
            parsed = urlparse(value)
            segments = [unquote(part) for part in parsed.path.split("/") if part]
            host = parsed.hostname or ""
            if host.lower() == "dev.azure.com" and len(segments) >= 4:
                if segments[2].lower() == "_git":
                    return segments[0], segments[1], segments[3]
            if host.lower().endswith(".visualstudio.com") and len(segments) >= 3:
                if segments[1].lower() == "_git":
                    return host.split(".", 1)[0], segments[0], segments[2]
            raise ValueError(
                "Azure DevOps repository URL must look like "
                "https://dev.azure.com/org/project/_git/repository."
            )

        parts = [part.strip() for part in value.split("/") if part.strip()]
        if len(parts) == 3:
            return parts[0], parts[1], parts[2]
        if len(parts) == 1:
            if not self._org or not self._project:
                raise ValueError(
                    "Azure DevOps organization and project are required when "
                    "--repository contains only a repository name. Configure "
                    "AZURE_DEVOPS_ORG and AZURE_DEVOPS_PROJECT, or use "
                    "organization/project/repository."
                )
            return self._org, self._project, parts[0]
        raise ValueError(
            "Azure DevOps repository must be "
            "'organization/project/repository', a repository URL, or a single "
            "repository name with AZURE_DEVOPS_ORG/AZURE_DEVOPS_PROJECT. "
            f"Got: {repository!r}"
        )

    def _base(self, org: str, project: str, repo: str) -> str:
        return (
            f"https://dev.azure.com/{quote(org, safe='')}/"
            f"{quote(project, safe='')}/_apis/git/"
            f"repositories/{quote(repo, safe='')}"
        )

    def _qs(self, **kwargs) -> dict:
        return {"api-version": self.API_VERSION, **kwargs}

    @staticmethod
    def _response_detail(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except Exception:
            return (getattr(response, "text", "") or "no response body")[:1000]
        if isinstance(payload, dict):
            message = payload.get("message") or payload.get("error")
            if message:
                return str(message)[:1000]
        return str(payload)[:1000]

    def _raise_for_status(self, response: httpx.Response, operation: str) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            hint = ""
            if status == 401:
                hint = " Check whether AZURE_DEVOPS_PAT is valid and unexpired."
            elif status == 403:
                hint = (
                    " Check repository access and the PAT Code / Pull Request "
                    "Threads permissions."
                )
            elif status == 404:
                hint = (
                    " Check the organization, project, repository, PR ID, and "
                    "file path."
                )
            elif status == 429:
                hint = " Azure DevOps rate-limited the request; retry later."
            detail = self._response_detail(exc.response)
            raise httpx.HTTPStatusError(
                f"Azure DevOps {operation} failed with HTTP {status}: "
                f"{detail}.{hint}",
                request=exc.request,
                response=exc.response,
            ) from exc

    @staticmethod
    def _json_object(response: httpx.Response, operation: str) -> dict:
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError(
                f"Azure DevOps {operation} response was not a JSON object."
            )
        return payload

    @staticmethod
    def _list_value(payload: dict, operation: str) -> list:
        value = payload.get("value", [])
        if not isinstance(value, list):
            raise ValueError(
                f"Azure DevOps {operation} response did not contain a list."
            )
        return value

    @staticmethod
    def _positive_int(value: object, fallback: int = 0) -> int:
        try:
            result = int(value)
        except (TypeError, ValueError):
            return fallback
        return result if result > 0 else fallback

    def _content_workers(self) -> int:
        raw = os.getenv("AZURE_DEVOPS_MAX_CONTENT_WORKERS", "8")
        try:
            value = int(raw)
        except ValueError:
            value = 8
        return max(1, min(value, 16))

    # ------------------------------------------------------------------
    # Pull-request discovery and metadata
    # ------------------------------------------------------------------

    def list_pull_requests(
        self,
        repository: str,
        state: str = "open",
    ) -> list[PullRequestSummary]:
        org, project, repo = self._parse_repository(repository)
        status = "active" if state == "open" else state
        url = f"{self._base(org, project, repo)}/pullrequests"
        summaries: list[PullRequestSummary] = []
        skip = 0

        while True:
            response = self.client.get(
                url,
                params=self._qs(
                    searchCriteria_status=status,
                    searchCriteria_includeLinks="false",
                    **{"$top": self.PR_PAGE_SIZE, "$skip": skip},
                ),
            )
            self._raise_for_status(response, "pull-request listing")
            payload = self._json_object(response, "pull-request listing")
            batch = self._list_value(payload, "pull-request listing")

            for pr in batch:
                if not isinstance(pr, dict):
                    continue
                summaries.append(
                    PullRequestSummary(
                        number=pr.get("pullRequestId", 0),
                        title=pr.get("title", ""),
                        author=pr.get("createdBy", {}).get(
                            "displayName", "unknown"
                        ),
                        base_branch=pr.get("targetRefName", "").removeprefix(
                            "refs/heads/"
                        ),
                        head_branch=pr.get("sourceRefName", "").removeprefix(
                            "refs/heads/"
                        ),
                        state=pr.get("status", ""),
                    )
                )

            if len(batch) < self.PR_PAGE_SIZE:
                break
            skip += len(batch)

        return summaries

    def _get_pull_request_data(self, repository: str, pull_number: int) -> dict:
        key = (repository, pull_number)
        with self._cache_lock:
            cached = self._pr_data_cache.get(key)
        if cached is not None:
            return cached

        org, project, repo = self._parse_repository(repository)
        url = f"{self._base(org, project, repo)}/pullrequests/{pull_number}"
        response = self.client.get(url, params=self._qs())
        self._raise_for_status(response, "pull-request metadata lookup")
        data = self._json_object(response, "pull-request metadata lookup")
        with self._cache_lock:
            self._pr_data_cache[key] = data
        return data

    def get_pull_request(self, repository: str, pull_number: int) -> PullRequest:
        data = self._get_pull_request_data(repository, pull_number)
        head_commit = data.get("lastMergeSourceCommit", {}).get("commitId", "")
        if not head_commit:
            head_commit = self._get_iteration_context(
                repository, pull_number
            ).source_commit
        return PullRequest(
            provider=self.provider_name,
            repository=repository,
            number=pull_number,
            title=data.get("title", ""),
            author=data.get("createdBy", {}).get("displayName", "unknown"),
            state=data.get("status", "unknown"),
            base_branch=data.get("targetRefName", "").removeprefix(
                "refs/heads/"
            ),
            head_branch=data.get("sourceRefName", "").removeprefix(
                "refs/heads/"
            ),
            head_commit=head_commit,
        )

    def _get_iteration_context(
        self,
        repository: str,
        pull_number: int,
    ) -> _IterationContext:
        key = (repository, pull_number)
        with self._cache_lock:
            cached = self._iteration_cache.get(key)
        if cached is not None:
            return cached

        org, project, repo = self._parse_repository(repository)
        url = f"{self._base(org, project, repo)}/pullrequests/{pull_number}/iterations"
        response = self.client.get(url, params=self._qs(includeCommits="false"))
        self._raise_for_status(response, "pull-request iteration lookup")
        payload = self._json_object(response, "pull-request iteration lookup")
        iterations = self._list_value(payload, "pull-request iteration lookup")
        candidates = [item for item in iterations if isinstance(item, dict)]
        if not candidates:
            raise ValueError(
                f"Azure DevOps PR #{pull_number} has no reviewable iterations."
            )

        latest = max(candidates, key=lambda item: item.get("id", 0))
        iteration_id = self._positive_int(latest.get("id"))
        if not iteration_id:
            raise ValueError("Azure DevOps returned an invalid PR iteration ID.")

        source_commit = latest.get("sourceRefCommit", {}).get("commitId", "")
        target_commit = latest.get("targetRefCommit", {}).get("commitId", "")
        common_commit = latest.get("commonRefCommit", {}).get("commitId", "")

        if not source_commit or not target_commit:
            pr_data = self._get_pull_request_data(repository, pull_number)
            source_commit = source_commit or pr_data.get(
                "lastMergeSourceCommit", {}
            ).get("commitId", "")
            target_commit = target_commit or pr_data.get(
                "lastMergeTargetCommit", {}
            ).get("commitId", "")

        if not source_commit:
            raise ValueError(
                "Azure DevOps did not provide the source commit for the latest "
                "pull-request iteration."
            )

        if not common_commit and target_commit:
            common_commit = self._resolve_common_commit(
                repository=repository,
                target_commit=target_commit,
                source_commit=source_commit,
            )
        common_commit = common_commit or target_commit
        if not common_commit:
            raise ValueError(
                "Azure DevOps did not provide a common or target commit for "
                "pull-request diff reconstruction."
            )

        context = _IterationContext(
            iteration_id=iteration_id,
            common_commit=common_commit,
            source_commit=source_commit,
            target_commit=target_commit,
        )
        with self._cache_lock:
            self._iteration_cache[key] = context
        return context

    def _resolve_common_commit(
        self,
        *,
        repository: str,
        target_commit: str,
        source_commit: str,
    ) -> str:
        org, project, repo = self._parse_repository(repository)
        url = f"{self._base(org, project, repo)}/diffs/commits"
        response = self.client.get(
            url,
            params=self._qs(
                baseVersion=target_commit,
                baseVersionType="commit",
                targetVersion=source_commit,
                targetVersionType="commit",
                diffCommonCommit="true",
                **{"$top": 1, "$skip": 0},
            ),
        )
        self._raise_for_status(response, "common-commit lookup")
        return str(
            self._json_object(response, "common-commit lookup").get(
                "commonCommit", ""
            )
        )

    # ------------------------------------------------------------------
    # Changed-file retrieval and patch reconstruction
    # ------------------------------------------------------------------

    def _get_all_change_entries(
        self,
        repository: str,
        pull_number: int,
        iteration_id: int,
    ) -> list[dict]:
        org, project, repo = self._parse_repository(repository)
        url = (
            f"{self._base(org, project, repo)}/pullrequests/{pull_number}"
            f"/iterations/{iteration_id}/changes"
        )
        entries: list[dict] = []
        skip = 0
        top = self.CHANGE_PAGE_SIZE
        visited_skips: set[int] = set()

        while True:
            if skip in visited_skips:
                raise ValueError(
                    "Azure DevOps returned a repeated pagination cursor while "
                    "listing pull-request changes."
                )
            visited_skips.add(skip)
            response = self.client.get(
                url,
                params=self._qs(
                    **{"$top": top, "$skip": skip, "$compareTo": 0}
                ),
            )
            self._raise_for_status(response, "pull-request change listing")
            payload = self._json_object(response, "pull-request change listing")
            batch = payload.get("changeEntries", [])
            if not isinstance(batch, list):
                raise ValueError(
                    "Azure DevOps pull-request changes response did not contain "
                    "a changeEntries list."
                )
            entries.extend(item for item in batch if isinstance(item, dict))

            next_skip = self._positive_int(payload.get("nextSkip"))
            next_top = self._positive_int(payload.get("nextTop"))
            if next_skip:
                skip = next_skip
                top = next_top or self.CHANGE_PAGE_SIZE
                continue
            # Azure explicitly returns zero cursors on the last page. Only use
            # the length fallback for older responses that omit both fields.
            if "nextSkip" in payload or "nextTop" in payload:
                break
            if len(batch) >= top and batch:
                skip += len(batch)
                continue
            break

        return entries

    @staticmethod
    def _map_change(entry: dict) -> _PullRequestChange | None:
        item = entry.get("item", {})
        if not isinstance(item, dict):
            return None
        if item.get("isFolder") is True or str(
            item.get("gitObjectType", "")
        ).lower() == "tree":
            return None

        path = str(item.get("path", "")).strip().lstrip("/")
        change_types = normalize_change_types(entry.get("changeType"))
        if not path or not change_types:
            return None

        status = changed_file_status(change_types)
        original = (
            entry.get("originalPath")
            or item.get("originalPath")
            or (entry.get("sourceServerItem") if status == "renamed" else None)
            or path
        )
        original_path = str(original).strip().lstrip("/") or path
        tracking = AzureDevOpsProvider._positive_int(
            entry.get("changeTrackingId"),
            AzureDevOpsProvider._positive_int(entry.get("changeId")),
        )
        if not tracking:
            raise ValueError(
                f"Azure DevOps did not provide changeTrackingId for {path}."
            )
        return _PullRequestChange(
            file_path=path,
            original_path=original_path,
            status=status,
            change_tracking_id=tracking,
        )

    def _fetch_text_content(
        self,
        repository: str,
        file_path: str,
        ref: str,
        *,
        allow_missing: bool = False,
    ) -> str | None:
        key = (repository, file_path, ref)
        with self._cache_lock:
            if key in self._content_cache:
                return self._content_cache[key]

        org, project, repo = self._parse_repository(repository)
        url = f"{self._base(org, project, repo)}/items"
        response = self.client.get(
            url,
            params=self._qs(
                path=f"/{file_path.lstrip('/')}",
                download="true",
                resolveLfs="false",
                **{
                    "versionDescriptor.version": ref,
                    "versionDescriptor.versionType": "commit",
                    "versionDescriptor.versionOptions": "none",
                },
            ),
            headers={"Accept": "application/octet-stream, text/plain"},
        )
        if getattr(response, "status_code", None) == 404 and allow_missing:
            value: str | None = ""
        else:
            self._raise_for_status(response, f"file-content lookup for {file_path}")
            value = self._decode_text_response(response)

        with self._cache_lock:
            self._content_cache[key] = value
        return value

    @staticmethod
    def _decode_text_response(response: httpx.Response) -> str | None:
        raw = getattr(response, "content", None)
        if not isinstance(raw, (bytes, bytearray)):
            text = getattr(response, "text", "")
            return text if isinstance(text, str) else str(text)

        data = bytes(raw)
        if not data:
            return ""
        try:
            if data.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
                return data.decode("utf-32")
            if data.startswith((b"\xff\xfe", b"\xfe\xff")):
                return data.decode("utf-16")
            if b"\x00" in data[:8192]:
                return None
            return data.decode("utf-8-sig", errors="replace")
        except (LookupError, UnicodeDecodeError):
            return None

    def _prefetch_change_content(
        self,
        repository: str,
        changes: list[_PullRequestChange],
        iteration: _IterationContext,
    ) -> None:
        requests: set[tuple[str, str]] = set()
        for change in changes:
            if change.status != "added":
                requests.add((change.original_path, iteration.common_commit))
            if change.status != "removed":
                requests.add((change.file_path, iteration.source_commit))
        if not requests:
            return

        def fetch(path_and_ref: tuple[str, str]) -> None:
            path, ref = path_and_ref
            self._fetch_text_content(repository, path, ref)

        workers = min(self._content_workers(), len(requests))
        if workers == 1:
            for request in requests:
                fetch(request)
            return

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(fetch, request) for request in requests]
            for future in as_completed(futures):
                future.result()

    def get_changed_files(
        self,
        repository: str,
        pull_number: int,
    ) -> list[ChangedFile]:
        iteration = self._get_iteration_context(repository, pull_number)
        entries = self._get_all_change_entries(
            repository, pull_number, iteration.iteration_id
        )
        changes = [
            change
            for entry in entries
            if (change := self._map_change(entry)) is not None
        ]
        with self._cache_lock:
            self._pending_changes[(repository, pull_number)] = {
                change.file_path: change for change in changes
            }
        return [
            ChangedFile(file_path=change.file_path, status=change.status)
            for change in changes
        ]

    def hydrate_changed_files(
        self,
        repository: str,
        pull_number: int,
        changed_files: list[ChangedFile],
    ) -> list[ChangedFile]:
        """Reconstruct patches only for the review-eligible file subset."""

        key = (repository, pull_number)
        with self._cache_lock:
            change_map = self._pending_changes.get(key)
        if change_map is None:
            self.get_changed_files(repository, pull_number)
            with self._cache_lock:
                change_map = self._pending_changes.get(key, {})

        selected_changes: list[_PullRequestChange] = []
        for changed_file in changed_files:
            change = change_map.get(changed_file.file_path)
            if change is None:
                raise ValueError(
                    f"{changed_file.file_path} is not part of Azure DevOps "
                    f"PR #{pull_number}."
                )
            selected_changes.append(change)

        iteration = self._get_iteration_context(repository, pull_number)
        self._prefetch_change_content(repository, selected_changes, iteration)

        hydrated: list[ChangedFile] = []
        for change in selected_changes:
            old_content = (
                ""
                if change.status == "added"
                else self._fetch_text_content(
                    repository,
                    change.original_path,
                    iteration.common_commit,
                )
            )
            new_content = (
                ""
                if change.status == "removed"
                else self._fetch_text_content(
                    repository,
                    change.file_path,
                    iteration.source_commit,
                )
            )

            patch = None
            if old_content is not None and new_content is not None:
                patch = build_unified_patch(
                    old_content=old_content,
                    new_content=new_content,
                    old_path=change.original_path,
                    new_path=change.file_path,
                )

            hydrated.append(
                ChangedFile(
                    file_path=change.file_path,
                    status=change.status,
                    patch=patch,
                    full_content=new_content,
                )
            )
            with self._cache_lock:
                self._inline_context[
                    (repository, pull_number, change.file_path)
                ] = _InlineContext(
                    iteration_id=iteration.iteration_id,
                    change_tracking_id=change.change_tracking_id,
                    changed_lines=added_line_numbers(patch),
                )

        return hydrated

    # ------------------------------------------------------------------
    # Repository context
    # ------------------------------------------------------------------

    def get_repository_tree(self, repository: str, ref: str) -> list[str]:
        key = (repository, ref)
        with self._cache_lock:
            cached = self._tree_cache.get(key)
        if cached is not None:
            return list(cached)

        org, project, repo = self._parse_repository(repository)
        url = f"{self._base(org, project, repo)}/items"
        response = self.client.get(
            url,
            params=self._qs(
                scopePath="/",
                recursionLevel="Full",
                includeContentMetadata="false",
                includeLinks="false",
                **{
                    "versionDescriptor.version": ref,
                    "versionDescriptor.versionType": "commit",
                    "versionDescriptor.versionOptions": "none",
                },
            ),
        )
        self._raise_for_status(response, "repository-tree lookup")
        payload = self._json_object(response, "repository-tree lookup")
        items = self._list_value(payload, "repository-tree lookup")
        paths = tuple(
            str(item.get("path", "")).lstrip("/")
            for item in items
            if isinstance(item, dict)
            and item.get("path")
            and item.get("isFolder") is not True
            and str(item.get("gitObjectType", "blob")).lower() != "tree"
        )
        with self._cache_lock:
            self._tree_cache[key] = paths
        return list(paths)

    def get_file_content(self, repository: str, file_path: str, ref: str) -> str:
        value = self._fetch_text_content(
            repository, file_path, ref, allow_missing=True
        )
        return value or ""

    # ------------------------------------------------------------------
    # Inline and summary comments
    # ------------------------------------------------------------------

    def _get_threads(self, repository: str, pull_number: int) -> list[dict]:
        org, project, repo = self._parse_repository(repository)
        url = f"{self._base(org, project, repo)}/pullrequests/{pull_number}/threads"
        response = self.client.get(url, params=self._qs())
        self._raise_for_status(response, "pull-request thread listing")
        payload = self._json_object(response, "pull-request thread listing")
        return [
            thread
            for thread in self._list_value(payload, "pull-request thread listing")
            if isinstance(thread, dict) and thread.get("isDeleted") is not True
        ]

    def get_existing_comments(self, repository: str, pull_number: int) -> list[dict]:
        comments: list[dict] = []
        for thread in self._get_threads(repository, pull_number):
            thread_context = thread.get("threadContext") or {}
            # PR-level summaries and Azure system threads are not inline review
            # comments and must not consume the inline-comment cap.
            if not thread_context.get("filePath"):
                continue
            for comment in thread.get("comments", []):
                if not isinstance(comment, dict) or comment.get("isDeleted") is True:
                    continue
                comments.append(
                    {
                        "id": comment.get("id"),
                        "thread_id": thread.get("id"),
                        "body": comment.get("content", ""),
                        "path": str(thread_context.get("filePath", "")).lstrip("/"),
                        "line": (thread_context.get("rightFileEnd") or {}).get(
                            "line"
                        ),
                    }
                )
        return comments

    def _inline_comment_context(
        self,
        repository: str,
        pull_number: int,
        file_path: str,
    ) -> _InlineContext:
        key = (repository, pull_number, file_path.lstrip("/"))
        with self._cache_lock:
            context = self._inline_context.get(key)
        if context is None:
            normalized_path = file_path.lstrip("/")
            pending_key = (repository, pull_number)
            with self._cache_lock:
                pending = self._pending_changes.get(pending_key, {})
                change = pending.get(normalized_path)
            if change is None:
                metadata = self.get_changed_files(repository, pull_number)
                matching = [
                    changed_file
                    for changed_file in metadata
                    if changed_file.file_path == normalized_path
                ]
            else:
                matching = [
                    ChangedFile(
                        file_path=change.file_path,
                        status=change.status,
                    )
                ]
            if matching:
                self.hydrate_changed_files(
                    repository,
                    pull_number,
                    matching,
                )
            with self._cache_lock:
                context = self._inline_context.get(key)
        if context is None:
            raise ValueError(
                f"{file_path} is not part of the current Azure DevOps PR diff."
            )
        return context

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
        del commit_id, diff_position
        context = self._inline_comment_context(
            repository, pull_number, file_path
        )
        if line_number not in context.changed_lines:
            raise ValueError(
                f"{file_path}:{line_number} is not an added line in the current "
                "Azure DevOps PR iteration."
            )

        org, project, repo = self._parse_repository(repository)
        url = f"{self._base(org, project, repo)}/pullrequests/{pull_number}/threads"
        payload = {
            "comments": [
                {"parentCommentId": 0, "content": body, "commentType": 1}
            ],
            "status": 1,
            "threadContext": {
                "filePath": f"/{file_path.lstrip('/')}",
                "rightFileEnd": {"line": line_number, "offset": 1},
                "rightFileStart": {"line": line_number, "offset": 1},
            },
            "pullRequestThreadContext": {
                "changeTrackingId": context.change_tracking_id,
                "iterationContext": {
                    "firstComparingIteration": context.iteration_id,
                    "secondComparingIteration": context.iteration_id,
                },
            },
            "properties": _MARKDOWN_PROPERTIES,
        }
        response = self.client.post(url, params=self._qs(), json=payload)
        self._raise_for_status(response, "inline-comment publishing")
        return self._json_object(response, "inline-comment publishing")

    def get_summary_comments(self, repository: str, pull_number: int) -> list[dict]:
        summaries: list[dict] = []
        for thread in self._get_threads(repository, pull_number):
            if thread.get("threadContext") is not None:
                continue
            for comment in thread.get("comments", []):
                if not isinstance(comment, dict) or comment.get("isDeleted") is True:
                    continue
                content = comment.get("content", "")
                if _SUMMARY_MARKER in content:
                    summaries.append(
                        {
                            "id": comment.get("id"),
                            "thread_id": thread.get("id"),
                            "body": content,
                        }
                    )
        return summaries

    def publish_summary_comment(
        self,
        repository: str,
        pull_number: int,
        body: str,
    ) -> dict:
        org, project, repo = self._parse_repository(repository)
        url = f"{self._base(org, project, repo)}/pullrequests/{pull_number}/threads"
        payload = {
            "comments": [
                {"parentCommentId": 0, "content": body, "commentType": 1}
            ],
            "status": 4,
            "properties": _MARKDOWN_PROPERTIES,
        }
        response = self.client.post(url, params=self._qs(), json=payload)
        self._raise_for_status(response, "summary publishing")
        return self._json_object(response, "summary publishing")

    def update_summary_comment(
        self,
        repository: str,
        comment_id: int,
        body: str,
        pull_number: int | None = None,
        thread_id: int | None = None,
    ) -> dict:
        if pull_number is None or thread_id is None:
            raise ValueError(
                "Azure DevOps summary updates require pull_number and thread_id."
            )
        org, project, repo = self._parse_repository(repository)
        url = (
            f"{self._base(org, project, repo)}/pullrequests/{pull_number}"
            f"/threads/{thread_id}/comments/{comment_id}"
        )
        response = self.client.patch(
            url,
            params=self._qs(),
            json={"content": body},
        )
        self._raise_for_status(response, "summary update")
        return self._json_object(response, "summary update")
