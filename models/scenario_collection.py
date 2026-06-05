from pydantic import BaseModel
from typing import List

from models.scenario import Scenario


class ScenarioCollection(BaseModel):
    scenarios: List[Scenario]