# AWS Deployment Guide: Paper Supply Agent API

## Deployment Strategy

This guide covers deploying the Paper Supply Agent API on AWS using:

- **Container Registry**: Amazon ECR (Elastic Container Registry)
- **Compute**: ECS Fargate (recommended) or EC2
- **Database**: Amazon RDS PostgreSQL
- **Load Balancing**: Application Load Balancer (optional)
- **Secrets Management**: AWS Secrets Manager

## Prerequisites

1. AWS Account with appropriate permissions
2. AWS CLI configured locally
3. Docker installed
4. Git access to your repository

## One-Command Provisioning Script

You can provision and deploy with the script in [deploy_aws_resources.sh](deploy_aws_resources.sh).

Run from [P05](P05):

```bash
chmod +x deploy_aws_resources.sh

AWS_REGION=us-east-1 \
AWS_ACCOUNT_ID=123456789012 \
OPENAI_API_KEY=sk-... \
DB_USERNAME=paperadmin \
DB_PASSWORD='StrongPassword123!' \
./deploy_aws_resources.sh
```

Optional variables:

```bash
PROJECT_NAME=paper-supply
DB_USERNAME=paperadmin
DB_INSTANCE_CLASS=db.t3.micro
DB_ALLOCATED_STORAGE=20
DB_ENGINE_VERSION=15.4
ECS_CPU=512
ECS_MEMORY=1024
IMAGE_TAG=latest
SKIP_IMAGE_PUSH=false
USE_EXISTING_IMAGE_URI=123456789012.dkr.ecr.us-east-1.amazonaws.com/paper-supply-api:latest
```

If `DB_ENGINE_VERSION` is omitted, the script lets AWS choose the default Postgres version available in your region.

The script creates ECR, Secrets Manager secrets, RDS, ECS/Fargate service, and an ALB endpoint.

## Reverse (Delete Resources)

Use the teardown script in [destroy_aws_resources.sh](destroy_aws_resources.sh) to delete resources in reverse order.

```bash
chmod +x destroy_aws_resources.sh

FORCE=true \
AWS_REGION=us-east-1 \
AWS_ACCOUNT_ID=123456789012 \
./destroy_aws_resources.sh
```

Useful options:

```bash
PROJECT_NAME=paper-supply
DELETE_RDS=true
SKIP_FINAL_SNAPSHOT=true
DELETE_SECRETS=true
DELETE_ECR=true
DELETE_LOG_GROUP=true
```

If you want to keep a final DB snapshot:

```bash
FORCE=true \
SKIP_FINAL_SNAPSHOT=false \
FINAL_SNAPSHOT_ID=paper-supply-final-$(date +%Y%m%d%H%M%S) \
./destroy_aws_resources.sh
```

## Architecture Overview

```
Internet
    ↓
Application Load Balancer (ELB)
    ↓
ECS Fargate Cluster (Paper Supply API)
    ↓
RDS PostgreSQL Database
    ↓
AWS Secrets Manager (OpenAI API Key)
```

## Step 1: Set Up Database (RDS PostgreSQL)

### Using AWS Console

1. **Navigate to RDS Dashboard**
   - Go to AWS Console → RDS → Databases → Create Database

2. **Database Configuration**
   - Engine: PostgreSQL 15
   - DB Instance Class: db.t3.micro (for dev), db.t3.small (for prod)
   - Allocated Storage: 20 GB
   - DB Instance Identifier: `paper-supplies-db`
   - Master Username: `admin`
   - Master Password: Generate strong password

3. **Connectivity Settings**
   - VPC: Default or your custom VPC
   - Subnet Group: Create new if needed
   - Public Accessibility: No (keep private)
   - VPC Security Group: Create new, configure inbound rules

4. **Database Settings**
   - Initial Database Name: `paper_supplies`
   - Deletion Protection: Enabled (for production)

5. **Backup & Monitoring**
   - Enable automated backups (7 days retention)
   - Enable enhanced monitoring

### Using AWS CLI

```bash
aws rds create-db-instance \
  --db-instance-identifier paper-supplies-db \
  --db-instance-class db.t3.micro \
  --engine postgres \
  --engine-version 15.3 \
  --master-username admin \
  --master-user-password "YourSecurePassword123!" \
  --allocated-storage 20 \
  --vpc-security-group-ids sg-xxxxxxxxx \
  --db-subnet-group-name default \
  --db-name paper_supplies \
  --backup-retention-period 7 \
  --enable-cloudwatch-logs-exports postgresql
```

### Get RDS Endpoint

```bash
aws rds describe-db-instances \
  --db-instance-identifier paper-supplies-db \
  --query 'DBInstances[0].Endpoint'
```

## Step 2: Store Secrets in AWS Secrets Manager

### Create OpenAI API Key Secret

```bash
aws secretsmanager create-secret \
  --name paper-supply/openai-key \
  --description "OpenAI API key for Paper Supply Agent" \
  --secret-string '{"api_key":"sk-your-actual-api-key"}'
```

### Create Database Credentials Secret

```bash
aws secretsmanager create-secret \
  --name paper-supply/db-credentials \
  --description "Database credentials" \
  --secret-string '{
    "username":"admin",
    "password":"YourSecurePassword123!",
    "host":"paper-supplies-db.XXXXXXXXXXXX.us-east-1.rds.amazonaws.com",
    "port":5432,
    "dbname":"paper_supplies"
  }'
```

## Step 3: Build and Push Docker Image to ECR

### Create ECR Repository

```bash
aws ecr create-repository \
  --repository-name paper-supply-api \
  --region us-east-1

# Output: repository URI
```

### Build and Push Image

```bash
# Login to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com

# Build image
docker build -t paper-supply-api:latest .

# Tag image for ECR
docker tag paper-supply-api:latest \
  YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/paper-supply-api:latest

# Push to ECR
docker push YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/paper-supply-api:latest

# Also push with version tag
docker tag paper-supply-api:latest \
  YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/paper-supply-api:v1.0
docker push YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/paper-supply-api:v1.0
```

## Step 4: Create ECS Cluster and Task Definition

### Create ECS Cluster

```bash
aws ecs create-cluster \
  --cluster-name paper-supply-cluster \
  --capacity-providers FARGATE FARGATE_SPOT \
  --region us-east-1
```

### Register Task Definition

Create `task-definition.json`:

```json
{
  "family": "paper-supply-api",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "containerDefinitions": [
    {
      "name": "paper-supply-api",
      "image": "YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/paper-supply-api:latest",
      "portMappings": [
        {
          "containerPort": 8000,
          "hostPort": 8000,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {
          "name": "PORT",
          "value": "8000"
        },
        {
          "name": "DB_TYPE",
          "value": "postgres"
        }
      ],
      "secrets": [
        {
          "name": "DATABASE_URL",
          "valueFrom": "arn:aws:secretsmanager:us-east-1:YOUR_ACCOUNT_ID:secret:paper-supply/db-url:password::"
        },
        {
          "name": "OPENAI_API_KEY",
          "valueFrom": "arn:aws:secretsmanager:us-east-1:YOUR_ACCOUNT_ID:secret:paper-supply/openai-key:api_key::"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "ecs/paper-supply-api",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      },
      "healthCheck": {
        "command": [
          "CMD-SHELL",
          "curl -f http://localhost:8000/health || exit 1"
        ],
        "interval": 30,
        "timeout": 10,
        "retries": 3,
        "startPeriod": 40
      }
    }
  ],
  "executionRoleArn": "arn:aws:iam::YOUR_ACCOUNT_ID:role/ecsTaskExecutionRole"
}
```

### Register the Task Definition

```bash
aws ecs register-task-definition \
  --cli-input-json file://task-definition.json \
  --region us-east-1
```

## Step 5: Create ECS Service

### With Load Balancer

```bash
aws ecs create-service \
  --cluster paper-supply-cluster \
  --service-name paper-supply-api-service \
  --task-definition paper-supply-api:1 \
  --desired-count 2 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxxxxx,subnet-yyyyyy],securityGroups=[sg-zzzzzz],assignPublicIp=ENABLED}" \
  --load-balancers targetGroupArn=arn:aws:elasticloadbalancing:us-east-1:YOUR_ACCOUNT_ID:targetgroup/paper-supply-api/xxxxxxxx,containerName=paper-supply-api,containerPort=8000 \
  --region us-east-1
```

### Without Load Balancer (Simple)

```bash
aws ecs create-service \
  --cluster paper-supply-cluster \
  --service-name paper-supply-api-service \
  --task-definition paper-supply-api:1 \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxxxxx],securityGroups=[sg-zzzzzz],assignPublicIp=ENABLED}" \
  --region us-east-1
```

## Step 6: Configure Auto-Scaling

```bash
# Register scalable target
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --resource-id service/paper-supply-cluster/paper-supply-api-service \
  --scalable-dimension ecs:service:DesiredCount \
  --min-capacity 1 \
  --max-capacity 4 \
  --region us-east-1

# Create scaling policy (CPU-based)
aws application-autoscaling put-scaling-policy \
  --policy-name cpu-scaling \
  --service-namespace ecs \
  --resource-id service/paper-supply-cluster/paper-supply-api-service \
  --scalable-dimension ecs:service:DesiredCount \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration \
    "TargetValue=70.0,PredefinedMetricSpecification={PredefinedMetricType=ECSServiceAverageCPUUtilization},ScaleOutCooldown=60,ScaleInCooldown=300" \
  --region us-east-1
```

## Step 7: Testing the Deployment

### Get Service Endpoint

```bash
aws ecs describe-services \
  --cluster paper-supply-cluster \
  --services paper-supply-api-service \
  --region us-east-1 \
  --query 'services[0].networkConfiguration.awsvpcConfiguration.subnets'
```

### Health Check

```bash
# If using public IP
curl http://YOUR_ECS_PUBLIC_IP:8000/health

# If using load balancer
curl http://YOUR_LB_DNS_NAME/health
```

### Test Order Processing

```bash
curl -X POST http://YOUR_ENDPOINT:8000/process-order \
  -H "Content-Type: application/json" \
  -d '{
    "customer_request": "I need 200 sheets of A4 glossy paper and 100 sheets of cardstock",
    "context": "office manager organizing ceremony",
    "request_date": "2025-04-01"
  }'
```

## Step 8: CI/CD Pipeline (Optional)

### GitHub Actions Example

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to AWS ECS

on:
  push:
    branches: [main, develop]

env:
  AWS_REGION: us-east-1
  ECR_REPOSITORY: paper-supply-api

jobs:
  deploy:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v2
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Login to Amazon ECR
        run: |
          aws ecr get-login-password --region $AWS_REGION | \
          docker login --username AWS --password-stdin ${{ secrets.AWS_ACCOUNT_ID }}.dkr.ecr.$AWS_REGION.amazonaws.com

      - name: Build and push Docker image
        env:
          ECR_REGISTRY: ${{ secrets.AWS_ACCOUNT_ID }}.dkr.ecr.${{ env.AWS_REGION }}.amazonaws.com
        run: |
          docker build -t $ECR_REGISTRY/$ECR_REPOSITORY:${{ github.sha }} .
          docker push $ECR_REGISTRY/$ECR_REPOSITORY:${{ github.sha }}

      - name: Update ECS service
        run: |
          aws ecs update-service \
            --cluster paper-supply-cluster \
            --service paper-supply-api-service \
            --force-new-deployment \
            --region $AWS_REGION
```

## Step 9: Database Initialization

### First-time Setup

```bash
# Connect to RDS database
psql -h paper-supplies-db.XXXXXXXXXXXX.us-east-1.rds.amazonaws.com \
     -U admin \
     -d paper_supplies

# Run migration (if using Alembic or similar)
# Or manually create tables based on your schema
```

### For Local Development

```bash
# The init_database() function will automatically run for local SQLite
python -c "from project_starter import init_database; init_database()"
```

## Monitoring and Logging

### CloudWatch Logs

```bash
# View logs
aws logs tail ecs/paper-supply-api --follow --region us-east-1

# Get log events
aws logs get-log-events \
  --log-group-name ecs/paper-supply-api \
  --log-stream-name ecs/paper-supply-api/YOUR_TASK_ID \
  --region us-east-1
```

### CloudWatch Metrics

Set up alarms:

```bash
aws cloudwatch put-metric-alarm \
  --alarm-name paper-supply-api-cpu-high \
  --alarm-description "Alert when CPU exceeds 80%" \
  --metric-name CPUUtilization \
  --namespace AWS/ECS \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold \
  --region us-east-1
```

## Cost Optimization

1. **Use Fargate Spot**: 70% cheaper but less reliable

   ```bash
   --launch-type FARGATE_SPOT
   ```

2. **Right-size instances**: Start with t3.micro/small

3. **Set up budget alerts**: AWS Budgets → Set monthly budget

## Troubleshooting

### Task fails to start

```bash
aws ecs describe-tasks \
  --cluster paper-supply-cluster \
  --tasks TASK_ARN \
  --region us-east-1 \
  --query 'tasks[0].{lastStatus:lastStatus,stoppedCode:stoppedCode,stoppedReason:stoppedReason}'
```

### Database connection issues

- Check RDS security group inbound rules
- Verify DATABASE_URL format
- Test connection locally

### High latency

- Check ECS task CPU/memory utilization
- Enable RDS Enhanced Monitoring
- Review CloudWatch metrics

## Rollback

```bash
# Revert to previous task definition
aws ecs update-service \
  --cluster paper-supply-cluster \
  --service paper-supply-api-service \
  --task-definition paper-supply-api:PREVIOUS_VERSION \
  --force-new-deployment
```

## Clean Up

```bash
# Delete service
aws ecs delete-service \
  --cluster paper-supply-cluster \
  --service paper-supply-api-service \
  --force

# Delete cluster
aws ecs delete-cluster --cluster paper-supply-cluster

# Delete ECR repository
aws ecr delete-repository \
  --repository-name paper-supply-api \
  --force

# Delete RDS instance
aws rds delete-db-instance \
  --db-instance-identifier paper-supplies-db \
  --skip-final-snapshot
```

## Next Steps

1. Set up automated backups for RDS
2. Implement CI/CD pipeline
3. Set up monitoring alerts
4. Create disaster recovery plan
5. Document API endpoints
6. Set up API rate limiting and authentication
