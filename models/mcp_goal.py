from pydantic import BaseModel


class MCPGoal(BaseModel):

    action: str

    instruction: str