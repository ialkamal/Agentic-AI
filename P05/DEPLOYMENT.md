# Paper Supply Agent API - Deployment Guide

Complete deployment solution for the Paper Supply multi-agent system with FastAPI, Docker, and AWS.

## Quick Start

### Local Development (SQLite)

1. **Install dependencies:**

   ```bash
   pip install -r requirements-prod.txt
   ```

2. **Set up environment:**

   ```bash
   cp .env.example .env.local
   # Edit .env.local with your OpenAI API key
   ```

3. **Run API:**

   ```bash
   python project_starter.py  # Initialize database
   uvicorn api:app --reload --port 8000
   ```

4. **Test endpoint:**
   ```bash
   curl http://localhost:8000/health
   ```

### Local Development (With PostgreSQL in Docker)

1. **Start services:**

   ```bash
   docker-compose up -d
   ```

2. **Check health:**
   ```bash
   curl http://localhost:8000/health
   ```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Client / Web UI                         │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ↓
         ┌──────────────────────────┐
         │  Application Load        │
         │  Balancer (ALB)          │
         └──────────────┬───────────┘
                        │
            ┌───────────┴───────────┐
            ↓                       ↓
    ┌───────────────┐      ┌───────────────┐
    │  ECS Fargate  │      │  ECS Fargate  │
    │  Container 1  │      │  Container 2  │
    │  :8000        │      │  :8000        │
    └───────┬───────┘      └───────┬───────┘
            │                      │
            └──────┬───────────────┘
                   ↓
            ┌─────────────────────┐
            │  AWS RDS            │
            │  PostgreSQL      │
            │  paper_supplies     │
            └─────────────────────┘
```

## Files Structure

```
.
├── api.py                      # FastAPI application
├── project_starter.py          # Agent implementation
├── db_config.py               # Database configuration
├── migrate_db.py              # SQLite → PostgreSQL migration
├── requirements-prod.txt      # Production dependencies
├── Dockerfile                 # Container image definition
├── docker-compose.yml         # Local dev with PostgreSQL
├── .env.example              # Environment configuration template
├── AWS_DEPLOYMENT.md         # Complete AWS deployment guide
└── README.md                 # This file
```

## Environment Configuration

### Local Development (SQLite)

```bash
DB_TYPE=sqlite
SQLITE_PATH=munder_difflin.db
OPENAI_API_KEY=sk-...
```

### Local Development (PostgreSQL via Docker)

```bash
DB_TYPE=postgres
DB_HOST=localhost
DB_PORT=5432
DB_USER=admin
DB_PASSWORD=localpassword123
DB_NAME=paper_supplies
OPENAI_API_KEY=sk-...
```

### AWS Production (RDS)

```bash
DATABASE_URL=postgresql://user:password@rds-endpoint.us-east-1.rds.amazonaws.com:5432/paper_supplies
OPENAI_API_KEY=sk-...
PORT=8000
```

## API Endpoints

### Health Check

```bash
GET /health
# Response: {"status": "healthy", "timestamp": "2024-01-01T00:00:00", "version": "1.0.0"}
```

### Readiness Check

```bash
GET /ready
# Response: {"status": "ready"}
```

### Process Order

```bash
POST /process-order
Content-Type: application/json

{
  "customer_request": "I need 200 sheets of A4 glossy paper and 100 sheets of cardstock",
  "context": "office manager organizing ceremony",
  "request_date": "2025-04-01"
}

# Response includes: parsed items, inventory assessment, quote, order_id
```

### Generate Quote

```bash
POST /quote
Content-Type: application/json

{
  "customer_request": "I need 200 sheets of A4 glossy paper",
  "context": "office manager",
  "request_date": "2025-04-01"
}

# Response includes: parsed items and quote only (no order created)
```

## Deployment Options

### Option 1: ECS Fargate (Recommended for AWS)

**Pros:**

- Serverless containers
- Auto-scaling built-in
- Pay per second
- No infrastructure management

**Steps:**

1. See `AWS_DEPLOYMENT.md` for detailed instructions
2. Approximately 20-30 minutes setup

### Option 2: ECS EC2

**Pros:**

- More control
- Can run long-running tasks
- Good for high-traffic apps

**Setup:**

```bash
--launch-type EC2
# Configure in ECS service creation
```

### Option 3: App Runner

**Pros:**

- Simplest to use
- Automatic builds from GitHub
- Good for small/medium apps

**Setup:**

```bash
aws apprunner create-service \
  --source-configuration ImageRepository={ImageIdentifier=YOUR_ECR_IMAGE,ImageRepositoryType=ECR}
  ...
```

## Database Migration

### From SQLite to PostgreSQL

1. **Dry run to preview:**

   ```bash
   python migrate_db.py --dry-run
   ```

2. **Perform migration:**

   ```bash
   python migrate_db.py \
     --source-path munder_difflin.db \
     --target-url postgresql://user:pass@host:5432/paper_supplies
   ```

3. **Verify:**
   ```bash
   python migrate_db.py \
     --source-path munder_difflin.db \
     --target-url postgresql://user:pass@host:5432/paper_supplies \
     --verify-only
   ```

## Docker Operations

### Build Image

```bash
docker build -t paper-supply-api:latest .
```

### Run Locally

```bash
docker run -p 8000:8000 \
  -e OPENAI_API_KEY=sk-... \
  -e DB_TYPE=sqlite \
  paper-supply-api:latest
```

### Run with PostgreSQL (docker-compose)

```bash
OPENAI_API_KEY=sk-... docker-compose up
```

### Push to ECR

```bash
# Get login token
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com

# Tag and push
docker tag paper-supply-api:latest \
  YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/paper-supply-api:latest

docker push \
  YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/paper-supply-api:latest
```

## Monitoring & Logging

### Local

```bash
tail -f /var/log/paper-supply-api.log
```

### AWS CloudWatch

```bash
# View logs
aws logs tail ecs/paper-supply-api --follow

# Get specific log events
aws logs get-log-events \
  --log-group-name ecs/paper-supply-api \
  --log-stream-name ecs/paper-supply-api/TASK_ID
```

### CloudWatch Metrics

- CPU Utilization
- Memory Utilization
- Task Count
- Request Count
- Request Duration

## Performance Tuning

### Container Resources

| Environment | CPU  | Memory | Cost       |
| ----------- | ---- | ------ | ---------- |
| Development | 256  | 512MB  | $0.01/hour |
| Staging     | 512  | 1GB    | $0.02/hour |
| Production  | 1024 | 2GB    | $0.04/hour |

### Database

- RDS Multi-AZ for high availability
- Read replicas for scaling read operations
- Automated backups (7-30 days)
- Point-in-time restore

## Troubleshooting

### API won't start

```bash
# Check logs
docker logs container_id

# Verify environment variables
env | grep -E "DB_|OPENAI|PORT"

# Test API directly
python -c "from api import app; print(app)"
```

### Database connection issues

```bash
# Test PostgreSQL connection
psql -h host -U user -d paper_supplies

# Test SQLite
sqlite3 munder_difflin.db ".tables"
```

### High latency

```bash
# Check container performance
aws ecs describe-tasks --cluster paper-supply-cluster --tasks TASK_ARN

# Check RDS metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name CPUUtilization \
  --dimensions Name=DBInstanceIdentifier,Value=paper-supplies-db \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-02T00:00:00Z \
  --period 300 \
  --statistics Average
```

## Cost Estimation (AWS)

| Service                        | Monthly Cost |
| ------------------------------ | ------------ |
| ECS Fargate (1 task, t3.micro) | $10-15       |
| RDS PostgreSQL (db.t3.micro)   | $25-40       |
| Data Transfer                  | $0-5         |
| CloudWatch Logs                | $0.50        |
| **Total**                      | **$35-60**   |

### Cost Reduction Tips

- Use Fargate Spot: -70% compute cost
- Use Reserved Instances: -30-40% RDS cost
- Implement caching: Reduce database queries
- Auto-scaling: Scale down during off-hours

## Security Best Practices

✓ Secrets in AWS Secrets Manager
✓ Non-root container user
✓ Private RDS database (no public access)
✓ VPC with security groups
✓ HTTPS/TLS load balancer
✓ CloudTrail logging
✓ Container image scanning

## Next Steps

1. **Set up CI/CD**: GitHub Actions → ECR → ECS
2. **Add authentication**: API key, OAuth2, or JWT
3. **Implement caching**: Redis for frequently accessed data
4. **Add observability**: DataDog, New Relic, or Prometheus
5. **Implement backups**: Automated RDS snapshots
6. **Set up alerts**: CPU, memory, error rates

## Support

For detailed AWS deployment steps, see: `AWS_DEPLOYMENT.md`

For API documentation, see: `api.py` docstrings

## License

MIT
