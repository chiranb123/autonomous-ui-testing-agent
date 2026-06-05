import json

from pathlib import Path
from string import Template

from models.scenario_collection import ScenarioCollection


class ScenarioGeneratorAgent:

    def __init__(self, provider):
        self.provider = provider

    def generate(self, requirement_analysis):

        prompt_path = (
                Path(__file__).parent.parent
                / "prompts"
                / "scenario_generation_prompt.txt"
        )

        prompt = prompt_path.read_text(
            encoding="utf-8"
        )

        prompt = Template(prompt).substitute(
            requirement_analysis=
            requirement_analysis.model_dump_json(
                indent=2
            )
        )

        response = self.provider.generate(
            prompt
        )

        response = (
            response
            .replace("```json", "")
            .replace("```", "")
            .strip()
        )

        print("\n===== SCENARIO RESPONSE =====\n")
        print(response)
        print("\n=============================\n")

        data = json.loads(response)
        data = self._normalize(data)

        return ScenarioCollection(**data)

    # ------------------------------------------------------------------
    # Normalisation — LLMs often return slight variations of the schema
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(data):
        """
        Coerce common LLM response shapes into {"scenarios": [...]}.

        Accepts:
          • {"scenarios": [...]}                 ← canonical
          • [{...}, {...}]                       ← bare list of scenarios
          • {"scenario_name": ..., "steps": ...} ← single scenario object
          • {"feature": ..., "scenarios": [...]} ← wrapped with extra metadata
          • {"data": [...]} / {"items": [...]}   ← common alternate keys
        """
        # Bare list → wrap
        if isinstance(data, list):
            return {"scenarios": data}

        if not isinstance(data, dict):
            raise ValueError(f"Unexpected scenario response shape: {type(data).__name__}")

        # Already correct
        if "scenarios" in data and isinstance(data["scenarios"], list):
            return {"scenarios": data["scenarios"]}

        # Common alternate keys
        for alt in ("data", "items", "test_scenarios", "testScenarios"):
            if alt in data and isinstance(data[alt], list):
                return {"scenarios": data[alt]}

        # Single scenario returned (model forgot the wrapper)
        if any(k in data for k in ("scenario_name", "steps", "name")):
            return {"scenarios": [data]}

        raise ValueError(
            f"Could not find scenarios in response. Top-level keys: {list(data.keys())}"
        )