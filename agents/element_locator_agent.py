# agents/element_locator_agent.py

import re
import json
from pathlib import Path
from string import Template


class ElementLocatorAgent:
    """
    Autonomous element locator.
    Uses the LLM to read the actual page snapshot and identify the
    correct [ref=...] for a given human-readable target description.
    Falls back to regex if no provider is available.
    """

    def __init__(self, provider=None):
        self.provider = provider
        self._prompt_template = None

    def _load_prompt(self) -> Template:
        if self._prompt_template is None:
            path = (
                Path(__file__).parent.parent
                / "prompts"
                / "element_locator_prompt.txt"
            )
            self._prompt_template = Template(
                path.read_text(encoding="utf-8")
            )
        return self._prompt_template

    def locate(self, snapshot_text: str, target: str) -> str | None:
        """
        Returns the ref string (e.g. 'e5') for the best-matching element.
        Uses LLM when a provider is available, regex otherwise.
        """
        if not target:
            return None

        if self.provider:
            return self._locate_with_llm(snapshot_text, target)

        return self._locate_with_regex(snapshot_text, target)

    # ------------------------------------------------------------------
    # LLM-based location
    # ------------------------------------------------------------------

    def _locate_with_llm(self, snapshot_text: str, target: str) -> str | None:
        try:
            prompt = self._load_prompt().substitute(
                target=target,
                snapshot=snapshot_text,
            )
            response = self.provider.generate(prompt)
            data = json.loads(response)
            ref = data.get("ref")
            confidence = data.get("confidence", "none")

            # Only trust medium or high confidence — low confidence often means
            # the model guessed wrong. Fall back to regex which searches exact text.
            if ref and confidence in ("high", "medium"):
                print(
                    f"    [locator] LLM found ref={ref} "
                    f"({data.get('element_text')}) "
                    f"confidence={confidence}"
                )
                return str(ref)

            if ref and confidence == "low":
                print(
                    f"    [locator] LLM low-confidence (ref={ref}, '{data.get('element_text')}') — trying regex"
                )
            else:
                print(f"    [locator] LLM could not find element: '{target}' — trying regex")
            return self._locate_with_regex(snapshot_text, target)

        except Exception as e:
            print(f"    [locator] LLM error ({e}), falling back to regex")
            return self._locate_with_regex(snapshot_text, target)

    # ------------------------------------------------------------------
    # Regex-based fallback
    # ------------------------------------------------------------------

    def _locate_with_regex(self, snapshot_text: str, target: str) -> str | None:
        # 1. Exact phrase before [ref=...]
        pattern = rf'.*{re.escape(target)}.*\[ref=([\w\d]+)\]'
        matches = re.findall(pattern, snapshot_text, re.IGNORECASE)
        if matches:
            return matches[0]

        # 2. Token-based: any significant word in target
        tokens = [
            t for t in re.split(r'\s+', target)
            if len(t) > 2
        ]
        for token in tokens:
            pattern = rf'.*{re.escape(token)}.*\[ref=([\w\d]+)\]'
            matches = re.findall(pattern, snapshot_text, re.IGNORECASE)
            if matches:
                return matches[0]

        # 3. ref comes before the label
        for token in tokens:
            pattern = rf'\[ref=([\w\d]+)\].*{re.escape(token)}'
            matches = re.findall(pattern, snapshot_text, re.IGNORECASE)
            if matches:
                return matches[0]

        return None