from abc import ABC, abstractmethod

from pr_reviewer.context.models import RepositoryContext
from pr_reviewer.review.models import ChangedFile


class LLMProvider(ABC):
    """
    Base interface for all LLM providers.

    Implementations may include:
    - Ollama / Qwen
    - OpenAI
    - Azure OpenAI
    - Anthropic
    - Gemini
    - Other future providers

    The review engine should depend only on this interface.
    """

    @property
    def recommended_concurrency(self) -> int | None:
        """Return a provider-specific safe concurrency recommendation.

        ``None`` keeps the orchestrator's generic default. Local providers can
        override this because parallel HTTP requests do not imply parallel
        model inference and can severely increase latency through contention.
        """

        return None

    @property
    def supports_batch_review(self) -> bool:
        return False

    def review_batch(
        self,
        changed_files: list[ChangedFile],
        repository_context: RepositoryContext,
    ) -> str:
        """Review a compatible file batch when the provider supports it."""

        raise NotImplementedError

    @abstractmethod
    def review(
        self,
        changed_file: ChangedFile,
        repository_context: RepositoryContext,
    ) -> str:
        """
        Review a changed file and return the raw LLM response.

        The provider is responsible only for communicating with
        the model.

        Parsing and converting the response into Findings belongs
        to another layer.
        """
        raise NotImplementedError
