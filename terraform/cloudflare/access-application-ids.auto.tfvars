# Dashboard IDs of the route Access applications (access-routes.tofu), import-first.
route_access_application_ids = {
  "heimdall"     = "01b92d9d-4025-415a-9293-b9f6fa4ca9d7" # gitleaks:allow
  "prometheus"   = "295810bb-80a7-4cc7-b120-0d829af6ba44" # gitleaks:allow
  "scrutiny"     = "3ea19f8d-b040-45fd-aa93-5af3184c6f39" # gitleaks:allow
  "ittools"      = "089f0fae-4797-481a-b137-d1cd797445ec" # gitleaks:allow
  "uptime-kuma"  = "6085e83f-55d6-4d47-a4ed-dbb05b5c9c79" # gitleaks:allow
  "2fauth"       = "aa269770-71c6-4584-a1e4-79db5fc0af5f" # gitleaks:allow
  "n8n"          = "a9a82278-4c6b-4da4-b0db-b5dfd90713be" # gitleaks:allow
  "n8n-slack"    = "4aa397b9-672a-4edb-ad41-cce0b334f927" # gitleaks:allow
  "grafana"      = "e189d241-fd8d-475a-b6b9-5bf215a66578" # gitleaks:allow
  "homarr"       = "d7bc2a2f-3f1f-46c9-8072-6abe2bcec953" # gitleaks:allow
  "gatus"        = "27a11912-e6d6-4502-b04e-958ded2da958" # gitleaks:allow
  "karakeep"     = "5e9918bd-4395-49fb-8634-36d490ccb060" # gitleaks:allow
  "searxng"      = "5bae4bd3-3cb8-4c88-96b3-200271f9fec7" # gitleaks:allow
  "openwebui"    = "9256a0ed-f4b2-410d-80b9-a1afac19ef77" # gitleaks:allow
  "reactive"     = "6c7b414d-2e9f-4524-88f7-41986bde4b6d" # gitleaks:allow
  "nginx"        = "5425fcd3-f78e-4cfb-baf2-18dfff27841d" # gitleaks:allow
  "code"         = "1f19f08f-12ae-4109-9de3-72a8a711601f" # gitleaks:allow
  "cadvisor"     = "ce6e73e1-edc6-469e-9d12-11c4480b79a0" # gitleaks:allow
  "npmplus"      = "794b60e5-0f2a-499f-bf98-8716e65c79a2" # gitleaks:allow
  "nexus"        = "5e3a4799-9307-48eb-9a3b-0036812a7bba" # gitleaks:allow
  "npm"          = "a67cf300-f5f9-436e-9c3f-1515b773e0ed" # gitleaks:allow
  "ddns-updater" = "81f9dcbe-7598-4f9e-bc1b-ac3a326f4852" # gitleaks:allow
  "minio"        = "263a86c4-6122-4556-be16-cc79b8b6951f" # gitleaks:allow
  "langfuse"     = "09a3a836-29f7-4dcb-a300-4c25604468a5" # gitleaks:allow
  "clickhouse"   = "701aa34d-771e-4fea-92d1-6898fbf7b90c" # gitleaks:allow
  "languagetool" = "84cbe693-a1c2-477e-8334-a53bfca8488d" # gitleaks:allow
  "vaultwarden"  = "e98222ab-bf29-43f3-ae77-ba5fe8addcec" # gitleaks:allow
  "openrag"      = "80ca0edb-cf9b-4910-96b0-c9a1d64d9782" # gitleaks:allow
  "garage"       = "9898af9b-1b55-44d6-b755-469436092439" # gitleaks:allow
}

# Access service token of the nabla-site-alban support chat (site_support policy on openwebui).
# Created outside OpenTofu on 27/11/2026; its secret lives in Vaultwarden nabla/prod/site-support and Vercel.
site_support_service_token_id = "abc09e29-31ca-48d7-96ae-916393bc441b" # gitleaks:allow
