from .base import BaseProvider

PROVIDERS = {
    "claude": ("ClaudeProvider",       "impact_check.providers.claude"),
    "gpt":    ("OpenAICompatProvider", "impact_check.providers.openai_compat"),
    "grok":   ("OpenAICompatProvider", "impact_check.providers.openai_compat"),
    "ollama": ("OpenAICompatProvider", "impact_check.providers.openai_compat"),
    "gemini": ("GeminiProvider",       "impact_check.providers.gemini"),
}


def get_provider(name: str, model: str = None) -> BaseProvider:
    if name not in PROVIDERS:
        raise ValueError(
            f"Unknown provider '{name}'. Choose from: {', '.join(PROVIDERS)}"
        )

    class_name, module_path = PROVIDERS[name]
    import importlib
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)

    # OpenAI-compatible providers need the provider name to pick defaults
    if name in ("gpt", "grok", "ollama"):
        return cls(name=name, model=model) if model else cls(name=name)

    return cls(model=model) if model else cls()
