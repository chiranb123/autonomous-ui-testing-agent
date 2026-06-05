from pydantic import BaseModel


class StepResult(BaseModel):
    action: str
    target: str = ""
    value: str = ""
    status: str  # PASSED | FAILED | SKIPPED | INFO
    message: str = ""
    screenshot_path: str | None = None

