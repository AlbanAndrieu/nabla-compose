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

output "talos_zvol_paths" {
  description = "TrueNAS device paths backing each Talos VM."
  value = {
    for name in keys(truenas_zvol.talos_disk) :
    name => "/dev/zvol/${var.truenas_pool}/${var.talos_zvol_parent}/${name}-disk0"
  }
}

output "talos_bootstrap_inventory" {
  description = "Non-sensitive Talos VM inventory for the later machine-configuration/bootstrap stage."
  value = {
    for name, vm in truenas_vm.talos : name => {
      id     = vm.id
      role   = startswith(lower(name), "taloscp") ? "controlplane" : "worker"
      bridge = var.vm_bridge
      disk   = "/dev/zvol/${var.truenas_pool}/${var.talos_zvol_parent}/${name}-disk0"
    }
  }
}
