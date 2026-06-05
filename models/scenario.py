from pydantic import BaseModel
from typing import List


class Scenario(BaseModel):

    title: str

    scenario_type: str

    acceptance_criteria: List[str]

    gherkin: str