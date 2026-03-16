variable "environment" {
  description = "Environment name (production, staging, development)"
  type        = string
  default     = "production"
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "aws_availability_zones" {
  description = "AWS availability zones"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b", "us-east-1c"]
}

variable "gcp_project_id" {
  description = "Google Cloud Platform project ID"
  type        = string
  default     = ""
}

variable "gcp_region" {
  description = "Google Cloud Platform region"
  type        = string
  default     = "us-central1"
}

variable "cloudflare_api_token" {
  description = "Cloudflare API token"
  type        = string
  sensitive   = true
}

variable "domain_name" {
  description = "Domain name for the application"
  type        = string
  default     = "videoaistudio.com"
}

variable "route53_zone_id" {
  description = "Route53 zone ID"
  type        = string
}

variable "docker_registry" {
  description = "Docker registry URL"
  type        = string
  default     = "ghcr.io/yourusername"
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.medium"
}

variable "db_username" {
  description = "Database username"
  type        = string
  default     = "videoai"
  sensitive   = true
}

variable "db_password" {
  description = "Database password"
  type        = string
  sensitive   = true
}

variable "redis_node_type" {
  description = "ElastiCache Redis node type"
  type        = string
  default     = "cache.t3.micro"
}

variable "secret_key" {
  description = "Application secret key"
  type        = string
  sensitive   = true
}

variable "openai_api_key" {
  description = "OpenAI API key"
  type        = string
  sensitive   = true
}

variable "google_api_key" {
  description = "Google API key"
  type        = string
  sensitive   = true
}

variable "stability_api_key" {
  description = "Stability AI API key"
  type        = string
  sensitive   = true
}

variable "stripe_secret_key" {
  description = "Stripe secret key"
  type        = string
  sensitive   = true
}

variable "sendgrid_api_key" {
  description = "SendGrid API key"
  type        = string
  sensitive   = true
}

variable "firebase_credentials" {
  description = "Firebase service account credentials"
  type        = string
  sensitive   = true
}

variable "slack_webhook_url" {
  description = "Slack webhook URL for notifications"
  type        = string
  sensitive   = true
}

variable "min_replicas" {
  description = "Minimum number of ECS task replicas"
  type        = number
  default     = 2
}

variable "max_replicas" {
  description = "Maximum number of ECS task replicas"
  type        = number
  default     = 10
}

variable "cpu_threshold" {
  description = "CPU threshold for auto-scaling"
  type        = number
  default     = 70
}

variable "memory_threshold" {
  description = "Memory threshold for auto-scaling"
  type        = number
  default     = 80
}

variable "alb_certificate_arn" {
  description = "ARN of the ALB SSL certificate"
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets"
  type        = list(string)
  default     = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default = {
    Project     = "Video AI Studio"
    Environment = "production"
    ManagedBy   = "terraform"
  }
}