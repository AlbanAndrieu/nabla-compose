# Nexus — dépôts gérés par OpenTofu

**État (27/11/2026) :** lots N1 (APT, 7 proxys), N2 (npm : `npm-proxy`,
`npm-local`, `npm-all`) et N3 (PyPI : `pypi-proxy`, `pypi-local`, `pypi-all`)
appliqués format par format depuis la workstation ; l'état Garage
`nexus/tfstate.json` existe et le plan final avec `["apt","npm","pypi"]` répond
`No changes`. Docker, Hugging Face et Terraform ne sont pas activés. Les 9 dépôts
Maven/NuGet créés à la main restent hors de ce module. Unité Terragrunt :
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

« Défaut » est celui du module. L'unité
[`infrastructure/nexus`](../../infrastructure/nexus/terragrunt.hcl) fixe
`enabled_formats = ["apt", "npm", "pypi"]` depuis le 27/11 : retirer un format
de cette liste **détruit** ses dépôts.

Élargir un format à la fois : l'ajouter à `enabled_formats` dans l'unité, plan
relu, `apply`, réception côté workstation, puis le format suivant. **Un
`TF_VAR_enabled_formats` exporté l'emporte sur `inputs`** (Terragrunt n'écrase
jamais un `TF_VAR_*` existant, vérifié avec 0.95.1) : le retirer avant un plan.
Le test hors ligne [`tests/formats.tftest.hcl`](tests/formats.tftest.hcl) fige
le contrat du module (défaut = APT seul, aucun realm/rôle/utilisateur).

**Realms** : relevé admin du 27/11, `NexusAuthenticatingRealm` seul actif (ni
`NpmToken` ni `DockerToken`). Avant `manage_realms=true`, recopier la liste
vivante à l'identique dans [`system.tofu`](system.tofu) : un oubli désactive le
realm en production.

**Utilisateurs** : plus de 1Password ni de mot de passe généré dans l'état.
Les mots de passe viennent de Vaultwarden par
`TF_VAR_nexus_user_passwords='{"home-ops":"…","albandrieu":"…"}'` (jamais dans
Git ni affichés). Au 27/11, seuls `admin` et `anonymous` existent : si
`albandrieu` est créé à la main d'ici là, l'importer avant le premier `apply`
avec `manage_rbac=true`.

## Identifiants (Vaultwarden, jamais affichés)

Attendus par [`config/secrets/manifest.json`](../../config/secrets/manifest.json),
**toujours absents de Vaultwarden au 27/11** :

- `nabla/prod/nexus-infrastructure` : champs `NEXUS_USERNAME`, `NEXUS_PASSWORD`
  (compte admin ou rôle avec `nx-repository-admin-*` et `nx-settings-read` ;
  la lecture seule suffit pour un `plan`) ;
- `nabla/prod/infrastructure-bootstrap` : champs `AWS_ACCESS_KEY_ID`,
  `AWS_SECRET_ACCESS_KEY` de la clé Garage du bucket `opentofu-state` (seuls
  `GARAGE_ADMIN_TOKEN` et `TRUENAS_INFRA_API_KEY` y sont présents).

Le run du 27/11 a utilisé en mémoire le compte `admin` existant (hors
Vaultwarden) et la clé Garage `opentofu` lue par l'API admin Garage, sans rien
écrire ni afficher. **À faire par le propriétaire** : créer un compte de service
Nexus et ces champs, puis changer le mot de passe `admin`. Sans eux, un `plan`
lancé par un agent reste `NOT_RUN`.

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
env -u TF_VAR_enabled_formats scripts/infra/terragrunt-safe.sh infrastructure/nexus plan -lock=false -detailed-exitcode -no-color
```

Attendu depuis le 27/11 : `No changes` (code 0). Un `destroy` sur `npm-*` ou
`pypi-*` signale un `TF_VAR_enabled_formats` encore exporté ou une régression de
l'unité. Pour un nouveau lot (N4 Docker), ajouter `-out=nexus-n4.tfplan` et
n'attendre que des créations du format ajouté, aucun
`sonatyperepo_security_realms`, `sonatyperepo_role` ni `sonatyperepo_user`.
Pour la PR, ne joindre que les adresses et la ligne `Plan:`
(`grep -E '^  # |^Plan:'`), jamais le plan binaire ni l'état.

## Apply et réception

`apply` uniquement après approbation explicite du propriétaire sur le plan
relu, unité par unité (`terragrunt-safe.sh` sauvegarde l'état Garage avant) :

```bash
scripts/infra/terragrunt-safe.sh infrastructure/nexus apply nexus-n4.tfplan
```

Réception depuis `ansible-workstation` : `mise run nexus-clients-check`
(5 sondes attendues à 200), puis le runbook client
`docs/workstation-nexus-package-cache.md` (N1 APT → N2 npm → N3 PyPI → N4 Docker).
