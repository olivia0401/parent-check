# --- RDS PostgreSQL (pgvector) + ElastiCache Redis --------------------------

resource "random_password" "db" {
  length  = 24
  special = false # keep it URL-safe for DATABASE_URL
}

resource "aws_db_subnet_group" "this" {
  name       = "${var.project}-db"
  subnet_ids = data.aws_subnets.default.ids
}

resource "aws_db_instance" "postgres" {
  identifier     = "${var.project}-pg"
  engine         = "postgres"
  engine_version = "16" # major-only: RDS picks a current 16.x minor (pinning 16.4 risks a deprecated-minor error). pgvector available; app runs CREATE EXTENSION vector
  instance_class = "db.t4g.micro"

  allocated_storage = 20
  storage_encrypted = true

  db_name  = var.db_name
  username = var.db_username
  password = random_password.db.result

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.data.id]
  publicly_accessible    = false

  skip_final_snapshot = true # demo convenience; set false in production
  apply_immediately   = true
}

resource "aws_elasticache_subnet_group" "this" {
  name       = "${var.project}-redis"
  subnet_ids = data.aws_subnets.default.ids
}

resource "aws_elasticache_cluster" "redis" {
  cluster_id           = "${var.project}-redis"
  engine               = "redis"
  node_type            = "cache.t4g.micro"
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
  port                 = 6379

  subnet_group_name  = aws_elasticache_subnet_group.this.name
  security_group_ids = [aws_security_group.data.id]
}
