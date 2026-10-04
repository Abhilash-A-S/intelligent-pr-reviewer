import re
from collections.abc import Iterable

from pr_reviewer.review.rules.models import RuleDefinition


class RuleRegistry:
    """Central canonical rule and alias registry."""

    def __init__(self, definitions: Iterable[RuleDefinition] = ()):
        self._definitions: dict[str, RuleDefinition] = {}
        self._aliases: dict[str, str] = {}

        for definition in definitions:
            self.register(definition)

    @staticmethod
    def normalize_token(rule_id: str) -> str:
        normalized = rule_id.strip().lower()
        normalized = re.sub(r"[\s_]+", "-", normalized)
        normalized = re.sub(r"-+", "-", normalized)
        return normalized.strip("-")

    def register(self, definition: RuleDefinition) -> None:
        canonical = self.normalize_token(definition.rule_id)
        self._definitions[canonical] = definition
        self._aliases[canonical] = canonical

        for alias in definition.aliases:
            self._aliases[self.normalize_token(alias)] = canonical

    def resolve(self, rule_id: str) -> str:
        token = self.normalize_token(rule_id)
        return self._aliases.get(token, token)

    def get(self, rule_id: str) -> RuleDefinition | None:
        return self._definitions.get(self.resolve(rule_id))

    def is_registered(self, rule_id: str) -> bool:
        return self.get(rule_id) is not None

    def definitions(self) -> tuple[RuleDefinition, ...]:
        return tuple(self._definitions.values())

    def ai_creatable_rule_ids(self) -> tuple[str, ...]:
        return tuple(
            definition.rule_id
            for definition in self._definitions.values()
            if definition.ai_policy.value == "validate"
        )
