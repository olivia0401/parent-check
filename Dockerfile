# Container image for ScamShield for Parents — a Flask app served by gunicorn.
# Used by docker-compose.yml / docker-compose.prod.yml (EC2) and the optional
# Terraform ECS stack in infra/. Python version matches CI.
FROM python:3.12-slim

WORKDIR /app

# Install dependencies first so this layer is cached across code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code.
COPY . .

# gunicorn binds to this port (Caddy / the ALB target group point at it).
ENV PORT=8000
EXPOSE 8000

# The rate limiter is shared through Redis (in-process fallback without it);
# the generous timeout covers requests that fetch an external URL first.
CMD ["sh", "-c", "gunicorn app:app --bind 0.0.0.0:${PORT} --workers 1 --timeout 120"]
