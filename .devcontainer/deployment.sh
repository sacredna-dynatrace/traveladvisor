#!/usr/bin/env bash

# Titan Text G1 models are End-of-Life, so the prebuilt image (thisthatdc/travel-advisor:v0.3.0-bedrock)
# no longer works. Build the app from this repo (Bedrock Converse API) and load it into kind.
docker build -t travel-advisor:local .
kind load docker-image travel-advisor:local --name kind

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

# Dynatrace: OTLP ingest + RUM(Real User Monitoring) JavaScript tag
#   DT_RUM_APP_ID : Web application ID (APPLICATION-XXXXXXXXXXXXXXXX). 앱 기동 시
#                   $DT_ENDPOINT/api/v2/rum/javaScriptTag/<id> 로 최신 tag를 받아 HTML <head>에 삽입
#                   (DT_TOKEN에 rumManualInsertionTags.read scope 필요)
#   DT_RUM_SNIPPET: API 대신 테넌트에서 복사한 <script ...></script> 전체를 직접 지정할 때 사용
#   둘 다 비어 있으면 RUM 비활성화
kubectl -n travel-advisor create secret generic dynatrace \
  --from-literal=token=$DT_TOKEN \
  --from-literal=endpoint=$DT_ENDPOINT/api/v2/otlp \
  --from-literal=rum-app-id="${DT_RUM_APP_ID:-}" \
  --from-literal=rum-snippet="${DT_RUM_SNIPPET:-}"

# Deploy the application
kubectl apply -f deployment/travel-advisor.yaml -n travel-advisor

# Wait for travel advisor system to be ready
echo "Waiting for Travel Advisor to be ready"
kubectl -n travel-advisor wait --for=condition=Ready pod --all --timeout=10m
