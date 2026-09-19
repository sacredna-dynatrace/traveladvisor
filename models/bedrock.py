import boto3
import json
import os

from models import Model
from utils.secrets import read_secret

from langchain_aws.embeddings.bedrock import BedrockEmbeddings
from langchain_aws import ChatBedrockConverse

# Amazon Titan Text G1 (Lite/Express) models reached End-of-Life on Amazon Bedrock.
# Chat now goes through the model-agnostic Bedrock Converse API, so any
# Converse-capable model works (Amazon Nova, Anthropic Claude, Meta Llama, Mistral, ...).
#
# Newer models are only served through cross-region inference profiles, so use the
# profile ID with its geo prefix (us. / eu. / jp. / apac. / global.), e.g.
#   us.amazon.nova-2-lite-v1:0                        (AWS_DEFAULT_REGION=us-east-1)
#   eu.amazon.nova-2-lite-v1:0                        (AWS_DEFAULT_REGION=eu-central-1)
#   global.amazon.nova-2-lite-v1:0                    (e.g. ap-northeast-2 / Seoul)
#   us.anthropic.claude-haiku-4-5-20251001-v1:0       (Anthropic use-case form required once)
DEFAULT_MODEL = "us.amazon.nova-2-lite-v1:0"
DEFAULT_EMBEDDING_MODEL = "amazon.titan-embed-text-v2:0"
DEFAULT_REGION = "us-east-1"

MAX_TOKENS = 512
TEMPERATURE = 0.5


class Bedrock(Model):

    def __init__(self) -> None:
        super().__init__()
        key = os.environ.get("AWS_ACCESS_KEY_ID", read_secret("aws-key"))
        sec = os.environ.get("AWS_SECRET_ACCESS_KEY", read_secret("aws-secret"))
        # "or" keeps the default when the variable/secret exists but is empty
        self.__embedding_model = (
            os.environ.get("AWS_EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL
        )
        self.__model = os.environ.get("AWS_MODEL") or DEFAULT_MODEL
        self.__guardrail_id = os.environ.get("AWS_GUARDRAIL_ID", "")
        # Guardrail version: DRAFT (working copy) or a published version number, e.g. "1"
        self.__guardrail_version = os.environ.get("AWS_GUARDRAIL_VERSION") or "DRAFT"

        self.__client = boto3.client(
            "bedrock-runtime",
            region_name=os.environ.get("AWS_DEFAULT_REGION") or DEFAULT_REGION,
            aws_access_key_id=key,
            aws_secret_access_key=sec,
        )
        self.__langchain_embedding = BedrockEmbeddings(
            client=self.__client,
            model_id=self.__embedding_model,
        )
        self.__langchain_llm = ChatBedrockConverse(
            client=self.__client,
            model=self.__model,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            guardrail_config=self.__guardrail_config(),
            # non-streaming Converse calls -> one complete bedrock.converse span per LLM call
            disable_streaming=True,
        )

    def __guardrail_config(self):
        if not self.__guardrail_id:
            return None
        return {
            "guardrailIdentifier": self.__guardrail_id,
            "guardrailVersion": self.__guardrail_version,
            "trace": "enabled",
        }

    def embedding(self, prompt):
        if self.__embedding_model.startswith("cohere."):
            native_request = {"texts": [prompt], "input_type": "search_query"}
        else:
            # Amazon Titan Text Embeddings (v1 / v2)
            native_request = {"inputText": prompt}
        response = self.__client.invoke_model(
            modelId=self.__embedding_model, body=json.dumps(native_request)
        )
        embed = json.loads(response["body"].read())
        if "embeddings" in embed:
            return embed["embeddings"][0]
        return embed["embedding"]

    def chat(self, prompt) -> str:
        request = {
            "modelId": self.__model,
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {"maxTokens": MAX_TOKENS, "temperature": TEMPERATURE},
        }
        guardrail = self.__guardrail_config()
        if guardrail:
            request["guardrailConfig"] = guardrail

        response = self.__client.converse(**request)
        # When a guardrail intervenes, stopReason is "guardrail_intervened" and the
        # output contains the blocked-message text configured on the guardrail.
        content = response["output"]["message"]["content"]
        return "".join(block.get("text", "") for block in content)

    def langchain_embedding(self):
        return self.__langchain_embedding

    def langchain_llm(self):
        return self.__langchain_llm
