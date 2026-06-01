"""
OpenAI-compatible provider — covers GPT, Grok, and Ollama.
All three expose the same /v1/chat/completions endpoint format.
"""
from .base import BaseProvider
from ..config import PROVIDER_LIMITS, DEFAULT_PROVIDER_LIMITS

DEFAULTS = {
    "gpt":    ("gpt-4o",   None,                       "OPENAI_API_KEY"),
    "grok":   ("grok-3",   "https://api.x.ai/v1",      "GROK_API_KEY"),
    "ollama": ("llama3",   "http://localhost:11434/v1", None),
}


class OpenAICompatProvider(BaseProvider):
    def __init__(self, name: str, model: str = None):
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("Run: pip install openai")

        import os

        default_model, base_url, env_key = DEFAULTS[name]
        self.model = model or default_model
        self.name  = name

        api_key = None
        if env_key:
            api_key = os.environ.get(env_key)
            if not api_key:
                raise EnvironmentError(f"{env_key} is not set.")
        else:
            api_key = "ollama"  # Ollama doesn't need a real key

        self.is_ollama = (base_url is not None and "localhost" in base_url)
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def complete(self, system: str, prompt: str) -> str:
        limits     = PROVIDER_LIMITS.get(self.name, DEFAULT_PROVIDER_LIMITS)
        max_tokens = limits["max_tokens"]
        timeout    = 300 if self.is_ollama else 120  # 5 phút local, 2 phút cloud
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            timeout=timeout,
        )
        return response.choices[0].message.content
