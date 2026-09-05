locals {
  active_talos_vms = var.enabled ? var.talos_vms : {}
}

resource "truenas_zvol" "talos_disk" {
  for_each = local.active_talos_vms

  pool         = var.truenas_pool
  name         = "${var.talos_zvol_parent}/${each.key}-disk0"
  volsize      = each.value.disk_size_gib * 1024 * 1024 * 1024
  volblocksize = "16K"
  compression  = "LZ4"
  comments     = "Talos test disk managed by OpenTofu/Terragrunt"

  # PjSalty/truenas 2.4.1 does not expose the TrueNAS `sparse` zvol option.
  # Keep the provider/API default until the provider schema supports it again.
}

resource "truenas_vm" "talos" {
  for_each = local.active_talos_vms

  name                  = each.key
  description           = "Talos Kubernetes test VM managed by OpenTofu/Terragrunt"
  memory                = each.value.memory_mib
  vcpus                 = 1
  cores                 = each.value.cores
  threads               = 1
  bootloader            = "UEFI"
  autostart             = false
  ensure_display_device = false
  time                  = "UTC"
  cpu_mode              = "HOST-PASSTHROUGH"
}

resource "truenas_vm_device" "talos_disk" {
  for_each = local.active_talos_vms

  vm    = tonumber(truenas_vm.talos[each.key].id)
  dtype = "DISK"
  order = 1000
  attributes = {
    path = "/dev/zvol/${var.truenas_pool}/${var.talos_zvol_parent}/${each.key}-disk0"
    type = "VIRTIO"
  }

  depends_on = [truenas_zvol.talos_disk]
}

resource "truenas_vm_device" "talos_nic" {
  for_each = local.active_talos_vms

  vm    = tonumber(truenas_vm.talos[each.key].id)
  dtype = "NIC"
  order = 1002
  attributes = {
    type       = "VIRTIO"
    nic_attach = var.vm_bridge
    mac        = each.value.mac
  }
}

resource "truenas_vm_device" "talos_iso" {
  for_each = var.enabled && var.talos_iso_path != "" ? var.talos_vms : {}

  vm    = tonumber(truenas_vm.talos[each.key].id)
  dtype = "CDROM"
  order = 1001
  attributes = {
    path = var.talos_iso_path
  }
}
