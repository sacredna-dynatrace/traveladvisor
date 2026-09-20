from abc import ABC, abstractmethod

from models import Model


class Pipeline(ABC):

    def __init__(self):
        pass

    @abstractmethod
    def start(self, model: Model, prompt: str, lang: str = "en") -> object:
        pass


def language_instruction(lang: str) -> str:
    """Instruction appended to prompts so the demo can answer in Korean."""
    if (lang or "").lower().startswith("ko"):
        return "Write the answer in Korean (keep place names and proper nouns in English)."
    return "Write the answer in English."
