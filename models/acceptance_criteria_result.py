from pydantic import BaseModel


class AcceptanceCriteriaResult(
    BaseModel
):

    ac_id: str

    description: str

    status: str

    related_scenarios: list[str] = []

    evidence: list[str] = []