# Container image for 爸妈求证 (Parent Check) — a Flask app served by gunicorn.
# Used for deployment to Amazon ECS Express Mode (Fargate).
FROM python:3.11-slim

WORKDIR /app

# Install dependencies first so this layer is cached across code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code.
COPY . .

# gunicorn binds to this port; the ECS Express "Container port" must match it.
ENV PORT=8000
EXPOSE 8000

# One worker keeps the app's in-memory rate limiter consistent; the generous
# timeout covers requests that fetch an external URL before responding.
CMD ["sh", "-c", "gunicorn app:app --bind 0.0.0.0:${PORT} --workers 1 --timeout 120"]
