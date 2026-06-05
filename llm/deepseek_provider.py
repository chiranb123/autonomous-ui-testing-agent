import json
import os
import time

from openai import OpenAI, RateLimitError
from dotenv import load_dotenv
from llm.provider import LLMProvider

load_dotenv()

# Default model on OpenRouter (free tier) — confirmed available June 2026.
# Llama-3.3-70b: fast (~80 tok/s), reliable JSON mode, strong general-purpose
# reasoning across any web-app domain (forms, e-commerce, dashboards, CRUD...).
_DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct:free"

# Fallback chain — confirmed-available OpenRouter free models (June 2026).
# Ordered: fast + reliable JSON first, then slower/higher-quality, then risky.
_MODEL_FALLBACK_CHAIN = [
    "meta-llama/llama-3.3-70b-instruct:free",   # fast, reliable, general
    "openai/gpt-oss-20b:free",                  # fastest reliable JSON model
    "qwen/qwen3-next-80b-a3b-instruct:free",    # fast MoE
    "qwen/qwen3-coder:free",                    # fast, structured-output friendly
    "z-ai/glm-4.5-air:free",                    # solid mid-tier
    "openai/gpt-oss-120b:free",                 # slower but very reliable
    "moonshotai/kimi-k2.6:free",                # long context, slower
    "nvidia/nemotron-3-super-120b-a12b:free",   # capable, JSON sometimes flaky
    "nvidia/nemotron-3-ultra-550b-a55b:free",   # last resort — slow, JSON flaky
    "nvidia/nemotron-3-nano-30b-a3b:free",
]


def _is_fatal_error(msg: str) -> bool:
    """Errors that mean: don't retry this model, move on immediately."""
    lower = msg.lower()
    return (
        "404" in msg
        or "no endpoints" in lower
        or "not found" in lower
        or "invalid model" in lower
        or "401" in msg
        or "unauthorized" in lower
        or "403" in msg
    )


def _is_rate_limit(msg: str) -> bool:
    lower = msg.lower()
    return (
        "429" in msg
        or "rate" in lower and "limit" in lower
        or "temporarily" in lower
        or "quota" in lower
    )


def _looks_like_garbage_json(text: str) -> bool:
    """
    Some free OpenRouter models don't really support response_format=json_object
    and return things like '{":  ": null}' or '{}' — garbage that satisfies
    JSON syntax but contains zero useful content.
    """
    if not text or len(text.strip()) < 5:
        return True
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return True

    if parsed in (None, [], {}, ""):
        return True

    if isinstance(parsed, dict):
        # All keys are whitespace/punctuation only? → garbage
        meaningful_keys = [
            k for k in parsed.keys()
            if isinstance(k, str) and any(c.isalnum() for c in k)
        ]
        if not meaningful_keys:
            return True
        # All values are None and there's only one key? → garbage
        if len(parsed) == 1 and next(iter(parsed.values())) is None:
            return True

    return False


class DeepSeekProvider(LLMProvider):
    """
    OpenRouter-backed provider (OpenAI-compatible).
    Despite the name, supports any OpenRouter model via DEEPSEEK_MODEL env var.
    Key format:  sk-or-v1-...
    Base URL:    https://openrouter.ai/api/v1
    """

    def __init__(self, model: str = None):
        preferred = model or os.getenv("DEEPSEEK_MODEL", _DEFAULT_MODEL)
        self._models = [preferred] + [
            m for m in _MODEL_FALLBACK_CHAIN if m != preferred
        ]
        self.model = self._models[0]
        self.client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://openrouter.ai/api/v1",
        )

    def generate(self, prompt: str) -> str:
        last_error = None
        for model in self._models:
            try:
                result = self._try_generate(prompt, model)
                if result is not None:
                    self.model = model
                    return result
            except Exception as e:
                last_error = e
                continue

        raise RuntimeError(
            "All OpenRouter models failed.\n"
            f"  Tried: {self._models}\n"
            f"  Last error: {last_error}\n"
            "  Check your DEEPSEEK_API_KEY, account credits, and that the "
            "models above still exist at https://openrouter.ai/models"
        )

    def _try_generate(self, prompt: str, model: str, retries: int = 2) -> str | None:
        """Returns response text, or None if model should be skipped."""
        for attempt in range(1, retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                    # Big enough for scenario lists with 10+ ACs.
                    # Most free models cap output anyway; this just ensures
                    # we don't truncate ourselves.
                    max_tokens=16384,
                    response_format={"type": "json_object"},
                )

                choice = response.choices[0]
                content = choice.message.content or ""
                finish_reason = getattr(choice, "finish_reason", None)

                content = (
                    content
                    .replace("```json", "")
                    .replace("```", "")
                    .strip()
                )

                # Detect truncation explicitly — better diagnostic than
                # "malformed JSON" when the response was cut off mid-token.
                if finish_reason == "length":
                    print(
                        f"    [openrouter] {model} hit output token limit "
                        f"(len={len(content)} chars). Response truncated → next model"
                    )
                    return None

                # Some free models silently return junk despite json_object mode.
                if _looks_like_garbage_json(content):
                    print(
                        f"    [openrouter] {model} returned malformed/empty JSON "
                        f"(len={len(content)}, finish={finish_reason}): "
                        f"{content[:120]!r} → next model"
                    )
                    return None

                if attempt > 1 or model != self._models[0]:
                    print(f"    [openrouter] Used model: {model}")
                return content

            except RateLimitError as e:
                msg = str(e)
                print(f"    [openrouter] Rate limit on {model} → next model")
                return None  # Don't retry rate-limited models — try next

            except Exception as e:
                msg = str(e)

                # Fast-fail on fatal errors (404, auth, etc.) — no retries
                if _is_fatal_error(msg):
                    print(f"    [openrouter] {model} unavailable (skipping): {msg[:140]}")
                    return None

                # Rate-limit signalled via generic exception — skip immediately
                if _is_rate_limit(msg):
                    print(f"    [openrouter] Rate-limited on {model} → next model")
                    return None

                # Genuine transient error — short backoff, then retry
                print(
                    f"    [openrouter] Transient error on {model} "
                    f"(attempt {attempt}/{retries}): {msg[:140]}"
                )
                if attempt < retries:
                    time.sleep(2 * attempt)

        return None
