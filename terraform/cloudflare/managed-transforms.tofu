# Zone-wide Managed Transforms of albandrieu.com, imported as found on
# 22/11/2026 (imports.tofu) except one: "remove_visitor_ip_headers" stripped
# CF-Connecting-IP before every origin. The honeypot then reported the Docker
# gateway (10.200.49.1) to Project Honey Pot for every visitor, and the
# Traefik/CrowdSec canary decides on Cf-Connecting-Ip (owner decision,
# 21/11/2026). Origins trust the header only from the cloudflared pool.
resource "cloudflare_managed_transforms" "albandrieu" {
  zone_id = var.zone_id
  managed_request_headers = [
    { id = "add_client_certificate_headers", enabled = true },
    { id = "add_visitor_location_headers", enabled = true },
    { id = "add_waf_credential_check_status_header", enabled = true },
  ]
  managed_response_headers = [
    { id = "add_security_headers", enabled = true },
    { id = "remove_x-powered-by_header", enabled = true },
  ]

  lifecycle {
    prevent_destroy = true
  }
}
