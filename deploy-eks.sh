#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# travel-advisor (oneagent-fullstack branch) → Amazon EKS 배포 스크립트
#   repo 루트에서 실행:  source .env-eks && ./deploy-eks.sh   (.env-eks.example 참고)
#   절차·검증 결과: docs/eks-oneagent-test.md
#   필요 도구: aws CLI(v2, 인증 완료), eksctl, kubectl, helm, docker(buildx)
#   원본 .devcontainer/deployment.sh(kind 전용)와의 차이
#     1) 이미지: kind load → ECR push (linux/amd64)
#     2) DynaKube 이름: kind-kind → ${DK_NAME}  (Dynatrace에 보이는 K8s cluster 이름)
#     3) Service: NodePort 30100 → LoadBalancer (ELB hostname)
#   순서는 원본과 동일: Operator/DynaKube 먼저 → 앱 배포 (Pod 생성 시 code module 주입)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ==== [개인 환경에 맞게 수정] ===============================================
AWS_REGION="${AWS_REGION:-ap-northeast-2}"          # EKS/ECR 리전 (서울)
CLUSTER="${CLUSTER:-traveladvisor}"                 # EKS 클러스터 이름
CREATE_CLUSTER="${CREATE_CLUSTER:-false}"           # true면 eksctl로 신규 생성 (약 15~20분)
NODE_TYPE="${NODE_TYPE:-t3.xlarge}"                 # 4 vCPU / 16 GiB, x86_64
NODES="${NODES:-2}"
ECR_REPO="${ECR_REPO:-travel-advisor}"
TAG="${TAG:-$(git rev-parse --short HEAD 2>/dev/null || echo v1)}"
DK_NAME="${DK_NAME:-eks-traveladvisor}"             # DynaKube 이름 = Dynatrace K8s cluster 이름
ALLOWED_CIDR="${ALLOWED_CIDR:-}"                    # 예: 203.0.113.10/32 (비우면 전체 공개 — 비권장)
SKIP_BUILD="${SKIP_BUILD:-false}"                   # true면 이미지 빌드/push 생략 (이미 ECR에 ${TAG} 가 있을 때)
# 아래 값은 원본 README와 동일하게 export 해서 전달
: "${DT_ENDPOINT:?}" "${DT_OPERATOR_TOKEN:?}" "${DT_TOKEN:?}"
LLM_PROVIDER="${LLM_PROVIDER:-anthropic}"
# ============================================================================

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGISTRY="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE="${REGISTRY}/${ECR_REPO}:${TAG}"
DT_ENDPOINT="${DT_ENDPOINT%/}"

# ── 0. (선택) EKS 클러스터 생성 ───────────────────────────────────────────────
#   - EC2 managed nodegroup(AL2023) 사용: cloudNativeFullStack 지원
#   - Fargate / Bottlerocket(=EKS Auto Mode 노드)은 노드 OneAgent 미지원 → 사용하지 않음
#   - eksctl managed nodegroup은 노드 IAM Role에 ECR read 권한을 기본 부여
if [ "$CREATE_CLUSTER" = "true" ]; then
  eksctl create cluster \
    --name "$CLUSTER" \
    --region "$AWS_REGION" \
    --managed \
    --node-type "$NODE_TYPE" \
    --nodes "$NODES" \
    --node-ami-family AmazonLinux2023
fi
aws eks update-kubeconfig --name "$CLUSTER" --region "$AWS_REGION"

# ── 1. 이미지 빌드 → ECR ──────────────────────────────────────────────────────
if [ "$SKIP_BUILD" != "true" ]; then
aws ecr describe-repositories --repository-names "$ECR_REPO" --region "$AWS_REGION" >/dev/null 2>&1 || \
  aws ecr create-repository --repository-name "$ECR_REPO" --region "$AWS_REGION" >/dev/null
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$REGISTRY"
# 노드가 x86_64이므로 amd64로 빌드 (Apple Silicon Mac에서도 동일하게 동작)
docker buildx build --platform linux/amd64 -t "$IMAGE" --push .
fi

# ── 2. Dynatrace Operator + DynaKube ─────────────────────────────────────────
helm upgrade --install dynatrace-operator oci://public.ecr.aws/dynatrace/dynatrace-operator \
  --create-namespace --namespace dynatrace --atomic
kubectl -n dynatrace wait pod --for=condition=ready \
  --selector=app.kubernetes.io/name=dynatrace-operator,app.kubernetes.io/component=webhook \
  --timeout=300s

# Secret 이름 = DynaKube 이름
kubectl -n dynatrace create secret generic "$DK_NAME" \
  --from-literal="apiToken=$DT_OPERATOR_TOKEN" \
  --from-literal="dataIngestToken=$DT_TOKEN" \
  --dry-run=client -o yaml | kubectl apply -f -

sed -e "s#\${DT_API_URL}#${DT_ENDPOINT}/api#" \
    -e "s#name: kind-kind#name: ${DK_NAME}#" \
    dynatrace/dynakube.yaml | kubectl apply -f -

kubectl -n dynatrace wait "dynakube/${DK_NAME}" --for=jsonpath='{.status.phase}'=Running --timeout=600s \
  || echo "WARNING: DynaKube not Running yet → kubectl -n dynatrace get dynakube,pods"
kubectl -n dynatrace rollout status daemonset -l app.kubernetes.io/name=oneagent --timeout=600s || true

# ── 3. 앱 Secret (원본 deployment.sh와 동일, 재실행 가능하도록 apply) ─────────
kubectl create namespace travel-advisor --dry-run=client -o yaml | kubectl apply -f -

# LLM_PROVIDER=bedrock 이면 BEDROCK_ACCESS_KEY_ID/SECRET 필수 (앱이 키를 명시적으로 boto3에 전달)
#   ※ AWS_ACCESS_KEY_ID 로 export 하면 aws CLI/eksctl 이 AWS_PROFILE 대신 그 키를 써버리므로 이름을 분리
kubectl -n travel-advisor create secret generic bedrock \
  --from-literal=region="${BEDROCK_REGION:-us-east-1}" \
  --from-literal=key="${BEDROCK_ACCESS_KEY_ID:-}" \
  --from-literal=secret="${BEDROCK_SECRET_ACCESS_KEY:-}" \
  --from-literal=embedding="${AWS_EMBEDDING_MODEL:-amazon.titan-embed-text-v2:0}" \
  --from-literal=model="${AWS_MODEL:-us.amazon.nova-2-lite-v1:0}" \
  --from-literal=guardrail="${AWS_GUARDRAIL_ID:-}" \
  --from-literal=guardrail-version="${AWS_GUARDRAIL_VERSION:-DRAFT}" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n travel-advisor create secret generic llm \
  --from-literal=provider="$LLM_PROVIDER" \
  --from-literal=anthropic-key="${ANTHROPIC_API_KEY:-}" \
  --from-literal=anthropic-model="${ANTHROPIC_MODEL:-claude-haiku-4-5-20251001}" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n travel-advisor create secret generic dynatrace \
  --from-literal=token="$DT_TOKEN" \
  --from-literal=endpoint="$DT_ENDPOINT" \
  --from-literal=rum-app-id="${DT_RUM_APP_ID:-}" \
  --from-literal=rum-snippet="${DT_RUM_SNIPPET:-}" \
  --dry-run=client -o yaml | kubectl apply -f -

# ── 4. 앱 배포 (kind 전용 값만 치환) ──────────────────────────────────────────
sed -e "s#image: travel-advisor:local#image: ${IMAGE}#" \
    -e "s#imagePullPolicy: Never#imagePullPolicy: IfNotPresent#" \
    -e "s#type: NodePort#type: LoadBalancer#" \
    -e "/nodePort: 30100/d" \
    deployment/travel-advisor.yaml | kubectl apply -f -

if [ -n "$ALLOWED_CIDR" ]; then
  kubectl -n travel-advisor patch svc travel-advisor \
    -p "{\"spec\":{\"loadBalancerSourceRanges\":[\"${ALLOWED_CIDR}\"]}}"
fi

kubectl -n travel-advisor rollout status deploy/travel-advisor --timeout=10m

echo "Waiting for ELB hostname..."
for _ in $(seq 1 30); do
  HOST=$(kubectl -n travel-advisor get svc travel-advisor -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' || true)
  [ -n "$HOST" ] && break; sleep 10
done
echo "UI: http://${HOST:-<pending>}/   Guide: http://${HOST:-<pending>}/guide.html"
echo "(ELB DNS 전파에 1~3분 걸릴 수 있음)"

# ── 정리 (비용 발생 중지) ─────────────────────────────────────────────────────
#   kubectl -n travel-advisor delete svc travel-advisor      # ELB 먼저 삭제
#   eksctl delete cluster --name "$CLUSTER" --region "$AWS_REGION"
#   aws ecr delete-repository --repository-name "$ECR_REPO" --region "$AWS_REGION" --force
