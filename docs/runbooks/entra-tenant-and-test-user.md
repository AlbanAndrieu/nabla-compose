# Entra Nabla — compte personnel, deux YubiKeys et pilote H16

**Actualisé le 22 novembre 2026.** Le compte Azure personnel, le tenant
Entra ID Free et l'enrôlement des **deux YubiKeys** sont **déclarés par
l'opérateur**, mais aucune authentification Microsoft n'a été vérifiée depuis
les outils du dépôt. Les applications Graph/OIDC, le workspace HCP et les
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
az login --tenant "$ENTRA_NABLA_TENANT_ID" --allow-no-subscriptions
az account tenant list --output table
bash scripts/entra/entra-nabla-preflight.sh
```

Vérifier le domaine et l'identité sous
[Entra admin center](https://entra.microsoft.com/) ; puis vérifier les
deux passkeys sous [Security info](https://mysignins.microsoft.com/security-info).
Le PIN et le toucher restent sous le contrôle du navigateur/clé physique.
Éviter `az login -u ... -p ...` et toute automatisation de mot de passe.

**Licence :** Security Defaults et les passkeys peuvent être utilisées
avec Entra ID Free. Imposer une force d'authentification Conditional Access
« phishing-resistant » nécessite **Entra ID P1**.

## Bootstrap des applications et environnement GitHub (non exécuté)

1. Créer dans HCP Terraform l'unique workspace `entra-nabla-state` en
   mode `Local`, organisation gratuite isolée ; son token possède des
   privilèges étendus, même si utilisé pour `plan`.
2. Entra ID → App registrations : créer deux enregistrements de service
   `entra-nabla-plan` et `entra-nabla-apply`, attribuer à chacun une
   identité fédérée GitHub (sans secret client) :
   - issuer : `https://token.actions.githubusercontent.com`
   - audience : `api://AzureADTokenExchange`
   - subject plan :
     `repo:AlbanAndrieu/nabla-compose:environment:entra-nabla-plan`
   - subject apply :
     `repo:AlbanAndrieu/nabla-compose:environment:entra-nabla-apply`
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
