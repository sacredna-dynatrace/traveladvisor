#!/usr/bin/env bash

# Titan Text G1 models are End-of-Life, so the prebuilt image (thisthatdc/travel-advisor:v0.3.0-bedrock)
# no longer works. Build the app from this repo (Bedrock Converse API) and load it into kind.
docker build -t travel-advisor:local .
kind load docker-image travel-advisor:local --name kind

# ─────────────────────────────────────────────────────────────────────────────
# Dynatrace Operator + DynaKube (OneAgent cloudNativeFullStack)
#   OneAgent가 먼저 준비되어야 앱 Pod 생성 시 code module이 주입되므로 앱보다 먼저 설치한다.
#   필요한 값: DT_ENDPOINT, DT_OPERATOR_TOKEN(Operator token), DT_TOKEN(Data ingest token)
# ─────────────────────────────────────────────────────────────────────────────
DT_ENDPOINT="${DT_ENDPOINT%/}"
if [ -n "$DT_OPERATOR_TOKEN" ] && [ -n "$DT_TOKEN" ] && [ -n "$DT_ENDPOINT" ]; then
  echo "Installing Dynatrace Operator"
  helm upgrade --install dynatrace-operator oci://public.ecr.aws/dynatrace/dynatrace-operator \
    --create-namespace \
    --namespace dynatrace \
    --atomic
  kubectl -n dynatrace wait pod --for=condition=ready \
    --selector=app.kubernetes.io/name=dynatrace-operator,app.kubernetes.io/component=webhook \
    --timeout=300s

  # DynaKube와 같은 이름(kind-kind)의 Secret에서 토큰을 읽는다
  kubectl -n dynatrace create secret generic kind-kind \
    --from-literal="apiToken=$DT_OPERATOR_TOKEN" \
    --from-literal="dataIngestToken=$DT_TOKEN" \
    --dry-run=client -o yaml | kubectl apply -f -

  sed "s#\${DT_API_URL}#${DT_ENDPOINT}/api#" dynatrace/dynakube.yaml | kubectl apply -f -

  echo "Waiting for DynaKube (OneAgent / ActiveGate) to be ready"
  if ! kubectl -n dynatrace wait dynakube/kind-kind --for=jsonpath='{.status.phase}'=Running --timeout=600s; then
    echo "WARNING: DynaKube is not Running yet. Check: kubectl -n dynatrace get dynakube,pods"
  fi
  kubectl -n dynatrace rollout status daemonset -l app.kubernetes.io/name=oneagent --timeout=600s || true
else
  echo "WARNING: DT_OPERATOR_TOKEN / DT_TOKEN / DT_ENDPOINT not set - skipping Dynatrace Operator. The app will run without OneAgent."
fi

kubectl create namespace travel-advisor

# Create secrets
kubectl -n travel-advisor create secret generic bedrock \
  --from-literal=region=$AWS_DEFAULT_REGION \
  --from-literal=key=$AWS_ACCESS_KEY_ID \
  --from-literal=secret=$AWS_SECRET_ACCESS_KEY \
  --from-literal=embedding=$AWS_EMBEDDING_MODEL \
  --from-literal=model=$AWS_MODEL \
  --from-literal=guardrail=$AWS_GUARDRAIL_ID \
  --from-literal=guardrail-version=${AWS_GUARDRAIL_VERSION:-DRAFT}

# LLM provider: "anthropic" (default, Claude via Anthropic API) or "bedrock"
kubectl -n travel-advisor create secret generic llm \
  --from-literal=provider=${LLM_PROVIDER:-anthropic} \
  --from-literal=anthropic-key=$ANTHROPIC_API_KEY \
  --from-literal=anthropic-model=${ANTHROPIC_MODEL:-claude-haiku-4-5-20251001}

# Dynatrace secret for the app — RUM(Real User Monitoring) JavaScript tag 전용
#   (트레이스·로그·메트릭은 OneAgent가 수집하므로 앱은 OTLP로 아무것도 보내지 않는다)
#   DT_RUM_SNIPPET: 테넌트에서 복사한 <script ...></script> 전체 (권장). 그대로 HTML <head>에 삽입
#   DT_RUM_APP_ID : (선택, classic RUM 전용) APPLICATION-XXXXXXXXXXXXXXXX 형식 ID. 앱 기동 시
#                   $DT_ENDPOINT/api/v2/rum/javaScriptTag/<id> 로 tag를 조회 (rumManualInsertionTags.read 필요)
#                   새 RUM의 FRONTEND-… ID는 이 API가 400(Invalid application identifier)을 반환하므로 쓸 수 없음
#   DT_RUM_SNIPPET이 있으면 DT_RUM_APP_ID는 무시. 둘 다 비어 있으면 RUM 비활성화
kubectl -n travel-advisor create secret generic dynatrace \
  --from-literal=token=$DT_TOKEN \
  --from-literal=endpoint=$DT_ENDPOINT \
  --from-literal=rum-app-id="${DT_RUM_APP_ID:-}" \
  --from-literal=rum-snippet="${DT_RUM_SNIPPET:-}"

# Deploy the application
kubectl apply -f deployment/travel-advisor.yaml -n travel-advisor

# Wait for travel advisor system to be ready
echo "Waiting for Travel Advisor to be ready"
kubectl -n travel-advisor wait --for=condition=Ready pod --all --timeout=10m
