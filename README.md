# ScamShield for Parents (爸妈求证)

Bilingual (English/Chinese) app for checking suspicious messages, links, screenshots and health claims. A deterministic rules layer sets a minimum risk level; optional AI and retrieval can increase caution. It is a second opinion, not proof that content is safe.

[Live app](https://parentcheck.duckdns.org) · [Render instance](https://parent-check.onrender.com)

## Stack

Next.js frontend; Flask API and LangGraph agent; PostgreSQL/pgvector for retrieval; Redis for background work. The production deployment and configuration are documented in [`DEPLOY.md`](DEPLOY.md).

## Local development

See [`frontend/README.md`](frontend/README.md), [`DEPLOY.md`](DEPLOY.md) and `.env.example` for prerequisites and environment variables. Do not commit secrets or real user messages.

Run backend checks:

```bash
python -m pytest -q
```

The AI service needs provider credentials and supporting services. Without them, use the deterministic checks where available. See [`SECURITY.md`](SECURITY.md) for security status and known gaps.

## Current evaluation and deployment status

The curated 61-case rule evaluation covers scam, health and benign examples; it is not a measure of real-world accuracy. The latest security status, CI evidence and remaining EC2 security checks are maintained in [`SECURITY.md`](SECURITY.md). Production deployment is live: the EC2 instance uses the `parent-check-ec2` IAM role to retrieve production credentials from AWS Secrets Manager; successful `GetSecretValue` calls were verified in CloudTrail. At verification, Caddy, web, database and Redis containers were running, with web/database/Redis health checks passing.
