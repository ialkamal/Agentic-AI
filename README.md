# Agentic-AI

GitHub Actions status:

[![P05 Deploy](https://github.com/ialkamal/Agentic-AI/actions/workflows/p05-deploy.yml/badge.svg)](https://github.com/ialkamal/Agentic-AI/actions/workflows/p05-deploy.yml)
[![P05 Destroy](https://github.com/ialkamal/Agentic-AI/actions/workflows/p05-destroy.yml/badge.svg)](https://github.com/ialkamal/Agentic-AI/actions/workflows/p05-destroy.yml)

## CI/CD Workflows

- Deploy workflow: automatically runs on push to `master` when files under `P05/` change. It can also be triggered manually.
- Destroy workflow: manual only and requires typing `DESTROY` as confirmation before teardown.

## Required GitHub Secrets

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_REGION`
- `AWS_ACCOUNT_ID`
- `OPENAI_API_KEY` (deploy)
- `DB_PASSWORD` (deploy)

Optional:

- `DB_USERNAME`
- `PROJECT_NAME`
