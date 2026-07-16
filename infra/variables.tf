variable "project" {
  type    = string
  default = "parent-check"
}

variable "aws_region" {
  type    = string
  default = "eu-west-1" # matches .github/workflows/deploy.yml
}

variable "container_port" {
  type    = number
  default = 8000 # gunicorn binds here (see Dockerfile)
}

variable "desired_count" {
  type    = number
  default = 1
}

variable "db_name" {
  type    = string
  default = "parentcheck"
}

variable "db_username" {
  type    = string
  default = "parentcheck"
}

variable "gemini_api_key" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Optional. Enables the AI/RAG path. Stored in Secrets Manager, never in state output."
}

variable "github_repo" {
  type        = string
  default     = "olivia0401/parent-check"
  description = "owner/repo allowed to assume the OIDC deploy role."
}

variable "enable_cicd" {
  type        = bool
  default     = false
  description = "Create the GitHub OIDC provider + deploy role for CI/CD. Off by default so a first manual apply never depends on an OIDC provider already existing in the account. Flip to true once you want GitHub Actions to deploy on push."
}
