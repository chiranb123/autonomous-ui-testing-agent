from pydantic import BaseModel
from typing import List

from models.execution_step import ExecutionStep


class ExecutionPlan(BaseModel):

    scenario_name: str

    steps: List[ExecutionStep]