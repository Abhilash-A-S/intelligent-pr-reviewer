from dataclasses import dataclass
from enum import Enum

from pr_reviewer.review.models import Severity


class RuleOwner(str, Enum):
    """Authoritative source for a rule family."""

    STATIC = "static"
    FRAMEWORK = "framework"
    COMPILER = "compiler"
    AI = "ai"
    SHARED = "shared"


class AIPolicy(str, Enum):
    """Whether an LLM may create an independent finding for a rule."""

    BLOCK = "block"
    VALIDATE = "validate"


@dataclass(frozen=True)
class RuleDefinition:
    """
    Technology-agnostic rule metadata.

    The core registry deliberately does not contain language names. Specific
    analyzers/adapters decide whether they can produce evidence for a rule.
    """

    rule_id: str
    category: str
    owner: RuleOwner
    ai_policy: AIPolicy
    max_severity: Severity | None = None
    minimum_severity: Severity | None = None
    aliases: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
