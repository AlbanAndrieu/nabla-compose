resource "cloudflare_dns_record" "fastapi_sample" {
  content                 = "${var.tunnel_id}.cfargotunnel.com"
  include_shadow_metadata = false
  name                    = "sample.albandrieu.com"
  proxied                 = true
  settings = {
    flatten_cname = false
    ipv4_only     = false
    ipv6_only     = false
  }
  tags    = []
  ttl     = 1
  type    = "CNAME"
  zone_id = var.zone_id

  lifecycle {
    prevent_destroy = true
  }
}
