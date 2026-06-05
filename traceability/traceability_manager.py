from models.acceptance_criteria_result import (
    AcceptanceCriteriaResult
)


class TraceabilityManager:

    def build(
            self,
            scenarios,
            execution_results
    ):

        results = []

        for scenario, execution in zip(
                scenarios,
                execution_results
        ):

            for ac in scenario.acceptance_criteria:

                results.append(
                    AcceptanceCriteriaResult(
                        ac_id=ac,
                        description=ac,
                        status=execution.status,
                        related_scenarios=[
                            scenario.title
                        ],
                        evidence=[
                            execution.screenshot_path
                        ] if execution.screenshot_path else []
                    )
                )

        return results