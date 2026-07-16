output "app_url" {
  description = "Public URL of the load-balanced app."
  value       = "http://${aws_lb.app.dns_name}"
}

output "ecr_repository_url" {
  description = "Push target for the CI/CD pipeline (deploy.yml)."
  value       = aws_ecr_repository.app.repository_url
}

output "rds_endpoint" {
  value = aws_db_instance.postgres.address
}

output "redis_endpoint" {
  value = aws_elasticache_cluster.redis.cache_nodes[0].address
}

output "github_deploy_role_arn" {
  description = "Set this as ROLE_ARN in .github/workflows/deploy.yml. Null unless enable_cicd=true."
  value       = var.enable_cicd ? aws_iam_role.github_deploy[0].arn : null
}
