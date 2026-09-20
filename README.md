# EasyTravel Bedrock - Travel Advisor

Python(FastAPI)로 작성한 여행 조언 데모 앱입니다. LLM 호출과 Agent 동작을 [Traceloop OpenLLMetry](https://github.com/traceloop/openllmetry)와 [OpenTelemetry](https://opentelemetry.io)로 계측해 Dynatrace로 보냅니다.
LLM은 [Amazon Bedrock](https://aws.amazon.com/bedrock/)(기본)과 [Anthropic Claude API](https://docs.anthropic.com/) 중 하나를 씁니다.

> **Note**
> This product is not officially supported by Dynatrace!

## 주요 기능

* **파이프라인 3종** (UI에서 선택)

  | 파이프라인 | 동작 |
  |---|---|
  | `none` | LLM을 한 번 호출 |
  | `rag` | LangChain으로 `destinations/` 문서를 검색한 뒤 호출 |
  | `agentic` | LangChain Agent가 `valid_city` 등 Tool을 스스로 골라 여러 번 호출 |

* **LLM Provider 전환**: `LLM_PROVIDER=bedrock`(기본) 또는 `anthropic`. Bedrock은 Converse API를 씁니다.
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
| `LLM_PROVIDER` | `bedrock` | `bedrock` 또는 `anthropic` |
| `AWS_DEFAULT_REGION` | `us-east-1` | Bedrock 리전 |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | - | Bedrock 인증 |
| `AWS_MODEL` | `us.amazon.nova-2-lite-v1:0` | Converse API를 지원하는 모델 또는 inference profile ID |
| `AWS_EMBEDDING_MODEL` | `amazon.titan-embed-text-v2:0` | Bedrock RAG 임베딩 |
| `AWS_GUARDRAIL_ID` / `AWS_GUARDRAIL_VERSION` | - / `DRAFT` | 선택 |
| `ANTHROPIC_API_KEY` | - | `LLM_PROVIDER=anthropic`일 때만 필요 |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5-20251001` | Anthropic 모델 |
| `LOCAL_EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Anthropic 사용 시 RAG 임베딩(fastembed, 이미지에 포함) |
| `DT_ENDPOINT` / `DT_TOKEN` | - | K8S 배포용. Dynatrace 환경 URL과 API Token |
| `OTEL_ENDPOINT` / `API_TOKEN` | - | 로컬 실행용. `https://<tenant>.live.dynatrace.com/api/v2/otlp`와 API Token |

API Token에는 `openTelemetryTrace.ingest`, `metrics.ingest`, `logs.ingest` 스코프가 필요합니다. K8S에서는 `deployment.sh`가 이 값들을 Secret(`bedrock`, `llm`, `dynatrace`)으로 만들고, 앱은 `/etc/secrets`에서 읽습니다.

## GitHub Codespaces에서 실행

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://github.com/codespaces/new/Dynatrace/obslab-llm-observability?ref=amazon-bedrock)

Codespace를 만들 때 `DT_ENDPOINT`, `DT_TOKEN`, `AWS_*`, `LLM_PROVIDER`, `ANTHROPIC_API_KEY`를 입력하면 `post-create.sh`가 kind 클러스터 생성부터 배포까지 자동으로 진행합니다. 배포가 끝나면 **포트** 탭에서 `30100`(travel-advisor User Interface)을 엽니다.

## 로컬 실행 (Python 3.11)

```bash
pip install -r requirements.txt

export LLM_PROVIDER=bedrock          # 또는 anthropic
export AWS_DEFAULT_REGION=us-east-1
export AWS_ACCESS_KEY_ID=<YOUR_AWS_KEY>
export AWS_SECRET_ACCESS_KEY=<YOUR_AWS_SECRET>
export AWS_MODEL=us.amazon.nova-2-lite-v1:0
export AWS_EMBEDDING_MODEL=amazon.titan-embed-text-v2:0
# export ANTHROPIC_API_KEY=<YOUR_ANTHROPIC_KEY>   # LLM_PROVIDER=anthropic일 때
export OTEL_ENDPOINT=https://<YOUR_DT_TENANT>.live.dynatrace.com/api/v2/otlp
export API_TOKEN=<YOUR_DT_TOKEN>

python app.py                         # http://localhost:8080
```

## 로컬 K8S(kind)에 배포

[Docker](https://docs.docker.com/engine/install/)와 [kind](https://kind.sigs.k8s.io/)가 필요합니다.

```bash
kind create cluster --config .devcontainer/kind-cluster.yml --wait 300s

export LLM_PROVIDER=bedrock          # 또는 anthropic
export AWS_DEFAULT_REGION=us-east-1
export AWS_ACCESS_KEY_ID=<YOUR_AWS_KEY>
export AWS_SECRET_ACCESS_KEY=<YOUR_AWS_SECRET>
export AWS_MODEL=us.amazon.nova-2-lite-v1:0
export AWS_EMBEDDING_MODEL=amazon.titan-embed-text-v2:0
export AWS_GUARDRAIL_ID=<OPTIONAL_YOUR_AWS_BEDROCK_GUARDRAIL>
# export ANTHROPIC_API_KEY=<YOUR_ANTHROPIC_KEY>   # LLM_PROVIDER=anthropic일 때
export DT_ENDPOINT=https://<YOUR_DT_TENANT>.live.dynatrace.com
export DT_TOKEN=<YOUR_DT_TOKEN>

.devcontainer/deployment.sh
```

이미지를 로컬에서 빌드해 kind에 올리고(`travel-advisor:local`), `travel-advisor` 네임스페이스에 배포합니다. UI는 NodePort `30100`으로 열립니다.

코드를 고친 뒤 다시 배포하려면:

```bash
docker build -t travel-advisor:local .
kind load docker-image travel-advisor:local --name kind
kubectl -n travel-advisor rollout restart deploy/travel-advisor
```

## Dynatrace에서 확인

* **Distributed Tracing**: `travel-advisor` 서비스의 LLM·Agent·Tool Span
* **AI Observability**: Model·Provider Overview, Agents topology
* **대시보드**: `dynatrace/dashboards/bedrock/[AiObs] AWS Bedrock.json`을 import
* **DQL**: `/guide.html`의 "7. 적용 검증" 참고

## 참고

* [Dynatrace Playground](https://dt-url.net/v203wj2)의 샘플 대시보드
* [Dynatrace AI Observability 문서](https://dt-url.net/oi23w9x)
* [Amazon Bedrock Getting Started](https://docs.aws.amazon.com/bedrock/latest/userguide/getting-started.html)
