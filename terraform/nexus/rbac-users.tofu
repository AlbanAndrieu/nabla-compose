# Passwords are read from Vaultwarden at plan time, never generated into state-only values.
resource "sonatyperepo_user" "home-ops" {
  count = var.manage_rbac ? 1 : 0

  user_id       = "home-ops"
  first_name    = "HomeOps"
  last_name     = "ServiceAccount"
  email_address = "homeops@albandrieu.com"
  password      = var.nexus_user_passwords["home-ops"]
  status        = "active"
  roles         = [sonatyperepo_role.docker_readonly[0].id]
}

resource "sonatyperepo_user" "albandrieu" {
  count = var.manage_rbac ? 1 : 0

  user_id       = "albandrieu"
  first_name    = "Alban"
  last_name     = "Andrieu"
  email_address = "nabla@albandrieu.com"
  password      = var.nexus_user_passwords["albandrieu"]
  status        = "active"

  roles = [sonatyperepo_role.global_readwrite[0].id]
}
