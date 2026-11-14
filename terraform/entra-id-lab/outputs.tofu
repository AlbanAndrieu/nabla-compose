output "tenant_id" {
  value = data.azuread_client_config.current.tenant_id
}
output "workload_client_ids" {
  value = { for k, v in azuread_application_registration.workload : k => v.client_id }
}
output "service_principal_object_ids" {
  value = { for k, v in azuread_service_principal.workload : k => v.object_id }
}
output "lab_group_ids" {
  value = { for k, v in azuread_group.lab : k => v.object_id }
}
