# DefectDojo GitHub App — sécurité et provisioning GitOps

**État : préparation de PR uniquement. GitHub App non créée, aucun token réel
émis, aucun job TrueNAS activé.**

## App cible

- Nom : `nabla-defectdojo-artifacts`
- Compte propriétaire : `AlbanAndrieu`
- Installation : **Selected repositories**, uniquement
  `AlbanAndrieu/nabla-site-alban`
- Permissions : Repository `Actions: read` et `Metadata: read` (implicite)
- Événements : aucun ; webhook désactivé ; aucune écriture de dépôt
- Déclaration versionnée : [manifest](../config/github-apps/defectdojo-artifacts.manifest.json)
- GitHub App distincte de l'identité **DefectDojo API** qui importe
  les rapports ; aucune permission d'administration GitHub nécessaire

Le provider `integrations/github` utilisé sous `terraform/github` sait
**s'authentifier avec une GitHub App existante** via `app_auth`, mais ne
sert pas à enregistrer initialement une GitHub App. Le Terraform de
gouvernance GitHub existant reste inchangé et désactivé par défaut.
L'enregistrement de l'App est une étape de confiance initiale, nécessitant
l'approbation du propriétaire via la page
https://github.com/settings/apps/new ou le *GitHub App Manifest Flow* :
https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-from-a-manifest.
Le fichier du dépôt documente les paramètres de cette étape ; ce n'est
**ni** un App créée, **ni** un Terraform `apply` automatique.

## Jeton dynamique (sans PAT)

1. Après validation de l'App, relever son **App ID** (distinct du Client ID)
   et son **installation ID**. Une clé RSA PEM est créée depuis GitHub.
2. Conserver le PEM dans un item Vaultwarden **séparé**
   `nabla/prod/defectdojo-github-app` (pièce jointe chiffrée) ;
   ne jamais l'insérer dans `nabla/prod/defectdojo` ou dans le
   `.env.secrets` du conteneur. La CLI `bw` doit le matérialiser sous
   `/mnt/cpool/secrets/runtime/defectdojo/github-app-private-key.pem`
   (root:root 0600), sans l'afficher et sans l'enregistrer dans Git ou
   Terraform state. La matérialisation du PEM depuis Vaultwarden reste
   à outiller/accepter sur TrueNAS ; aucune clé n'existe dans la PR.
3. Un fichier metadata également privé `github-app.json` (root:root 0600)
   contient uniquement les identifiants numériques et le dépôt autorisé :

```json
{
  "app_id": 0,
  "installation_id": 0,
  "repository": "AlbanAndrieu/nabla-site-alban"
}
```

Les zéros sont uniquement des placeholders : le collecteur les refuse.
Les vrais IDs sont découverts après installation et ne sont pas devinés.

4. À chaque invocation du poll TrueNAS, `github_app_auth.py` vérifie
   l'identité des fichiers et génère un JWT **RS256 signé par OpenSSL**
   sur une durée de 9 minutes. Le secret PEM ne passe ni dans
   les arguments CLI, ni dans les logs, ni dans un environnement Compose.
5. Le client envoie ce JWT à
   `POST /app/installations/{installation_id}/access_tokens` avec :
   `{"repositories":["nabla-site-alban"],"permissions":{"actions":"read"}}`.
   Il refuse une réponse ne confirmant pas le scope du dépôt,
   les permissions et une expiration dans l'heure.
   **Le jeton d'installation (durée maximale 1 h) reste en mémoire** :
   il n'est ni archivé dans Vaultwarden, ni écrit sur disque,
   ni transmis au stockage des ZIP lors des redirections GitHub.
6. Le job Cron natif TrueNAS lit les **runs master réussis** en lecture
   seule et récupère les JSON filtrés ; il reste désactivé jusqu'à
   vérification des artefacts et du produit/engagement dans DefectDojo.

Le GitHub App ne peut **pas** importer dans DefectDojo : cette action
nécessite un jeton DefectDojo distinct, limité au produit autorisé.
Les rapports BetterLeaks, GitGuardian, secrets bruts et DAST avec PII
restent hors ingestion automatique.

## Refus et maintenance

- Clé PEM absente, trop permissive, symlink, App ID non numérique,
  installation inexistante, retour token hors scope, erreur réseau :
  `ERROR/UNKNOWN`, **jamais** un résultat de scan à zéro finding.
- Aucune substitution automatique par PAT. Ne pas mettre de PAT dans
  le checkout, dans un GitHub Actions secret pour TrueNAS ni dans le state.
- Rotation clé : nouvelle clé depuis GitHub, mise à jour atomique
  de la pièce jointe Vaultwarden et de la matérialisation, test
  du mint, puis révocation de l'ancienne clé.
- Vérifier que l'accès GitHub aux archives GitHub Actions n'est pas
  plus large que nécessaire et que les rapports DAST téléchargés
  ne contiennent pas de données sensibles.
- Les credentials UI DefectDojo doivent utiliser le login **`nabla`** ;
  si Vaultwarden contient un mot de passe existant pour `admin`,
  le bootstrap **refuse** toute modification automatique. La base
  Django initialisée ne renomme pas un utilisateur par un simple
  changement de `DD_ADMIN_USER`.

Sources :
- https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app
- https://docs.github.com/en/rest/apps/apps
- https://registry.terraform.io/providers/integrations/github/latest/docs
