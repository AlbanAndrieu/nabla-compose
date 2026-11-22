# Entra Nabla — compte personnel, deux YubiKeys et pilote H16

**Actualisé le 22 novembre 2026.** La connexion Azure CLI a confirmé le tenant
Entra ID Free déclaré par l'opérateur ; l'enrôlement des **deux YubiKeys** sont **déclarés par
l'opérateur**, mais aucune authentification Microsoft n'a été exécutée par les outils du dépôt. Les applications Graph/OIDC, le workspace HCP et les
ressources IaC restent `NOT_APPLIED`.

Source : [architecture, modèle de menace et signature YubiKey](../security/entra-id-homelab-lab.md).
Module : [terraform/entra](../../terraform/entra/README.md).

## Choix d'architecture

- Utiliser exclusivement **le tenant Workforce personnel**, sans toucher
  au tenant de l'employeur. Le compte administrateur personnel et le domaine
  initial sont fournis par l'opérateur, **jamais publiés dans le dépôt**.
- Privilégier la connexion **FIDO2 matérielle dans le navigateur** avec la
  YubiKey principale. Confirmer séparément la seconde clé et sa capacité à
  se connecter à l'**identité Entra effective**, pas seulement au compte
  Microsoft personnel. Conserver une méthode de récupération indépendante.
- Backend de state : **HCP Terraform Free** dans une organisation dédiée,
  workspace `entra-nabla-state` en mode `Local`, zéro autre état. **L'ancien
  guide Azure Blob est obsolète** ; ne pas créer de compte de stockage Azure
  pour ce pilote.
- Apps OIDC GitHub : `entra-nabla-plan`, `entra-nabla-apply`.
  Aucun mot de passe d'application ou jeton personnel dans la CI.

## Connexion sur la workstation

Saisir l'ID du tenant depuis la console locale uniquement (pas dans Git) :

```bash
export AGENT_EXECUTION_MODE=workstation
export ENTRA_NABLA_CONFIRMED=true
export ENTRA_NABLA_TENANT_ID="<GUID-du-tenant-personnel>"
export AZURE_CONFIG_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/nabla-entra/azure-cli"
install -d -m 700 "$AZURE_CONFIG_DIR"
# Interactive sign-in: select the intended directory and use a YubiKey.
az login --tenant "$ENTRA_NABLA_TENANT_ID" --allow-no-subscriptions
# Stable core command: avoid experimental 'az account tenant list' extension.
az account show --query '{tenant:tenantId,subscription:name}' --output json
bash scripts/entra/entra-nabla-preflight.sh
```

Le domaine initial déclaré pour ce tenant est
`albanandrieuhotmail.onmicrosoft.com`. La session Azure CLI doit être
vérifiée par **Tenant ID** via `az account show`, pas uniquement par le nom
« Répertoire par défaut ». Le nom `nabla-test.onmicrosoft.com` était une
fixture de test, **jamais le domaine de production**.
`az account tenant list` peut tenter d'installer l'extension expérimentale
`account` ; ne pas l'utiliser pour ce préflight.

**Diagnostic des erreurs Azure CLI sur Ubuntu/mise.** Des erreurs
`pkg_resources` dans l'extension facultative `ai-examples` et
`No module named rpds.rpds` révèlent un environnement Python/extension
incohérent, pas nécessairement un échec de connexion. Les avertissements
`SyntaxWarning` d'Azure Batch ne sont pas bloquants. Sur la workstation,
tester dans l'ordre `az version`, `az extension list -o table` et
`az account show --query tenantId -o tsv`; retirer `ai-examples`
et l'extension `account` si elle a été installée uniquement par
la commande expérimentale, après revue des extensions nécessaires.
Le client mise actuel utilise un Python 3.14 : préférer un environnement
Azure CLI **Python 3.12** isolé pour éviter les incompatibilités de
modules compilés. Ne pas supprimer la session Azure existante ni
modifier la version globale de Python pour cela.

Vérifier le domaine et l'identité sous
[Entra admin center](https://entra.microsoft.com/) ; puis vérifier les
deux passkeys sous [Security info](https://mysignins.microsoft.com/security-info).
Le PIN et le toucher restent sous le contrôle du navigateur/clé physique.
Éviter `az login -u ... -p ...` et toute automatisation de mot de passe.

**Licence :** Security Defaults et les passkeys peuvent être utilisées
avec Entra ID Free. Imposer une force d'authentification Conditional Access
« phishing-resistant » nécessite **Entra ID P1**.

## Bootstrap Terraform contrôlé depuis la workstation (NOT_APPLIED)

Le tenant personnel a été **confirmé par la sortie Azure CLI** fournie par
l'opérateur le 22/11/2026 ; il n'existe toujours aucune preuve de création
des applications, des rôles Graph ou de l'état HCP.

**Prérequis** : disposer du workspace **HCP Free**
`entra-nabla-state`, seul workspace de son organisation dédiée, en
mode d'exécution **Local**. Préparer les credentials HCP personnels dans
`TF_TOKEN_app_terraform_io` hors dépôt (ne les transmettre à personne).
Le workspace, ses variables et ses secrets doivent rester distincts de
tous les états Garage. Ne pas demander de ressources Azure payantes.

L'authentification CLI utilise `AZURE_CONFIG_DIR` isolé et YubiKey FIDO2.
Depuis un checkout à jour, dans un shell de confiance :

```bash
set -euo pipefail
export AGENT_EXECUTION_MODE=workstation
export ENTRA_NABLA_CONFIRMED=true
export ENTRA_NABLA_TENANT_ID="<GUID-du-tenant-personnel>"
export AZURE_CONFIG_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/nabla-entra/azure-cli"
install -d -m 700 "$AZURE_CONFIG_DIR"

# If not already logged in with the personal FIDO2 key:
az login --tenant "$ENTRA_NABLA_TENANT_ID" --allow-no-subscriptions
bash scripts/entra/entra-nabla-preflight.sh
export TF_VAR_tenant_id="$ENTRA_NABLA_TENANT_ID"
export TF_VAR_nabla_tenant_confirmed=true
export TF_VAR_enable_ci_identity_bootstrap=true
export TF_VAR_enable_workload_pilot=false
export TF_VAR_enable_group_management=false
export TF_VAR_enable_user_management=false

# Use the *Entra directory object ID*, never the subscription GUID or UPN.
export TF_VAR_ci_bootstrap_operator_object_id="$(az ad signed-in-user show --query id -o tsv)"
test -n "$TF_VAR_ci_bootstrap_operator_object_id"

# Inspect existing app names FIRST to avoid creating duplicates. If they
# already exist, import into the HCP state rather than creating another.
az ad app list --filter "displayName eq 'entra-nabla-plan'" \
  --query '[].{appId:appId,id:id}' --output table
az ad app list --filter "displayName eq 'entra-nabla-apply'" \
  --query '[].{appId:appId,id:id}' --output table

# In a private directory, create HCP remote backend config. Substitute the
# dedicated HCP *organization name* (not a secret).
umask 077
mkdir -p "$HOME/.local/state/nabla-entra/bootstrap"
cat > "$HOME/.local/state/nabla-entra/bootstrap/hcp.tfbackend" <<'HCP'
hostname = "app.terraform.io"
organization = "<DEDICATED_HCP_ORGANIZATION>"
workspaces { name = "entra-nabla-state" }
HCP

tofu -chdir=terraform/entra init -lockfile=readonly \
  -backend-config="$HOME/.local/state/nabla-entra/bootstrap/hcp.tfbackend"
tofu -chdir=terraform/entra validate
tofu -chdir=terraform/entra plan -input=false -lock-timeout=5m \
  -out="$HOME/.local/state/nabla-entra/bootstrap/plan.tfplan"
tofu -chdir=terraform/entra show -no-color \
  "$HOME/.local/state/nabla-entra/bootstrap/plan.tfplan"
```

**Acceptance gate before applying manually**: the plan should contain
only the **two** CI app registrations, their home-tenant service
principals, GitHub federated credentials, their requested (not consented)
Graph API roles and the tenant `terraform_data` guard. No extra users,
groups, demo workloads, Azure subscription RBAC, Defender plans,
destroy/replacement or unknown tenant. A submitted plan is not approval.

After reviewing the exact saved plan and confirming the HCP state is
isolated and locked, an authorized operator may execute
`tofu -chdir=terraform/entra apply -input=false <saved-plan-file>`
**locally with the YubiKey interactive session**. This explicit
operator-only bootstrap is an exception to the usual CI signed apply
gate; no GitHub runner can bootstrap its own OIDC identity. Do **not**
trigger a CI apply before this bootstrap.

After apply, run
`tofu -chdir=terraform/entra output entra_nabla_ci_client_ids`
and
`tofu -chdir=terraform/entra output entra_nabla_ci_principal_object_ids`.
The two nonsecret Client IDs go to the matching GitHub protected
environments as `ENTRA_GRAPH_CLIENT_ID`; save the stable operator
object ID as `ENTRA_NABLA_OPERATOR_OBJECT_ID`, plus the tenant ID
`ENTRA_NABLA_TENANT_ID`, HCP organization/workspace and HCP token
in their appropriate variables/secrets.

**Permissions and consent still require review**:
the requested role for plan is `Application.Read.All`
(broad application directory read); for apply
`Application.ReadWrite.OwnedBy` (can create and manage owned apps).
These **are requested in Terraform but not admin-consented or
granted**. Explicit administrator consent occurs only after reviewing
application principals, owners, subjects, exact role IDs and negative
tests, and must be audited. `OwnedBy` must be proven to permit the
future workload policy with only the intended app/SP ownership; if the
test fails, *stop*, do not escalate to `Application.ReadWrite.All`.

A failed bootstrap requires examining partial HCP state and Entra
objects before retrying. Never delete the remote state or run
`tofu apply -replace` to bypass guardrails. `prevent_destroy`
makes accidental removals fail closed.

## Bootstrap des applications et environnement GitHub (non exécuté)

1. Créer dans HCP Terraform l'unique workspace `entra-nabla-state` en
   mode `Local`, organisation gratuite isolée ; son token possède des
   privilèges étendus, même si utilisé pour `plan`.
2. Entra ID → **App registrations** : créer deux **enregistrements
   d'application monolocataire** `entra-nabla-plan` et
   `entra-nabla-apply` dans le **tenant personnel vérifié**.
   Entra crée normalement aussi les **service principals** correspondants
   (visibles dans **Enterprise applications**) : ne pas exécuter
   `az ad sp create-for-rbac` et ne pas créer un deuxième objet en doublon.
   Donner à chaque enregistrement une identité fédérée GitHub
   (Certificates & secrets → Federated credentials → GitHub Actions,
   Entity type = Environment), **sans secret client** :
   - issuer : `https://token.actions.githubusercontent.com`
   - audience : `api://AzureADTokenExchange`
   - subject plan :
     `repo:AlbanAndrieu/nabla-compose:environment:entra-nabla-plan`
   - subject apply :
     `repo:AlbanAndrieu/nabla-compose:environment:entra-nabla-apply`
   Vérifier séparément les deux **Application (client) IDs**, leurs
   **Object IDs**, les principals associés et la liste exacte des
   permissions **Microsoft Graph**. Commencer avec un accès de lecture
   minimal pour `plan`, puis réserver les écritures autorisées à
   `apply`; ne pas attribuer automatiquement `Contributor` à
   l'abonnement Azure ni accorder de permissions tenant-wide.
   Un consentement administrateur devra être approuvé sur un périmètre
   explicitement recensé. GitHub ne doit pas pouvoir utiliser une
   application d'un autre environnement.

3. Dans GitHub Actions, pour les deux **environnements protégés** :
   `ENTRA_NABLA_TENANT_ID`, `ENTRA_GRAPH_CLIENT_ID`
   (Client ID distinct par environnement), `HCP_TF_ORGANIZATION`,
   `HCP_TF_WORKSPACE` et secret d'environnement `HCP_TF_TOKEN`.
   Enregistrer la ligne `ENTRA_APPROVAL_ALLOWED_SIGNER` au **niveau
   du dépôt** (clé publique SSH-FIDO2 seulement), car le job
   `approval_gate` ne possède pas d'environnement.
4. Ne pas activer `ENTRA_NABLA_APPLY_ENABLED` avant contrôle du périmètre
   Graph et du plan, validation des tests négatifs, signature YubiKey,
   et protection des environnements GitHub.
5. Les applications OIDC GitHub s'authentifient **automatiquement par
   fédération**, pas en touchant une YubiKey sur le runner. La clé matérielle
   fournit l'**approbation humaine indépendante** de l'apply Terraform.

## Sécurité et recette

Vérifier mauvais tenant, mauvais subject OIDC, token HCP absent, signature
incorrecte/expirée, différence d'empreinte de plan, refus de l'écriture
de groupes et utilisateurs en CI, et absence de client secret.
`CODED` ne vaut pas `DEPLOYED` ou `ACCEPTED`.
Ne pas exécuter d'apply depuis ce runbook.

Références :
- https://learn.microsoft.com/en-us/entra/identity/authentication/how-to-register-passkey-with-security-key
- https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation-create-trust
- https://learn.microsoft.com/en-us/entra/fundamentals/security-defaults
