output "talos_vm_ids" {
  description = "TrueNAS VM IDs created for the Talos test cluster."
  value       = { for name, vm in truenas_vm.talos : name => vm.id }
}

output "talos_vm_status" {
  description = "Current TrueNAS VM status values."
  value       = { for name, vm in truenas_vm.talos : name => vm.status }
}

output "talos_zvol_ids" {
  description = "Zvol identifiers backing the Talos test VMs."
  value       = { for name, disk in truenas_zvol.talos_disk : name => disk.id }
}
