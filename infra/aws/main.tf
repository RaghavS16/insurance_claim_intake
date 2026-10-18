# Remote State Configuration:
# Initialize remote state using:
#   terraform init -backend-config="bucket=YOUR_TF_STATE_BUCKET" -backend-config="key=insurance-claim-intake/terraform.tfstate" -backend-config="region=YOUR_AWS_REGION"
terraform {
  required_version = ">= 1.8.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {}
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

locals {
  name = var.project_name
  tags = merge({
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }, var.tags)
}
