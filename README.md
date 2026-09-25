# EasyTravel Bedrock - Travel Advisor

Python(FastAPI)로 작성한 여행 조언 데모 앱입니다. LLM 호출과 Agent 동작을 [Traceloop OpenLLMetry](https://github.com/traceloop/openllmetry)와 [OpenTelemetry](https://opentelemetry.io)로 계측해 Dynatrace로 보냅니다.
LLM은 [Anthropic Claude API](https://docs.anthropic.com/)(기본)과 [Amazon Bedrock](https://aws.amazon.com/bedrock/) 중 하나를 씁니다.

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
* **GenAI Agent 계측**: `invoke_agent` / `execute_tool` Span을 OpenTelemetry GenAI semantic conventions에 맞춰 보내 Dynatrace AI Observability의 Agents topology에 표시됩니다.
* **한국어 데모 UI**: 응답 언어(ko/en) 선택, 파이프라인 비교, 아키텍처 설명. 영문 원본 UI는 `public/index-original-en.html`에 남겨 두었습니다.
* **적용 가이드** (`/guide.html`): Agent 동작 원리와 Traceloop 적용 방법(Python·Node.js), Kubernetes 배포, 검증용 DQL을 한국어로 정리했습니다.

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
| `DT_ENDPOINT` / `DT_TOKEN` | - | K8S 배포용. Dynatrace 환경 URL과 API Token |
| `OTEL_ENDPOINT` / `API_TOKEN` | - | 로컬 실행용. `https://<tenant>.live.dynatrace.com/api/v2/otlp`와 API Token |
| `DT_RUM_SNIPPET` | - | 선택(RUM 수집 시 권장). 테넌트에서 복사한 RUM JavaScript tag `<script …></script>` 전체. 모든 HTML `<head>`에 그대로 삽입 |
| `DT_RUM_APP_ID` | - | 선택, classic RUM 전용. `APPLICATION-…` 형식 ID로 기동 시 tag를 API 조회. 새 RUM의 `FRONTEND-…` ID는 지원하지 않음(API 400). `DT_RUM_SNIPPET`이 있으면 무시 |

API Token에는 `openTelemetryTrace.ingest`, `metrics.ingest`, `logs.ingest` 스코프가 필요하고, `DT_RUM_SNIPPET`을 쓰면 추가 스코프는 필요 없습니다(`DT_RUM_APP_ID`를 쓸 때만 `rumManualInsertionTags.read` 추가). K8S에서는 `deployment.sh`가 이 값들을 Secret(`bedrock`, `llm`, `dynatrace`)으로 만들고, 앱은 `/etc/secrets`에서 읽습니다.

## GitHub Codespaces에서 실행

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/sacredna-dynatrace/traveladvisor/tree/amazon-bedrock?quickstart=1)

Codespace를 만들 때 `DT_ENDPOINT`, `DT_TOKEN`, `AWS_*`, `LLM_PROVIDER`, `ANTHROPIC_API_KEY`(RUM 수집 시 `DT_RUM_SNIPPET`)를 입력하면 `post-create.sh`가 kind 클러스터 생성부터 배포까지 자동으로 진행합니다. 배포가 끝나면 **포트** 탭에서 `30100`(travel-advisor User Interface)을 엽니다.

## 로컬 실행 (Python 3.11)

```bash
pip install -r requirements.txt

export LLM_PROVIDER=anthropic       # 또는 bedrock
export AWS_DEFAULT_REGION=us-east-1
export AWS_ACCESS_KEY_ID=<YOUR_AWS_KEY>
export AWS_SECRET_ACCESS_KEY=<YOUR_AWS_SECRET>
export AWS_MODEL=us.amazon.nova-2-lite-v1:0
export AWS_EMBEDDING_MODEL=amazon.titan-embed-text-v2:0
export ANTHROPIC_API_KEY=<YOUR_ANTHROPIC_KEY>   # 기본(anthropic) Provider
export OTEL_ENDPOINT=https://<YOUR_DT_TENANT>.live.dynatrace.com/api/v2/otlp
export API_TOKEN=<YOUR_DT_TOKEN>
export DT_RUM_SNIPPET='<script type="text/javascript" src="https://js-cdn.dynatrace.com/jstag/..." crossorigin="anonymous"></script>'   # RUM 수집 시(선택)

python app.py                         # http://localhost:8080
```

## 로컬 K8S(kind)에 배포

[Docker](https://docs.docker.com/engine/install/)와 [kind](https://kind.sigs.k8s.io/)가 필요합니다.

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
export DT_TOKEN=<YOUR_DT_TOKEN>
export DT_RUM_SNIPPET='<script type="text/javascript" src="https://js-cdn.dynatrace.com/jstag/..." crossorigin="anonymous"></script>'   # RUM 수집 시(선택)

.devcontainer/deployment.sh
```

이미지를 로컬에서 빌드해 kind에 올리고(`travel-advisor:local`), `travel-advisor` 네임스페이스에 배포합니다. UI는 NodePort `30100`으로 열립니다.

코드를 고친 뒤 다시 배포하려면:

```bash
docker build -t travel-advisor:local .
kind load docker-image travel-advisor:local --name kind
kubectl -n travel-advisor rollout restart deploy/travel-advisor
```

## Real User Monitoring (RUM)

이 앱은 OneAgent 없이 OpenTelemetry로만 계측되고 Python은 RUM 자동 주입 대상이 아니므로, **Agentless RUM** JavaScript tag를 앱이 직접 `public/*.html`의 `<head>` 맨 앞에 삽입합니다(`utils/rum.py`, `app.py`의 `RumStaticFiles`).

1. 테넌트(`diw85600`)에서 Frontend(Web) application을 만들고 **Agentless monitoring**으로 설정한 뒤, 제공되는 JavaScript tag(`<script …></script>`) 전체를 복사합니다.
2. 복사한 tag를 `DT_RUM_SNIPPET`에 넣어 배포합니다(Codespaces는 Codespace 생성 화면의 `DT_RUM_SNIPPET` 입력란). 기동 로그(`run.log`)에 `Dynatrace RUM: using JavaScript tag from DT_RUM_SNIPPET`이 찍히고, 페이지 `<head>`에 `js-cdn.dynatrace.com/jstag/…` 스크립트가 보이면 적용된 것입니다.
   > `DT_RUM_APP_ID`는 classic RUM의 `APPLICATION-…` ID만 지원합니다. 새 RUM의 `FRONTEND-…` ID를 넣으면 `/api/v2/rum/javaScriptTag` API가 `400 Invalid application identifier`를 반환해 tag가 삽입되지 않으므로 `DT_RUM_SNIPPET`을 쓰세요.
3. 브라우저 요청(`/api/v1/completion` 등)과 백엔드 Trace를 이으려면 해당 앱의 RUM 설정에서 same-origin 요청에 W3C `traceparent` 헤더 전파를 켭니다. 백엔드는 `FastAPIInstrumentor`가 `traceparent`를 받아 같은 Trace로 이어 줍니다.
4. 이미 배포된 클러스터는 Secret만 갱신하고 재시작하면 됩니다.

```bash
kubectl -n travel-advisor create secret generic dynatrace \
  --from-literal=token=$DT_TOKEN --from-literal=endpoint=$DT_ENDPOINT/api/v2/otlp \
  --from-literal=rum-app-id= --from-literal=rum-snippet="$DT_RUM_SNIPPET" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n travel-advisor rollout restart deploy/travel-advisor
```

확인 DQL(새 RUM):

```
fetch user.events, from: now()-1h
| filter dt.rum.application.entity == "<APPLICATION-ID>"
| summarize events = count(), sessions = countDistinctExact(dt.rum.session.id), by: { characteristics.classifier }
```

## Kubernetes 인프라 연결

OTel만으로 계측된 서비스는 resource에 `k8s.*` 속성이 없으면 Services 앱의 **Infrastructure** 탭이 비어 있습니다. `deployment/travel-advisor.yaml`은 Downward API와 `OTEL_RESOURCE_ATTRIBUTES`로 `k8s.cluster.uid`(kube-system namespace UID), `k8s.namespace.name`, `k8s.pod.name/uid`, `k8s.node.name`, `k8s.workload.kind/name`, `k8s.container.name`을 붙이고, `deployment.sh`가 cluster UID·이름을 ConfigMap `k8s-cluster-info`로 만듭니다(`K8S_CLUSTER_NAME`, 기본 `kind-kind`). DynaKube(`kubernetes-monitoring`)가 수집하는 같은 cluster의 pod·workload와 연결됩니다.

## 로그 (OTLP)

앱 로그(`logging`)는 `TRACELOOP_LOGGING_ENABLED=true`(기본값)로 OTLP `/v1/logs`에 전송됩니다. 로그에는 span과 같은 resource(`service.name`, `k8s.*`)와 현재 `trace_id`/`span_id`가 붙어 Services 앱의 **Logs** 탭과 Distributed Tracing에서 연결됩니다. DynaKube `logMonitoring`이 수집하는 container stdout(uvicorn access log, LangChain verbose 출력)은 서비스 정보가 없어 Logs 탭에는 나오지 않고 Kubernetes workload 로그로만 보입니다. `run.log` 파일에도 계속 남습니다.

## Dynatrace에서 확인

* **Distributed Tracing**: `travel-advisor` 서비스의 LLM·Agent·Tool Span
* **AI Observability**: Model·Provider Overview, Agents topology
* **참고 대시보드**: [TravelAdvisor AI Observability Overview](https://diw85600.apps.dynatrace.com/ui/apps/dynatrace.dashboards/dashboard/b8b75bca-6577-4692-8093-b815e8da2e51#vfilter_Service=3420b2ac-f1cf-4b24-b62d-61ba1ba8ed05*&vfilter_Provider=3420b2ac-f1cf-4b24-b62d-61ba1ba8ed05*&vfilter_JudgeModel=3420b2ac-f1cf-4b24-b62d-61ba1ba8ed05*&vfilter_Metric=3420b2ac-f1cf-4b24-b62d-61ba1ba8ed05*&vfilter_RunId=3420b2ac-f1cf-4b24-b62d-61ba1ba8ed05*&from=%40d&to=now%28%29) — Agent·AI 서비스·Model·LLM Provider 수, AI 요청 수, p95 latency, Token 사용량, 예상 비용을 한 화면에서 확인할 수 있습니다.
* **Real User Monitoring**: `DT_RUM_SNIPPET`의 tag로 수집되는 Frontend application — 페이지 로드, Core Web Vitals, `/api/v1/completion` 요청 성능·오류
* **DQL**: `/guide.html`의 "7. 적용 검증" 참고

## 참고

* [Dynatrace AI Observability 문서](https://dt-url.net/oi23w9x)
* [Amazon Bedrock Getting Started](https://docs.aws.amazon.com/bedrock/latest/userguide/getting-started.html)
