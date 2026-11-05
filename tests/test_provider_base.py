import pytest

from pr_reviewer.providers.base import PullRequestProvider


def test_pull_request_provider_cannot_be_instantiated():
    with pytest.raises(TypeError):
        PullRequestProvider()