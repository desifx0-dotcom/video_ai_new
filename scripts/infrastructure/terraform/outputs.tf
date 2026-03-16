output "application_url" {
  description = "URL of the deployed application"
  value       = "https://${var.domain_name}"
}

output "api_url" {
  description = "URL of the API"
  value       = "https://api.${var.domain_name}"
}

output "load_balancer_dns" {
  description = "DNS name of the load balancer"
  value       = aws_lb.main.dns_name
}

output "cloudfront_distribution_url" {
  description = "URL of the CloudFront distribution"
  value       = aws_cloudfront_distribution.cdn.domain_name
}

output "cloudfront_distribution_id" {
  description = "ID of the CloudFront distribution"
  value       = aws_cloudfront_distribution.cdn.id
}

output "database_endpoint" {
  description = "Endpoint of the RDS database"
  value       = aws_db_instance.main.endpoint
}

output "database_name" {
  description = "Name of the RDS database"
  value       = aws_db_instance.main.db_name
}

output "redis_endpoint" {
  description = "Endpoint of the Redis cluster"
  value       = aws_elasticache_cluster.redis.cache_nodes[0].address
}

output "s3_bucket_name" {
  description = "Name of the S3 bucket for uploads"
  value       = aws_s3_bucket.uploads.bucket
}

output "s3_bucket_arn" {
  description = "ARN of the S3 bucket for uploads"
  value       = aws_s3_bucket.uploads.arn
}

output "ecs_cluster_name" {
  description = "Name of the ECS cluster"
  value       = aws_ecs_cluster.main.name
}

output "ecs_cluster_arn" {
  description = "ARN of the ECS cluster"
  value       = aws_ecs_cluster.main.arn
}

output "ecs_service_web_arn" {
  description = "ARN of the web ECS service"
  value       = aws_ecs_service.web.id
}

output "ecs_service_celery_arn" {
  description = "ARN of the celery ECS service"
  value       = aws_ecs_service.celery.id
}

output "vpc_id" {
  description = "ID of the VPC"
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "IDs of the public subnets"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "IDs of the private subnets"
  value       = aws_subnet.private[*].id
}

output "security_group_alb_id" {
  description = "ID of the ALB security group"
  value       = aws_security_group.alb.id
}

output "security_group_ecs_id" {
  description = "ID of the ECS security group"
  value       = aws_security_group.ecs.id
}

output "security_group_database_id" {
  description = "ID of the database security group"
  value       = aws_security_group.database.id
}

output "security_group_redis_id" {
  description = "ID of the Redis security group"
  value       = aws_security_group.redis.id
}

output "acm_certificate_arn" {
  description = "ARN of the ACM certificate"
  value       = aws_acm_certificate.main.arn
}

output "route53_zone_id" {
  description = "ID of the Route53 zone"
  value       = var.route53_zone_id
}

output "cloudwatch_log_group_name" {
  description = "Name of the CloudWatch log group"
  value       = aws_cloudwatch_log_group.ecs.name
}

output "secrets_manager_secret_arns" {
  description = "ARNs of the secrets in Secrets Manager"
  value = {
    secret_key   = aws_secretsmanager_secret.secret_key.arn
    database_url = aws_secretsmanager_secret.database_url.arn
  }
}

output "iam_role_ecs_execution_arn" {
  description = "ARN of the ECS execution role"
  value       = aws_iam_role.ecs_execution_role.arn
}

output "iam_role_ecs_task_arn" {
  description = "ARN of the ECS task role"
  value       = aws_iam_role.ecs_task_role.arn
}

output "terraform_state_bucket" {
  description = "Name of the S3 bucket for Terraform state"
  value       = "video-ai-studio-terraform-state"
}

output "deployment_instructions" {
  description = "Instructions for deploying the application"
  value = <<EOF
  Video AI Studio has been deployed successfully!

  Application URL: https://${var.domain_name}
  API URL: https://api.${var.domain_name}

  Next steps:
  1. Update DNS records to point to the CloudFront distribution
  2. Configure environment variables in ECS task definitions
  3. Run database migrations: flask db upgrade
  4. Seed initial data if needed
  5. Monitor application logs in CloudWatch

  Infrastructure details:
  - Database: ${aws_db_instance.main.endpoint}
  - Redis: ${aws_elasticache_cluster.redis.cache_nodes[0].address}
  - Storage: ${aws_s3_bucket.uploads.bucket}
  - CDN: ${aws_cloudfront_distribution.cdn.domain_name}
  EOF
}