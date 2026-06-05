import os
import time

from groq import Groq, RateLimitError
from dotenv import load_dotenv
from llm.provider import LLMProvider

load_dotenv()

# Fallback model order — each has its own separate daily quota on Groq free tier
# Updated June 2026: removed decommissioned models (llama3-8b-8192, gemma2-9b-it, mixtral-8x7b-32768)
_MODEL_FALLBACK_CHAIN = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
]


class GroqProvider(LLMProvider):

    def __init__(self, model: str = None):
        preferred = model or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        # Build the fallback chain starting from preferred model
        self._models = [preferred] + [
            m for m in _MODEL_FALLBACK_CHAIN if m != preferred
        ]
        self.model = self._models[0]
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    def generate(self, prompt: str) -> str:

        for model in self._models:
            result = self._try_generate(prompt, model)
            if result is not None:
                self.model = model   # remember which worked
                return result

        raise RuntimeError(
            "All Groq models exhausted their daily quota. "
            "Try again tomorrow or upgrade at https://console.groq.com/settings/billing"
        )

    def _try_generate(self, prompt: str, model: str, retries: int = 3) -> str | None:
        """
        Try to generate with one model. Returns None if quota is fully exhausted
        (so caller can try next model). Retries on transient rate limits.
        """
        for attempt in range(1, retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                    max_tokens=4096,
                    response_format={"type": "json_object"},
                )
                content = response.choices[0].message.content or ""
                content = (
                    content
                    .replace("```json", "")
                    .replace("```", "")
                    .strip()
                )
                if attempt > 1 or model != self._models[0]:
                    print(f"    [groq] Used model: {model}")
                return content

            except RateLimitError as e:
                msg = str(e)
                # "tokens per day" → quota fully gone for this model, skip it
                if "per day" in msg or "TPD" in msg:
                    print(f"    [groq] Daily quota exhausted for {model}, trying next model...")
                    return None   # signal: try next model

                # Per-minute / per-request rate limit → wait and retry
                wait = 30 * attempt
                print(
                    f"    [groq] Rate limited on {model} "
                    f"(attempt {attempt}/{retries}). Waiting {wait}s..."
                )
                time.sleep(wait)

            except Exception as e:
                msg = str(e)
                # Decommissioned models fail immediately — no point retrying
                if "decommissioned" in msg or "model_decommissioned" in msg:
                    print(f"    [groq] {model} decommissioned — skipping")
                    return None
                print(f"    [groq] Error on {model}: {e}")
                if attempt == retries:
                    return None

        return None
