import os
import json
from dataclasses import dataclass
from threading import Lock
import time

import httpx
from dotenv import load_dotenv

from pr_reviewer.context.models import RepositoryContext
from pr_reviewer.llm.base import LLMProvider
from pr_reviewer.llm.models import ReviewResponse
from pr_reviewer.llm.prompt import ReviewPromptBuilder
from pr_reviewer.review.models import ChangedFile


load_dotenv()


@dataclass(frozen=True)
class OllamaCallMetric:
    call_id: int
    files: tuple[str, ...]
    elapsed_seconds: float
    prompt_tokens: int
    generated_tokens: int
    prompt_eval_seconds: float
    generation_seconds: float
    raw_findings: int


class OllamaProvider(LLMProvider):
    """
    Local Ollama-backed LLM provider.

    Responsibilities:

    - Resolve Ollama connection configuration.
    - Build the review prompt.
    - Send the prompt to Ollama.
    - Return the raw model response.

    Review strategy selection is handled by
    ReviewPromptBuilder.

    This keeps the provider focused only on LLM
    communication rather than review-routing logic.
    """

    DEFAULT_BASE_URL = "http://localhost:11434"

    DEFAULT_MODEL = "qwen2.5-coder:7b"

    DEFAULT_CONNECT_TIMEOUT = 10.0

    DEFAULT_READ_TIMEOUT = 300.0
    DEFAULT_NUM_PREDICT = 512
    DEFAULT_KEEP_ALIVE = "15m"
    DEFAULT_MAX_CONCURRENT_REVIEWS = 1

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        read_timeout: float | None = None,
    ):
        self.model = (
            model
            or os.getenv("OLLAMA_MODEL")
            or self.DEFAULT_MODEL
        )

        self.base_url = (
            base_url
            or os.getenv("OLLAMA_BASE_URL")
            or self.DEFAULT_BASE_URL
        )

        configured_timeout = (
            read_timeout
            if read_timeout is not None
            else self._get_read_timeout()
        )

        timeout = httpx.Timeout(
            connect=self.DEFAULT_CONNECT_TIMEOUT,
            read=configured_timeout,
            write=30.0,
            pool=30.0,
        )

        self.num_predict = self._get_positive_int(
            "OLLAMA_NUM_PREDICT",
            self.DEFAULT_NUM_PREDICT,
        )
        self.keep_alive = (
            os.getenv("OLLAMA_KEEP_ALIVE")
            or self.DEFAULT_KEEP_ALIVE
        )
        self.max_concurrent_reviews = self._get_positive_int(
            "OLLAMA_MAX_CONCURRENT_REVIEWS",
            self.DEFAULT_MAX_CONCURRENT_REVIEWS,
        )

        self.client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            limits=httpx.Limits(
                max_connections=8,
                max_keepalive_connections=8,
            ),
        )
        self._metrics_lock = Lock()
        self._metrics: list[OllamaCallMetric] = []
        self._next_call_id = 1

    def reset_call_metrics(self) -> None:
        with self._metrics_lock:
            self._metrics = []
            self._next_call_id = 1

    def call_metrics(self) -> tuple[OllamaCallMetric, ...]:
        with self._metrics_lock:
            return tuple(sorted(self._metrics, key=lambda metric: metric.call_id))

    @property
    def recommended_concurrency(self) -> int:
        """Keep one local model request active unless explicitly tuned.

        Ollama commonly serializes inference for a single loaded model. Sending
        four large prompts concurrently can therefore turn useful parallelism
        into memory pressure and queueing. Advanced users with enough GPU memory
        can opt in through ``OLLAMA_MAX_CONCURRENT_REVIEWS``.
        """

        return self.max_concurrent_reviews

    @property
    def supports_batch_review(self) -> bool:
        return True

    @property
    def recommended_max_attempts(self) -> int:
        """Avoid repeating a multi-minute local inference after a timeout."""

        return self._get_positive_int("OLLAMA_MAX_ATTEMPTS", 1)

    def review(
        self,
        changed_file: ChangedFile,
        repository_context: RepositoryContext,
    ) -> str:
        """
        Review one changed file through Ollama.

        ReviewPromptBuilder automatically determines
        whether the file requires:

        - semantic review
        - test review
        - template review
        - stylesheet review
        - configuration review

        based on the current routing architecture.
        """

        prompt = ReviewPromptBuilder.build_batch(
            changed_files=[changed_file],
            repository_context=repository_context,
            max_code_tokens_per_file=1400,
        )

        return self._generate(prompt, [changed_file.file_path])

    def review_batch(
        self,
        changed_files: list[ChangedFile],
        repository_context: RepositoryContext,
    ) -> str:
        prompt = ReviewPromptBuilder.build_batch(
            changed_files=changed_files,
            repository_context=repository_context,
        )
        return self._generate(
            prompt,
            [changed_file.file_path for changed_file in changed_files],
        )

    def _generate(self, prompt: str, files: list[str]) -> str:
        started = time.perf_counter()
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": self._response_schema(files),
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": 0,
                "num_predict": self.num_predict,
            },
        }
        response = self.client.post("/api/generate", json=payload)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Older Ollama releases accept JSON mode but not a JSON Schema
            # object. Their 400/422 response occurs before model inference, so
            # compatibility fallback does not repeat an expensive generation.
            if exc.response.status_code not in {400, 422}:
                raise
            payload["format"] = "json"
            response = self.client.post("/api/generate", json=payload)
            response.raise_for_status()
        data = response.json()
        elapsed = time.perf_counter() - started
        try:
            parsed_output = json.loads(data["response"])
            raw_findings = len(parsed_output.get("findings", []))
        except (KeyError, TypeError, ValueError):
            raw_findings = 0
        with self._metrics_lock:
            call_id = self._next_call_id
            self._next_call_id += 1
            self._metrics.append(
                OllamaCallMetric(
                    call_id=call_id,
                    files=tuple(files),
                    elapsed_seconds=elapsed,
                    prompt_tokens=int(data.get("prompt_eval_count") or 0),
                    generated_tokens=int(data.get("eval_count") or 0),
                    prompt_eval_seconds=float(data.get("prompt_eval_duration") or 0) / 1_000_000_000,
                    generation_seconds=float(data.get("eval_duration") or 0) / 1_000_000_000,
                    raw_findings=raw_findings,
                )
            )
        return data["response"]

    @staticmethod
    def _response_schema(files: list[str]) -> dict:
        """Build an ownership-safe schema for the current request.

        Single-file providers historically allow an omitted path because the
        reviewer can map the response to its only file. A multi-file response
        has no safe implicit owner, so its path must be one of the exact files
        supplied in that batch.
        """
        schema = ReviewResponse.model_json_schema()
        if len(files) <= 1:
            return schema
        finding = schema["$defs"]["LLMFinding"]
        finding["properties"]["file_path"] = {
            "type": "string",
            "enum": list(dict.fromkeys(files)),
            "title": "File Path",
        }
        required = finding.setdefault("required", [])
        if "file_path" not in required:
            required.append("file_path")
        return schema


    @staticmethod
    def _get_positive_int(
        name: str,
        default: int,
    ) -> int:
        value = os.getenv(name)
        if not value:
            return default
        try:
            parsed = int(value)
        except ValueError:
            return default
        return parsed if parsed > 0 else default

    @classmethod
    def _get_read_timeout(
        cls,
    ) -> float:
        """
        Resolve Ollama read timeout from environment.

        Invalid or missing values safely fall back to
        DEFAULT_READ_TIMEOUT.
        """

        value = os.getenv(
            "OLLAMA_READ_TIMEOUT"
        )

        if not value:
            return cls.DEFAULT_READ_TIMEOUT

        try:
            return float(
                value
            )

        except ValueError:
            return cls.DEFAULT_READ_TIMEOUT
