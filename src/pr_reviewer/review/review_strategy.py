from enum import Enum


class ReviewStrategy(str, Enum):
    """
    Describes the type of semantic review that should
    be performed for a changed file.

    The strategy is intentionally separate from
    FileCategory.

    FileCategory answers:

        "What kind of file is this?"

    ReviewStrategy answers:

        "How should the LLM review this file?"

    This separation allows routing behavior to evolve
    independently from file classification.
    """

    SEMANTIC = "semantic"

    TEST = "test"

    TEMPLATE = "template"

    STYLESHEET = "stylesheet"

    CONFIGURATION = "configuration"

    SKIP = "skip"