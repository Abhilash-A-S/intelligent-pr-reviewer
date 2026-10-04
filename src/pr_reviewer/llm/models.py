from pydantic import BaseModel, Field

from pr_reviewer.review.models import Severity


class LLMFinding(BaseModel):
    file_path: str | None = None
    line_number: int = Field(gt=0)
    severity: Severity
    rule_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    suggestion: str | None = None


class ReviewResponse(BaseModel):
    findings: list[LLMFinding] = Field(max_length=5)
