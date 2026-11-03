# Cloudflare homelab — OpenTofu (Tunnel, DNS, Access)

**État : import-first, rien n'est appliqué.** Premier changement porté :
renommer le hostname public `sample.albandrieu.com` en
`fastapi-sample.albandrieu.com`. Le nom interne `sample.int.albandrieu.com`
(Pi-hole/Traefik) et l'App TrueNAS `sample` ne changent pas.

Provider `cloudflare/cloudflare` épinglé en `= 5.28.1` (dernière v5 au
31/10/2026). État distant : bucket Garage `opentofu-state`, clé
`cloudflare-homelab/tfstate.json`, hérité de [`root.hcl`](../../root.hcl).
Garage n'a pas de verrou natif : passer **toujours** par
`scripts/infra/terragrunt-safe.sh` (verrou local, sauvegarde de l'état avant
apply), depuis une seule workstation sur le LAN (`s3.int.albandrieu.com`).

## Ressources et propriété

| Adresse | Objet Cloudflare | Particularité |
| --- | --- | --- |
| `cloudflare_zero_trust_tunnel_cloudflared_config.homelab` | Public Hostnames du tunnel partagé `1d98bede-…` (`config_src=cloudflare`) | Remplace la configuration **entière** : possède les routes de **tous** les services (Garage, OpenWebUI, Vaultwarden, 2FAuth…). Une route absente du code est supprimée à l'apply. |
| `cloudflare_dns_record.fastapi_sample` | CNAME proxied vers `<tunnel>.cfargotunnel.com` | Renommage = update in-place (`name` ne force pas de remplacement). |
| `cloudflare_zero_trust_access_application.fastapi_sample` | Application Access `sample` (tout le hostname) | Politiques `nabla` (allow) et `fastapi-sample-monitor` (jeton de service). Le tag AUD ne change pas : la validation JWT côté FastAPI reste valide. |
| `cloudflare_zero_trust_access_application.fastapi_sample_api` | Application Access `sample-api` (chemin `/api`) | Politique `nabla` seule : le jeton du monitor n'atteint pas `/api`. À renommer **avec** l'application principale, sinon `/api` retombe sous ses politiques. |

Les politiques réutilisables ne contiennent aucun hostname et `nabla` est
partagée avec d'autres applications : elles restent gérées dans le dashboard,
référencées par identifiant (`locals` de `access.tofu`).

Après adoption, ne plus modifier ces objets dans le dashboard : la dérive
serait écrasée au prochain apply. Le module voisin
[`cloudflare-ops`](../cloudflare-ops/README.md) reste dédié à un tunnel séparé.

## Jeton API (hors dépôt)

`CLOUDFLARE_API_TOKEN` vient de Vaultwarden, n'est jamais écrit dans un
fichier du dépôt ni affiché (vérifier avec `[ -n "${CLOUDFLARE_API_TOKEN:-}" ]`).
Deux jetons distincts, limités au compte `bdfe00ee…` et à la zone
`albandrieu.com`, idéalement avec filtrage d'IP client et date d'expiration :

| Usage | Type | Élément | Permission |
| --- | --- | --- | --- |
| capture, plan | Account | Cloudflare Tunnel | Read |
| capture, plan | Account | Access: Apps and Policies | Read |
| capture, plan | Zone | Zone, DNS | Read |
| apply | Account | Cloudflare Tunnel | Edit |
| apply | Account | Access: Apps and Policies | Edit |
| apply | Zone | DNS | Edit |

Source : [guide Terraform Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/deployment-guides/terraform/).
L'état Garage exige en plus `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`
(voir [infrastructure-bootstrap](../../docs/infrastructure-bootstrap.md)).

## 1. Capture (lecture seule)

```bash
scripts/cloudflare/capture-homelab-tofu.sh
```

Le script n'envoie que des `GET` à l'API, puis lance un `tofu plan` local
(aucun état écrit) avec `-generate-config-out`. Il produit :

- `import-ids.auto.tfvars` : identifiants (non secrets) à commiter ; les UUID
  Access portent `# gitleaks:allow`, comme ceux de `.doco-cd.yaml` ;
- `generated.tofu` (ignoré par Git) : configuration live des 4 ressources.

Le script échoue si une autre application Access vise ce hostname. Répartir
`generated.tofu` dans `tunnel.tofu`, `dns.tofu` et `access.tofu`, puis le
supprimer :

- recopier **toutes** les routes `config.ingress`, y compris la route finale
  `http_status:404` et les `origin_request = {}` vides (attribut non calculé :
  l'omettre crée une dérive) ; ajouter `lifecycle { prevent_destroy = true }`
  aux 4 ressources ;
- supprimer les attributs `null` et remplacer les identifiants littéraux par
  `var.account_id`, `var.tunnel_id`, `var.zone_id` ;
- le dépôt est **public** : aucune donnée personnelle (e-mail, IP publique)
  dans le code ; les règles `include`/`require` vivent dans les politiques,
  hors de ce module.

Plan de référence, **sans renommage** :

```bash
scripts/infra/terragrunt-safe.sh infrastructure/cloudflare-homelab init -reconfigure
scripts/infra/terragrunt-safe.sh infrastructure/cloudflare-homelab plan
```

Attendu : `4 to import, 0 to add, 0 to change, 0 to destroy`. Toute autre
différence signifie que le code ne reflète pas l'existant : corriger le code,
jamais Cloudflare, et relancer.

## 2. Renommage

- `tunnel.tofu` : `hostname = "fastapi-sample.albandrieu.com"` sur la route
  dont le `service` est `http://172.17.0.24:8091` ;
- `dns.tofu` : `name = "fastapi-sample.albandrieu.com"` ;
- `access.tofu`, pour **les deux** applications : `domain` devient le nouveau
  nom (`…/api` pour `sample-api`) ; les destinations publiques listent le
  nouveau nom **puis** l'ancien, pour qu'aucun des deux ne soit jamais servi
  sans Access pendant la bascule ; la destination privée reste inchangée ;
- ajouter `depends_on` vers les deux applications au tunnel et au DNS :
  Access protège le nouveau nom avant sa publication.

Attendu : `4 to import, 0 to add, 4 to change, 0 to destroy`, chaque
changement ne portant que sur le hostname. Toute autre ligne : s'arrêter.

## 3. Apply (accord explicite du propriétaire)

```bash
scripts/infra/terragrunt-safe.sh infrastructure/cloudflare-homelab plan -out=rename.tfplan
scripts/infra/terragrunt-safe.sh infrastructure/cloudflare-homelab apply rename.tfplan
```

Jamais depuis la CI. Appliquer au moment de la fusion des PR qui renomment le
hostname côté code (nabla-compose #304 et fastapi-sample) : FastAPI ne filtre
pas le `Host`, mais sondes et catalogue visent encore l'ancien nom avant elles.

Réception :

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://fastapi-sample.albandrieu.com/
python3 scripts/cloudflare/diagnose-cloudflare-api.py \
  --tunnel-id 1d98bede-6fa0-42a8-971c-cd390d74d7f6 \
  --expect-hostname fastapi-sample.albandrieu.com \
  --access-url https://fastapi-sample.albandrieu.com/
scripts/infra/terragrunt-safe.sh infrastructure/cloudflare-homelab plan
```

Attendu : défi Access anonyme (302/403, pas 200), route présente dans
l'ingress, autres hostnames du tunnel inchangés, puis `No changes`.

## 4. Rollback

- Revert Git du commit de renommage, puis même séquence plan/apply :
  4 updates in-place vers `sample.albandrieu.com`.
- Urgence sans OpenTofu : remettre l'ancien hostname dans le dashboard, puis
  reverter le code avant tout nouvel apply (sinon il re-renomme).
- État corrompu : restaurer la sauvegarde prise par `terragrunt-safe.sh`
  (`${NABLA_STATE_BACKUP_DIR}` ou `~/.local/state/nabla-compose/opentofu-state-backups/`).
- Jamais de `destroy` : détruire la configuration du tunnel supprimerait les
  routes de tous les services.

## 5. Après réception

Retirer `sample.albandrieu.com` (et `…/api`) des `destinations` des deux
applications Access (plan attendu : 2 change). Les blocs `import` deviennent
des no-op une fois les ressources dans l'état.

## Validation hors ligne

```bash
tofu -chdir=terraform/cloudflare-homelab fmt -check
tofu -chdir=terraform/cloudflare-homelab init -backend=false -input=false
tofu -chdir=terraform/cloudflare-homelab validate
```
