from models import Model
from pipeline import Pipeline, language_instruction
from utils import format_message


class Basic(Pipeline):

    def __init__(self):
        super().__init__()

    def start(self, model: Model, prompt: str, lang: str = "en"):
        prompt = (
            f"Give travel advise in a paragraph of max 50 words about {prompt}. "
            f"{language_instruction(lang)}"
        )
        answer = model.chat(prompt)
        return format_message(answer)
