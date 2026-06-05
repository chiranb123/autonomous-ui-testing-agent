import json

from pathlib import Path
from string import Template
from models.requirement_analysis import RequirementAnalysis


class RequirementAnalyzer:

    def __init__(
            self,
            provider
    ):

        self.provider = provider

    def analyze(
            self,
            user_story,
            acceptance_criteria
    ):

        prompt_path = (
            Path(__file__).parent.parent
            / "prompts"
            / "requirement_analysis_prompt.txt"
        )

        prompt = prompt_path.read_text(
            encoding="utf-8"
        )
        template = Template(prompt)
        prompt = template.substitute(
            user_story=user_story,
            acceptance_criteria=acceptance_criteria
        )

        response = self.provider.generate(
            prompt
        )

        data = json.loads(
            response
        )

        return RequirementAnalysis(
            **data
        )