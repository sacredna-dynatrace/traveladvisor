from langchain_core.tools import tool

from models.factory import get_model


@tool
def movie_quote(city: str) -> str:
    """Returns a quote from a movie"""
    prompt = f"Provide a quote from the movie {city}"
    response = get_model().chat(prompt)
    return response
