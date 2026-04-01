#!/usr/bin/env bash
set -euo pipefail

# Prevent Git Bash/MSYS from rewriting AWS CLI args like /ecs/... into Windows paths.
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

# Destroy AWS resources created by deploy_aws_resources.sh
#
# This script deletes, in dependency-safe order:
# - ECS service and cluster
# - ALB/listeners/target group
# - Task definitions (deregister all active revisions for family)
# - CloudWatch log group
# - RDS instance + DB subnet group
# - Secrets Manager secrets
# - ECR repository (force)
# - Security groups (ALB/ECS/RDS)
#
# Usage:
#   chmod +x destroy_aws_resources.sh
#   AWS_REGION=us-east-1 AWS_ACCOUNT_ID=123456789012 ./destroy_aws_resources.sh
#
# Optional variables:
#   PROJECT_NAME=paper-supply
#   FORCE=true                         # required to proceed (default false)
#   DELETE_ECR=true                    # delete ECR repo (default true)
#   DELETE_SECRETS=true                # delete Secrets Manager secrets (default true)
#   DELETE_LOG_GROUP=true              # delete CloudWatch log group (default true)
#   DELETE_RDS=true                    # delete RDS instance (default true)
#   SKIP_FINAL_SNAPSHOT=true           # RDS delete snapshot behavior (default true)
#   FINAL_SNAPSHOT_ID=<snapshot-id>    # required if SKIP_FINAL_SNAPSHOT=false

PROJECT_NAME="${PROJECT_NAME:-paper-supply}"
AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-}"
FORCE="${FORCE:-false}"
DELETE_ECR="${DELETE_ECR:-true}"
DELETE_SECRETS="${DELETE_SECRETS:-true}"
DELETE_LOG_GROUP="${DELETE_LOG_GROUP:-true}"
DELETE_RDS="${DELETE_RDS:-true}"
SKIP_FINAL_SNAPSHOT="${SKIP_FINAL_SNAPSHOT:-true}"
FINAL_SNAPSHOT_ID="${FINAL_SNAPSHOT_ID:-}"

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
DB_SUBNET_GROUP_NAME="${PROJECT_NAME}-db-subnets"

if [[ "${FORCE}" != "true" ]]; then
  echo "Refusing to run destructive delete without FORCE=true"
  echo "Example: FORCE=true AWS_REGION=${AWS_REGION} ./destroy_aws_resources.sh"
  exit 1
fi

if [[ -z "${AWS_ACCOUNT_ID}" ]]; then
  AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
fi

command -v aws >/dev/null 2>&1 || { echo "ERROR: aws cli is required"; exit 1; }

echo "[1/10] Delete ECS service and cluster..."
SERVICE_STATUS="$(aws ecs describe-services --region "${AWS_REGION}" --cluster "${ECS_CLUSTER_NAME}" --services "${ECS_SERVICE_NAME}" --query 'services[0].status' --output text 2>/dev/null || true)"
if [[ "${SERVICE_STATUS}" == "ACTIVE" || "${SERVICE_STATUS}" == "DRAINING" ]]; then
  aws ecs update-service --region "${AWS_REGION}" --cluster "${ECS_CLUSTER_NAME}" --service "${ECS_SERVICE_NAME}" --desired-count 0 >/dev/null || true
  aws ecs delete-service --region "${AWS_REGION}" --cluster "${ECS_CLUSTER_NAME}" --service "${ECS_SERVICE_NAME}" --force >/dev/null || true

  # Wait until service no longer ACTIVE
  for _ in $(seq 1 40); do
    STATUS_NOW="$(aws ecs describe-services --region "${AWS_REGION}" --cluster "${ECS_CLUSTER_NAME}" --services "${ECS_SERVICE_NAME}" --query 'services[0].status' --output text 2>/dev/null || true)"
    [[ "${STATUS_NOW}" != "ACTIVE" ]] && break
    sleep 15
  done
fi

if aws ecs describe-clusters --region "${AWS_REGION}" --clusters "${ECS_CLUSTER_NAME}" --query 'clusters[0].clusterName' --output text 2>/dev/null | grep -q "${ECS_CLUSTER_NAME}"; then
  aws ecs delete-cluster --region "${AWS_REGION}" --cluster "${ECS_CLUSTER_NAME}" >/dev/null || true
fi

echo "[2/10] Delete ALB listener/target group/load balancer..."
ALB_ARN="$(aws elbv2 describe-load-balancers --region "${AWS_REGION}" --names "${ALB_NAME}" --query 'LoadBalancers[0].LoadBalancerArn' --output text 2>/dev/null || true)"
if [[ -n "${ALB_ARN}" && "${ALB_ARN}" != "None" ]]; then
  LISTENER_ARNS="$(aws elbv2 describe-listeners --region "${AWS_REGION}" --load-balancer-arn "${ALB_ARN}" --query 'Listeners[].ListenerArn' --output text 2>/dev/null || true)"
  for l in ${LISTENER_ARNS}; do
    aws elbv2 delete-listener --region "${AWS_REGION}" --listener-arn "${l}" >/dev/null || true
  done
  aws elbv2 delete-load-balancer --region "${AWS_REGION}" --load-balancer-arn "${ALB_ARN}" >/dev/null || true

  # Wait for ALB deletion to complete to release dependencies on SGs
  for _ in $(seq 1 40); do
    EXISTS="$(aws elbv2 describe-load-balancers --region "${AWS_REGION}" --load-balancer-arns "${ALB_ARN}" --query 'LoadBalancers[0].LoadBalancerArn' --output text 2>/dev/null || true)"
    [[ -z "${EXISTS}" || "${EXISTS}" == "None" ]] && break
    sleep 10
  done
fi

TG_ARN="$(aws elbv2 describe-target-groups --region "${AWS_REGION}" --names "${TG_NAME}" --query 'TargetGroups[0].TargetGroupArn' --output text 2>/dev/null || true)"
if [[ -n "${TG_ARN}" && "${TG_ARN}" != "None" ]]; then
  aws elbv2 delete-target-group --region "${AWS_REGION}" --target-group-arn "${TG_ARN}" >/dev/null || true
fi

echo "[3/10] Deregister ECS task definition revisions..."
TASK_DEF_ARNS="$(aws ecs list-task-definitions --region "${AWS_REGION}" --family-prefix "${ECS_TASK_FAMILY}" --status ACTIVE --query 'taskDefinitionArns[]' --output text 2>/dev/null || true)"
for td in ${TASK_DEF_ARNS}; do
  aws ecs deregister-task-definition --region "${AWS_REGION}" --task-definition "${td}" >/dev/null || true
done

echo "[4/10] Delete RDS instance (optional)..."
if [[ "${DELETE_RDS}" == "true" ]]; then
  if aws rds describe-db-instances --region "${AWS_REGION}" --db-instance-identifier "${RDS_INSTANCE_ID}" >/dev/null 2>&1; then
    if [[ "${SKIP_FINAL_SNAPSHOT}" == "true" ]]; then
      aws rds delete-db-instance \
        --region "${AWS_REGION}" \
        --db-instance-identifier "${RDS_INSTANCE_ID}" \
        --skip-final-snapshot >/dev/null || true
    else
      if [[ -z "${FINAL_SNAPSHOT_ID}" ]]; then
        echo "ERROR: FINAL_SNAPSHOT_ID is required when SKIP_FINAL_SNAPSHOT=false"
        exit 1
      fi
      aws rds delete-db-instance \
        --region "${AWS_REGION}" \
        --db-instance-identifier "${RDS_INSTANCE_ID}" \
        --final-db-snapshot-identifier "${FINAL_SNAPSHOT_ID}" >/dev/null || true
    fi

    for _ in $(seq 1 80); do
      if ! aws rds describe-db-instances --region "${AWS_REGION}" --db-instance-identifier "${RDS_INSTANCE_ID}" >/dev/null 2>&1; then
        break
      fi
      sleep 20
    done
  fi

  if aws rds describe-db-subnet-groups --region "${AWS_REGION}" --db-subnet-group-name "${DB_SUBNET_GROUP_NAME}" >/dev/null 2>&1; then
    aws rds delete-db-subnet-group --region "${AWS_REGION}" --db-subnet-group-name "${DB_SUBNET_GROUP_NAME}" >/dev/null || true
  fi
fi

echo "[5/10] Delete secrets (optional)..."
if [[ "${DELETE_SECRETS}" == "true" ]]; then
  for s in "${OPENAI_SECRET_NAME}" "${RDS_SECRET_NAME}" "${DB_URL_SECRET_NAME}"; do
    if aws secretsmanager describe-secret --region "${AWS_REGION}" --secret-id "${s}" >/dev/null 2>&1; then
      aws secretsmanager delete-secret --region "${AWS_REGION}" --secret-id "${s}" --force-delete-without-recovery >/dev/null || true
    fi
  done
fi

echo "[6/10] Delete ECR repository (optional)..."
if [[ "${DELETE_ECR}" == "true" ]]; then
  if aws ecr describe-repositories --region "${AWS_REGION}" --repository-names "${ECR_REPO_NAME}" >/dev/null 2>&1; then
    aws ecr delete-repository --region "${AWS_REGION}" --repository-name "${ECR_REPO_NAME}" --force >/dev/null || true
  fi
fi

echo "[7/10] Delete CloudWatch log group (optional)..."
if [[ "${DELETE_LOG_GROUP}" == "true" ]]; then
  if aws logs describe-log-groups --region "${AWS_REGION}" --log-group-name-prefix "${LOG_GROUP_NAME}" --query 'logGroups[?logGroupName==`'"${LOG_GROUP_NAME}"'`].logGroupName' --output text | grep -q "${LOG_GROUP_NAME}"; then
    aws logs delete-log-group --region "${AWS_REGION}" --log-group-name "${LOG_GROUP_NAME}" >/dev/null || true
  fi
fi

echo "[8/10] Delete security groups..."
VPC_ID="$(aws ec2 describe-vpcs --region "${AWS_REGION}" --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text 2>/dev/null || true)"
if [[ -n "${VPC_ID}" && "${VPC_ID}" != "None" ]]; then
  for sg_name in "${PROJECT_NAME}-alb-sg" "${PROJECT_NAME}-ecs-sg" "${PROJECT_NAME}-rds-sg"; do
    SG_ID="$(aws ec2 describe-security-groups --region "${AWS_REGION}" --filters Name=group-name,Values="${sg_name}" Name=vpc-id,Values="${VPC_ID}" --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || true)"
    if [[ -n "${SG_ID}" && "${SG_ID}" != "None" ]]; then
      aws ec2 delete-security-group --region "${AWS_REGION}" --group-id "${SG_ID}" >/dev/null || true
    fi
  done
fi

echo "[9/10] Final status summary..."
echo "Project: ${PROJECT_NAME}"
echo "Region: ${AWS_REGION}"
echo "Deleted (requested): ECS, ALB/TG, task defs, RDS=${DELETE_RDS}, secrets=${DELETE_SECRETS}, ECR=${DELETE_ECR}, logs=${DELETE_LOG_GROUP}"

echo "[10/10] Done."
