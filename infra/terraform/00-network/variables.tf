variable "region" {
  type    = string
  default = "eu-south-2"
}

variable "azs" {
  description = "Dos AZs — Aurora Multi-AZ y las subredes van repartidas entre ellas."
  type        = list(string)
  default     = ["eu-south-2a", "eu-south-2b"]
}
