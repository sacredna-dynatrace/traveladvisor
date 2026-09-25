import logging
import os
import sys
import time
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
import uvicorn

from models.factory import get_model
from pipeline.agentic import Agentic
from pipeline.basic import Basic
from pipeline.langchain import LangChain
from utils import format_message
from utils.secrets import read_secret
from utils.rum import load_rum_snippet, inject_snippet

# ################
# # OBSERVABILITY
# 이 branch는 코드 계측(Traceloop/OpenTelemetry SDK)을 쓰지 않는다.
# Dynatrace OneAgent(cloudNativeFullStack)가 Pod에 주입되어 Python 프로세스를 자동 계측한다.
#   - HTTP 요청(FastAPI)         : OneAgent feature "Python FastAPI"
#   - Bedrock(boto3/botocore)     : "Python AWS SDK Client" + "Python AWS SDK GenAI Bedrock"
#   - LangChain(chain/agent)      : "Python GenAI Langchain"
#   - Anthropic SDK               : experimental sensor (best-effort)
# 로그는 stdout으로 내보내고 OneAgent Log module이 container 로그로 수집한다.


def read_token():
    return os.environ.get("API_TOKEN", read_secret("token"))


def read_endpoint():
    # Dynatrace 환경 URL (예: https://abc12345.live.dynatrace.com). RUM tag API 조회에만 쓴다.
    return os.environ.get("DT_ENDPOINT", read_secret("endpoint"))


DT_ENDPOINT = read_endpoint()
TOKEN = read_token()

# ################
# # CONFIGURE LOGGING
# stdout → OneAgent Log module(container 로그)로 Dynatrace에 수집. run.log 파일에도 남긴다.
_log_format = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
_root = logging.getLogger()
_root.setLevel(logging.INFO)
_stdout_handler = logging.StreamHandler(sys.stdout)
_stdout_handler.setFormatter(_log_format)
_file_handler = logging.FileHandler("run.log")
_file_handler.setFormatter(_log_format)
_root.addHandler(_stdout_handler)
_root.addHandler(_file_handler)
# 라이브러리 내부 HTTP 로그는 노이즈라 WARNING 이상만
for _name in ("httpx", "httpcore", "urllib3", "botocore", "anthropic"):
    logging.getLogger(_name).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Dynatrace RUM JavaScript tag (agentless). DT_RUM_SNIPPET 으로 활성화 — utils/rum.py 참고
# (RUM tag는 앱이 직접 HTML <head>에 삽입한다 — 태그 값만 바꾸면 되도록 OneAgent 설정과 분리)
RUM_SNIPPET = load_rum_snippet(DT_ENDPOINT, TOKEN)

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

@app.exception_handler(HTTPException)
async def validation_exception_handler(request, exc):
    return JSONResponse(exc.detail, status_code=500)


####################################
@app.get("/api/v1/completion")
def submit_completion(prompt: str, pipeline: str, lang: str = "en"):
    return submit_workflow(prompt, pipeline, lang)


@app.get("/api/v1/info")
def info():
    """Active LLM configuration, shown in the demo UI."""
    return {
        "provider": bedrock.provider_name,
        "model": bedrock.model_name,
        "embedding_model": bedrock.embedding_model_name,
        "pipelines": list(pipelines.keys()),
    }


def submit_workflow(prompt: str, pipeline: str, lang: str = "en"):
    clean_prompt = prompt.lower().strip()
    if clean_prompt:
        p = pipeline.lower()
        if not p in pipelines:
            raise HTTPException(
                status_code=404,
                detail=format_message("Sorry, the selected framework doesn't exist"),
            )
        pipeline = pipelines[p]
        logger.info(f"Completion request: pipeline={p} lang={lang} prompt={clean_prompt!r}")
        started = time.perf_counter()
        try:
            result = pipeline.start(bedrock, clean_prompt, lang)
        except Exception:
            logger.exception(f"Completion failed: pipeline={p} lang={lang}")
            raise
        logger.info(
            f"Completion finished: pipeline={p} lang={lang} "
            f"provider={bedrock.provider_name} model={bedrock.model_name} "
            f"elapsed_ms={(time.perf_counter() - started) * 1000:.0f}"
        )
        return result
    else:  # No, or invalid prompt given
        logger.warning("Completion rejected: empty or invalid prompt")
        return format_message("Sorry, the prompt provided is invalid")


####################################
@app.get("/api/v1/thumbsUp")
def thumbs_up(prompt: str):
    logger.info(f"Positive user feedback for search term: {prompt}")


@app.get("/api/v1/thumbsDown")
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
