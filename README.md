# EasyTravel Bedrock - Travel Advisor (OneAgent Full-Stack)

Python(FastAPI)로 작성한 여행 조언 데모 앱입니다. 이 branch(`oneagent-fullstack`)는 **코드 계측(Traceloop/OpenTelemetry SDK) 없이 Dynatrace OneAgent만으로** Observability를 구성합니다. Dynatrace Operator가 kind 클러스터에 OneAgent를 `cloudNativeFullStack`으로 배포하고, 앱 Pod가 생성될 때 OneAgent code module이 주입되어 FastAPI·LLM 호출·LangChain을 자동 계측합니다.
LLM은 [Anthropic Claude API](https://docs.anthropic.com/)(기본)과 [Amazon Bedrock](https://aws.amazon.com/bedrock/) 중 하나를 씁니다.

> Traceloop(OpenLLMetry) 기반 구성은 [`amazon-bedrock`](https://github.com/sacredna-dynatrace/traveladvisor/tree/amazon-bedrock) branch를 참고하세요.

> **Note**
> This product is not officially supported by Dynatrace!

## 주요 기능

* **파이프라인 3종** (UI에서 선택)

  | 파이프라인 | 동작 |
  |---|---|
  | `none` | LLM을 한 번 호출 |
  | `rag` | LangChain으로 `destinations/` 문서를 검색한 뒤 호출 |
  | `agentic` | LangChain Agent가 `valid_city` 등 Tool을 스스로 골라 여러 번 호출 |

* **LLM Provider 전환**: `LLM_PROVIDER=anthropic`(기본) 또는 `bedrock`. Bedrock은 Converse API를 씁니다.
* **OneAgent 자동 계측**: 애플리케이션 코드에 계측 라이브러리가 없습니다. 무엇이 계측되는지는 [OneAgent 계측 범위](#oneagent-계측-범위)를 참고하세요.
* **한국어 데모 UI**: 응답 언어(ko/en) 선택, 파이프라인 비교, 아키텍처 설명. 영문 원본 UI는 `public/index-original-en.html`에 남겨 두었습니다.
* **적용 가이드** (`/guide.html`): Agent 동작 원리와 OneAgent 기반 AI Observability 적용 방법, 검증 방법을 한국어로 정리했습니다.

## 엔드포인트

| 경로 | 설명 |
|---|---|
| `/` | 데모 UI |
| `/guide.html` | AI 앱 Observability 가이드 |
| `/api/v1/completion?prompt=...&pipeline=none\|rag\|agentic&lang=ko\|en` | 답변 생성 |
| `/api/v1/info` | 현재 Provider·Model·Embedding 모델·파이프라인 목록 |
| `/api/v1/thumbsUp`, `/api/v1/thumbsDown` | 사용자 피드백 |

## 설정값

| 환경 변수 | 기본값 | 설명 |
|---|---|---|
| `LLM_PROVIDER` | `anthropic` | `anthropic` 또는 `bedrock` |
| `AWS_DEFAULT_REGION` | `us-east-1` | Bedrock 리전 |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | - | Bedrock 인증 |
| `AWS_MODEL` | `us.amazon.nova-2-lite-v1:0` | Converse API를 지원하는 모델 또는 inference profile ID |
| `AWS_EMBEDDING_MODEL` | `amazon.titan-embed-text-v2:0` | Bedrock RAG 임베딩 |
| `AWS_GUARDRAIL_ID` / `AWS_GUARDRAIL_VERSION` | - / `DRAFT` | 선택 |
| `ANTHROPIC_API_KEY` | - | 기본(`anthropic`) Provider 사용 시 필요 |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5-20251001` | Anthropic 모델 |
| `LOCAL_EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Anthropic 사용 시 RAG 임베딩(fastembed, 이미지에 포함) |
| `DT_ENDPOINT` | - | Dynatrace 환경 URL (예: `https://abc12345.live.dynatrace.com`). DynaKube `apiUrl`은 `$DT_ENDPOINT/api` |
| `DT_OPERATOR_TOKEN` | - | Dynatrace Operator token (DynaKube `apiToken`) |
| `DT_TOKEN` | - | Data ingest token (DynaKube `dataIngestToken`) |
| `DT_RUM_SNIPPET` | - | 선택(RUM 수집 시 권장). 테넌트에서 복사한 RUM JavaScript tag `<script …></script>` 전체. 모든 HTML `<head>`에 그대로 삽입 |
| `DT_RUM_APP_ID` | - | 선택, classic RUM 전용. `APPLICATION-…` 형식 ID로 기동 시 tag를 API 조회. 새 RUM의 `FRONTEND-…` ID는 지원하지 않음(API 400). `DT_RUM_SNIPPET`이 있으면 무시 |

토큰에 필요한 권한은 [Tokens and permissions](https://docs.dynatrace.com/docs/ingest-from/setup-on-k8s/deployment/tokens-permissions) 문서를 따릅니다(Platform token / Classic API token 모두 가능). `deployment.sh`는 두 토큰을 Secret `dynatrace/kind-kind`로, 앱 설정은 Secret(`bedrock`, `llm`, `dynatrace`)으로 만들고, 앱은 `/etc/secrets`에서 읽습니다.

## 1. Dynatrace 테넌트 설정 (최초 1회)

OneAgent의 Python 계측과 AI SDK sensor는 테넌트 설정에서 켭니다. 참고: [Get started with OneAgent and AI Observability](https://docs.dynatrace.com/docs/observe/dynatrace-for-ai-observability/get-started/oneagent), [Python](https://docs.dynatrace.com/docs/ingest-from/technology-support/application-software/python)

1. **Settings > Monitoring > Monitored technologies > Python** 에서 **Monitor Python**을 켭니다.
2. **Settings > Collect and capture > General monitoring settings > OneAgent features** 에서 `Python`으로 필터링한 뒤 아래 기능을 켭니다.

   | 기능 | 용도 | 비고 |
   |---|---|---|
   | Python FastAPI | HTTP 요청(`/api/v1/*`) | 필수 |
   | Python GenAI Langchain | `rag`·`agentic` 파이프라인의 chain/agent 실행 | 필수 |
   | Python AWS SDK Client | boto3/botocore 호출 | `LLM_PROVIDER=bedrock` 시 필수 |
   | Python AWS SDK GenAI Bedrock | Bedrock LLM 호출·Token | `LLM_PROVIDER=bedrock` 시 필수 |
   | Python AWS SDK Bedrock prompt capture | Prompt/Completion 내용 | 선택 |
   | Anthropic 관련 Python 기능 (experimental sensor, 테넌트 목록에서 이름 확인) | Anthropic SDK LLM 호출 | `LLM_PROVIDER=anthropic` 시. **experimental — best-effort, 정식 지원 아님** |

3. 기능을 바꾼 뒤에는 앱 Pod를 재시작해야 반영됩니다: `kubectl -n travel-advisor rollout restart deploy/travel-advisor`

## 2. GitHub Codespaces에서 실행

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/sacredna-dynatrace/traveladvisor/tree/oneagent-fullstack?quickstart=1)

Codespace를 만들 때 `DT_ENDPOINT`, `DT_OPERATOR_TOKEN`, `DT_TOKEN`, `AWS_*`, `LLM_PROVIDER`, `ANTHROPIC_API_KEY`(RUM 수집 시 `DT_RUM_SNIPPET`)를 입력하면 `post-create.sh`가 아래 순서로 자동 진행합니다. 배포가 끝나면 **포트** 탭에서 `30100`(travel-advisor User Interface)을 엽니다.

1. kind 클러스터 생성, 앱 이미지 빌드(`travel-advisor:local`)
2. Dynatrace Operator 설치(Helm) → 토큰 Secret → DynaKube(`dynatrace/dynakube.yaml`) 적용 → OneAgent·ActiveGate 준비 대기
3. 앱 배포 (Pod 생성 시 OneAgent code module 자동 주입)

`DT_OPERATOR_TOKEN`이 비어 있으면 Operator 설치를 건너뛰고 OneAgent 없이 앱만 배포합니다.

> **kind 지원 범위**: kind는 Dynatrace Operator의 [공식 지원 배포판](https://docs.dynatrace.com/docs/ingest-from/setup-on-k8s/installation/supported-technologies) 목록에 없습니다. 데모·검증 용도로 사용하세요.

## 3. 로컬 K8S(kind)에 배포

[Docker](https://docs.docker.com/engine/install/), [kind](https://kind.sigs.k8s.io/), [Helm](https://helm.sh/)이 필요합니다.

```bash
kind create cluster --config .devcontainer/kind-cluster.yml --wait 300s

export LLM_PROVIDER=anthropic       # 또는 bedrock
export AWS_DEFAULT_REGION=us-east-1
export AWS_ACCESS_KEY_ID=<YOUR_AWS_KEY>
export AWS_SECRET_ACCESS_KEY=<YOUR_AWS_SECRET>
export AWS_MODEL=us.amazon.nova-2-lite-v1:0
export AWS_EMBEDDING_MODEL=amazon.titan-embed-text-v2:0
export AWS_GUARDRAIL_ID=<OPTIONAL_YOUR_AWS_BEDROCK_GUARDRAIL>
export ANTHROPIC_API_KEY=<YOUR_ANTHROPIC_KEY>   # 기본(anthropic) Provider
export DT_ENDPOINT=https://<YOUR_DT_TENANT>.live.dynatrace.com
export DT_OPERATOR_TOKEN=<YOUR_OPERATOR_TOKEN>
export DT_TOKEN=<YOUR_DATA_INGEST_TOKEN>
export DT_RUM_SNIPPET='<script type="text/javascript" src="https://js-cdn.dynatrace.com/jstag/..." crossorigin="anonymous"></script>'   # RUM 수집 시(선택)

.devcontainer/deployment.sh
```

코드를 고친 뒤 다시 배포하려면:

```bash
docker build -t travel-advisor:local .
kind load docker-image travel-advisor:local --name kind
kubectl -n travel-advisor rollout restart deploy/travel-advisor
```

OneAgent 상태 확인:

```bash
kubectl -n dynatrace get dynakube,pods
kubectl -n travel-advisor describe pod -l name=travel-advisor | grep -i dynatrace   # 주입 init container / annotation
```

## 로컬 실행 (Python 3.11, 계측 없음)

```bash
pip install -r requirements.txt
python app.py                         # http://localhost:8080
```

이 branch는 앱 코드에 계측이 없으므로, 호스트에 OneAgent가 설치되어 있지 않으면 Dynatrace로 데이터가 가지 않습니다.

## OneAgent 계측 범위

| 대상 | 계측 방법 | 비고 |
|---|---|---|
| HTTP 요청 (FastAPI) | OneAgent `Python FastAPI` | Service·Request 자동 생성 |
| Bedrock (boto3 Converse) | `Python AWS SDK Client` + `Python AWS SDK GenAI Bedrock` | 정식 지원. Prompt capture 선택 가능 |
| Anthropic SDK | experimental sensor | best-effort. 누락·변경 가능 |
| LangChain (RAG, Agent) | `Python GenAI Langchain` | chain/agent 실행 span |
| 로그 | OneAgent Log module (`logMonitoring`) | 앱은 stdout으로 로그 출력, `run.log`에도 기록 |
| K8s 연결 | OneAgent + ActiveGate `kubernetes-monitoring` | cluster·workload·pod Smartscape 자동 연결 |
| 로컬 임베딩 (fastembed) | 계측 대상 아님 | Anthropic 사용 시 RAG 임베딩 |

**`amazon-bedrock`(Traceloop) branch와의 차이**

* 코드에서 만들던 `invoke_agent` / `execute_tool` span(GenAI semantic conventions)과 `@workflow` span은 이 branch에 없습니다. Agent·Tool 표시는 OneAgent LangChain sensor가 만드는 데이터에 따릅니다.
* `amazon-bedrock` branch 기준으로 만든 대시보드는 필드 구성이 달라 일부 타일이 비어 있을 수 있습니다.

## Real User Monitoring (RUM)

**Agentless RUM** JavaScript tag를 앱이 직접 `public/*.html`의 `<head>` 맨 앞에 삽입합니다(`utils/rum.py`, `app.py`의 `RumStaticFiles`). OneAgent의 자동 주입이 동작하는 환경이라면 `DT_RUM_SNIPPET`을 비워 이중 삽입을 피하세요.

1. 테넌트에서 Frontend(Web) application을 만들고 **Agentless monitoring**으로 설정한 뒤, 제공되는 JavaScript tag(`<script …></script>`) 전체를 복사합니다.
2. 복사한 tag를 `DT_RUM_SNIPPET`에 넣어 배포합니다(Codespaces는 Codespace 생성 화면의 `DT_RUM_SNIPPET` 입력란). 기동 로그에 `Dynatrace RUM: using JavaScript tag from DT_RUM_SNIPPET`이 찍히고, 페이지 `<head>`에 `js-cdn.dynatrace.com/jstag/…` 스크립트가 보이면 적용된 것입니다.
   > `DT_RUM_APP_ID`는 classic RUM의 `APPLICATION-…` ID만 지원합니다. 새 RUM의 `FRONTEND-…` ID를 넣으면 `/api/v2/rum/javaScriptTag` API가 `400 Invalid application identifier`를 반환해 tag가 삽입되지 않으므로 `DT_RUM_SNIPPET`을 쓰세요.
3. 이미 배포된 클러스터는 Secret만 갱신하고 재시작하면 됩니다.

```bash
kubectl -n travel-advisor create secret generic dynatrace \
  --from-literal=token=$DT_TOKEN --from-literal=endpoint=$DT_ENDPOINT \
  --from-literal=rum-app-id= --from-literal=rum-snippet="$DT_RUM_SNIPPET" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n travel-advisor rollout restart deploy/travel-advisor
```

## Dynatrace에서 확인

* **Infrastructure & Operations / Kubernetes**: `travel-advisor` Pod의 Python 프로세스가 OneAgent로 모니터링되는지 확인
* **Distributed Tracing / Services**: FastAPI 요청과 하위 LLM·LangChain 호출
* **AI Observability > Explorer**: LLM 요청·Token 집계
* **참고 대시보드**: [TravelAdvisor AI Observability Overview](https://diw85600.apps.dynatrace.com/ui/apps/dynatrace.dashboards/dashboard/b8b75bca-6577-4692-8093-b815e8da2e51#vfilter_Service=3420b2ac-f1cf-4b24-b62d-61ba1ba8ed05*&vfilter_Provider=3420b2ac-f1cf-4b24-b62d-61ba1ba8ed05*&vfilter_JudgeModel=3420b2ac-f1cf-4b24-b62d-61ba1ba8ed05*&vfilter_Metric=3420b2ac-f1cf-4b24-b62d-61ba1ba8ed05*&vfilter_RunId=3420b2ac-f1cf-4b24-b62d-61ba1ba8ed05*&from=%40d&to=now%28%29) — Agent·AI 서비스·Model·LLM Provider 수, AI 요청 수, p95 latency, Token 사용량, 예상 비용을 한 화면에서 확인할 수 있습니다. (`amazon-bedrock` branch 데이터 기준으로 구성됨)
* **Real User Monitoring**: `DT_RUM_SNIPPET`의 tag로 수집되는 Frontend application — 페이지 로드, Core Web Vitals, `/api/v1/completion` 요청 성능·오류

## 참고

* [Get started with OneAgent and AI Observability](https://docs.dynatrace.com/docs/observe/dynatrace-for-ai-observability/get-started/oneagent)
* [Kubernetes platform monitoring + Full-Stack observability](https://docs.dynatrace.com/docs/ingest-from/setup-on-k8s/deployment/full-stack-observability)
* [OneAgent — Python](https://docs.dynatrace.com/docs/ingest-from/technology-support/application-software/python)
* [Amazon Bedrock Getting Started](https://docs.aws.amazon.com/bedrock/latest/userguide/getting-started.html)
