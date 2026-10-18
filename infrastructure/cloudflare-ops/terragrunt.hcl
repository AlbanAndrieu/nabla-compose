include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = find_in_parent_folders("terraform/cloudflare-ops")
}

# The Garage backend is inherited from root.hcl; apply requires the existing
# external single-writer guard and approved credentials. No CI auto-apply.
inputs = {
  account_id                     = get_env("CLOUDFLARE_ACCOUNT_ID", "")
  zone_id                        = get_env("CLOUDFLARE_ZONE_ID", "")
  dedicated_tunnel_id            = get_env("CLOUDFLARE_OPS_TUNNEL_ID", "")
  manage_dedicated_tunnel        = false
  tunnel_creation_approved       = false
  enable_ops_ingress             = false
  publish_ops_dns                = false
  dedicated_tunnel_verified      = false
  access_policy_verified         = false
  fastapi_origin_jwt_verified    = false
  public_site_redaction_verified = false
  private_origin_https_url       = ""
  access_application_audience    = ""
  access_team_name               = ""
}
