from models.mcp_goal import MCPGoal


class MCPGoalTranslator:

    def translate(self, execution_step):

        if execution_step.action == "navigate":

            return MCPGoal(
                action="navigate",
                instruction=
                f"Navigate to the "
                f"{execution_step.target}"
            )

        if execution_step.action == "type":

            return MCPGoal(
                action="type",
                instruction=
                f"Enter "
                f"{execution_step.value} "
                f"into the "
                f"{execution_step.target}"
            )

        if execution_step.action == "click":

            return MCPGoal(
                action="click",
                instruction=
                f"Click the "
                f"{execution_step.target}"
            )

        if execution_step.action == "verify":

            return MCPGoal(
                action="verify",
                instruction=
                f"Verify "
                f"{execution_step.target}"
            )

        return MCPGoal(
            action="unknown",
            instruction=
            execution_step.original_step
        )