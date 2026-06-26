variable "garage_url" {
  type = string
}

variable "garage_token" {
  type      = string
  sensitive = true
}

variable "op_vault_name" {
  type    = string
  default = "Automation"
}
