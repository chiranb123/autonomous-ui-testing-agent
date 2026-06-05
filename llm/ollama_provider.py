import os
import re
import ollama
from dotenv import load_dotenv
from llm.provider import LLMProvider
load_dotenv()
class GroqProvider(LLMProvider):
    def __init__(
            self,
            model=None,
            host=None,
            json_mode=True
    ):
        self.model = model or os.getenv("OLLAMA_MODEL", "qwen3:8b")
        self.host  = host  or os.getenv("OLLAMA_HOST",  "http://localhost:11434")
        self.json_mode = json_mode
        self.client = ollama.Client(host=self.host)
    def generate(self, prompt: str) -> str:
        kwargs = dict(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            options={
                "temperature": 0,
                "num_predict": 4096,   # cap max tokens — prevents runaway generation
                "think": False,        # disable qwen3 chain-of-thought thinking mode
            },
        )
        if self.json_mode:
            kwargs["format"] = "json"
        response = self.client.chat(**kwargs)
        content  = response.message.content
        # Strip any remaining thinking blocks (deepseek-r1, etc.)
        content = re.sub(r"(?s)<think>.*?<\/think>", "", content)
        # Strip markdown fences
        content = content.replace("```json", "").replace("```", "").strip()
        return content