from abc import ABC, abstractmethod


class BaseProvider(ABC):
    @abstractmethod
    def complete(self, system: str, prompt: str) -> str:
        """Send prompt to AI and return raw text response."""
        pass
