import logging
import os
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
import uvicorn

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from traceloop.sdk import Traceloop
from traceloop.sdk.decorators import workflow
from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from models.factory import get_model
from pipeline.agentic import Agentic
from pipeline.basic import Basic
from pipeline.langchain import LangChain
from utils import format_message
from utils.secrets import read_secret
from utils.rum import load_rum_snippet, inject_snippet

# disable traceloop telemetry
os.environ["TRACELOOP_TELEMETRY"] = "false"
# configure OTel accumulation method
os.environ["OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE"] = "delta"


def read_token():
    return os.environ.get("API_TOKEN", read_secret("token"))


def read_endpoint():
    return os.environ.get("OTEL_ENDPOINT", read_secret("endpoint"))


OTEL_ENDPOINT = read_endpoint()
if OTEL_ENDPOINT.endswith("/v1/traces"):
    OTEL_ENDPOINT = OTEL_ENDPOINT[: OTEL_ENDPOINT.find("/v1/traces")]


# Initialise the logger
logging.basicConfig(level=logging.INFO, filename="run.log")
logger = logging.getLogger(__name__)

# ################
# # CONFIGURE OPENTELEMETRY

resource = Resource.create(
    {"service.name": "travel-advisor", "service.version": "0.3.0"}
)

TOKEN = read_token()
headers = {"Authorization": f"Api-Token {TOKEN}"}

otel_tracer = trace.get_tracer("travel-advisor")

# Dynatrace RUM JavaScript tag (agentless). DT_RUM_SNIPPET 또는 DT_RUM_APP_ID 로 활성화 — utils/rum.py 참고
RUM_SNIPPET = load_rum_snippet(OTEL_ENDPOINT, TOKEN)

Traceloop.init(
    app_name="travel-advisor",
    api_endpoint=OTEL_ENDPOINT,
    disable_batch=True,
    headers=headers,
)

# AWS SDK(botocore) 호출 계측: Bedrock Runtime / S3 / STS 등 모든 AWS API 호출을 CLIENT span으로 기록
# (rpc.service, rpc.method, aws.request_id, aws.region 속성 포함)
# 주의: botocore instrumentation의 Bedrock 확장은 gen_ai.usage.* 속성을 붙인다.
#       Traceloop(OpenLLMetry)이 이미 같은 LLM 호출에 gen_ai span을 만들기 때문에
#       그대로 두면 AI Observability 대시보드에서 토큰/비용이 2배로 집계된다.
#       Bedrock 확장만 끄고 일반 AWS SDK span(Bedrock Runtime.InvokeModel 등)만 남긴다.
if os.environ.get("OTEL_BOTOCORE_BEDROCK_GENAI", "false").lower() != "true":
    from opentelemetry.instrumentation.botocore import extensions as _botocore_ext

    # private API: opentelemetry-instrumentation-botocore 0.65b0 기준. 버전 올릴 때 이 dict 이름 확인할 것
    _botocore_ext._BOTOCORE_EXTENSIONS.pop("bedrock-runtime", None)
BotocoreInstrumentor().instrument()

## Pipelines

bedrock = get_model()  # Bedrock or Anthropic, see LLM_PROVIDER
basic = Basic()
langchain = LangChain()
agentic = Agentic()

pipelines = {
    "none": basic,
    "rag": langchain,
    "agentic": agentic,
}

############
# CONFIGURE ENDPOINTS

app = FastAPI()

# FastAPI(ASGI) 인바운드 요청 계측: 모든 HTTP 요청을 SERVER span으로 기록하고
# traceparent 헤더를 받아 upstream(RUM, Gateway 등)과 trace를 이어준다.
# Traceloop.init()이 global TracerProvider를 설정한 뒤에 호출해야 같은 exporter로 나간다.
FastAPIInstrumentor.instrument_app(
    app,
    # 정적 파일(public/) 요청은 trace에서 제외 — 데모 환경에 맞게 조정
    excluded_urls=os.environ.get(
        "OTEL_PYTHON_FASTAPI_EXCLUDED_URLS",
        r"\.(css|js|map|png|jpg|jpeg|svg|ico|woff2?)$",
    ),
    # ASGI http.receive / http.send 내부 span 제거 (노이즈 감소)
    exclude_spans=["receive", "send"],
)


@app.exception_handler(HTTPException)
async def validation_exception_handler(request, exc):
    return JSONResponse(exc.detail, status_code=500)


####################################
@app.get("/api/v1/completion")
def submit_completion(prompt: str, pipeline: str, lang: str = "en"):
    # SERVER span은 FastAPIInstrumentor가 만들므로 여기서는 INTERNAL로 바꿔 SERVER span 중복을 피한다
    with otel_tracer.start_as_current_span(
        name="/api/v1/completion", kind=trace.SpanKind.INTERNAL
    ) as span:
        span.set_attribute("travel_advisor.pipeline", pipeline)
        span.set_attribute("travel_advisor.language", lang)
        return submit_workflow(prompt, pipeline, span, lang)


@app.get("/api/v1/info")
def info():
    """Active LLM configuration, shown in the demo UI."""
    return {
        "provider": bedrock.provider_name,
        "model": bedrock.model_name,
        "embedding_model": bedrock.embedding_model_name,
        "pipelines": list(pipelines.keys()),
    }


@workflow(name="travel_answer_generator")
def submit_workflow(prompt: str, pipeline: str, span: trace.Span, lang: str = "en"):
    clean_prompt = prompt.lower().strip()
    if clean_prompt:
        p = pipeline.lower()
        if not p in pipelines:
            raise HTTPException(
                status_code=404,
                detail=format_message("Sorry, the selected framework doesn't exist"),
            )
        pipeline = pipelines[p]
        return pipeline.start(bedrock, clean_prompt, lang)
    else:  # No, or invalid prompt given
        span.set_status(trace.status.StatusCode.ERROR, "Invalid prompt")
        return format_message("Sorry, the prompt provided is invalid")


####################################
@app.get("/api/v1/thumbsUp")
@otel_tracer.start_as_current_span("/api/v1/thumbsUp")
def thumbs_up(prompt: str):
    logger.info(f"Positive user feedback for search term: {prompt}")


@app.get("/api/v1/thumbsDown")
@otel_tracer.start_as_current_span("/api/v1/thumbsDown")
def thumbs_down(prompt: str):
    logger.info(f"Negative user feedback for search term: {prompt}")


class RumStaticFiles(StaticFiles):
    """public/*.html 응답의 <head>에 Dynatrace RUM JavaScript tag를 삽입한다."""

    def is_not_modified(self, response_headers, request_headers) -> bool:
        # 브라우저에 남은 (tag 없는) 이전 캐시로 304 응답하지 않도록 조건부 요청을 무시
        if RUM_SNIPPET:
            return False
        return super().is_not_modified(response_headers, request_headers)

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if (
            RUM_SNIPPET
            and isinstance(response, FileResponse)
            and str(response.path).endswith(".html")
        ):
            with open(response.path, "r", encoding="utf-8") as f:
                html = inject_snippet(f.read(), RUM_SNIPPET)
            # 주입 결과가 tag 버전에 따라 바뀌므로 파일 기반 ETag/304 캐시는 쓰지 않는다
            return HTMLResponse(
                html,
                status_code=response.status_code,
                headers={"Cache-Control": "no-cache"},
            )
        return response


if __name__ == "__main__":
    # Mount static files at the root (HTML에는 Dynatrace RUM tag 자동 삽입)
    app.mount("/", RumStaticFiles(directory="./public", html=True), name="public")

    # Run the app using uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
