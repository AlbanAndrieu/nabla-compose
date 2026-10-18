output "ops_hostname" {
  value       = "ops.albandrieu.com"
  description = "Reserved public hostname; not proof of provisioned DNS or Access."
}

output "dns_publication_enabled" {
  value       = var.publish_ops_dns
  description = "Declarative intent only. DNS runtime evidence requires Cloudflare API verification."
}

output "tunnel_ingress_enabled" {
  value       = var.enable_ops_ingress
  description = "Declarative intent only. A tunnel config in state does not prove a live connector."
}
