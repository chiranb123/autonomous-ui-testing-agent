import json
import re
from pathlib import Path
from string import Template

from models.execution_plan import ExecutionPlan

# Generic descriptive words that look like page text but aren't.
# If a verify value is ONLY these words (no proper nouns, no quoted values),
# the step interpreter hallucinated it — drop the step.
_GENERIC_VERIFY_WORDS = {
    "the", "a", "an", "is", "are", "be", "been", "was", "were",
    "page", "screen", "view", "display", "displayed", "shown", "visible",
    "appears", "appear", "loaded", "available", "list", "of", "on",
    "and", "or", "to", "in", "at", "for", "with", "that", "this",
    "user", "should", "must", "will", "it", "its", "their", "by",
    "products", "items", "content", "data", "information", "result",
    "results", "message", "messages",
}


def _is_hallucinated_verify(value: str) -> bool:
    """
    Return True if a verify value is not usable as real page text.

    Rules:
    - Blank → drop
    - Credential placeholder tokens (__READ_FROM_PAGE__, __INVALID_VALUE__) in
      a verify step are always wrong — they only make sense for type actions
    - If every meaningful word is a generic description word → drop
    - Quoted values (from Gherkin) are trusted as-is
    """
    if not value or not value.strip():
        return True
    val = value.strip()

    # Placeholder tokens are never valid verify text
    if val in ("__READ_FROM_PAGE__", "__INVALID_VALUE__"):
        return True

    # Quoted values came directly from Gherkin — trust them
    if val.startswith(('"', "'")) and val.endswith(('"', "'")):
        return False

    tokens = [t.lower() for t in re.findall(r'[A-Za-z]+', val)]
    if not tokens:
        return True
    meaningful = [t for t in tokens if t not in _GENERIC_VERIFY_WORDS]
    return len(meaningful) == 0


class StepInterpreterAgent:

    def __init__(self, provider):
        self.provider = provider

    def interpret(self, steps, scenario_name: str = "Unnamed Scenario"):

        prompt_path = (
            Path(__file__).parent.parent
            / "prompts"
            / "step_interpreter_prompt.txt"
        )

        prompt = prompt_path.read_text(encoding="utf-8")

        prompt = Template(prompt).substitute(
            scenario_name=scenario_name,
            steps=json.dumps(steps, indent=2),
        )

        response = self.provider.generate(prompt)

        response = (
            response
            .replace("```json", "")
            .replace("```", "")
            .strip()
        )

        data = json.loads(response)

        # Drop verify steps whose value is a generic description, not page text
        original_count = len(data.get("steps", []))
        data["steps"] = [
            s for s in data.get("steps", [])
            if not (s.get("action") == "verify" and _is_hallucinated_verify(s.get("value", "")))
        ]
        dropped = original_count - len(data["steps"])
        if dropped:
            print(f"    [interpreter] Dropped {dropped} hallucinated verify step(s)")

        print("\n===== EXECUTION PLAN =====\n")
        print(json.dumps(data, indent=2))
        print("\n==========================\n")

        return ExecutionPlan(**data)
