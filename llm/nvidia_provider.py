import os

from openai import OpenAI
from dotenv import load_dotenv
from llm.provider import LLMProvider

load_dotenv()


class NvidiaProvider(LLMProvider):

    def __init__(self, model: str = None):
        self.model = model or os.getenv(
            "NVIDIA_MODEL", "nvidia/nemotron-3-ultra-550b-a55b"
        )
        self.client = OpenAI(
            api_key=os.getenv("NVIDIA_API_KEY"),
            base_url="https://integrate.api.nvidia.com/v1",
        )

    def generate(self, prompt: str) -> str:

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=4096,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content or ""

        # Strip markdown fences just in case
        content = (
            content
            .replace("```json", "")
            .replace("```", "")
            .strip()
        )

        return content

