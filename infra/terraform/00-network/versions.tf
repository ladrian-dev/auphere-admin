terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.70, < 7.0"
    }
  }

  backend "s3" {
    key = "nexus/00-network.tfstate"
    # bucket / dynamodb_table / region / encrypt vienen de ../backend.hcl:
    #   terraform init -backend-config=../backend.hcl
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = "nexus"
      ManagedBy   = "terraform"
      Stack       = "00-network"
      Environment = terraform.workspace
    }
  }
}

# Los workspaces son el mecanismo de entorno: aplicar en ``default`` sería
# crear un tercer entorno fantasma con tamaños de staging.
check "workspace_is_named" {
  assert {
    condition     = contains(["staging", "prod"], terraform.workspace)
    error_message = "Selecciona un workspace válido: terraform workspace select staging|prod."
  }
}
