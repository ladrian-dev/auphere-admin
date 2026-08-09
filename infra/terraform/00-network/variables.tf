variable "region" {
  type    = string
  default = "eu-west-1"
}

variable "azs" {
  description = "Dos AZs — Aurora Multi-AZ y las subredes van repartidas entre ellas."
  type        = list(string)
  default     = ["eu-west-1a", "eu-west-1b"]
}
