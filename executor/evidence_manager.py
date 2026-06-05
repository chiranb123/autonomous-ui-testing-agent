from pathlib import Path
from datetime import datetime


class EvidenceManager:

    def __init__(self):

        project_root = (
            Path(__file__)
            .resolve()
            .parent.parent
        )

        self.screenshot_dir = (
            project_root /
            "tests" /
            "evidence" /
            "screenshots"
        )

        self.screenshot_dir.mkdir(
            parents=True,
            exist_ok=True
        )

    def screenshot_name(
            self,
            scenario_name
    ):

        timestamp = (
            datetime.now()
            .strftime("%Y%m%d_%H%M%S")
        )

        return str(
            self.screenshot_dir /
            f"{scenario_name}_{timestamp}.png"
        )