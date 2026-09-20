import os

import anthropic

from models import Model
from utils.secrets import read_secret

from langchain_anthropic import ChatAnthropic
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings

# Claude via the Anthropic API (https://platform.claude.com/docs/en/models/overview).
# Anthropic does not offer an embeddings API, so the RAG pipeline uses a small local
# embedding model (FastEmbed / ONNX, pre-downloaded into the image at build time).
PROVIDER_NAME = "Anthropic Claude"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_CACHE_DIR = os.environ.get("FASTEMBED_CACHE_PATH", "/opt/fastembed")

MAX_TOKENS = 512
TEMPERATURE = 0.5


class AnthropicClaude(Model):

    def __init__(self) -> None:
        super().__init__()
        api_key = os.environ.get("ANTHROPIC_API_KEY") or read_secret("anthropic-key")
        self.__model = (
            os.environ.get("ANTHROPIC_MODEL")
            or read_secret("anthropic-model")
            or DEFAULT_MODEL
        )
        self.__embedding_model = (
            os.environ.get("LOCAL_EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL
        )

        self.__client = anthropic.Anthropic(api_key=api_key)
        self.__langchain_llm = ChatAnthropic(
            model=self.__model,
            api_key=api_key,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            # non-streaming calls -> one complete anthropic.chat span per LLM call
            disable_streaming=True,
        )
        self.__langchain_embedding = FastEmbedEmbeddings(
            model_name=self.__embedding_model,
            cache_dir=EMBEDDING_CACHE_DIR,
        )

    def embedding(self, prompt):
        return self.__langchain_embedding.embed_query(prompt)

    def chat(self, prompt) -> str:
        response = self.__client.messages.create(
            model=self.__model,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(
            block.text for block in response.content if block.type == "text"
        )

    @property
    def provider_name(self) -> str:
        return PROVIDER_NAME

    @property
    def model_name(self) -> str:
        return self.__model

    @property
    def embedding_model_name(self) -> str:
        return self.__embedding_model

    def langchain_embedding(self):
        return self.__langchain_embedding

    def langchain_llm(self):
        return self.__langchain_llm
