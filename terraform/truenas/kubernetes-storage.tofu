locals {
  kubernetes_csi_nfs_path = "/mnt/${var.truenas_pool}/${var.kubernetes_csi_dataset}"
}

resource "truenas_share_nfs" "kubernetes_csi" {
  count = var.enabled && var.kubernetes_nfs_share_enabled ? 1 : 0

  path          = local.kubernetes_csi_nfs_path
  comment       = "Kubernetes democratic-csi nfs-client bootstrap export"
  hosts         = var.kubernetes_nfs_allowed_hosts
  readonly      = false
  maproot_user  = "root"
  maproot_group = "wheel"
  security      = ["SYS"]
  enabled       = true
}
