import os
from .base import BaseProvider

DEFAULT_MODEL = "claude-sonnet-4-6"


class ClaudeProvider(BaseProvider):
    def __init__(self, model: str = DEFAULT_MODEL):
        try:
            import anthropic
        except ImportError:
            raise ImportError("Run: pip install anthropic")

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError("ANTHROPIC_API_KEY is not set.")

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def complete(self, system: str, prompt: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=8192,
            system=[
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
