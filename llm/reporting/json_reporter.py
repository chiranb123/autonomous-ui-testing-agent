import json
from pathlib import Path
from datetime import datetime


class JsonReporter:

    def __init__(self):

        self.report_dir = Path(
            "evidence/reports"
        )

        self.report_dir.mkdir(
            parents=True,
            exist_ok=True
        )

    def generate(
            self,
            execution_result
    ):

        timestamp = (
            datetime.now()
            .strftime("%Y%m%d_%H%M%S")
        )

        report_path = (
            self.report_dir /
            f"{execution_result.scenario_name}_{timestamp}.json"
        )

        with open(
                report_path,
                "w",
                encoding="utf-8"
        ) as file:

            json.dump(
                execution_result.model_dump(),
                file,
                indent=4
            )

        return str(
            report_path
        )