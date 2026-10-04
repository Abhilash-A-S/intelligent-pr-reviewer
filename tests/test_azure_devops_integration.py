from unittest.mock import Mock

import httpx
import pytest

from pr_reviewer.providers.azure_devops import AzureDevOpsProvider
from pr_reviewer.publishing.service import PublishingService
from pr_reviewer.review.diff_parser import DiffParser
from pr_reviewer.review.models import Finding, Severity
from pr_reviewer.review.orchestrator import ReviewOrchestrator


REPOSITORY = "acme/platform/reviewer"


def json_response(payload, status=200, url="https://dev.azure.com/test"):
    return httpx.Response(
        status,
        json=payload,
        request=httpx.Request("GET", url),
    )


def content_response(content: bytes, status=200):
    return httpx.Response(
        status,
        content=content,
        request=httpx.Request("GET", "https://dev.azure.com/content"),
    )


def iteration_payload(common="base", source="head", target="target"):
    return {
        "value": [
            {
                "id": 1,
                "commonRefCommit": {"commitId": "older-base"},
                "sourceRefCommit": {"commitId": "older-head"},
                "targetRefCommit": {"commitId": "older-target"},
            },
            {
                "id": 2,
                "commonRefCommit": {"commitId": common},
                "sourceRefCommit": {"commitId": source},
                "targetRefCommit": {"commitId": target},
            },
        ]
    }


class AzureApiStub:
    def __init__(self):
        self.get_calls = []
        self.post_calls = []
        self.patch_calls = []
        self.threads = {"value": []}
        self.contents = {
            ("/src/edit.py", "base"): b"first\nsafe = True\n",
            ("/src/edit.py", "head"): b"first\nprint('debug')\n",
            ("/src/new.py", "head"): b"name = 'new'\nprint(name)\n",
            ("/src/old.py", "base"): b"value = 1\n",
            ("/src/renamed.py", "head"): b"value = 2\n",
            ("/src/deleted.py", "base"): b"obsolete = True\n",
            ("/assets/image.bin", "head"): b"\x00\x01binary",
        }
        self.pages = {
            0: {
                "changeEntries": [
                    {
                        "changeTrackingId": 1,
                        "changeId": 1,
                        "changeType": "add",
                        "item": {"path": "/src/new.py", "gitObjectType": "blob"},
                    },
                    {
                        "changeTrackingId": 2,
                        "changeId": 2,
                        "changeType": "edit",
                        "item": {"path": "/src/edit.py", "gitObjectType": "blob"},
                    },
                    {
                        "changeTrackingId": 3,
                        "changeId": 3,
                        "changeType": "edit, rename",
                        "originalPath": "/src/old.py",
                        "item": {
                            "path": "/src/renamed.py",
                            "gitObjectType": "blob",
                        },
                    },
                ],
                "nextSkip": 3,
                "nextTop": 3,
            },
            3: {
                "changeEntries": [
                    {
                        "changeTrackingId": 4,
                        "changeId": 4,
                        "changeType": "delete",
                        "item": {
                            "path": "/src/deleted.py",
                            "gitObjectType": "blob",
                        },
                    },
                    {
                        "changeTrackingId": 5,
                        "changeId": 5,
                        "changeType": "add",
                        "item": {
                            "path": "/assets/image.bin",
                            "gitObjectType": "blob",
                        },
                    },
                    {
                        "changeTrackingId": 6,
                        "changeId": 6,
                        "changeType": "add",
                        "item": {
                            "path": "/src/folder",
                            "gitObjectType": "tree",
                            "isFolder": True,
                        },
                    },
                ],
                "nextSkip": 0,
                "nextTop": 0,
            },
        }

    def get(self, url, params=None, headers=None):
        params = params or {}
        self.get_calls.append((url, params, headers))
        if url.endswith("/pullrequests/7/iterations"):
            return json_response(iteration_payload())
        if url.endswith("/pullrequests/7/iterations/2/changes"):
            return json_response(self.pages[int(params.get("$skip", 0))])
        if url.endswith("/items") and params.get("recursionLevel") == "Full":
            return json_response(
                {
                    "value": [
                        {"path": "/src", "isFolder": True, "gitObjectType": "tree"},
                        {"path": "/src/new.py", "gitObjectType": "blob"},
                        {"path": "/pyproject.toml", "gitObjectType": "blob"},
                    ]
                }
            )
        if url.endswith("/items"):
            key = (params["path"], params["versionDescriptor.version"])
            if key not in self.contents:
                return content_response(b"missing", status=404)
            return content_response(self.contents[key])
        if url.endswith("/pullrequests/7/threads"):
            return json_response(self.threads)
        if url.endswith("/pullrequests/7"):
            return json_response(
                {
                    "title": "Azure integration",
                    "createdBy": {"displayName": "Developer"},
                    "status": "active",
                    "targetRefName": "refs/heads/main",
                    "sourceRefName": "refs/heads/feature/azure",
                    "lastMergeSourceCommit": {"commitId": "head"},
                    "lastMergeTargetCommit": {"commitId": "target"},
                }
            )
        raise AssertionError(f"Unexpected GET {url} {params}")

    def post(self, url, params=None, json=None):
        self.post_calls.append((url, params, json))
        return json_response({"id": 91, "comments": [{"id": 1}]})

    def patch(self, url, params=None, json=None):
        self.patch_calls.append((url, params, json))
        return json_response({"id": 3, "content": json["content"]})


def provider_with_stub():
    stub = AzureApiStub()
    client = Mock()
    client.get.side_effect = stub.get
    client.post.side_effect = stub.post
    client.patch.side_effect = stub.patch
    return AzureDevOpsProvider(client=client), stub, client


def test_changed_files_are_paginated_and_reconstructed_for_all_change_types():
    provider, stub, _client = provider_with_stub()

    metadata = provider.get_changed_files(REPOSITORY, 7)
    files = provider.hydrate_changed_files(REPOSITORY, 7, metadata)

    assert [(file.file_path, file.status) for file in files] == [
        ("src/new.py", "added"),
        ("src/edit.py", "modified"),
        ("src/renamed.py", "renamed"),
        ("src/deleted.py", "removed"),
        ("assets/image.bin", "added"),
    ]
    parsed = {
        file.file_path: DiffParser().parse_file(file).changed_lines
        for file in files
    }
    assert [line.line_number for line in parsed["src/new.py"]] == [1, 2]
    assert [line.line_number for line in parsed["src/edit.py"]] == [2]
    assert [line.line_number for line in parsed["src/renamed.py"]] == [1]
    assert parsed["src/deleted.py"] == []
    assert parsed["assets/image.bin"] == []

    change_calls = [
        params
        for url, params, _headers in stub.get_calls
        if url.endswith("/iterations/2/changes")
    ]
    assert [call["$skip"] for call in change_calls] == [0, 3]
    assert all(call["$compareTo"] == 0 for call in change_calls)


def test_head_content_is_cached_after_patch_reconstruction():
    provider, stub, _client = provider_with_stub()
    metadata = provider.get_changed_files(REPOSITORY, 7)
    provider.hydrate_changed_files(REPOSITORY, 7, metadata)
    before = len([call for call in stub.get_calls if call[0].endswith("/items")])

    content = provider.get_file_content(REPOSITORY, "src/new.py", "head")

    after = len([call for call in stub.get_calls if call[0].endswith("/items")])
    assert content == "name = 'new'\nprint(name)\n"
    assert after == before


def test_repository_tree_uses_pr_head_commit_and_returns_only_files():
    provider, stub, _client = provider_with_stub()

    paths = provider.get_repository_tree(REPOSITORY, "head")

    assert paths == ["src/new.py", "pyproject.toml"]
    tree_call = next(
        params
        for url, params, _headers in stub.get_calls
        if url.endswith("/items") and params.get("recursionLevel") == "Full"
    )
    assert tree_call["versionDescriptor.version"] == "head"
    assert tree_call["versionDescriptor.versionType"] == "commit"


def test_inline_comment_contains_iteration_and_change_tracking_context():
    provider, stub, _client = provider_with_stub()
    metadata = provider.get_changed_files(REPOSITORY, 7)
    provider.hydrate_changed_files(REPOSITORY, 7, metadata)

    provider.publish_inline_comment(
        repository=REPOSITORY,
        pull_number=7,
        body="Review",
        commit_id="head",
        file_path="src/edit.py",
        line_number=2,
    )

    payload = stub.post_calls[-1][2]
    assert payload["threadContext"]["filePath"] == "/src/edit.py"
    assert payload["threadContext"]["rightFileStart"]["line"] == 2
    assert payload["pullRequestThreadContext"] == {
        "changeTrackingId": 2,
        "iterationContext": {
            "firstComparingIteration": 2,
            "secondComparingIteration": 2,
        },
    }


def test_inline_comment_fails_closed_for_unchanged_line():
    provider, stub, _client = provider_with_stub()
    metadata = provider.get_changed_files(REPOSITORY, 7)
    provider.hydrate_changed_files(REPOSITORY, 7, metadata)

    with pytest.raises(ValueError, match="not an added line"):
        provider.publish_inline_comment(
            repository=REPOSITORY,
            pull_number=7,
            body="Review",
            commit_id="head",
            file_path="src/edit.py",
            line_number=1,
        )

    assert stub.post_calls == []


def test_deleted_threads_and_comments_do_not_block_duplicate_logic():
    provider, stub, _client = provider_with_stub()
    stub.threads = {
        "value": [
            {
                "id": 1,
                "isDeleted": True,
                "threadContext": {"filePath": "/src/edit.py"},
                "comments": [{"id": 1, "content": "ignored"}],
            },
            {
                "id": 2,
                "threadContext": {"filePath": "/src/edit.py"},
                "comments": [
                    {"id": 1, "content": "deleted", "isDeleted": True},
                    {"id": 2, "content": "active", "isDeleted": False},
                ],
            },
        ]
    }

    assert provider.get_existing_comments(REPOSITORY, 7) == [
        {
            "id": 2,
            "thread_id": 2,
            "body": "active",
            "path": "src/edit.py",
            "line": None,
        }
    ]


def test_summary_thread_is_not_returned_as_an_inline_comment():
    provider, stub, _client = provider_with_stub()
    stub.threads = {
        "value": [
            {
                "id": 30,
                "threadContext": None,
                "comments": [
                    {
                        "id": 1,
                        "content": (
                            "<!-- intelligent-pr-reviewer:summary -->\nSummary"
                        ),
                    }
                ],
            }
        ]
    }

    assert provider.get_existing_comments(REPOSITORY, 7) == []
    assert provider.get_summary_comments(REPOSITORY, 7) == [
        {
            "id": 1,
            "thread_id": 30,
            "body": "<!-- intelligent-pr-reviewer:summary -->\nSummary",
        }
    ]


def test_azure_duplicate_marker_skips_second_publish():
    provider, stub, _client = provider_with_stub()
    provider.get_changed_files(REPOSITORY, 7)
    stub.threads = {
        "value": [
            {
                "id": 12,
                "threadContext": {
                    "filePath": "/src/edit.py",
                    "rightFileEnd": {"line": 2},
                },
                "comments": [
                    {
                        "id": 1,
                        "content": (
                            "<!-- intelligent-pr-reviewer:no-console:"
                            "src/edit.py:2 -->\nExisting"
                        ),
                    }
                ],
            }
        ]
    }
    result = PublishingService(provider).publish_findings(
        repository=REPOSITORY,
        pull_number=7,
        commit_id="head",
        findings=[
            Finding(
                file_path="src/edit.py",
                line_number=2,
                severity=Severity.LOW,
                rule_id="no-console",
                message="Debug output.",
            )
        ],
    )

    assert result.published_count == 0
    assert result.skipped_duplicates == 1
    assert stub.post_calls == []


def test_repository_urls_are_accepted():
    provider = AzureDevOpsProvider(client=Mock())

    assert provider._parse_repository(
        "https://dev.azure.com/acme/Platform%20App/_git/reviewer"
    ) == ("acme", "Platform App", "reviewer")
    assert provider._parse_repository(
        "https://acme.visualstudio.com/Platform/_git/reviewer"
    ) == ("acme", "Platform", "reviewer")


def test_pull_request_listing_uses_all_pages():
    client = Mock()
    provider = AzureDevOpsProvider(client=client)
    provider.PR_PAGE_SIZE = 2
    first = {
        "value": [
            {
                "pullRequestId": 1,
                "title": "One",
                "createdBy": {"displayName": "A"},
                "targetRefName": "refs/heads/main",
                "sourceRefName": "refs/heads/one",
                "status": "active",
            },
            {
                "pullRequestId": 2,
                "title": "Two",
                "createdBy": {"displayName": "B"},
                "targetRefName": "refs/heads/main",
                "sourceRefName": "refs/heads/two",
                "status": "active",
            },
        ]
    }
    second = {
        "value": [
            {
                "pullRequestId": 3,
                "title": "Three",
                "createdBy": {"displayName": "C"},
                "targetRefName": "refs/heads/main",
                "sourceRefName": "refs/heads/three",
                "status": "active",
            }
        ]
    }
    client.get.side_effect = [json_response(first), json_response(second)]

    result = provider.list_pull_requests(REPOSITORY)

    assert [summary.number for summary in result] == [1, 2, 3]
    assert [call.kwargs["params"]["$skip"] for call in client.get.call_args_list] == [
        0,
        2,
    ]


def test_permission_failure_has_actionable_azure_message():
    client = Mock()
    client.get.return_value = json_response(
        {"message": "Access denied"}, status=403
    )
    provider = AzureDevOpsProvider(client=client)

    with pytest.raises(httpx.HTTPStatusError, match="PAT Code"):
        provider.get_repository_tree(REPOSITORY, "head")


def test_missing_context_file_returns_empty_string_without_failing_review():
    provider, _stub, _client = provider_with_stub()

    assert provider.get_file_content(REPOSITORY, "missing.html", "head") == ""


def test_common_commit_is_resolved_when_iteration_omits_it():
    client = Mock()

    def get(url, params=None, headers=None):
        if url.endswith("/iterations"):
            return json_response(iteration_payload(common=""))
        if url.endswith("/diffs/commits"):
            return json_response({"commonCommit": "resolved-base"})
        raise AssertionError(url)

    client.get.side_effect = get
    provider = AzureDevOpsProvider(client=client)

    context = provider._get_iteration_context(REPOSITORY, 7)

    assert context.common_commit == "resolved-base"


def test_no_iterations_fails_with_clear_message():
    client = Mock()
    client.get.return_value = json_response({"value": []})
    provider = AzureDevOpsProvider(client=client)

    with pytest.raises(ValueError, match="no reviewable iterations"):
        provider.get_changed_files(REPOSITORY, 7)


def test_full_orchestrator_reviews_reconstructed_azure_patch():
    stub = AzureApiStub()
    stub.pages = {
        0: {
            "changeEntries": [
                {
                    "changeTrackingId": 9,
                    "changeId": 9,
                    "changeType": "edit",
                    "item": {"path": "/src/app.js", "gitObjectType": "blob"},
                },
                {
                    "changeTrackingId": 10,
                    "changeId": 10,
                    "changeType": "add",
                    "item": {"path": "/README.md", "gitObjectType": "blob"},
                },
            ],
            "nextSkip": 0,
            "nextTop": 0,
        }
    }
    stub.contents = {
        ("/src/app.js", "base"): b"const value = 1;\n",
        ("/src/app.js", "head"): b"const value = 1;\nconsole.log(value);\n",
    }
    client = Mock()
    client.get.side_effect = stub.get
    client.post.side_effect = stub.post
    client.patch.side_effect = stub.patch
    provider = AzureDevOpsProvider(client=client)
    llm = Mock()
    llm.review.return_value = '{"findings": []}'

    result = ReviewOrchestrator(provider=provider, llm_provider=llm).run(
        repository=REPOSITORY,
        pull_number=7,
        publish=False,
    )

    assert result.pull_request.provider == "azure-devops"
    assert result.diagnostics.changed_files == 2
    assert result.diagnostics.ai_review_files == 0
    assert result.diagnostics.semantic_skipped_files == 1
    assert {(finding.file_path, finding.line_number, finding.rule_id) for finding in result.findings} == {
        ("src/app.js", 2, "no-console")
    }
    assert not any(
        params.get("path") == "/README.md"
        for _url, params, _headers in stub.get_calls
    )
