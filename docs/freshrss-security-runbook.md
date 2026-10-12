# FreshRSS — runbook d'activation CISO/CTID (préparation, non exécutée)

> Statut : **SOURCE READY / RUNTIME NOT VALIDATED**. Aucun redémarrage
> TrueNAS, changement de DNS, compte, secret ou API publique effectué ici.
> Les PR concernées : `nabla-compose#254` puis `nabla-site-alban#220`.

## Choix d'administration : CLI officielle > API GReader > Terraform

- **Comptes et import OPML** : CLI native de FreshRSS
  (`cli/list-users.php`, `cli/create-user.php`, `cli/import-for-user.php`).
  L'API GReader ne propose pas de création d'utilisateur administrateur.
- **Consommation / validation** : API Google Reader compatible :
  `POST /api/greader.php/accounts/ClientLogin`, puis
  `GET /api/greader.php/reader/api/0/subscription/list?output=json` et
  `GET .../stream/contents/reading-list?output=json&n=100`.
- **Terraform** : utile pour DNS, tunnels, Access et ressources externes
  déclaratives, mais pas le mécanisme natif du compte FreshRSS.
- Attention : les usernames FreshRSS sont **ASCII alphanumériques** :
  `securitypublic` (publication) et `securityagent` (MCP privé).
- **Limitation de la CLI native** : `--password` et `--api-password`
  passent brièvement dans `argv`. Le bootstrap doit rester local,
  opéré comme root sur TrueNAS, sans `bash -x`, avec secret files
  `root:root 0600`. Option plus stricte : création et rotation via UI
  FreshRSS, puis uniquement scripts de vérification/import.
  Les comptes existants ne sont jamais recréés ni remis à zéro.

## 0 — Prérequis de stabilité et sauvegarde

Respecter le chemin critique `docs/roadmap.md` : aucune activation
tant que les services socles et leur sauvegarde ne sont pas acceptés.

Vérifier l'App FreshRSS existante sur TrueNAS **sans** recréer une
seconde App (nom/ID exact à confirmer). Documenter image et version,
UID de service (`www-data` ou `apache`), datasets, montage,
état et disponibilité de `cli/list-users.php`, mode API global, sauvegarde
SQLite/PostgreSQL, sécurité DNS/egress et route Cloudflare Access.
Ne jamais vider le répertoire `data` pour rejouer un bootstrap.

## 1 — Préflight reproductible, sans mutation

Depuis le checkout canonique `/mnt/cpool/compose/nabla-compose` :

```bash
# FRESHRSS_CONTAINER doit viser le conteneur TrueNAS réel.
FRESHRSS_CONTAINER=freshrss bash scripts/truenas/freshrss-ops.sh --check
python3 -m unittest tests/test_freshrss_mcp_contract.py
python3 -m py_compile scripts/mcp/freshrss_readonly.py
```

Préflight refuse : conteneur absent/arrêté, image non FreshRSS,
mauvaise identité CLI, fichier OPML absent.
Inspecter l'image et le conteneur, ne pas modifier le script pour
contourner un diagnostic inexpliqué.

## 2 — Secrets *hors Git* et bootstrap opt-in

Sur TrueNAS, préparer, via le coffre ou un canal administrateur sécurisé,
quatre fichiers indépendants :

```text
/mnt/cpool/secrets/runtime/freshrss/securitypublic.login-password
/mnt/cpool/secrets/runtime/freshrss/securitypublic.api-password
/mnt/cpool/secrets/runtime/freshrss/securityagent.login-password
/mnt/cpool/secrets/runtime/freshrss/securityagent.api-password
```

Chaque fichier doit contenir **un secret distinct généré
cryptographiquement de >=24 caractères**, appartenir à `root:root`
et avoir `0600`. Ne pas les générer/afficher dans des logs ou copier
des modèles avec de vrais secrets dans Git.

```bash
# Seulement après backup, revue image, compte et approbation :
sudo -E env FRESHRSS_APPROVE_APPLY=YES FRESHRSS_CONTAINER=freshrss \
  bash scripts/truenas/freshrss-ops.sh --apply

# Si comptes existants mais abonnements non importés : étape séparée
# NON strictement idempotente, vérifier les abonnements avant réimport !
sudo -E env FRESHRSS_APPROVE_APPLY=YES FRESHRSS_IMPORT_APPROVED=YES \
  FRESHRSS_CONTAINER=freshrss \
  bash scripts/truenas/freshrss-ops.sh --import-opml
```

Le script crée les comptes **seulement si absents**, avec
`--no-default-feeds` et importe les dix sources depuis
`config/freshrss/public-security.opml`. Il ne crée aucune API
accessible publiquement et ne démarre aucune App.
Valider dans l'UI le nombre **exact** et les URL des abonnements ;
l'import OPML ne garantit pas que tous les feeds distants répondent.
Ne pas auto-supprimer des flux supplémentaires sur des comptes existants.

## 3 — API GReader et identités séparées

Si l'API n'est pas activée, examiner puis activer `api-enabled` via
l'interface administrateur (ou `cli/reconfigure.php --api-enabled`,
après approbation). La CLI `--api-password` est distincte du login.
Pour chaque compte, obtenir **son propre** `Auth` en appelant
`ClientLogin` avec le nom et le mot de passe API dans le **corps POST**,
et conserver le jeton dans le gestionnaire de secrets correspondant.

- Vercel serveur : `FRESHRSS_GREADER_AUTH` de **securitypublic** et
  `FRESHRSS_PUBLICATION_ENABLED=true` seulement après recette.
- Agent local MCP : `FRESHRSS_MCP_AUTH` de **securityagent**,
  variables du client dans `.mcp.json`; aucun port HTTP ouvert.
- Cloudflare Access : un service token limité au hostname/chemin GReader
  et à la machine consommatrice, seulement si l'API est protégée
  par Access; ne pas désactiver Access pour faire réussir le POC.
- Les jetons API FreshRSS ne sont **pas finement scopés read-only** ;
  les comptes ne contiennent **que des flux approuvés** et le MCP
  masque les outils d'écriture. Pour une isolation renforcée, restreindre
  egress/processus, rotation et accès aux variables.
- Les secrets ne doivent pas être préfixés `NEXT_PUBLIC_`.

## 4 — MCP sécurisé, sans service HTTP supplémentaire

Le fichier racine `.mcp.json` contient
`freshrss-security-readonly` → `python3 scripts/mcp/freshrss_readonly.py`.
C'est un **serveur MCP local stdio** (pas de Docker socket,
shell, écriture, crawler arbitraire ni port publié). Deux outils :

- `list_security_feeds` : sources publiques autorisées seulement ;
- `recent_security_articles(limit<=20)` : titres, brefs résumés,
  liens HTTPS filtrés ; rejette les abonnements privés/inconnus.

Enregistrer le MCP seulement dans les agents autorisés ; le lancer
depuis la racine du checkout avec les secrets injectés au runtime.
`scripts/mcp/freshrss_readonly.py` utilise uniquement la bibliothèque
standard Python ; TLS validé, pas de redirections, taille/latence bornées
et erreurs génériques pour éviter les leaks.

**Alternative upstream** : `ChrisLAS/freshrss-mcp` fonctionne en
HTTP Streamable et propose aussi `mark_as_read`, `star_article`, etc.
Ne pas l'exposer publiquement ni le substituer sans revue de code,
pinnage du commit, tests SAST, contrôle d'authentification et
autorisation explicite des outils d'écriture.

## 5 — Recette et cutover vers le site Next.js

1. Vérifier la liste d'abonnements *effective* par GReader et l'absence
   de flux privés, chez chaque compte. Comparer avec
   `config/freshrss/security-sources.json`.
2. Contrôler `/api/ciso/threat-feed` de la preview Next.js :
   modes 503 sans secrets/flag, 200 seulement si configuré, origin IDs
   dans l'allowlist ; aucun PII/hostname/IP/version sensible.
3. Vérifier `/security-feed.xml` (<=10 articles, XML valide) et
   conserver `/feed.xml` historique. Les flux RSS ne valident
   **aucune** vulnérabilité technique du homelab.
4. Passer Playwright, ZAP, Semgrep, CodeQL, pipeline site et
   accessibilité ; surveiller le cache CDN (TTL de 10 minutes).
5. Rollback : mettre `FRESHRSS_PUBLICATION_ENABLED=false`,
   invalider le cache CDN si fuite, révoquer le jeton concerné
   et désactiver la connexion MCP. Ne jamais supprimer les comptes
   ni la base sans backup et revue des dépendances.

## Critères Done / Deferred

**Done** lorsque l'App est saine, les comptes distincts réels sont
confirmés, chacun a le jeu de sources attendu, l'API et le MCP sont
accessibles uniquement aux identités autorisées, les tests anti-fuite
passent et le site publie *uniquement* le contenu validé.

**Deferred** : flux privés éditoriaux, write-tools MCP, Terraform
Cloudflare sans inventaire réel, automatisation des rotations,
publication DefectDojo et reboot/rollout TrueNAS.

Références :
- https://github.com/FreshRSS/FreshRSS/blob/edge/cli/README.md
- https://freshrss.github.io/FreshRSS/en/developers/06_GoogleReader_API.html
- https://github.com/ChrisLAS/freshrss-mcp
