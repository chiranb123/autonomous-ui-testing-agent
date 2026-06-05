from pydantic import BaseModel

from models.verification_result import VerificationResult
from models.step_result import StepResult


class ExecutionResult(BaseModel):

    scenario_name: str

    status: str

    screenshot_path: str | None = None

    error_message: str | None = None

    verifications: list[
        VerificationResult
    ] = []

    step_results: list[
        StepResult
    ] = []

    duration_seconds: float = 0.0
