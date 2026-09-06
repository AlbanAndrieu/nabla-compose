output "talos_vm_ids" {
  description = "TrueNAS VM IDs created for the Talos test cluster."
  value       = { for name, vm in truenas_vm.talos : name => vm.id }
}

output "talos_vm_status" {
  description = "Current TrueNAS VM status values."
  value       = { for name, vm in truenas_vm.talos : name => vm.status }
}

output "talos_vm_macs" {
  description = "Deterministic Talos VM MAC addresses for DHCP reservations."
  value       = { for name in keys(truenas_vm.talos) : name => var.talos_vms[name].mac }
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
      role   = lower(trimspace(var.talos_vms[name].role))
      bridge = var.vm_bridge
      mac    = var.talos_vms[name].mac
      disk   = "/dev/zvol/${var.truenas_pool}/${var.talos_zvol_parent}/${name}-disk0"
    }
  }
}

output "kubernetes_nfs_share_id" {
  description = "TrueNAS NFS share identifier for the Kubernetes CSI export, or null when disabled."
  value       = try(truenas_share_nfs.kubernetes_csi[0].id, null)
}

output "kubernetes_nfs_share_path" {
  description = "TrueNAS filesystem path exported to democratic-csi."
  value       = local.kubernetes_csi_nfs_path
}

output "kubernetes_nfs_allowed_hosts" {
  description = "Talos node addresses authorized for the Kubernetes NFS export."
  value       = var.kubernetes_nfs_allowed_hosts
}
