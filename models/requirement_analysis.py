from pydantic import BaseModel, ConfigDict, field_validator
from typing import List


class RequirementAnalysis(BaseModel):

    model_config = ConfigDict(extra="ignore")

    feature_name: str
    business_goal: str
    user_actions: List[str]
    expected_outcomes: List[str]
    validations: List[str]
    edge_cases: List[str]
    assumptions: List[str]

    @field_validator(
        "user_actions", "expected_outcomes", "validations",
        "edge_cases", "assumptions",
        mode="before"
    )
    @classmethod
    def flatten_to_strings(cls, v):
        """
        LLMs sometimes return list items as dicts instead of strings.
        Coerce any dict or non-string to its string representation.
        """
        if not isinstance(v, list):
            return v
        result = []
        for item in v:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict):
                # Join all dict values into one readable string
                result.append(
                    " — ".join(str(val) for val in item.values() if val)
                )
            else:
                result.append(str(item))
        return result
