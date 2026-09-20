from langchain_core.tools import tool

from models.factory import get_model
from utils.genai import mark_tool_span


@tool
def travel_advice(city: str) -> str:
    """Provide travel advice for the given city"""
    mark_tool_span("travel_advice", "Provide travel advice for the given city")
    prompt = f"Give travel advise in a paragraph of max 50 words about {city}"
    response = get_model().chat(prompt)
    print(f"Tool answer: -->{response}<--")
    return response
