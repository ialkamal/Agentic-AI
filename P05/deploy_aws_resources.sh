#!/usr/bin/env bash
set -euo pipefail

# Prevent Git Bash/MSYS from rewriting AWS CLI args like /ecs/... into Windows paths.
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

# Deploy core AWS resources for Paper Supply API:
# - ECR repository
# - Secrets Manager secrets (OpenAI key, DB credentials, DATABASE_URL)
# - RDS PostgreSQL instance
# - ECS cluster + task definition + Fargate service
# - Application Load Balancer + target group + listener
#
# Prerequisites:
# - aws cli configured with permissions
# - docker installed and running (unless SKIP_IMAGE_PUSH=true)
# - jq is NOT required
#
# Usage:
#   chmod +x deploy_aws_resources.sh
#   AWS_REGION=us-east-1 \
#   AWS_ACCOUNT_ID=123456789012 \
#   OPENAI_API_KEY=sk-... \
#   DB_PASSWORD='StrongPassword123!' \
#   ./deploy_aws_resources.sh
#
# Optional variables:
#   PROJECT_NAME=paper-supply
#   DB_INSTANCE_CLASS=db.t3.micro
#   DB_ALLOCATED_STORAGE=20
#   ECS_CPU=512
#   ECS_MEMORY=1024
#   IMAGE_TAG=latest
#   SKIP_IMAGE_PUSH=false
#   USE_EXISTING_IMAGE_URI=<full-ecr-image-uri>

PROJECT_NAME="${PROJECT_NAME:-paper-supply}"
AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-}"
OPENAI_API_KEY="${OPENAI_API_KEY:-}"
DB_PASSWORD="${DB_PASSWORD:-}"
DB_USERNAME="${DB_USERNAME:-paperadmin}"
DB_NAME="${DB_NAME:-paper_supplies}"
DB_INSTANCE_CLASS="${DB_INSTANCE_CLASS:-db.t3.micro}"
DB_ALLOCATED_STORAGE="${DB_ALLOCATED_STORAGE:-20}"
DB_ENGINE_VERSION="${DB_ENGINE_VERSION:-}"
ECS_CPU="${ECS_CPU:-512}"
ECS_MEMORY="${ECS_MEMORY:-1024}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
SKIP_IMAGE_PUSH="${SKIP_IMAGE_PUSH:-false}"
USE_EXISTING_IMAGE_URI="${USE_EXISTING_IMAGE_URI:-}"

ECR_REPO_NAME="${PROJECT_NAME}-api"
ECS_CLUSTER_NAME="${PROJECT_NAME}-cluster"
ECS_SERVICE_NAME="${PROJECT_NAME}-service"
ECS_TASK_FAMILY="${PROJECT_NAME}-task"
RDS_INSTANCE_ID="${PROJECT_NAME//_/}-db"
RDS_SECRET_NAME="${PROJECT_NAME}/db-credentials"
OPENAI_SECRET_NAME="${PROJECT_NAME}/openai-key"
DB_URL_SECRET_NAME="${PROJECT_NAME}/database-url"
LOG_GROUP_NAME="ecs/${PROJECT_NAME}-api"
ALB_NAME="${PROJECT_NAME}-alb"
TG_NAME="${PROJECT_NAME}-tg"

TMP_DIR="${PWD}/.aws-deploy-tmp"
mkdir -p "${TMP_DIR}"
TRUST_POLICY_FILE="${TMP_DIR}/ecs-task-trust-policy.json"
SECRETS_POLICY_FILE="${TMP_DIR}/${PROJECT_NAME}-task-secrets-policy.json"
TASKDEF_FILE="${TMP_DIR}/${PROJECT_NAME}-taskdef.json"

cleanup() {
  rm -f "${TRUST_POLICY_FILE}" "${SECRETS_POLICY_FILE}" "${TASKDEF_FILE}" 2>/dev/null || true
  rmdir "${TMP_DIR}" 2>/dev/null || true
}
trap cleanup EXIT

if [[ -z "${AWS_ACCOUNT_ID}" ]]; then
  AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
fi

if [[ -z "${OPENAI_API_KEY}" ]]; then
  echo "ERROR: OPENAI_API_KEY is required."
  exit 1
fi

if [[ -z "${DB_PASSWORD}" ]]; then
  echo "ERROR: DB_PASSWORD is required."
  exit 1
fi

command -v aws >/dev/null 2>&1 || { echo "ERROR: aws cli is required"; exit 1; }

if [[ "${SKIP_IMAGE_PUSH}" != "true" ]]; then
  command -v docker >/dev/null 2>&1 || { echo "ERROR: docker is required when SKIP_IMAGE_PUSH=false"; exit 1; }
fi

echo "[1/12] Resolving default VPC and subnets..."
VPC_ID="$(aws ec2 describe-vpcs --region "${AWS_REGION}" --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)"
if [[ "${VPC_ID}" == "None" || -z "${VPC_ID}" ]]; then
  echo "ERROR: No default VPC found. Please create one or customize this script for your VPC."
  exit 1
fi

SUBNET_IDS_RAW="$(aws ec2 describe-subnets --region "${AWS_REGION}" --filters Name=vpc-id,Values="${VPC_ID}" --query 'Subnets[].SubnetId' --output text)"
read -r -a SUBNET_IDS <<< "${SUBNET_IDS_RAW}"
if (( ${#SUBNET_IDS[@]} < 2 )); then
  echo "ERROR: Need at least 2 subnets for RDS/ECS/ALB."
  exit 1
fi

SUBNET_ID_1="${SUBNET_IDS[0]}"
SUBNET_ID_2="${SUBNET_IDS[1]}"
ALB_ECS_SUBNET_IDS_CSV="${SUBNET_ID_1},${SUBNET_ID_2}"

echo "[2/12] Creating ECR repository (if missing)..."
if ! aws ecr describe-repositories --region "${AWS_REGION}" --repository-names "${ECR_REPO_NAME}" >/dev/null 2>&1; then
  aws ecr create-repository --region "${AWS_REGION}" --repository-name "${ECR_REPO_NAME}" >/dev/null
fi

ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO_NAME}"
IMAGE_URI="${ECR_URI}:${IMAGE_TAG}"

if [[ -n "${USE_EXISTING_IMAGE_URI}" ]]; then
  IMAGE_URI="${USE_EXISTING_IMAGE_URI}"
fi

echo "[3/12] Building and pushing container image (optional)..."
if [[ "${SKIP_IMAGE_PUSH}" != "true" && -z "${USE_EXISTING_IMAGE_URI}" ]]; then
  aws ecr get-login-password --region "${AWS_REGION}" | docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
  docker build -t "${ECR_REPO_NAME}:${IMAGE_TAG}" .
  docker tag "${ECR_REPO_NAME}:${IMAGE_TAG}" "${IMAGE_URI}"
  docker push "${IMAGE_URI}"
fi

echo "[4/12] Ensuring security groups exist..."
ALB_SG_ID="$(aws ec2 describe-security-groups --region "${AWS_REGION}" --filters Name=group-name,Values="${PROJECT_NAME}-alb-sg" Name=vpc-id,Values="${VPC_ID}" --query 'SecurityGroups[0].GroupId' --output text)"
if [[ "${ALB_SG_ID}" == "None" ]]; then
  ALB_SG_ID="$(aws ec2 create-security-group --region "${AWS_REGION}" --group-name "${PROJECT_NAME}-alb-sg" --description "ALB SG for ${PROJECT_NAME}" --vpc-id "${VPC_ID}" --query 'GroupId' --output text)"
  aws ec2 authorize-security-group-ingress --region "${AWS_REGION}" --group-id "${ALB_SG_ID}" --protocol tcp --port 80 --cidr 0.0.0.0/0 >/dev/null || true
fi

ECS_SG_ID="$(aws ec2 describe-security-groups --region "${AWS_REGION}" --filters Name=group-name,Values="${PROJECT_NAME}-ecs-sg" Name=vpc-id,Values="${VPC_ID}" --query 'SecurityGroups[0].GroupId' --output text)"
if [[ "${ECS_SG_ID}" == "None" ]]; then
  ECS_SG_ID="$(aws ec2 create-security-group --region "${AWS_REGION}" --group-name "${PROJECT_NAME}-ecs-sg" --description "ECS SG for ${PROJECT_NAME}" --vpc-id "${VPC_ID}" --query 'GroupId' --output text)"
  aws ec2 authorize-security-group-ingress --region "${AWS_REGION}" --group-id "${ECS_SG_ID}" --protocol tcp --port 8000 --source-group "${ALB_SG_ID}" >/dev/null || true
fi

RDS_SG_ID="$(aws ec2 describe-security-groups --region "${AWS_REGION}" --filters Name=group-name,Values="${PROJECT_NAME}-rds-sg" Name=vpc-id,Values="${VPC_ID}" --query 'SecurityGroups[0].GroupId' --output text)"
if [[ "${RDS_SG_ID}" == "None" ]]; then
  RDS_SG_ID="$(aws ec2 create-security-group --region "${AWS_REGION}" --group-name "${PROJECT_NAME}-rds-sg" --description "RDS SG for ${PROJECT_NAME}" --vpc-id "${VPC_ID}" --query 'GroupId' --output text)"
  aws ec2 authorize-security-group-ingress --region "${AWS_REGION}" --group-id "${RDS_SG_ID}" --protocol tcp --port 5432 --source-group "${ECS_SG_ID}" >/dev/null || true
fi

echo "[5/12] Ensuring DB subnet group exists..."
DB_SUBNET_GROUP_NAME="${PROJECT_NAME}-db-subnets"
if ! aws rds describe-db-subnet-groups --region "${AWS_REGION}" --db-subnet-group-name "${DB_SUBNET_GROUP_NAME}" >/dev/null 2>&1; then
  aws rds create-db-subnet-group \
    --region "${AWS_REGION}" \
    --db-subnet-group-name "${DB_SUBNET_GROUP_NAME}" \
    --db-subnet-group-description "DB subnet group for ${PROJECT_NAME}" \
    --subnet-ids "${SUBNET_ID_1}" "${SUBNET_ID_2}" >/dev/null
fi

echo "[6/12] Ensuring RDS PostgreSQL instance exists..."
if ! aws rds describe-db-instances --region "${AWS_REGION}" --db-instance-identifier "${RDS_INSTANCE_ID}" >/dev/null 2>&1; then
  CREATE_DB_ARGS=(
    aws rds create-db-instance
    --region "${AWS_REGION}"
    --db-instance-identifier "${RDS_INSTANCE_ID}"
    --db-instance-class "${DB_INSTANCE_CLASS}"
    --engine postgres
    --master-username "${DB_USERNAME}"
    --master-user-password "${DB_PASSWORD}"
    --allocated-storage "${DB_ALLOCATED_STORAGE}"
    --db-name "${DB_NAME}"
    --vpc-security-group-ids "${RDS_SG_ID}"
    --db-subnet-group-name "${DB_SUBNET_GROUP_NAME}"
    --no-publicly-accessible
    --backup-retention-period 7
  )

  # Optional override if you need a specific engine version available in your region.
  if [[ -n "${DB_ENGINE_VERSION}" ]]; then
    CREATE_DB_ARGS+=(--engine-version "${DB_ENGINE_VERSION}")
  fi

  "${CREATE_DB_ARGS[@]}" >/dev/null
fi

aws rds wait db-instance-available --region "${AWS_REGION}" --db-instance-identifier "${RDS_INSTANCE_ID}"

DB_HOST="$(aws rds describe-db-instances --region "${AWS_REGION}" --db-instance-identifier "${RDS_INSTANCE_ID}" --query 'DBInstances[0].Endpoint.Address' --output text)"
DATABASE_URL="postgresql://${DB_USERNAME}:${DB_PASSWORD}@${DB_HOST}:5432/${DB_NAME}"

echo "[7/12] Creating/updating secrets..."
upsert_secret() {
  local name="$1"
  local value="$2"
  if aws secretsmanager describe-secret --region "${AWS_REGION}" --secret-id "${name}" >/dev/null 2>&1; then
    aws secretsmanager put-secret-value --region "${AWS_REGION}" --secret-id "${name}" --secret-string "${value}" >/dev/null
  else
    aws secretsmanager create-secret --region "${AWS_REGION}" --name "${name}" --secret-string "${value}" >/dev/null
  fi
}

upsert_secret "${OPENAI_SECRET_NAME}" "{\"api_key\":\"${OPENAI_API_KEY}\"}"
upsert_secret "${RDS_SECRET_NAME}" "{\"username\":\"${DB_USERNAME}\",\"password\":\"${DB_PASSWORD}\",\"host\":\"${DB_HOST}\",\"port\":5432,\"dbname\":\"${DB_NAME}\"}"
upsert_secret "${DB_URL_SECRET_NAME}" "{\"url\":\"${DATABASE_URL}\"}"

echo "[8/12] Ensuring CloudWatch log group exists..."
if ! aws logs describe-log-groups --region "${AWS_REGION}" --log-group-name-prefix "${LOG_GROUP_NAME}" --query 'logGroups[?logGroupName==`'"${LOG_GROUP_NAME}"'`].logGroupName' --output text | grep -q "${LOG_GROUP_NAME}"; then
  aws logs create-log-group --region "${AWS_REGION}" --log-group-name "${LOG_GROUP_NAME}" >/dev/null
fi

echo "[9/12] Ensuring ECS cluster exists..."
if ! aws ecs describe-clusters --region "${AWS_REGION}" --clusters "${ECS_CLUSTER_NAME}" --query 'clusters[0].clusterName' --output text | grep -q "${ECS_CLUSTER_NAME}"; then
  aws ecs create-cluster --region "${AWS_REGION}" --cluster-name "${ECS_CLUSTER_NAME}" >/dev/null
fi

echo "[10/12] Ensuring task execution role exists..."
ROLE_NAME="ecsTaskExecutionRole"
ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/${ROLE_NAME}"

if ! aws iam get-role --role-name "${ROLE_NAME}" >/dev/null 2>&1; then
  cat > "${TRUST_POLICY_FILE}" <<'JSON'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {"Service": "ecs-tasks.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }
  ]
}
JSON
  TRUST_POLICY_JSON="$(cat "${TRUST_POLICY_FILE}")"
  aws iam create-role --role-name "${ROLE_NAME}" --assume-role-policy-document "${TRUST_POLICY_JSON}" >/dev/null
  aws iam attach-role-policy --role-name "${ROLE_NAME}" --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy >/dev/null
fi

cat > "${SECRETS_POLICY_FILE}" <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["secretsmanager:GetSecretValue", "kms:Decrypt"],
      "Resource": "*"
    }
  ]
}
JSON
SECRETS_POLICY_JSON="$(cat "${SECRETS_POLICY_FILE}")"
aws iam put-role-policy --role-name "${ROLE_NAME}" --policy-name "${PROJECT_NAME}-secrets-inline" --policy-document "${SECRETS_POLICY_JSON}" >/dev/null

OPENAI_SECRET_ARN="$(aws secretsmanager describe-secret --region "${AWS_REGION}" --secret-id "${OPENAI_SECRET_NAME}" --query 'ARN' --output text)"
DB_URL_SECRET_ARN="$(aws secretsmanager describe-secret --region "${AWS_REGION}" --secret-id "${DB_URL_SECRET_NAME}" --query 'ARN' --output text)"

cat > "${TASKDEF_FILE}" <<JSON
{
  "family": "${ECS_TASK_FAMILY}",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "${ECS_CPU}",
  "memory": "${ECS_MEMORY}",
  "executionRoleArn": "${ROLE_ARN}",
  "containerDefinitions": [
    {
      "name": "${PROJECT_NAME}-api",
      "image": "${IMAGE_URI}",
      "essential": true,
      "portMappings": [
        {"containerPort": 8000, "hostPort": 8000, "protocol": "tcp"}
      ],
      "environment": [
        {"name": "PORT", "value": "8000"}
      ],
      "secrets": [
        {"name": "OPENAI_API_KEY", "valueFrom": "${OPENAI_SECRET_ARN}:api_key::"},
        {"name": "DATABASE_URL", "valueFrom": "${DB_URL_SECRET_ARN}:url::"}
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "${LOG_GROUP_NAME}",
          "awslogs-region": "${AWS_REGION}",
          "awslogs-stream-prefix": "ecs"
        }
      },
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"],
        "interval": 30,
        "timeout": 10,
        "retries": 3,
        "startPeriod": 45
      }
    }
  ]
}
JSON

TASK_DEF_JSON="$(cat "${TASKDEF_FILE}")"
TASK_DEF_ARN="$(aws ecs register-task-definition --region "${AWS_REGION}" --cli-input-json "${TASK_DEF_JSON}" --query 'taskDefinition.taskDefinitionArn' --output text)"

echo "[11/12] Ensuring ALB + target group + listener exist..."
ALB_ARN="$(aws elbv2 describe-load-balancers --region "${AWS_REGION}" --names "${ALB_NAME}" --query 'LoadBalancers[0].LoadBalancerArn' --output text 2>/dev/null || true)"
if [[ -z "${ALB_ARN}" || "${ALB_ARN}" == "None" ]]; then
  ALB_ARN="$(aws elbv2 create-load-balancer --region "${AWS_REGION}" --name "${ALB_NAME}" --subnets "${SUBNET_ID_1}" "${SUBNET_ID_2}" --security-groups "${ALB_SG_ID}" --scheme internet-facing --type application --query 'LoadBalancers[0].LoadBalancerArn' --output text)"
fi

TG_ARN="$(aws elbv2 describe-target-groups --region "${AWS_REGION}" --names "${TG_NAME}" --query 'TargetGroups[0].TargetGroupArn' --output text 2>/dev/null || true)"
if [[ -z "${TG_ARN}" || "${TG_ARN}" == "None" ]]; then
  TG_ARN="$(aws elbv2 create-target-group --region "${AWS_REGION}" --name "${TG_NAME}" --protocol HTTP --port 8000 --target-type ip --vpc-id "${VPC_ID}" --health-check-path /health --query 'TargetGroups[0].TargetGroupArn' --output text)"
fi

LISTENER_ARN="$(aws elbv2 describe-listeners --region "${AWS_REGION}" --load-balancer-arn "${ALB_ARN}" --query 'Listeners[?Port==`80`].ListenerArn' --output text)"
if [[ -z "${LISTENER_ARN}" || "${LISTENER_ARN}" == "None" ]]; then
  aws elbv2 create-listener --region "${AWS_REGION}" --load-balancer-arn "${ALB_ARN}" --protocol HTTP --port 80 --default-actions Type=forward,TargetGroupArn="${TG_ARN}" >/dev/null
fi

echo "[12/12] Creating/updating ECS service..."
SERVICE_STATUS="$(aws ecs describe-services --region "${AWS_REGION}" --cluster "${ECS_CLUSTER_NAME}" --services "${ECS_SERVICE_NAME}" --query 'services[0].status' --output text 2>/dev/null || true)"

NETWORK_CFG="awsvpcConfiguration={subnets=[${ALB_ECS_SUBNET_IDS_CSV}],securityGroups=[${ECS_SG_ID}],assignPublicIp=ENABLED}"

if [[ "${SERVICE_STATUS}" == "ACTIVE" || "${SERVICE_STATUS}" == "DRAINING" ]]; then
  aws ecs update-service \
    --region "${AWS_REGION}" \
    --cluster "${ECS_CLUSTER_NAME}" \
    --service "${ECS_SERVICE_NAME}" \
    --network-configuration "${NETWORK_CFG}" \
    --task-definition "${TASK_DEF_ARN}" \
    --force-new-deployment >/dev/null
else
  aws ecs create-service \
    --region "${AWS_REGION}" \
    --cluster "${ECS_CLUSTER_NAME}" \
    --service-name "${ECS_SERVICE_NAME}" \
    --task-definition "${TASK_DEF_ARN}" \
    --desired-count 1 \
    --launch-type FARGATE \
    --network-configuration "${NETWORK_CFG}" \
    --load-balancers targetGroupArn="${TG_ARN}",containerName="${PROJECT_NAME}-api",containerPort=8000 >/dev/null
fi

ALB_DNS="$(aws elbv2 describe-load-balancers --region "${AWS_REGION}" --load-balancer-arns "${ALB_ARN}" --query 'LoadBalancers[0].DNSName' --output text)"

echo
echo "Deployment complete."
echo "Project: ${PROJECT_NAME}"
echo "Region: ${AWS_REGION}"
echo "Image URI: ${IMAGE_URI}"
echo "RDS host: ${DB_HOST}"
echo "ALB endpoint: http://${ALB_DNS}"
echo "Health check: http://${ALB_DNS}/health"
