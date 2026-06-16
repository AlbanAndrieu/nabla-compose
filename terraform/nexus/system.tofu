resource "sonatyperepo_security_realms" "realms" {
  active = [
    "NexusAuthenticatingRealm",
    "DockerToken",
    "NpmToken",
    "TerraformToken",
  ]
}
