from pydantic import BaseModel


class VerificationResult(BaseModel):

    passed: bool

    expected: str

    actual: str

    message: str