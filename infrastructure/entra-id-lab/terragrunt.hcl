include "root" {
  path = find_in_parent_folders("root.hcl")
}
terraform {
  source = find_in_parent_folders("terraform/entra-id-lab")
}
locals {
  reader_upn = get_env("ENTRA_LAB_READER_UPN", "")
  operator_upn = get_env("ENTRA_LAB_OPERATOR_UPN", "")
}
inputs = {
  tenant_id = get_env("ENTRA_LAB_TENANT_ID", "")
  lab_tenant_confirmed = get_env("ENTRA_LAB_CONFIRMED", "false") == "true"
  test_users = merge(
    local.reader_upn == "" ? {} : { reader = { upn = local.reader_upn, group = "readers" } },
    local.operator_upn == "" ? {} : { operator = { upn = local.operator_upn, group = "operators" } }
  )
}
