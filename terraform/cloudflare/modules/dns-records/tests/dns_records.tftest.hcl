# Offline contract of the dns-records module (mocked provider, no API call):
#   tofu -chdir=terraform/cloudflare/modules/dns-records init -backend=false
#   tofu -chdir=terraform/cloudflare/modules/dns-records test
mock_provider "cloudflare" {}

variables {
  zone_id          = "00000000000000000000000000000000"
  tunnel_target    = "tunnel-id.cfargotunnel.com"
  tunnel_hostnames = ["grafana.albandrieu.com", "gatus.albandrieu.com"]
  tunnel_record_ids = {
    "grafana.albandrieu.com" = "id-grafana"
    "gatus.albandrieu.com"   = "id-gatus"
  }
  retired_hostnames = ["radarr.albandrieu.com", "emby.albandrieu.com"]
}

run "blind_create_is_refused" {
  command = plan

  variables {
    tunnel_record_ids = { "grafana.albandrieu.com" = "id-grafana" }
  }

  expect_failures = [cloudflare_dns_record.tunnel]
}

run "declared_new_hostname_may_be_created" {
  command = plan

  variables {
    tunnel_record_ids    = { "grafana.albandrieu.com" = "id-grafana" }
    new_tunnel_hostnames = ["gatus.albandrieu.com"]
  }

  assert {
    condition     = length(cloudflare_dns_record.tunnel) == 2
    error_message = "an explicitly new hostname is allowed"
  }
}

run "tunnel_routes_get_proxied_cnames" {
  command = plan

  assert {
    condition = alltrue([
      for record in cloudflare_dns_record.tunnel :
      record.type == "CNAME" && record.proxied && record.content == "tunnel-id.cfargotunnel.com" && record.ttl == 1
    ])
    error_message = "tunnel records must be proxied CNAMEs to the tunnel"
  }
}

run "a_retired_name_cannot_stay_routed" {
  command = plan

  variables {
    tunnel_hostnames  = ["radarr.albandrieu.com"]
    tunnel_record_ids = { "radarr.albandrieu.com" = "id-radarr" }
  }

  expect_failures = [cloudflare_dns_record.tunnel]
}

run "retired_records_are_adopted_first" {
  command = plan

  variables {
    retired_record_ids = {
      "radarr.albandrieu.com/CNAME" = "id-radarr"
      "emby.albandrieu.com/A"       = "id-emby"
      "grafana.albandrieu.com/A"    = "not-retired"
    }
  }

  assert {
    condition     = toset(output.retired_record_keys) == toset(["radarr.albandrieu.com/CNAME", "emby.albandrieu.com/A"])
    error_message = "only retired hostnames are adopted"
  }
}

run "retire_phase_drops_them" {
  command = plan

  variables {
    retirement_phase   = "retire"
    retired_record_ids = { "radarr.albandrieu.com/CNAME" = "id-radarr" }
  }

  assert {
    condition     = length(cloudflare_dns_record.retired) == 0
    error_message = "the retire phase must leave no retired record in configuration"
  }
}
