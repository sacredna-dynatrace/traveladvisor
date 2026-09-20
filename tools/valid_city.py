import re

from models.factory import get_model
from utils.genai import mark_tool_span

regex = re.compile("[^a-zA-Z]")

from langchain_core.tools import tool


@tool
def valid_city(city: str) -> bool:
    """Returns if the input is a valid city"""
    mark_tool_span("valid_city", "Returns if the input is a valid city")
    prompt = f"Is {city} a city? respond only with yes or no."
    response = get_model().chat(prompt)
    response = regex.sub("", response).lower()
    print(f"Tool answer: -->{response}<--")
    return response == "yes"
