resource "sonatyperepo_role" "global_readonly" {
  id          = "global-readonly"
  name        = "Global Read-Only"
  description = "Read and browse access to all repositories"
  privileges = [
    "nx-repository-view-*-*-browse",
    "nx-repository-view-*-*-read",
  ]
}

resource "sonatyperepo_role" "global_readwrite" {
  id          = "global-readwrite"
  name        = "Global Read-Write"
  description = "Full read and write access to all repositories"
  privileges = [
    "nx-repository-view-*-*-browse",
    "nx-repository-view-*-*-read",
    "nx-repository-view-*-*-add",
    "nx-repository-view-*-*-edit",
    "nx-repository-view-*-*-delete",
  ]
}

resource "sonatyperepo_role" "docker_readonly" {
  id          = "docker-readonly"
  name        = "Docker Read-Only"
  description = "Read and browse access to all Docker repositories"
  privileges = [
    "nx-repository-view-docker-*-browse",
    "nx-repository-view-docker-*-read",
  ]
}

resource "sonatyperepo_role" "docker_readwrite" {
  id          = "docker-readwrite"
  name        = "Docker Read-Write"
  description = "Full read and write access to all Docker repositories"
  privileges = [
    "nx-repository-view-docker-*-browse",
    "nx-repository-view-docker-*-read",
    "nx-repository-view-docker-*-add",
    "nx-repository-view-docker-*-edit",
    "nx-repository-view-docker-*-delete",
  ]
}
