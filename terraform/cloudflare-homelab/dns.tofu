resource "cloudflare_dns_record" "fastapi_sample" {
  content                 = "${var.tunnel_id}.cfargotunnel.com"
  include_shadow_metadata = false
  name                    = "fastapi-sample.albandrieu.com"
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

  # Access must protect a hostname before DNS publishes it.
  depends_on = [
    cloudflare_zero_trust_access_application.fastapi_sample,
    cloudflare_zero_trust_access_application.fastapi_sample_api,
  ]

  lifecycle {
    prevent_destroy = true
  }
}
