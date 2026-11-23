# Independent Azure subscription security pricing root.
# Foundational CSPM opt-in is a DIFFERENT service setting, and cannot be
# inferred or enabled by setting CloudPosture to Free.
# No paid Defender plan can ever be selected in this module.
terraform {
  backend "remote" {}
}

variable "tenant_id" {
  description = "Personal Entra Nabla tenant. No workplace tenant is permitted."
  type        = string
  default     = "441414ec-960f-4d6a-a00c-d0d14955a7f1"
  validation {
    condition     = var.tenant_id == "441414ec-960f-4d6a-a00c-d0d14955a7f1"
    error_message = "Refusing a non-Nabla Entra tenant."
  }
}

variable "subscription_id" {
  description = "Personal Azure Free subscription, not a professional subscription."
  type        = string
  default     = "6391d770-8956-47ab-8696-18ad1d52ecc5"
  validation {
    condition     = var.subscription_id == "6391d770-8956-47ab-8696-18ad1d52ecc5"
    error_message = "Refusing an Azure subscription outside the personal Nabla pilot."
  }
}

variable "manage_free_cloud_posture_tier" {
  description = "Opt-in only AFTER importing existing CloudPosture pricing into this dedicated state. NEVER implies Foundational CSPM enrollment."
  type        = bool
  default     = false
}

resource "azurerm_security_center_subscription_pricing" "cloud_posture_free" {
  count         = var.manage_free_cloud_posture_tier ? 1 : 0
  tier          = "Free"
  resource_type = "CloudPosture"

  lifecycle {
    prevent_destroy = true
    precondition {
      condition = (
        var.tenant_id == "441414ec-960f-4d6a-a00c-d0d14955a7f1" &&
        var.subscription_id == "6391d770-8956-47ab-8696-18ad1d52ecc5"
      )
      error_message = "Refusing Defender pricing changes outside the Nabla personal subscription."
    }
  }
}

output "free_cloud_posture_tier_managed" {
  description = "Does NOT verify Foundational CSPM enrollment; only whether the Free pricing resource is managed."
  value       = var.manage_free_cloud_posture_tier
}
