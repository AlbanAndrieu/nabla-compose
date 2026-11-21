# Runbook CTEM — installation, exécution, réception

Décision : [ADR 0004](../adr/0004-ctem.md). Le workflow existant
`external-attack-surface.yml` est le point d'entrée outside-in. Toute
mesure requiert périmètre, date, révision, scanner et conclusion.
Aucune des opérations runtime décrites ci-dessous n'a été exécutée
dans cette contribution API-only.

## 1. Campagnes externes et intégration

Dans [External attack surface](https://github.com/AlbanAndrieu/nabla-compose/actions/workflows/external-attack-surface.yml),
après fusion et validation du workflow :
- `mail` : audit DNS natif et job indépendant checkdmarc 6.0.3 / Nuclei DNS (templates épinglés SPF et DMARC, DKIM uniquement sur sélecteurs renseignés) ; compléter la liste depuis les zones Cloudflare réellement possédées et confirmer les fournisseurs. Pas de découverte par dictionnaire de sélecteurs ni de données TXT publiées.
- `nuclei` : HTTP borné, résultats minimisés; les alias épinglés et IP
  directes nécessitent `confirm_wan=true` après vérification de la propriété.
- `network` : TCP sur ports sélectionnés uniquement; confirmer le WAN,
  sinon le résultat ports est NOT_RUN_OR_INCOMPLETE; les observations
  TLS de base et HEAD peuvent rester utiles.
- `tls` : testssl.sh sur noms HTTPS publics connus, protocole, ciphers,
  préférences, certificat et forward secrecy. Pin de la branche stable 3.2
  au commit adf4dd45ed5a1a0e29097b747cbfc43d7b193821 ; mise à jour revue.
  Le JSON public ne conserve que IDs/sévérités, pas les données brutes.
- `all` : déclenchement manuel groupé; pas un gate de chaque PR.

Conserver Nmap XML, rapports TLS et Nuclei complets dans un coffre local
chiffré quand une analyse détaillée est nécessaire. Pour un certificat
non validé, distinguer expiration, SAN/hostname, chaîne, timeout et
frontend CDN/origine. Comparer SSL Labs (soumission manuelle uniquement,
désactiver la publication du résultat), SSLyze et testssl; SSLCheck n'est
pas configuré sans identification de l'outil exact. La note A/A+ n'est
pas une preuve de conformité FIPS. Ne pas scanner l'origine d'un CDN
en déduisant une IP mutualisée d'une réponse DNS.

### Double perspective — TrueNAS LAN vs Amass actif extérieur

- **Depuis TrueNAS** : `run-ctem-amass-truenas.sh --run` interroge
  les domaines déclarés et historise les relations d'actifs dans le
  PostgreSQL commun `assetdb`. La résolution peut refléter le split DNS
  LAN ; ce constat **ne prouve pas** l'exposition publique.
- **Depuis GitHub Actions** : `External attack surface (homelab)`,
  `workflow_dispatch`, profil `discovery-active`,
  `confirm_active_discovery=true`. L'énumération Amass est **active**,
  `-rigid -p 80,443`, sans bruteforce et sans accès PostgreSQL
  TrueNAS. La base Amass externe est éphémère ; seuls les **compteurs**
  et l'horodatage, mode, périmètre, `vantage=external-github-hosted`
  et `catalogRevision` vont dans l'artifact
  `public-amass-summary-<run_id>` (rétention 7 jours). Le profil
  `discovery` reste passif et `all` ne lance pas d'actif par défaut.
- Comparer les **comptes** entre les deux observateurs, avec prudence :
  les environnements DNS, délais d'exécution et périmètres évoluent.
  Le dédoublonnage **nominatif** entre observations exige un transfert
  chiffré vers TrueNAS (à faire) : les noms externes ne sont pas publiés.
  Ni GitHub Actions ni les runners ne doivent accéder à `assetdb`
  en direct. Les fournisseurs CDN doivent autoriser la reconnaissance
  active sur leurs points de présence.

### Visualisation privée des actifs Amass

Le runner TrueNAS produit après scan **achevé** :

- `summary-<UTC>.json` et `summary-latest.json` : statut, agrégats
  par domaine, catégories de réconciliation, révision Backstage et vantage ;
- `candidates-<UTC>.json` : FQDN, statut, correspondance exacte
  `entityRef` (privé 0600) ;
- **`ctem-amass-<UTC>.html`** : tableau de bord autonome (couverture,
  statut V2, liste filtrable par recherche navigateur), HTML échappé,
  sans CDN, script tiers, télémétrie ou serveur HTTP.
  Ce fichier **doit rester local** et inaccessible depuis Internet.

Le fichier HTML n'est créé que si le scan est complet, si le rapport
`candidates` correspond au `summary` et si la révision V2 est
valide. Son contenu n'est **pas une analyse de vulnérabilités**.
On peut ouvrir une **copie privée** dans un navigateur de workstation
de confiance après un transfert SSH/SFTP authentifié :
ne pas exposer le dossier via Traefik, Cloudflare Tunnel, n8n ou nginx.
Les graphiques Amass natifs `viz` nécessitent en outre l'installation
de la CLI v5 et son accès contrôlé au graphe PostgreSQL ; aucun portail
Amass web public n'est créé.

### TrueNAS — Amass actif + PostgreSQL commun + Cron existant (21/11/2026)

**Décision opérateur :** exécuter Amass **actif** sur TrueNAS (DNS, TLS,
HTTP limités aux ports 80/443) ; réutiliser la **même instance PostgreSQL**
TrueNAS, le **cron horaire existant** (`scripts/cron.sh`) et le collecteur
DefectDojo existant. Aucun nouvel App Postgres/Neo4j, aucune interface WAN,
aucun `git clone` upstream sur l'appliance. Le projet officiel
[`amass-docker-compose`](https://github.com/owasp-amass/amass-docker-compose)
fournit une stack multi-services ; elle n'est pas installée telle quelle ici.

- Identités : `assetdb` (une **nouvelle base au sein du serveur PostgreSQL
  existant**, pas une seconde instance) et rôle strict `amass`. Extension
  `pg_trgm` uniquement dans cette base ; état applicatif Amass persistant.
- Sortie opérationnelle : `/mnt/cpool/ctem/amass/reports` (répertoire root 0700,
  `candidates-<UTC>.json` privé 0600, `summary-<UTC>.json` et
  `summary-latest.json`, eux aussi privés) ; table
  `assetdb.ctem.scan_reports` pour reçus JSON **expurgés**, SHA-256 et révision
  V2, sans aucun hostname découvert.
- Publication : le cron horaire **envoie déjà un compte rendu par e-mail**
  à l'opérateur ; pour CTEM, uniquement `status`, compteur agrégé et erreur.
  Les détails sont consultables **localement**, jamais dans GitHub Actions,
  FastAPI public, n8n webhook public ni DefectDojo sans triage.
- Active boundary : domaines explicitement revus dans
  `config/security/public-mail-domains.json` ; `-active -rigid -p 80,443`,
  sans brute force, altération, plages IP, scanning WAN direct. **Amass actif
  peut contacter des infrastructures CDN/tiers** derrière un hostname :
  valider les autorisations et règles du fournisseur avant lancement. Le
  réseau Docker bridge n'est pas une politique d'egress.
- Secret PostgreSQL `root:root 0600` hors dépôt, jamais en argument CLI :
  `/mnt/cpool/secrets/runtime/ctem-amass/.env.secrets` avec
  `AMASS_DB_USER=amass`, `AMASS_DB_NAME=assetdb`,
  `AMASS_DB_HOST=172.17.0.24`, `AMASS_DB_PASSWORD=<secret>`.
  Il faut préalablement vérifier le SAN de la CA PostgreSQL pour
  `sslmode=verify-full` (CA :
  `/mnt/cpool/secrets/runtime/postgres/tls/ca.crt`). Aucune valeur
  réelle de secret ne figure dans ce runbook.

Procédure après fusion, checkout propre et provisioning du secret via
Vaultwarden (pas d'installation `apt` sur TrueNAS) :

```bash
cd /mnt/cpool/compose/nabla-compose
sudo install -d -o root -g root -m 0700 /mnt/cpool/ctem/amass \
  /mnt/cpool/ctem/amass/bin /mnt/cpool/ctem/amass/reports

# Le binaire v5.1.3 est vérifié par SHA-256. Son installateur l'exécute
# brièvement sur l'hôte ; variante stricte : préparer dans une VM amd64.
sudo bash scripts/security/install-pinned-amass.sh \
  /mnt/cpool/ctem/amass/bin/amass
sudo docker pull python:3.13-slim

# Vérifier d'abord le serveur Postgres existant (aucune mutation)
sudo bash scripts/truenas/bootstrap-ctem-amass-db.sh --check
# Muter uniquement le rôle/base Amass après revue et secret 0600
sudo env CTEM_AMASS_DB_APPROVED=YES \
  bash scripts/truenas/bootstrap-ctem-amass-db.sh --apply

sudo docker compose -f config/security/ctem/amass-job.compose.yml \
  --profile manual config --quiet
bash scripts/security/run-ctem-amass-truenas.sh --check

# PREMIER SMOKE actif approuvé ; sortie nominative jamais dans les logs
sudo env CTEM_AMASS_ACTIVE_APPROVED=YES CTEM_REPORT_STORE_APPROVED=YES \
  bash scripts/security/run-ctem-amass-truenas.sh --run

# Preuves : aucun candidat n'est imprimé
sudo ls -l /mnt/cpool/ctem/amass/reports/
sudo jq '{scan_mode,status,counts,catalogReconciliation}' \
  /mnt/cpool/ctem/amass/reports/summary-latest.json
```

**Cron intégré** : le job TrueNAS horaire existant (ID 6 dans le dernier
relevé documenté, à revérifier) continue d'appeler `scripts/cron.sh`.
Aucun second `cronjob.create`. La fonction `run_weekly_ctem_amass`
s'exécute uniquement **dimanche à 05:00** heure de l'appliance, si le
checkout `master` a été synchronisé et si
`NABLA_CRON_CTEM_AMASS_ENABLED=true`. Elle reste **opt-in** : pour
activer, ajouter cette variable à la tâche Cron horaire déjà enregistrée,
après un smoke concluant, et vérifier via `midclt call cronjob.query`.
La commande lance `sudo -n` ; les permissions sudoers réelles doivent
autoriser ce chemin précis, sinon `NOT_RUN` avec erreur explicite.
Le verrou `flock` empêche les chevauchements. Les résumés sont persistés
dans PostgreSQL (approval d'écriture bornée à ce flux) et le mail Cron.
Ne pas transformer l'absence de relevé en statut DOWN.

**Résultats externes/checkdmarc** : le workflow GitHub
`external-attack-surface.yml` utilise `checkdmarc==6.0.3`,
`-f json` pour le JSON natif temporaire (SPF, DMARC, MX, TLS-RPT,
MTA-STS, DNSSEC), puis `run-public-mail-deep.py` construit
`public-mail-deep.json`, uniquement les validations et politiques
autorisées. Cet artifact est conservé **7 jours** dans GitHub Actions.

**Nouveau collecteur GitHub App (CODED, non déployé)** :
`scripts/security/pull-ctem-mail-artifact.py` utilise l'installation
GitHub App déjà utilisée pour les imports DefectDojo, en permission
`Actions:read` sur `nabla-compose`. Il sélectionne **uniquement la
dernière** run `master` réussie du workflow
`external-attack-surface.yml` (schedule ou workflow_dispatch),
strictement âgée de 7 jours au maximum. Une run plus récente en échec
empêche de rejouer un succès ancien. Le fichier ZIP doit contenir
**exactement** `public-mail-deep.json` ; son contenu est vérifié avec
le même validateur de portée et de minimisation que l'insertion PostgreSQL.
Aucun token GitHub App n'est transmis au stockage externe de l'artifact.
`/mnt/cpool/ctem/amass/reports/mail/` conserve le JSON brut *déjà
minimisé* en `root:root 0600`, dans un sous-répertoire 0700.
La base PostgreSQL partagée reçoit le reçu expurgé
`assetdb.ctem.scan_reports`, idempotent par SHA-256.

```bash
# Aucun réseau, token ou écriture en --check
python3 scripts/security/pull-ctem-mail-artifact.py --check

# Pull + vérification du dernier artifact autorisé, sans mutation PostgreSQL
sudo env CTEM_MAIL_PULL_APPROVED=YES \
  python3 scripts/security/pull-ctem-mail-artifact.py --pull

# Pull + dépôt privé + UPSERT dans PostgreSQL partagé
sudo env CTEM_MAIL_PULL_APPROVED=YES CTEM_REPORT_STORE_APPROVED=YES \
  python3 scripts/security/pull-ctem-mail-artifact.py --store
```

Le cron horaire **déjà existant** déclenche ce collecteur seulement le
**lundi à 08:00**, si `NABLA_CRON_CTEM_MAIL_ENABLED=true` est activé
dans sa propre configuration, après vérification du secret GitHub App,
des ACL root et du connecteur SQL. Le fichier GitHub reste soumis à
sa rétention de 7 jours ; la copie privée et le reçu PostgreSQL
persistent indépendamment. Le pipeline de collecte ne crée aucun
DefectDojo Test, ne réimporte aucun scan et ne publie rien sur le WAN.

En secours, un import interne manuel d'un fichier déjà récupéré est
préparé par :

```bash
python3 scripts/security/store-ctem-summary.py \
  --kind checkdmarc --input /chemin-prive/public-mail-deep.json --check
sudo env CTEM_REPORT_STORE_APPROVED=YES \
  python3 scripts/security/store-ctem-summary.py \
  --kind checkdmarc --input /chemin-prive/public-mail-deep.json --apply
```

Le validateur rejette les champs DNS non minimisés ; les rapports complets
ne sont **pas** téléversés vers un dépôt public. La récupération GitHub
App et son insertion PostgreSQL sont désormais **CODED**, mais leur
réception TrueNAS, le dernier artifact réel et le déclenchement Cron
restent **NOT_RUN**. L'intégration éventuelle à l'outbox de notifications
FastAPI/Slack est un travail distinct, non nécessaire à la persistance.

**DefectDojo** : il n'existe pas de parser `checkdmarc` natif prouvé dans
notre configuration actuelle. Une revue explicite du résultat expurgé
permet de préparer des *findings* SPF/DMARC via le format
`Generic Findings Import` (produit logique `ctem-mail`, engagement
privé **à identifier**, IDs de déduplication stables, `verified=false`).
Ce n'est ni une importation de tout l'inventaire Amass ni un import
automatique des rapports non concluants :

```bash
python3 scripts/security/project-ctem-mail-findings.py \
  --input /chemin-prive/public-mail-deep.json \
  --output /chemin-prive/ctem-mail-findings.json --reviewed

DEFECTDOJO_SERVICE_ID=ctem-mail \
DEFECTDOJO_SCAN_TYPE='Generic Findings Import' \
DEFECTDOJO_ENGAGEMENT_ID=<identifiant-existant> \
  bash scripts/security/import-scan-defectdojo.sh \
  --check /chemin-prive/ctem-mail-findings.json
# --apply uniquement après validation parser, RBAC, token et déduplication.
```

Pour les résultats **Nuclei**, le parser DefectDojo natif `Nuclei Scan`
est disponible, mais l'allowlist et les preuves ont leurs contraintes
propres. Les noms Amass et les échecs d'exécution restent des **observations**
Backstage/CTEM, et non des Findings DefectDojo.

**Statut** : CODED, CI ciblée à vérifier, installation TrueNAS/PG,
premier scan actif, collecte du rapport GitHub, import DefectDojo et
contrôles WAN : **NOT_RUN**.

### Amass — inventaire passif, pas un scanner de vulnérabilités

Le profil manuel `discovery` utilise Amass v5.1.3 (archive Linux amd64
vérifiée par SHA-256 publié dans la release). Le moteur v5 utilise
127.0.0.1:4000 : ne pas le lancer sur la workstation LiteLLM, ni partager
le réseau hôte TrueNAS. Le runner GitHub éphémère ou une VM dédiée suffit.
Aucun port entrant, aucun secret fournisseur, aucune connexion à Neo4j
Security. Le profil GitHub passif est limité aux apices du fichier
`config/security/public-mail-domains.json` (20 domaines déclarés au 21/11, à réviser avant active);
`-rigid` interdit d'élargir le scope, sans brute force ni mode actif.
Le job est borné; une interruption ou un export vide reste INCOMPLETE.

Pour récupérer les noms, exécuter sur une **VM de confiance dédiée** :

```bash
umask 077
mkdir -p "$HOME/ctem-private"
bash scripts/security/install-pinned-amass.sh "$HOME/ctem-private/amass"
python3 scripts/security/run-amass-inventory.py \
  --amass "$HOME/ctem-private/amass" \
  --output "$HOME/ctem-private/amass-summary.json" \
  --private-output "$HOME/ctem-private/amass-candidates.json"
```

Utiliser des noms de rapports datés pour les runs suivants (écriture
exclusive). GitHub ne reçoit que compteurs, version, scope et statut;
les candidats détaillés restent dans le coffre de la VM. Comparer chaque
nom aux zones DNS Cloudflare réellement contrôlées puis à Backstage.
Ni port scan de l'IP résolue d'un CDN, ni extension automatique de la
liste de cibles, ni mutation de catalogue. Accepter le premier run manuel
avant d'ajouter une cadence hebdomadaire et un transfert privé.

#### Préflight de conformité déclarative (sans Amass)

Avant un scan ou pour un contrôle PR hors LAN :

```bash
python3 -m unittest tests.test_ctem_catalog_policy -v
python3 scripts/security/audit-ctem-catalog-policy.py
# Option : rapport public agrégé, sans nom, fichier créé exclusivement
python3 scripts/security/audit-ctem-catalog-policy.py --output /tmp/ctem-policy-counts.json
# VM de confiance uniquement : détails privés 0600
# python3 scripts/security/audit-ctem-catalog-policy.py --private-output /chemin-prive/ctem-conflicts.json
```

Exit code `0` : **aucune contradiction LAN-only dans le périmètre déclaré**, pas une attestation d'absence de route WAN ; `3` : conflit déclaratif ou catalogue/scope invalide. Ce contrôle appelle uniquement la jointure V2 exacte de `run-amass-inventory.py`, sans démarrer Amass, DNS ou HTTP. Le JSON public ne contient ni hostname, ni `entityRef`, ni valeur de secret. Le rapport nominatif est refusé dans GitHub Actions. Les scripts `--output` refusent d'écraser les fichiers existants, choisir un nom neuf pour chaque exécution.

À la révision observée le 21/11, `ollama-gpu.albandrieu.com` est toujours porté par une intention publique dans le généré V2, contraire à `LAN_ONLY_NAMES`. Cela impose une correction du descripteur **source** et une régénération coordonnée, puis une preuve externe négative : ce n'est pas une démonstration de route effectivement ouverte. Ne pas rendre ce contrôle bloquant dans la CI tant que l'écart historique n'est pas corrigé, puis l'ajouter au quality gate.

#### Rapprochement avec Backstage V2

Le job Amass joint les noms découverts **en mémoire** aux hostnames exacts de
`catalog/generated/entities.json` (`x-nabla.exposure.hostnames`, `entityRef`,
`visibility`, `access.required`, et annotation `github.com/project-slug`).
Aucune expansion de wildcard, correspondance par préfixe ou déduction depuis
le nom du service. Un projet GitHub non renseigné reste inconnu ; le slug
déclaré peut être le dépôt de déploiement et non le code de l'application.

Le JSON public contient `catalogRevision`, compteurs par classification et
nombre de conflits LAN-only, jamais les noms candidats, les références
d'entité ou le graphe. L'export privé ajoute les correspondances et leur
intention (pas de backend, token ou corps HTTP). Une correspondance ambiguë,
un nom absent, un hostname LAN-only ou une intention non publique nécessite
une revue ; la découverte passive seule ne prouve pas une exposition.
La politique LAN-only réutilise `LAN_ONLY_NAMES` du contrôle HEAD existant,
et signale les déclarations publiques contradictoires même si Amass ne les
retrouve pas. Un catalogue invalide ou une découverte incomplète ne permet
pas de conclure à zéro écart. Aucun élargissement du scope ni import automatique.

La réception du catalogue reste distincte : régénérer les artefacts V2 à
partir des sources après les changements Ollama, vérifier leur cohérence
de révision et compléter les annotations GitHub manquantes à la source
lorsque l'attribution est établie. Ne pas modifier le JSON généré à la main.

**DefectDojo :** ne pas importer les noms Amass comme vulnérabilités.
Une exposition inattendue doit être vérifiée et triée, puis un finding
qualifié issu de Nuclei ou d'un contrôle d'exposition validé peut rejoindre
un Test stable du produit CTEM via le collecteur privé
`scripts/security/import-scan-defectdojo.sh`.
Le parseur, le mapping de produit/engagement et la déduplication doivent
être confirmés avant d'élargir l'allowlist. La policy de Compose n'autorise
pas encore Nuclei pour ce producteur; aucune exception globale ni import
automatique n'est ajouté. Préserver `close_old_findings=false` tant que
la couverture est partielle. L'inventaire et les écarts non confirmés
restent des observations Backstage/CTEM, pas des findings DefectDojo.

La présence de `/wp-login.php` et `/wp-admin/` dans les contrôles HEAD
est une détection de résidu : WordPress a été retiré du dépôt le 5/11
([historique](2026-11-04-probe-remediation.md)). Aucun WordPress actif
n'est présumé et aucune réinstallation n'est prévue.

### Messagerie

`config/security/public-mail-domains.json` recense désormais 20 domaines
issus du catalogue de zones, avec `mail_use` différencié (`sending`,
`unverified`, `no-mail`) et des sélecteurs DKIM renseignés quand connus.
Ce périmètre est une déclaration d'autorité, pas une vérification dynamique
de leur exposition ni un droit de sonder des IP CDN non détenues. Ajouter domaines d'envoi, domaines
de stationnement et sous-domaines de messagerie explicitement.
Vérifier les sélecteurs DKIM depuis chaque fournisseur, pas par liste
devinée. Pour contrôle approfondi, sur runner extérieur de confiance :

```bash
umask 077
python3 -m venv /tmp/ctem-mail
/tmp/ctem-mail/bin/pip install 'checkdmarc==6.0.3'
/tmp/ctem-mail/bin/checkdmarc albandrieu.com albanandrieu.com bababou.com \
  --skip-tls -f json -o /tmp/ctem-mail-private.json
```

Le rapport checkdmarc (SPF lookup limit, DMARC, MX/STARTTLS, MTA-STS,
TLS-RPT, DNSSEC selon version) peut comporter TXT et adresses : ne pas
publier son JSON brut. Nuclei DNS `spf-limit-lookup` et les détections SPF/DMARC sont des signaux
complémentaires, pas un substitut au validateur ni à DKIM. Collecter
`rua` avec parsedmarc dans un premier temps, puis définir p/sp=reject
après contrôle d'alignement. Aucun changement DNS mail automatique.

### LiteLLM et Ollama — LAN uniquement

Retrait des routes Cloudflare Ollama et Ollama GPU ; le bind TrueNAS
est limité à l'adresse LAN déclarée. Vérifier cette adresse après
changement de routeur. Examiner les routes, NAT, UPnP, Cloudflare,
workstation et règles Docker/Traefik; un bind LAN n'est pas une preuve
d'absence de redirection WAN. LiteLLM était déjà déclaré LAN-only.

Appliquer via le circuit Terraform Cloudflare existant, **plan avant apply**.
Si les deux CNAME sont déjà dans l'état `tunnel[...]`, supprimer les routes
doit produire leur destruction dans le plan. Sinon recueillir les IDs live
et suivre le workflow existant adopt/retire dans
[README Cloudflare](../../terraform/cloudflare/README.md). Ne pas importer
une deuxième fois un ID déjà dans l'état. Vérifier aussi les éventuelles
routes workstation indépendantes. Après apply, refaire les contrôles
HEAD publics; LAN et dépendances locales doivent continuer à fonctionner.
Régénérer les sorties Backstage/consommateurs depuis les sources après
coordination avec la PR #416; ne pas publier d'artefacts désynchronisés.

## 2. Cartography et Neo4j Security

Réutiliser `apps/neo4j/compose.yml` et `apps/cartography/compose.yml`;
Neo4j doit être authentifié, dataset persistant, uniquement LAN/intranet.
Les deux services étaient déclarés planned. Déployer Neo4j par le circuit
TrueNAS Apps versionné existant après contrôle du secret, des datasets,
de la mémoire et des ports. Vérifier que Neo4j répond et valider la connexion
avant de lancer la première ingestion.

Cartography est un **job one-shot**, pas un daemon à démarrer sans provider.
Une fois l'identité fournisseur dédiée lecture seule et les variables
`NEO4J_PASSWORD` / `GITHUB_CONFIG` matérialisées dans son fichier runtime
privé, utiliser depuis l'hôte autorisé :

```bash
cd /mnt/cpool/compose/nabla-compose
sudo docker compose -f apps/cartography/compose.yml --profile manual config --quiet
sudo docker compose -f apps/cartography/compose.yml --profile manual run --rm cartography \
  --selected-modules github --neo4j-uri bolt://neo4j-security:7687 \
  --neo4j-user neo4j --neo4j-password-env-var NEO4J_PASSWORD \
  --github-config-env-var GITHUB_CONFIG
```

Confirmer les options avec `--help` sur l'image réelle et l'identité GitHub
dédiée. Ne pas lancer tous les modules ni monter un kubeconfig admin.
Accepter seulement après une synchronisation terminée, graphe non vide,
scope vérifié et absence de secret dans les logs. Ajouter la cadence
ensuite; paramètres de GitHub selon [Cartography CLI](https://docs.cartography.dev/usage/cli.html).

## 3. Prowler

Ancien `compose.prowler.yml` : ne pas déployer ses ports API/UI/MCP.
La nouvelle configuration
`config/security/ctem/prowler.compose.yml` est un job manuel CLI.
Créer le dataset rapports dédié, vérifier propriétaire/permissions et
matérialiser les seules variables nécessaires au tenant pilote dans Vaultwarden.
Pas de credentiels administrateur et pas de socket Docker dans le conteneur.
Image CLI tag 5.50.0 vérifié sur Docker Hub; verrouiller le digest après pull.

```bash
sudo docker compose -f config/security/ctem/prowler.compose.yml --profile manual config --quiet
sudo docker compose -f config/security/ctem/prowler.compose.yml --profile manual run --rm prowler azure --help
sudo docker compose -f config/security/ctem/prowler.compose.yml --profile manual run --rm prowler azure -M json-ocsf -o /output
```

Exécuter sur tenant explicitement autorisé, droits minimaux; M365/Entra
et Kubernetes ont leurs identités, permissions et scopes distincts.
Ne pas présumer d'une couverture équivalente ni déployer Server Prowler
avant mesure RAM/stockage. Parser DefectDojo et mapping OCSF à accepter.

## 4. OASM

Le dépôt officiel `oasm-platform/oasm-docker` au commit
`56dc2c657743200363b65cf2168ae4f91d0a953c` utilise un worker avec socket
Docker, PostgreSQL 18, Redis, RustFS, API, console, migration et GeoIP.
Lancer exclusivement sur une **VM dédiée isolée**, disposant de son
moteur Docker propre, egress filtré et sans accès aux secrets/volumes
TrueNAS. Pas de socket TrueNAS ni de montage kubeconfig. Le POC utilise
ses dépendances isolées à cause de cette frontière de confiance; réévaluer
la réutilisation des services seulement après preuve d'isolation.
Le Compose contient des versions flottantes et des secrets par défaut,
et une clé OASM Cloud obligatoire : il faut valider le fonctionnement sans
export des données privées et verrouiller tous les digests avant lancement.
Ne pas exécuter `make`/quick-start tel quel.

`config/security/ctem/oasm-isolated.override.yml` limite la console et
l'API à loopback. Vérifier la version Compose et toutes les autres
publications, générer des secrets uniques dans le coffre, vérifier que
`docker compose config --quiet` passe sans afficher les valeurs,
puis démarrer sur la VM seulement. Prévoir CPU/RAM/stockage dédiés.
Ne pas déployer un service TrueNAS non revu. L'acceptation doit prouver
les limites de scan, les permissions et une exportation minimisée
vers l'inventaire/DefectDojo. Aucun OASM cloud API key provisionné.

## 5. Critères de clôture

Les comptes d'actifs, expositions divergence, findings actifs par gravité,
freshness, durée de résolution, couverture par type de scanner et échecs
de jobs doivent rester séparés. Implémenter l'adaptation FastAPI dans son
dépôt après versionnement du contrat et contrôles de visibilité. Importer
uniquement les formats compatibles via le collecteur privé DefectDojo
existant; ne pas élargir ses allowlists sans vérifier les parsers et la
déduplication. Backstage garde l'intention; OASM et Cartography enrichissent
avec observations, jamais avec une mutation automatique du catalogue.

Prochaines preuves: quality gate, plan Cloudflare, catalogue généré,
récupération des artefacts GitHub, Nmap/TLS/DMARC réels, sync Cartography,
scan Prowler et POC OASM sur infrastructure dédiée. Statut NOT_RUN tant
que ces observations ne sont pas enregistrées.
