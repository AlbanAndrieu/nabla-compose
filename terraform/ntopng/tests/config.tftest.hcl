# Offline: the mock provider never reaches ntopng, so the token is a placeholder.
mock_provider "restapi" {}

variables {
  ntopng_url   = "http://ntopng.invalid"
  ntopng_token = "not-a-real-token"
}

run "alert_store_is_capped_and_noisy_flow_checks_are_off" {
  command = plan

  assert {
    condition     = jsondecode(restapi_object.alert_preference["max_entity_alerts"].data).pref_value == "20000"
    error_message = "the alert cap must stay far below the 1,000,000 default"
  }

  assert {
    condition     = keys(restapi_object.disabled_flow_check) == ["ndpi_probing_attempt", "ndpi_unidirectional_traffic", "tcp_no_data_exchanged"]
    error_message = "exactly the three flow checks of the 22/11 flood are disabled"
  }

  assert {
    condition = alltrue([for check in restapi_object.disabled_flow_check :
    check.path == "/lua/rest/v2/disable/check.lua" && check.destroy_path == "/lua/rest/v2/enable/check.lua"])
    error_message = "apply disables the checks and destroy enables them again"
  }
}
