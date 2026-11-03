# Import-first: every resource of this unit already exists in the Cloudflare
# dashboard. The first plan must show "will be imported", never "will be created".

import {
  to = cloudflare_zero_trust_tunnel_cloudflared_config.homelab
  id = "${var.account_id}/${var.tunnel_id}"
}

import {
  to = cloudflare_dns_record.fastapi_sample
  id = "${var.zone_id}/${var.fastapi_sample_dns_record_id}"
}

import {
  to = cloudflare_zero_trust_access_application.fastapi_sample
  id = "accounts/${var.account_id}/${var.fastapi_sample_access_application_id}"
}

import {
  to = cloudflare_zero_trust_access_application.fastapi_sample_api
  id = "accounts/${var.account_id}/${var.fastapi_sample_api_access_application_id}"
}
