import os
from .base import BaseProvider

DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiProvider(BaseProvider):
    def __init__(self, model: str = DEFAULT_MODEL):
        try:
            from google import genai
            from google.genai import types
            self._types = types
        except ImportError:
            raise ImportError("Run: pip install google-genai")

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError("GEMINI_API_KEY is not set.")

        self.client = genai.Client(api_key=api_key)
        self.model = model

    def complete(self, system: str, prompt: str) -> str:
        response = self.client.models.generate_content(
            model=self.model,
            config=self._types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=8192,
            ),
            contents=prompt,
        )
        try:
            text = response.text
        except ValueError:
            # Response bị block bởi safety filter hoặc không có text content
            candidates = getattr(response, "candidates", [])
            reason = candidates[0].finish_reason if candidates else "unknown"
            raise RuntimeError(f"Gemini returned no text (finish_reason={reason})")
        if not text:
            raise RuntimeError("Gemini returned an empty response.")
        return text
