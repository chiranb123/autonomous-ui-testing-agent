import os
import time

import google.generativeai as genai

from dotenv import load_dotenv
from google.api_core.exceptions import (
    ResourceExhausted,
    ServiceUnavailable,
    DeadlineExceeded,
)

from llm.provider import LLMProvider

load_dotenv()


class GeminiProvider(LLMProvider):

    def __init__(
            self,
            model_name: str = "gemini-2.5-flash",
            max_retries: int = 5
    ):

        genai.configure(
            api_key=os.getenv(
                "GEMINI_API_KEY"
            )
        )

        self.model = genai.GenerativeModel(model_name)
        self.max_retries = max_retries

    def generate(
            self,
            prompt: str
    ) -> str:

        last_exc = None

        for attempt in range(1, self.max_retries + 1):

            try:

                response = self.model.generate_content(
                    prompt
                )

                return response.text

            except ResourceExhausted as e:

                last_exc = e

                # Daily quota? No point retrying within this run.
                if self._is_daily_quota(e):
                    raise RuntimeError(
                        "Gemini DAILY free-tier quota exhausted. "
                        "Enable billing, switch model "
                        "(e.g. gemini-2.5-flash-lite), or wait "
                        "until the daily reset."
                    ) from e

                # Try to use the server's suggested retry_delay,
                # otherwise exponential backoff (max 60s).
                delay = self._extract_retry_delay(e)

                if delay is None:
                    delay = min(2 ** attempt, 60)

                # Add a small buffer.
                delay += 1

                print(
                    f"[GeminiProvider] Rate-limited "
                    f"(attempt {attempt}/{self.max_retries}). "
                    f"Sleeping {delay}s..."
                )
                time.sleep(delay)

            except (ServiceUnavailable, DeadlineExceeded) as e:

                last_exc = e
                delay = min(2 ** attempt, 30)

                print(
                    f"[GeminiProvider] Transient error "
                    f"({type(e).__name__}). "
                    f"Retrying in {delay}s..."
                )
                time.sleep(delay)

        raise RuntimeError(
            f"Gemini call failed after "
            f"{self.max_retries} retries"
        ) from last_exc

    @staticmethod
    def _extract_retry_delay(exc) -> int | None:
        """Pull server-suggested retry_delay seconds from the exception."""
        try:
            for detail in getattr(exc, "details", lambda: [])():
                seconds = getattr(
                    getattr(detail, "retry_delay", None),
                    "seconds",
                    None
                )
                if seconds:
                    return int(seconds)
        except Exception:
            pass
        return None

    @staticmethod
    def _is_daily_quota(exc) -> bool:
        """Detect if the 429 is a per-day quota vs per-minute."""
        try:
            text = str(exc)
            if "PerDay" in text:
                return True
            for detail in getattr(exc, "details", lambda: [])():
                quota_id = getattr(detail, "quota_id", "")
                if "PerDay" in quota_id:
                    return True
        except Exception:
            pass
        return False

