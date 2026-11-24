# Replaces the whole live realm list: the list below must stay a copy of
# GET /service/rest/v1/security/realms/active before manage_realms is enabled.
resource "sonatyperepo_security_realms" "realms" {
  count = var.manage_realms ? 1 : 0

  active = [
    "NexusAuthenticatingRealm",
    "DockerToken",
    "NpmToken",
    "TerraformToken",
  ]
}
