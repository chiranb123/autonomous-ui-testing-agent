from pydantic import BaseModel, field_validator


class ExecutionStep(BaseModel):

    action: str

    target: str | None = None

    value: str | None = None

    expected: str | None = None

    verification_type: str | None = None

    original_step: str = ""

    @field_validator("target", "value", "expected", "original_step", mode="before")
    @classmethod
    def coerce_none_to_str(cls, v, info):
        """Convert None to empty string for string fields that must not be None at runtime."""
        if v is None:
            return ""
        return v
