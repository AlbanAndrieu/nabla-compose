# Nexus — dépôts gérés par OpenTofu

**État (23/11/2026) :** jamais appliqué. Nexus 3.92.3 Community sert 9 dépôts
Maven/NuGet créés à la main (lecture anonyme de
`/service/rest/v1/repositories`, 23/11) ; aucun dépôt de ce module n'existe, il
n'y a donc pas de collision de nom au premier `apply`. Unité Terragrunt :
[`infrastructure/nexus`](../../infrastructure/nexus/terragrunt.hcl), état
`nexus/tfstate.json` dans Garage, cible LAN `https://nexus.int.albandrieu.com`
([apps/nexus](../../apps/nexus/README.md)).

## Ce que l'unité gère, format par format

| Interrupteur | Défaut | Ressources |
| --- | --- | --- |
| `enabled_formats` contient `apt` | **oui** | 7 proxys APT dont `apt-ubuntu-26-04` et `apt-ubuntu-26-04-security` (lot N1) |
| `enabled_formats` contient `npm` | non | `npm-proxy`, `npm-local`, groupe `npm-all` (N2) |
| `enabled_formats` contient `pypi` | non | `pypi-proxy`, `pypi-local`, groupe `pypi-all` (N3) |
| `enabled_formats` contient `docker` | non | 7 proxys de registre, `docker-internal`, groupe `docker-all` (N4) |
| `enabled_formats` contient `huggingface` / `terraform` | non | `huggingface-proxy-repo`, `terraform-proxy` |
| `manage_rbac` | non | rôles `global-*`/`docker-*`, utilisateurs `home-ops` et `albandrieu` |
| `manage_realms` | non | liste des realms actifs (remplace **toute** la liste vivante) |

Élargir un format à la fois : `TF_VAR_enabled_formats='["apt","npm"]'`, plan
relu, `apply`, réception côté workstation, puis le format suivant. Le test
hors ligne [`tests/formats.tftest.hcl`](tests/formats.tftest.hcl) fige ce
contrat (défaut = APT seul, aucun realm/rôle/utilisateur).

**Realms** : `GET /service/rest/v1/security/realms/active` répond 403 en
anonyme (23/11) ; la liste vivante n'est pas encore relevée. Avant
`manage_realms=true`, recopier cette liste à l'identique dans
[`system.tofu`](system.tofu) : un oubli (par ex. `NuGetApiKey`, utilisé par
les dépôts NuGet) désactive le realm en production.

**Utilisateurs** : plus de 1Password ni de mot de passe généré dans l'état.
Les mots de passe viennent de Vaultwarden par
`TF_VAR_nexus_user_passwords='{"home-ops":"…","albandrieu":"…"}'` (jamais dans
Git ni affichés). Si `albandrieu` existe déjà dans Nexus, l'importer avant le
premier `apply` avec `manage_rbac=true`.

## Identifiants (Vaultwarden, jamais affichés)

Attendus par [`config/secrets/manifest.json`](../../config/secrets/manifest.json),
**absents de Vaultwarden au 23/11** (relevé par noms de champs, valeurs non lues) :

- `nabla/prod/nexus-infrastructure` : champs `NEXUS_USERNAME`, `NEXUS_PASSWORD`
  (compte admin ou rôle avec `nx-repository-admin-*` et `nx-settings-read` ;
  la lecture seule suffit pour un `plan`) ;
- `nabla/prod/infrastructure-bootstrap` : champs `AWS_ACCESS_KEY_ID`,
  `AWS_SECRET_ACCESS_KEY` de la clé Garage du bucket `opentofu-state` (seuls
  `GARAGE_ADMIN_TOKEN` et `TRUENAS_INFRA_API_KEY` y sont présents).

**À faire par le propriétaire** : créer ces champs. Sans eux le relevé des
realms et le `plan` restent `NOT_RUN`.

## Plan en lecture seule (workstation)

```bash
export BW_SESSION="$(bw unlock --raw)"   # ou ~/.local/bin/bw-unlocked
export NEXUS_USERNAME="$(bw get item nabla/prod/nexus-infrastructure | jq -r '.fields[]|select(.name=="NEXUS_USERNAME").value')"
export NEXUS_PASSWORD="$(bw get item nabla/prod/nexus-infrastructure | jq -r '.fields[]|select(.name=="NEXUS_PASSWORD").value')"
export GARAGE_OPENTOFU_AWS_ACCESS_KEY_ID="$(bw get item nabla/prod/infrastructure-bootstrap | jq -r '.fields[]|select(.name=="AWS_ACCESS_KEY_ID").value')"
export GARAGE_OPENTOFU_AWS_SECRET_ACCESS_KEY="$(bw get item nabla/prod/infrastructure-bootstrap | jq -r '.fields[]|select(.name=="AWS_SECRET_ACCESS_KEY").value')"
unset BW_SESSION
curl -sS --max-time 10 -K <(printf 'user = "%s:%s"\n' "$NEXUS_USERNAME" "$NEXUS_PASSWORD") \
  https://nexus.int.albandrieu.com/service/rest/v1/security/realms/active
scripts/infra/terragrunt-safe.sh infrastructure/nexus plan -lock=false -no-color -out=nexus-n1.tfplan
```

Attendu pour le lot N1 : `Plan: 7 to add, 0 to change, 0 to destroy`, uniquement
des `sonatyperepo_repository_apt_proxy.apt_proxy[...]`, aucun
`sonatyperepo_security_realms`, `sonatyperepo_role` ni `sonatyperepo_user`.
Pour la PR, ne joindre que les adresses et la ligne `Plan:`
(`grep -E '^  # |^Plan:'`), jamais le plan binaire ni l'état.

## Apply et réception

`apply` uniquement après approbation explicite du propriétaire sur le plan
relu, unité par unité (`terragrunt-safe.sh` sauvegarde l'état Garage avant) :

```bash
scripts/infra/terragrunt-safe.sh infrastructure/nexus apply nexus-n1.tfplan
```

Réception depuis `ansible-workstation` : `mise run nexus-clients-check`
(5 sondes attendues à 200), puis le runbook client
`docs/workstation-nexus-package-cache.md` (N1 APT → N2 npm → N3 PyPI → N4 Docker).
