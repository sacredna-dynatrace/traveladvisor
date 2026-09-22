import os

from utils.secrets import read_secret

# LLM_PROVIDER selects the backend: "anthropic" (default) or "bedrock".
_instance = None


def provider() -> str:
    return (
        os.environ.get("LLM_PROVIDER") or read_secret("provider") or "anthropic"
    ).strip().lower()


def get_model():
    """Return a shared model instance for the configured provider."""
    global _instance
    if _instance is None:
        if provider() == "anthropic":
            from models.anthropic_claude import AnthropicClaude

            _instance = AnthropicClaude()
        else:
            from models.bedrock import Bedrock

            _instance = Bedrock()
    return _instance
