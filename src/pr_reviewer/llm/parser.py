import json
import re

from pydantic import ValidationError

from pr_reviewer.llm.models import ReviewResponse


class LLMResponseParser:
    """
    Converts raw LLM output into a validated ReviewResponse.

    Responsibilities:
    - Reject empty responses.
    - Remove Markdown code fences.
    - Extract JSON when the model adds surrounding text.
    - Parse JSON safely.
    - Validate the response against ReviewResponse.

    Retry behavior does NOT belong here.
    LLMReviewer owns retries because it owns the LLM call.
    """

    @staticmethod
    def parse(
        response: str,
    ) -> ReviewResponse:

        if not response:
            raise ValueError(
                "LLM response is empty."
            )

        cleaned_response = (
            response.strip()
        )

        if not cleaned_response:
            raise ValueError(
                "LLM response is empty."
            )

        cleaned_response = (
            LLMResponseParser
            ._remove_code_fences(
                cleaned_response
            )
        )

        cleaned_response = (
            LLMResponseParser
            ._extract_json_object(
                cleaned_response
            )
        )

        try:
            data = json.loads(cleaned_response)
        except json.JSONDecodeError as exc:
            data = LLMResponseParser._recover_truncated_findings(cleaned_response)
            if data is None:
                raise ValueError(
                    "LLM response is not valid JSON."
                ) from exc

        if isinstance(data, dict) and "findings" in data and isinstance(data["findings"], list):
            data["findings"] = data["findings"][:3]

        try:
            return (
                ReviewResponse
                .model_validate(data)
            )
        except ValidationError as exc:
            raise ValueError(
                "LLM response does not match "
                "the expected review schema."
            ) from exc

    @staticmethod
    def _remove_code_fences(
        response: str,
    ) -> str:
        """
        Handles responses such as:

        ```json
        {"findings": []}
        ```

        and:

        ```
        {"findings": []}
        ```
        """

        cleaned = response.strip()

        cleaned = re.sub(
            r"^```(?:json)?\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )

        cleaned = re.sub(
            r"\s*```$",
            "",
            cleaned,
        )

        return cleaned.strip()

    @staticmethod
    def _extract_json_object(
        response: str,
    ) -> str:
        """
        Extract the outer JSON object when an LLM adds
        harmless text around the requested JSON.

        Example:

        Here is the review:
        {"findings": []}

        becomes:

        {"findings": []}

        This deliberately does NOT attempt to repair
        malformed JSON. A malformed response should fail
        parsing so LLMReviewer can retry the LLM request.
        """

        response = response.strip()

        if (
            response.startswith("{")
            and response.endswith("}")
        ):
            return response

        first_brace = response.find("{")
        last_brace = response.rfind("}")

        if (
            first_brace == -1
            or last_brace == -1
            or first_brace >= last_brace
        ):
            return response

        return response[
            first_brace:last_brace + 1
        ]

    @staticmethod
    def _recover_truncated_findings(response: str) -> dict | None:
        """Recover only complete objects from a truncated findings array.

        Local models can hit their output-token boundary after emitting one or
        more complete finding objects. This recovery never edits a finding,
        closes partial JSON, or accepts surrounding prose. The normal Pydantic
        schema still validates every recovered object afterward.
        """
        match = re.search(r'\{\s*"findings"\s*:\s*\[', response)
        if not match:
            return None
        decoder = json.JSONDecoder()
        position = match.end()
        recovered: list[dict] = []
        while position < len(response):
            while position < len(response) and response[position] in " \t\r\n,":
                position += 1
            if position >= len(response):
                break
            if response[position] == "]":
                # A closed array followed by malformed content is not a
                # token-boundary truncation and must remain rejected.
                return None
            if response[position] != "{":
                break
            try:
                value, end = decoder.raw_decode(response, position)
            except json.JSONDecodeError:
                break
            if not isinstance(value, dict):
                return None
            recovered.append(value)
            position = end
        return {"findings": recovered} if recovered else None
