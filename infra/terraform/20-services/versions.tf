terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.70, < 7.0"
    }
  }

  backend "s3" {
    key = "nexus/20-services.tfstate"
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = "nexus"
      ManagedBy   = "terraform"
      Stack       = "20-services"
      Environment = terraform.workspace
    }
  }
}

check "workspace_is_named" {
  assert {
    condition     = contains(["staging", "prod"], terraform.workspace)
    error_message = "Selecciona un workspace válido: terraform workspace select staging|prod."
  }
}

variable "region" {
  type    = string
  default = "eu-south-2"
}

variable "state_bucket" {
  description = "Bucket del estado remoto — para terraform_remote_state."
  type        = string
}

data "terraform_remote_state" "network" {
  backend   = "s3"
  workspace = terraform.workspace

  config = {
    bucket = var.state_bucket
    key    = "nexus/00-network.tfstate"
    region = var.region
  }
}

data "terraform_remote_state" "data" {
  backend   = "s3"
  workspace = terraform.workspace

  config = {
    bucket = var.state_bucket
    key    = "nexus/10-data.tfstate"
    region = var.region
  }
}

data "aws_caller_identity" "current" {}

locals {
  name = "nexus-${terraform.workspace}"
  # Fallback solo para que ``validate`` (workspace default) evalúe; la
  # precondition del cluster ECS impide aplicar fuera de staging/prod.
  env        = contains(["staging", "prod"], terraform.workspace) ? terraform.workspace : "staging"
  account_id = data.aws_caller_identity.current.account_id
  network    = data.terraform_remote_state.network.outputs
  data       = data.terraform_remote_state.data.outputs
  ecr_base   = "${local.account_id}.dkr.ecr.${var.region}.amazonaws.com"
}
