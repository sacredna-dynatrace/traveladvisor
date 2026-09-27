# Amazon EKS 배포 및 OneAgent AI Observability 검증 기록

> 대상 branch: `oneagent-fullstack` · 1차 검증일: 2026-09-27 · LLM Provider: **Anthropic** (Bedrock 검증은 [5장](#5-다음-단계-bedrock-검증-계획) 참고)

이 문서는 `oneagent-fullstack` branch를 개인 AWS 계정의 EKS에 배포하고, **OTel/Traceloop 없이 OneAgent만으로** 어디까지 AI Observability가 되는지 확인한 결과입니다. 다음 테스트(Bedrock 전환)를 이어서 진행할 수 있도록 절차·결과·남은 과제를 함께 정리합니다.

---

## 1. 요약

| 계층 | 결과 | 비고 |
|---|---|---|
| K8s 클러스터 / 노드 / 워크로드 (Smartscape) | ✅ 수집 | ActiveGate `kubernetes-monitoring` |
| 인프라 (Host, Process) | ✅ 수집 | cloudNativeFullStack |
| 로그 | ✅ 수집 | `logMonitoring` |
| FastAPI 서비스 / 요청 (`GET /api/v1/completion`) | ✅ 수집 | `Python FastAPI` |
| LLM 호출 span (`anthropic.chat`, `gen_ai.operation.name=chat`) | ✅ 수집 | Experimental Anthropic sensor |
| 모델명 / 토큰 사용량 / 지연시간 | ✅ 수집 | `gen_ai.request.model`, `gen_ai.usage.*_tokens` |
| **Prompt / Completion 내용** | ❌ 미수집 | prompt capture 켜도 속성 null, 전문 검색 0건 |
| **LangChain chain / agent / tool span** | ❌ 미수집 | Anthropic 조합은 LangChain sensor 지원 범위 밖 |
| RUM | ⏳ 미적용 | `DT_RUM_SNIPPET` 미설정 상태로 배포됨 |

**결론**: Anthropic(experimental) 경로에서는 *모델·토큰·지연시간*까지는 코드 변경 없이 수집되지만, *Prompt 내용과 Agent 구조*는 수집되지 않는다. 공식 지원 조합인 **LangChain + Bedrock**으로 전환해 재검증이 필요하다.

---

## 2. 검증 환경

| 항목 | 값 |
|---|---|
| 클러스터 | Amazon EKS, `ap-northeast-2`, eksctl로 생성 (`traveladvisor`) |
| 노드 | EC2 managed nodegroup, `t3.xlarge` × 2, Amazon Linux 2023 (x86_64) |
| Dynatrace Operator | Helm `oci://public.ecr.aws/dynatrace/dynatrace-operator` (최신) |
| DynaKube | `eks-traveladvisor` — `cloudNativeFullStack` + ActiveGate(`routing`, `kubernetes-monitoring`) + `logMonitoring` |
| OneAgent / CodeModules | `1.345.81.20260917-170831` |
| 앱 이미지 | ECR `travel-advisor:<git short sha>` (linux/amd64) |
| LLM | Anthropic `claude-haiku-4-5-20251001` |
| 외부 노출 | Service `LoadBalancer`(ELB) + `loadBalancerSourceRanges`(작업 PC IP) |

### 노드 유형 선택 근거

[Supported distributions](https://docs.dynatrace.com/docs/ingest-from/setup-on-k8s/deployment/supported-technologies) 기준:

* **EKS on EC2**: 모든 배포 모드 지원 → 사용
* **EKS on Fargate**: App Observability만 지원 → 사용 불가 (노드 OneAgent 필요)
* **Bottlerocket**: OneAgent 기반 Platform Observability 미지원 → 사용 불가 (EKS Auto Mode 노드 포함)
* 참고: **GKE Autopilot**도 App Observability만 지원 → GKE를 쓸 경우 Standard 클러스터 필요

---

## 3. 배포 절차

### 3.1 작업 PC 준비 (Windows)

1. Docker Desktop → Settings → General → **Use the WSL 2 based engine**, Resources → WSL integration → **Ubuntu** ON
2. Ubuntu 터미널: 시작 메뉴 **Ubuntu** 또는 PowerShell `wsl -d Ubuntu` → `echo $HOME`이 `/root`(또는 사용자 홈)인지 확인
3. 도구 설치

   ```bash
   apt update && apt install -y git unzip curl
   curl -sL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip && unzip -q awscliv2.zip && ./aws/install
   curl -sL "https://github.com/eksctl-io/eksctl/releases/latest/download/eksctl_Linux_amd64.tar.gz" | tar xz -C /usr/local/bin
   curl -sLO "https://dl.k8s.io/release/$(curl -sL https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && install kubectl /usr/local/bin/
   curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
   ```

### 3.2 AWS IAM — 사용자 2개로 분리

| 사용자 | 용도 | 권한 |
|---|---|---|
| `eks-admin` (예시) | eksctl / ECR / kubectl 배포 | 개인 데모 계정이므로 `AdministratorAccess` (eksctl이 IAM Role·CloudFormation까지 생성) |
| Bedrock 전용 사용자 | 앱이 Bedrock 호출 시 사용 (K8s Secret에 저장) | Bedrock 호출 권한만 |

```bash
aws configure --profile eks-admin        # region: ap-northeast-2
export AWS_PROFILE=eks-admin
aws sts get-caller-identity --query Arn  # .../user/eks-admin 확인
```

### 3.3 Dynatrace 테넌트 설정 (앱 배포 전)

1. **Settings > Monitoring > Monitored technologies > Python** → **Monitor Python** ON
2. **Settings > Processes and containers > Custom process monitoring rules** → Add item
   * Mode `Monitor`, Condition `Kubernetes namespace` `equals` `travel-advisor`
3. **Settings > Collect and capture > General monitoring settings > OneAgent features** (1차 검증 시 설정)

   | Feature | 상태 |
   |---|---|
   | Python FastAPI | ON |
   | Python GenAI Langchain | ON |
   | Experimental Python GenAI Anthropic [Opt-In] (min 1.339) | ON |
   | Experimental Python GenAI Anthropic prompt capture [Opt-In] (min 1.345) | ON |

4. 토큰 2개 (Platform token 기준, [Tokens and permissions](https://docs.dynatrace.com/docs/ingest-from/setup-on-k8s/deployment/tokens-permissions/tokens-permissions))

   | 변수 | 권한 |
   |---|---|
   | `DT_OPERATOR_TOKEN` | `fleet-management:activegate.connection-info:read`, `fleet-management:activegate.tokens:create`, `fleet-management:container-images:read`, `fleet-management:oneagent.connection-info:read`, `fleet-management:oneagents:download`, `settings:objects:read`, `settings:objects:write` |
   | `DT_TOKEN` | `openpipeline:logs:ingest`, `openpipeline:metrics:ingest`, `openpipeline:traces:ingest`, `storage:metrics:write` |

### 3.4 이미지 로컬 검증 (선택)

```bash
docker build -t travel-advisor:local .
docker run --rm -p 8080:8080 -e LLM_PROVIDER=anthropic -e ANTHROPIC_API_KEY=... travel-advisor:local
# http://localhost:8080 — /etc/secrets/... No such file 로그는 로컬에서 정상(Secret 미존재 시 기본값 사용)
```

### 3.5 배포 (`deploy-eks.sh`)

```bash
cp .env-eks.example .env-eks && chmod 600 .env-eks && nano .env-eks   # 값 입력
source .env-eks
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY    # 남아 있으면 AWS_PROFILE보다 우선함
./deploy-eks.sh
```

스크립트 순서: (0) eksctl 클러스터 생성(`CREATE_CLUSTER=true`) → (1) 이미지 빌드·ECR push(`SKIP_BUILD=true`면 생략) → (2) Operator·DynaKube → (3) 앱 Secret → (4) 앱 배포·LB 주소 출력.
전체 약 25~30분(클러스터 생성 15~20분). **실행 중 Ctrl+C 금지** — 확인은 별도 터미널에서.

### 3.6 배포 후 확인

```bash
aws eks update-kubeconfig --name traveladvisor --region ap-northeast-2   # 새 터미널마다 필요 시
kubectl -n dynatrace get dynakube,pods
kubectl -n travel-advisor get pod -l name=travel-advisor \
  -o jsonpath='{.items[0].metadata.annotations}' | tr ',' '\n' | grep -i dynatrace   # injected=true
kubectl -n dynatrace get dynakube eks-traveladvisor \
  -o jsonpath='{.status.oneAgent.version}{"\n"}{.status.codeModules.version}{"\n"}'

URL=http://<ELB 주소>
for p in none rag agentic; do for c in bali sydney tokyo; do
  curl -s -o /dev/null -w "$p/$c %{http_code}\n" "$URL/api/v1/completion?prompt=$c&pipeline=$p&lang=ko"
done; done
```

---

## 4. 검증 결과 상세 (Anthropic)

### 4.1 AI Observability 화면

* AI apps 1, AI models 1, LLM requests·Tokens 집계 정상 (예: 24 requests / 11K tokens)
* **AI agents 0**, **Prompt trace: No results**, 좌측 Token usage 타일 "No data available"

### 4.2 span 구성

```
fetch spans, from:now()-15m
| filter k8s.namespace.name == "travel-advisor"
| summarize spans = count(), by:{span.name, gen_ai.operation.name}
```

| span.name | gen_ai.operation.name | 비고 |
|---|---|---|
| `anthropic.chat` | `chat` | LLM 호출 (agentic은 요청당 여러 번 호출) |
| `GET /api/v1/completion` | null | FastAPI |
| `GET`, `GET /api/v1/info` | null | FastAPI |
| *(LangChain chain/agent/tool)* | — | **0건** |

### 4.3 GenAI 속성

```
fetch spans, from:now()-15m
| filter k8s.namespace.name == "travel-advisor" and span.name == "anthropic.chat"
| sort start_time desc
| limit 3
| fields start_time, gen_ai.request.model, gen_ai.response.model,
         gen_ai.usage.input_tokens, gen_ai.usage.output_tokens,
         gen_ai.input.messages, gen_ai.output.messages,
         gen_ai.prompt, gen_ai.completion,
         gen_ai.prompt.0.content, gen_ai.completion.0.content
```

| 속성 | 결과 |
|---|---|
| `gen_ai.request.model` / `gen_ai.response.model` | `claude-haiku-4-5-20251001` |
| `gen_ai.usage.input_tokens` / `output_tokens` | 값 있음 (예: 656 / 275) |
| `gen_ai.input.messages` / `gen_ai.output.messages` 등 prompt 관련 | **null** |

```
fetch spans, from:now()-15m
| filter k8s.namespace.name == "travel-advisor" and span.name == "anthropic.chat"
| search "tokyo"
```

→ **0건**. 속성 이름 문제가 아니라 prompt 내용이 span에 전혀 기록되지 않음. OneAgent 1.345.81, Pod 재시작 후 신규 트래픽으로도 동일.

> DQL 참고: `fieldsKeep gen_ai.*` 는 `*`가 연산자로 해석되어 PARSE_ERROR 발생 → 필드를 명시하거나 레코드 상세에서 확인.

### 4.4 원인 분석

| 현상 | 원인 | 근거 |
|---|---|---|
| Prompt 미수집 | Anthropic sensor는 experimental — prompt capture 옵션이 있으나 현 버전에서 내용 미기록 | 공식 문서의 prompt capture 지원은 Bedrock·OpenAI만 명시. Anthropic은 "experimental … not covered by Dynatrace support SLAs" |
| Agent/LangChain span 없음 | LangChain sensor는 하위 provider가 Bedrock 또는 OpenAI인 조합을 전제 | [Get started with OneAgent and AI Observability](https://docs.dynatrace.com/docs/observe/dynatrace-for-ai-observability/get-started/oneagent): *"Python GenAI Langchain" is required, plus the underlying model provider's features (Bedrock or OpenAI)* |
| RUM 없음 | Python(uvicorn)이 HTML을 직접 서빙 → OneAgent RUM 자동 삽입 대상 아님, `DT_RUM_SNIPPET` 미설정 | [Configure automatic injection](https://docs.dynatrace.com/docs/observe/digital-experience/rum/web-frontends/initial-setup/configure-auto-injection) — 지원 기술 외에는 수동 삽입 |

---

## 5. 다음 단계: Bedrock 검증 계획

### 5.1 사전 준비 체크리스트

- [ ] AWS Console (us-east-1) → Bedrock → **Model access**: `amazon.nova-2-lite`(또는 `AWS_MODEL`로 지정할 모델), `amazon.titan-embed-text-v2` 허용
- [ ] Bedrock 전용 IAM 사용자 키 준비 (`BEDROCK_ACCESS_KEY_ID` / `BEDROCK_SECRET_ACCESS_KEY`)
- [ ] OneAgent features ON
  - [ ] `Python AWS SDK Client`
  - [ ] `Python AWS SDK GenAI Bedrock`
  - [ ] `Python AWS SDK Bedrock prompt capture`
  - [ ] `Python GenAI Langchain` (유지)
- [ ] (RUM 동시 진행 시) Frontend(Web) 생성 → JS tag를 `DT_RUM_SNIPPET`에 준비

### 5.2 클러스터가 살아 있을 때 — Secret만 교체

```bash
kubectl -n travel-advisor patch secret llm -p '{"stringData":{"provider":"bedrock"}}'
kubectl -n travel-advisor patch secret bedrock -p "{\"stringData\":{\"key\":\"$BEDROCK_ACCESS_KEY_ID\",\"secret\":\"$BEDROCK_SECRET_ACCESS_KEY\",\"region\":\"us-east-1\"}}"
# RUM 동시 적용
kubectl -n travel-advisor create secret generic dynatrace \
  --from-literal=token="$DT_TOKEN" --from-literal=endpoint="$DT_ENDPOINT" \
  --from-literal=rum-app-id= --from-literal=rum-snippet="$DT_RUM_SNIPPET" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n travel-advisor rollout restart deploy/travel-advisor
curl -s $URL/api/v1/info           # provider: bedrock 확인
```

### 5.3 클러스터를 삭제한 뒤 — 재배포

`.env-eks`에서 `CREATE_CLUSTER=true`, `LLM_PROVIDER=bedrock`, `BEDROCK_*`, `DT_RUM_SNIPPET` 설정 후 `./deploy-eks.sh`.
ECR 이미지를 재사용하려면 `SKIP_BUILD=true`와 `TAG=<기존 태그>`를 함께 지정 (TAG 기본값은 현재 git commit이므로 commit이 바뀌면 달라짐).

### 5.4 검증 항목과 기대 결과

| # | 확인 | 방법 | 기대 결과 |
|---|---|---|---|
| 1 | Bedrock LLM span | 4.2 DQL | Bedrock/Converse 관련 span, `gen_ai.operation.name` 존재 |
| 2 | 모델·토큰 | 4.3 DQL (`span.name` 필터 제거, `isNotNull(gen_ai.request.model)`) | `gen_ai.request.model` = nova 모델, 토큰 값 |
| 3 | **Prompt 내용** | 4.3 DQL + `search "tokyo"` / AI Observability → Prompts 탭 | prompt·completion 속성 채워짐, Prompt trace 표시 |
| 4 | **LangChain / Agent** | 4.2 DQL (`rag`, `agentic` 호출 후) | chain/agent/tool span 생성, AI agents > 0 |
| 5 | RUM | Frontend 앱, `curl -s $URL/ \| grep js-cdn.dynatrace.com` | 사용자 세션·페이지 로드 수집 |
| 6 | RUM ↔ Backend 연결 | UI에서 질문 후 trace 확인 | 브라우저 요청에서 FastAPI → LLM까지 이어짐 |

결과는 이 문서 4장 형식으로 "Bedrock" 절을 추가해 기록한다.

### 5.5 선택 과제

* **NGINX 앞단 배치**: OneAgent가 NGINX에 주입되면 RUM 자동 삽입 가능 → "코드·설정 변경 없이 OneAgent만으로 RUM"까지 시연 가능
* DynaKube `apiVersion`을 최신으로 갱신 (현재 `v1beta5`는 deprecated 경고), `feature.dynatrace.com/injection-readonly-volume` 어노테이션 제거(unknown flag 경고)
* `amazon-bedrock`(Traceloop) branch와 동일 시나리오 비교표 작성

---

## 6. 트러블슈팅 기록

| 증상 | 원인 | 조치 |
|---|---|---|
| `unzip: not found` | 패키지 미설치 | `apt install -y unzip git curl` (root이면 `sudo` 불필요) |
| `docker run ... <YOUR_KEY>` → `cannot open YOUR_KEY` | 셸이 `<`를 입력 리다이렉션으로 해석 | 실제 값으로 치환, 여러 줄 붙여넣기 대신 한 줄씩 실행 |
| `AccessDeniedException ... ecr:GetAuthorizationToken` | CLI가 Bedrock 전용 사용자로 설정됨 | 배포용 사용자(`eks-admin`) 프로파일 사용 |
| `DT_TOKEN: parameter null or not set` | 환경 변수 누락 | `.env-eks`로 관리 후 `source` |
| eksctl 도중 Ctrl+C → 노드그룹 미생성 | 스크립트 중단 | `eksctl create nodegroup --cluster traveladvisor --region ap-northeast-2 --name ng-1 --managed --node-type t3.xlarge --nodes 2 --node-ami-family AmazonLinux2023` 후 `CREATE_CLUSTER=false`로 재실행 |
| `kubectl` → `localhost:8080 refused` | 해당 셸에 kubeconfig 없음 | `aws eks update-kubeconfig --name traveladvisor --region ap-northeast-2` |
| `The config profile (eks-admin) could not be found` | 셸마다 `HOME`이 달라(`/` vs `/root`) `~/.aws`, `~/.kube` 위치가 다름 | `/.aws`, `/.kube`를 `/root`로 복사하거나 `AWS_CONFIG_FILE`/`AWS_SHARED_CREDENTIALS_FILE`/`KUBECONFIG` 지정. Ubuntu는 시작 메뉴 또는 `wsl -d Ubuntu`로 진입 |
| eksctl `OIDC is disabled ... vpc-cni` 경고 | Pod Identity 권장 안내 | 무시 가능 (노드 Role에 CNI 정책 기본 부여) |
| DynaKube `API version is deprecated` / `unknown feature flags` 경고 | 레포의 DynaKube 템플릿이 구버전 | 동작에는 영향 없음 (5.5 참고) |
| Bedrock 키를 `AWS_ACCESS_KEY_ID`로 export 시 배포 권한 오류 | 환경 변수 자격 증명이 `AWS_PROFILE`보다 우선 | `BEDROCK_*` 변수명 사용 (스크립트 반영 완료) |

---

## 7. 정리 (과금 중지)

```bash
kubectl -n travel-advisor delete svc travel-advisor          # ELB 먼저 삭제
eksctl delete cluster --name traveladvisor --region ap-northeast-2
# 이미지까지 삭제하려면 (재배포 시 SKIP_BUILD 불가)
aws ecr delete-repository --repository-name travel-advisor --region ap-northeast-2 --force
```

배포용 IAM 사용자의 액세스 키는 테스트 후 비활성화/삭제 권장.
