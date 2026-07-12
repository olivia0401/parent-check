# Use the account's default VPC and subnets to keep this example self-contained.
# In a hardened setup you'd create a VPC with private subnets for RDS/Redis and
# put only the ALB in public subnets.
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}
