from langchain_core.tools import tool

from models.factory import get_model
from utils.genai import mark_tool_span


@tool
def movie_quote(city: str) -> str:
    """Returns a quote from a movie"""
    mark_tool_span("movie_quote", "Returns a quote from a movie")
    prompt = f"Provide a quote from the movie {city}"
    response = get_model().chat(prompt)
    return response
