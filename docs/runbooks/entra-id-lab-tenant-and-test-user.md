# Entra ID Free — tenant personnel et utilisateur de test (H16)

**État : CODED, test OpenTofu simulé au vert ; aucun compte, tenant, state ni
utilisateur créé.** L'opérateur crée lui-même le compte, accepte les conditions
et saisit téléphone et carte. Contexte et modèle de menace :
[lab Entra H16](../security/entra-id-homelab-lab.md) ; module :
[`terraform/entra-id-lab`](../../terraform/entra-id-lab/README.md).

## 0. Quelle voie pour un tenant gratuit (vérifié le 15/11/2026)

| Voie | Ce qu'on obtient | Verdict |
| --- | --- | --- |
| [Compte Azure gratuit](https://azure.microsoft.com/pricing/purchase-options/azure-account) | Un tenant Entra ID Free (« Default Directory », domaine `*.onmicrosoft.com`) dont on est Global Administrator, et un abonnement Azure : 200 $ de crédit sur 30 jours. Carte de crédit ou de débit non prépayée, avec une autorisation temporaire d'environ 1 $, et vérification par téléphone. | **Retenu** : l'abonnement porte aussi le state Azure Blob. |
| [Programme développeur Microsoft 365](https://learn.microsoft.com/office/developer-program/microsoft-365-developer-program-faq) | Bac à sable E5 de 90 jours, renouvelable sous conditions. Le compte de facturation est obligatoire. | Réservé aux abonnés Visual Studio Pro/Enterprise, aux partenaires (ISV Success, AI Cloud Partner Program) et aux contrats Premier/Unified : pas accessible à titre personnel. |
| [Entra : Gérer les locataires > Créer](https://learn.microsoft.com/entra/fundamentals/create-new-tenant) | Un tenant supplémentaire | Réservé aux clients payants ; un tenant gratuit ou d'essai ne peut pas en créer d'autre. |
| Essai Entra External ID | Un tenant *externe* (CIAM) de 30 jours | Hors sujet : ce n'est pas un tenant d'effectifs. |

Le tenant Entra ID Free n'expire pas. **L'abonnement Azure, si** : avant le
30ᵉ jour, il faut passer au paiement à l'utilisation, sinon l'abonnement est
désactivé et le state Blob devient inaccessible. Le tenant, lui, reste. On n'a
droit qu'à un seul compte gratuit par personne : si le tien a déjà servi,
souscris directement au paiement à l'utilisation. Entra ID Free reste gratuit
et le state ne pèse que quelques Ko.

## 1. Créer le compte et le tenant (toi)

1. Utilise un **compte Microsoft personnel**, jamais un compte professionnel,
   dans une fenêtre de navigation privée. Ajoute la YubiKey comme clé de
   sécurité (passkey) dans *Compte Microsoft > Sécurité*.
2. Va sur <https://azure.microsoft.com/free>, clique sur « Commencer
   gratuitement » et connecte-toi avec ce compte. Remplis le profil, puis
   la vérification par téléphone et la carte. Accepte le contrat.
3. Dans le [centre d'administration Entra](https://entra.microsoft.com), ouvre
   *Entra ID > Vue d'ensemble*. Note l'**ID de locataire** (GUID) et le
   **domaine initial** `*.onmicrosoft.com`, et vérifie que la licence est
   « Microsoft Entra ID Free ». Facultatif : *Propriétés > Nom* →
   `Nabla IAM Lab`.
4. Laisse les **paramètres de sécurité par défaut** activés : ils imposent la
   MFA aux comptes du tenant.
5. Dans le [portail Azure](https://portal.azure.com), ouvre *Gestion des coûts
   > Budgets* et crée un budget de 1 € par mois avec une alerte. Avant le
   30ᵉ jour, *Abonnements > Mettre à niveau* : passe au paiement à
   l'utilisation.

## 2. State Azure Blob (toi, une seule fois)

Le state H16 est un blob Azure, avec bail natif et authentification Entra
uniquement. Ce n'est **jamais Garage** : la CI GitHub ne joint pas le LAN.

```bash
export AGENT_EXECUTION_MODE=workstation
export ENTRA_LAB_CONFIRMED=true
export ENTRA_LAB_TENANT_ID="<GUID du tenant>"
export ENTRA_STATE_RG=nabla-entra-lab-state
export ENTRA_STATE_ACCOUNT="<nom unique : 3 à 24 minuscules ou chiffres>"
export ENTRA_STATE_CONTAINER=entra-lab-tfstate
az login --tenant "$ENTRA_LAB_TENANT_ID"
az account show --query '{tenant:tenantId, subscription:name}' -o table
az group create --name "$ENTRA_STATE_RG" --location francecentral
az storage account create --name "$ENTRA_STATE_ACCOUNT" --resource-group "$ENTRA_STATE_RG" \
  --location francecentral --sku Standard_LRS --kind StorageV2 --https-only true \
  --min-tls-version TLS1_2 --allow-blob-public-access false --allow-shared-key-access false
az storage account blob-service-properties update --account-name "$ENTRA_STATE_ACCOUNT" \
  --resource-group "$ENTRA_STATE_RG" --enable-versioning true \
  --enable-delete-retention true --delete-retention-days 30 \
  --enable-container-delete-retention true --container-delete-retention-days 30
az storage container-rm create --storage-account "$ENTRA_STATE_ACCOUNT" \
  --resource-group "$ENTRA_STATE_RG" --name "$ENTRA_STATE_CONTAINER" --public-access off
scope="$(az storage account show --name "$ENTRA_STATE_ACCOUNT" --resource-group "$ENTRA_STATE_RG" --query id -o tsv)/blobServices/default/containers/$ENTRA_STATE_CONTAINER"
az role assignment create --assignee "$(az ad signed-in-user show --query id -o tsv)" \
  --role "Storage Blob Data Contributor" --scope "$scope"
```

Le chiffrement au repos est toujours actif côté Azure. Le rôle `Owner` de
l'abonnement ne donne pas accès aux blobs par Entra : c'est l'affectation
ci-dessus qui le donne, avec quelques minutes de propagation.

## 3. Mot de passe initial (toi)

Dans Vaultwarden, crée l'élément `nabla/lab/entra-id-lab-test-user` avec un
mot de passe généré d'au moins 16 caractères. Tu le transmets ensuite à
OpenTofu sans jamais l'afficher :

```bash
export BW_SESSION="$(bw unlock --raw)"
export TF_VAR_test_user_initial_password="$(bw get password nabla/lab/entra-id-lab-test-user)"
```

## 4. Préflight, init, plan (toi)

```bash
cd ~/w/nabla-compose
bash scripts/entra/entra-lab-preflight.sh
export TF_VAR_tenant_id="$ENTRA_LAB_TENANT_ID" TF_VAR_lab_tenant_confirmed=true TF_VAR_enable_user_management=true
cd terraform/entra-id-lab
tofu init -backend-config="storage_account_name=$ENTRA_STATE_ACCOUNT" -backend-config="container_name=$ENTRA_STATE_CONTAINER"
tofu validate
umask 077
tofu plan -out=entra.tfplan
```

Plan attendu : **6 to add, 0 to change, 0 to destroy**.

- `terraform_data.personal_tenant_guard` ;
- `azuread_application_registration.workload["reader"|"denied"]` ;
- `azuread_service_principal.workload["reader"|"denied"]`, avec `denied`
  désactivé ;
- `azuread_user.test[0]` : UPN `nabla-iam-lab-user@<domaine initial>`,
  `password = (sensitive value)`, `force_password_change = true`.

Au moindre écart (update, destroy, autre ressource ou autre tenant), arrête.
`ENTRA_LAB_PREFLIGHT_OK` doit s'afficher avant le plan.

## 5. Apply contrôlé (toi, après relecture du plan)

```bash
tofu apply entra.tfplan
rm -f entra.tfplan
tofu output test_user_principal_name
unset TF_VAR_test_user_initial_password
```

Le fichier `entra.tfplan` contient le mot de passe en clair : supprime-le
juste après l'apply. Il est ignoré par Git (`*.tfplan`).

## 6. Première connexion de l'utilisateur de test

Dans une fenêtre privée, ouvre <https://myaccount.microsoft.com> et connecte-toi
avec l'UPN et le mot de passe initial. Entra impose un nouveau mot de passe, puis
l'enregistrement de la MFA (paramètres de sécurité par défaut). Range le
nouveau mot de passe dans l'élément Vaultwarden.

## Garanties et limites

- **CI : plan seulement, jamais d'utilisateur.** Le workflow fixe
  `TF_VAR_enable_user_management: "false"`, et `check-plan.py` rejette toute
  ressource `azuread_user` hors liste blanche.
- **Mot de passe** : variable sensible, absente du code et des sorties,
  masquée dans le plan. `azuread` 3.10.0 n'a pas d'attribut *write-only* :
  la valeur est donc **dans le state**, lisible par qui lit le blob,
  identité CI de plan comprise. Elle ne vaut que jusqu'à la première
  connexion, qu'il faut faire juste après l'apply.
- `ignore_changes = [password]` : changer la valeur dans Vaultwarden ne
  réinitialise rien. Pour réinitialiser, passe par le portail Entra ou
  recrée l'utilisateur (`tofu plan -replace='azuread_user.test[0]' -out=entra.tfplan`).
- **Suppression** : `TF_VAR_enable_user_management=false` puis plan et apply
  (1 to destroy). L'utilisateur reste 30 jours dans les utilisateurs
  supprimés.
- Test hors ligne : `TF_VAR_test_user_initial_password=dummy tofu -chdir=terraform/entra-id-lab test`.

## Dépannage

| Symptôme | Cause probable |
| --- | --- |
| `ENTRA_LAB_BLOCKED: …` | Variable manquante, autre tenant actif dans `az`, ou clé statique `ARM_*` exportée. |
| `AuthorizationPermissionMismatch` à l'init | Affectation `Storage Blob Data Contributor` pas encore propagée : attendre. |
| `MissingSubscriptionRegistration` | `az provider register --namespace Microsoft.Storage` |
| `Refusing changes until personal tenant is confirmed…` | `TF_VAR_lab_tenant_confirmed` absent ou identité `az` sur un autre tenant. |
| `Export TF_VAR_test_user_initial_password…` | Étape 3 non faite dans ce shell. |
