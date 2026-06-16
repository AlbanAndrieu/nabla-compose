
variable "nexus_url" {
  type = string
}

variable "nexus_username" {
  type = string
}

variable "nexus_password" {
  type      = string
  sensitive = true
}

variable "op_vault_name" {
  type    = string
  default = "Automation"
}
