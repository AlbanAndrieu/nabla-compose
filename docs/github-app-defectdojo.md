# GitOps bootstrap : une seule GitHub App Nabla pour plusieurs dépôts

**Décision du 19 octobre 2026 : une seule App `nabla-github-app`,
pas une App par dépôt, pas de PAT permanent, pas de runner GitHub interne.**

La source d'autorité est
[`config/github-apps/defectdojo-artifacts.manifest.json`](../config/github-apps/defectdojo-artifacts.manifest.json).
Les dépôts candidats explicitement autorisés sont :
`nabla-compose`, `fastapi-sample`, `nabla-site-alban`,
`nabla-site-bababou`. L'installation GitHub reste *Selected repositories*.
Les permissions de l'App sont `Actions:read` et `Metadata:read` implicite,
aucun webhook et aucun événement. Chaque jeton d'installation est limité
à **un seul dépôt** et à `actions:read`.

## Création en code open source (bootstrap initial)

Le provider `integrations/github` peut utiliser une App existante et
gérer la gouvernance GitHub, mais **ne crée pas l'enregistrement initial** de
la GitHub App. GitHub expose plutôt un protocole officiel
[App Manifest Flow](https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-from-a-manifest).

1. Revoir/valider hors ligne le manifeste : `python3
   scripts/security/bootstrap-github-app-manifest.py --check`.
2. Sur une machine opérateur disposant d'un navigateur, préparer un répertoire
   **hors Git, 0700 et privé**, puis lancer `python3
   scripts/security/bootstrap-github-app-manifest.py --serve
   --output-dir /chemin/prive/0700`.
3. Visiter le point d'entrée local `http://127.0.0.1:8765/`,
   puis confirmer la création dans GitHub. Le formulaire poste
   **le manifeste versionné** ; seul GitHub peut enregistrer une App.
   Le callback reçoit un `state` aléatoire et un code à usage unique.
   Le code est échangé contre l'App ID et la clé RSA via
   `POST /app-manifests/{code}/conversions` dans l'heure.
4. Le script laisse `github-app-private-key.pem` et `github-app.json` dans
   le dossier 0700, tous deux **0600** ; il refuse tout écrasement,
   n'affiche aucun secret et n'écoute que sur 127.0.0.1.
   Il ne conserve pas `client_secret` ou `webhook_secret` du résultat.
5. Importer le PEM dans un item **Vaultwarden distinct**
   `nabla/prod/nabla-github-app` en pièce jointe chiffrée,
   puis **supprimer le PEM local de staging**. Ne jamais placer le PEM
   en `*.tfvars`, dans le state OpenTofu, dans un secret Actions ou
   dans le `.env.secrets` du conteneur DefectDojo.
6. Installer **une seule fois** l'App depuis les paramètres GitHub
   et sélectionner explicitement les dépôts autorisés. Pour TrueNAS,
   matérialiser PEM + JSON en `root:root 0600` dans
   `/mnt/cpool/secrets/runtime/defectdojo/`.
   L'ID d'installation vaut initialement **0** pour empêcher toute
   activation prématurée.
7. Depuis TrueNAS, le script
   `scripts/security/discover-github-app-installation.py --apply`
   consulte l'installation du dépôt Bababou via un JWT App signé.
   Il exige propriétaire `AlbanAndrieu`, `repository_selection=selected`,
   `Actions:read`, puis remplit l'ID privé sans le stocker dans Git.
8. Activer le Cron **seulement** après vérification des permissions,
   artefacts autorisés, ACL Vaultwarden et acceptation du product DefectDojo.

Le manifeste versionné constitue l'état désiré. La création est **un
bootstrap autorisé une seule fois**, pas un Terraform `apply` en CI ;
les scripts de validation sont le contrôleur de dérive.
La gestion GitHub Terraform existante peut poursuivre après ce bootstrap,
mais l'inventaire import-first et les droits réels priment sur le state.

## Convergence avec Site Bababou

Le workflow `production-dast.yml` sur `master` est nommé
`Production DAST` et produit l'artefact ZAP
`zap-production-report`. Aucun nouveau job DAST n'est déclenché :
le collecteur TrueNAS réutilise ce résultat uniquement s'il s'agit du
**dernier run terminé avec succès** (aucun fallback vers un run ancien
si un scan récent est rouge).

L'adaptateur n'autorise aujourd'hui que **ZAP HIGH**, transformé du
JSON original en XML minimal consommable par le parseur DefectDojo ;
aucun cookie, header, corps HTTP, URL authentifiée, query string,
token, PII, ni rapport ZAP brut n'est conservé. Il refuse les hôtes
hors `https://www.bababou.com` / `https://bababou.com`.
Le contenu brut du rapport GitHub peut malgré tout être sensible :
**ne pas activer l'import sans preuve de minimisation à la source**.

L'analyse Bababou mentionne un futur rapport Nuclei SARIF minimisé.
Ce flux n'est **pas encore vérifié sur `master`**. Il reste désactivé ;
pas d'activation automatique de Nuclei/SARIF, ni ingestion SARIF brute.

## Sécurité et limitations

- Un seul App ID et PEM, mais jetons de collecte **par dépôt**, durée
  maximale 1 heure. Aucune propagation du jeton GitHub vers les URLs
  de stockage de ZIP ; aucun accès entrant DefectDojo depuis GitHub.
- L'App est en **lecture seule** ; un jeton DefectDojo distinct et
  des engagements isolés contrôlent chaque réimport.
- L'intégration ne suppose pas que la CI réussie signifie que la donnée
  est saine ; acceptation obligatoire du parseur, des findings et de la
  déduplication dans DefectDojo.
- Les états `--check` de tous les scripts restent offline ;
  `--serve`, `--apply` et le polling réel exigent une action explicite.
- La GitHub App n'est **pas créée** par ce commit.

Références :
- https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-from-a-manifest
- https://docs.github.com/en/rest/apps/apps
- https://registry.terraform.io/providers/integrations/github/latest/docs

## Coffre Vaultwarden et vrai environnement Cron

Après création et consentement GitHub pour les **quatre** dépôts, le script
`scripts/security/sync-nabla-github-app-vaultwarden.py` fournit :

```bash
python3 scripts/security/sync-nabla-github-app-vaultwarden.py --check
python3 scripts/security/sync-nabla-github-app-vaultwarden.py \\
  --import-vaultwarden --pem /chemin/prive/github-app-private-key.pem \\
  --metadata /chemin/prive/github-app.json
python3 scripts/security/sync-nabla-github-app-vaultwarden.py \\
  --materialize --metadata /chemin/prive/github-app.json
```

Les actions de coffre nécessitent un opérateur `BW_SESSION` déverrouillé ;
elles **ne sont pas exécutées dans cette PR**. La pièce jointe PEM est
chiffrée dans l'item `nabla/prod/nabla-github-app`. La matérialisation
sur TrueNAS crée sous `/mnt/cpool/secrets/runtime/nabla-github-app/` :
`github-app-private-key.pem`, `github-app.json` et `.env.secrets`, avec
permissions `root:root 0600`. Le PEM reste un fichier séparé, **jamais
une chaîne Base64 dotenv** ; `.env.secrets` contient uniquement les chemins
canoniques et l'indicateur d'acceptation du handoff FastAPI. Le Cron native
exécute `run-nabla-github-app-cron.py --run`, qui valide ces références
avant le polling `--source all --pull`.

L'ID d'installation reste à 0 jusqu'à l'installation GitHub vérifiée
et `discover-github-app-installation.py --apply`. Ne pas déclarer l'App
créée, la PEM importée ou le Cron activé sans preuves runtime.
