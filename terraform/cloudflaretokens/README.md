# Cloudflare — jetons d'API gérés par OpenTofu

**État : code prêt, rien n'est appliqué.** Cette unité crée le jeton de compte
`nabla-opentofu` (`CLOUDFLARE_API_TOKEN_NABLA_OPENTOFU`) utilisé par
[`terraform/cloudflare`](../cloudflare/README.md) pour `plan`/`apply`. Ses droits
sont relisibles dans [`tokens.tofu`](tokens.tofu) au lieu du dashboard :

| Portée | Permission |
| --- | --- |
| Compte `bdfe00ee…` | Access: Apps and Policies Write, Cloudflare Tunnel Write |
| Zone `albandrieu.com` | DNS Write |
| Condition | adresses clientes de `TF_VAR_opentofu_token_client_ips` |
| Expiration | `opentofu_token_expires_on` (rotation : avancer la date) |

État séparé (`cloudflaretokens/tfstate.json` dans Garage) : seule cette unité
exige le droit de gérer des jetons. **La valeur du jeton est dans l'état** :
le bucket Garage et les sauvegardes de `terragrunt-safe.sh` restent sur le LAN.

## Identifiant d'amorçage (une fois)

Créer et lire des jetons exige un jeton de compte portant **Account API Tokens
Write** (ou **Edit**), idéalement de courte durée et filtré par IP, exporté en
`CLOUDFLARE_API_TOKEN` pour la seule commande. Le jeton « Read all resources »
ne suffit pas, même pour le `plan` (lecture des groupes de permissions).

## Plan, apply et stockage

```bash
export TF_VAR_opentofu_token_client_ips='["<IP WAN>/32"]'
scripts/infra/terragrunt-safe.sh infrastructure/cloudflaretokens init
scripts/infra/terragrunt-safe.sh infrastructure/cloudflaretokens plan -out=tokens.tfplan
scripts/infra/terragrunt-safe.sh infrastructure/cloudflaretokens apply tokens.tfplan
```

Attendu : `1 to add`. Une erreur « Unknown permission group names » signifie
que Cloudflare a renommé un groupe : corriger le nom dans `tokens.tofu`.
Ensuite, copier la valeur dans Vaultwarden (`nabla/prod/cloudflare`, champ
`CLOUDFLARE_API_TOKEN_NABLA_OPENTOFU`) sans l'afficher, via
`tofu output -raw opentofu_token` redirigé vers `bw`, puis l'exporter dans
le shell de l'opérateur.
