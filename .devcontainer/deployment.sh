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
#   DT_RUM_SNIPPET: 테넌트에서 복사한 <script ...></script> 전체 (권장). 그대로 HTML <head>에 삽입
#   DT_RUM_APP_ID : (선택, classic RUM 전용) APPLICATION-XXXXXXXXXXXXXXXX 형식 ID. 앱 기동 시
#                   $DT_ENDPOINT/api/v2/rum/javaScriptTag/<id> 로 tag를 조회 (rumManualInsertionTags.read 필요)
#                   새 RUM의 FRONTEND-… ID는 이 API가 400(Invalid application identifier)을 반환하므로 쓸 수 없음
#   DT_RUM_SNIPPET이 있으면 DT_RUM_APP_ID는 무시. 둘 다 비어 있으면 RUM 비활성화
kubectl -n travel-advisor create secret generic dynatrace \
  --from-literal=token=$DT_TOKEN \
  --from-literal=endpoint=$DT_ENDPOINT/api/v2/otlp \
  --from-literal=rum-app-id="${DT_RUM_APP_ID:-}" \
  --from-literal=rum-snippet="${DT_RUM_SNIPPET:-}"

# Kubernetes cluster identity for OTel resource attributes (k8s.cluster.uid / k8s.cluster.name)
#   k8s.cluster.uid : kube-system namespace UID — Dynatrace가 K8s cluster entity를 식별하는 값
#   k8s.cluster.name: Dynatrace에 보이는 cluster 이름 (DynaKube 이름 기준, 기본 kind-kind)
kubectl -n travel-advisor create configmap k8s-cluster-info \
  --from-literal=cluster-uid="$(kubectl get namespace kube-system -o jsonpath='{.metadata.uid}')" \
  --from-literal=cluster-name="${K8S_CLUSTER_NAME:-kind-kind}" \
  --dry-run=client -o yaml | kubectl apply -f -

# Deploy the application
kubectl apply -f deployment/travel-advisor.yaml -n travel-advisor

# Wait for travel advisor system to be ready
echo "Waiting for Travel Advisor to be ready"
kubectl -n travel-advisor wait --for=condition=Ready pod --all --timeout=10m
