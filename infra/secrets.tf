# --- Secrets Manager: app config injected into the ECS task ------------------
# The app reads SECRET_KEY / DATABASE_URL / REDIS_URL / GEMINI_API_KEY from the
# environment. We build them here from the RDS/Redis outputs and hand them to
# the task as `secrets` (valueFrom), so no plaintext credentials live in the
# task definition or in CI.

resource "random_password" "flask_secret" {
  length  = 48
  special = false
}

locals {
  database_url = format(
    "postgresql+psycopg2://%s:%s@%s:5432/%s",
    var.db_username,
    random_password.db.result,
    aws_db_instance.postgres.address,
    var.db_name,
  )
  redis_url = format("redis://%s:6379/0", aws_elasticache_cluster.redis.cache_nodes[0].address)

  app_secrets = {
    SECRET_KEY     = random_password.flask_secret.result
    DATABASE_URL   = local.database_url
    REDIS_URL      = local.redis_url
    GEMINI_API_KEY = var.gemini_api_key
  }
}

resource "aws_secretsmanager_secret" "app" {
  name                    = "${var.project}/app"
  recovery_window_in_days = 0 # demo convenience
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id     = aws_secretsmanager_secret.app.id
  secret_string = jsonencode(local.app_secrets)
}
