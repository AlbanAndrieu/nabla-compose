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

### TrueNAS — job Compose passif et ordonnanceur natif (21/11/2026)

Le projet officiel [`owasp-amass/amass-docker-compose`](https://github.com/owasp-amass/amass-docker-compose)
est une infrastructure **beta** avec `enum/subs/viz/assoc/track`, un moteur
Amass sur :4000 **dans son réseau Compose**, une base `assetdb`,
`postal`, `syslog` et Neo4j. Son Compose upstream publie par défaut
`55432:5432`, `7474:7474`, `7687:7687`, utilise des images
`latest`, des builds distants `#main` et des noms de conteneur génériques.
**Ne pas importer ni exécuter tel quel comme TrueNAS Custom App.**
Une installation de la stack complète demandera un clone Git épinglé,
le verrouillage des builds/images, des mots de passe hors Git, des volumes ZFS,
la suppression des ports publiés et des noms globaux, un audit
`docker compose config` et des tests de restauration. Cette variante est
un POC ultérieur, pas une dépendance de la découverte passive H05.

Pour le besoin CTEM actuel, le dépôt fournit à la place
`config/security/ctem/amass-job.compose.yml` : **job Docker Compose
éphémère**, sans App persistante ni port publié, sur réseau Docker isolé
du namespace de LiteLLM (port Amass :4000 uniquement dans ce conteneur).
Il réutilise **sans réimplémentation** `run-amass-inventory.py` et sa jointure
Backstage V2 ; la base `assetdb` ne tourne pas. Le conteneur ne reçoit
aucun socket Docker, aucun secret, ni écriture dans le checkout Git.
L'image Python doit être verrouillée par digest après validation du pull.
Un réseau bridge n'est **pas** une ACL de sortie LAN : la politique des
cibles, le caractère passif, la suppression des ports entrants et les ACL
réseau restent des contrôles distincts.

Sur **TrueNAS amd64**, créer d'abord le dataset ZFS `cpool/ctem/amass`
via l'UI TrueNAS si la rétention/snapshot ZFS dédiée est souhaitée ;
`install -d` crée uniquement les répertoires et **ne crée pas un dataset ZFS**.
Puis préparer les répertoires privés et le binaire, uniquement après
fusion/déploiement de ce commit, sans `apt` ni `pip` sur l'appliance :

```bash
cd /mnt/cpool/compose/nabla-compose
sudo install -d -o root -g root -m 0700 \
  /mnt/cpool/ctem/amass \
  /mnt/cpool/ctem/amass/bin \
  /mnt/cpool/ctem/amass/reports
# L'installateur existant vérifie l'archive officielle v5.1.3 par SHA-256.
# Il exécute -version sur l'hôte : pour isolation stricte, effectuer cette
# étape sur une VM amd64 de confiance et transférer le binaire contrôlé.
sudo bash scripts/security/install-pinned-amass.sh \
  /mnt/cpool/ctem/amass/bin/amass
sudo docker pull python:3.13-slim
sudo docker compose -f config/security/ctem/amass-job.compose.yml \
  --profile manual config --quiet
bash scripts/security/run-ctem-amass-truenas.sh --check
sudo python3 scripts/truenas/reconcile-ctem-amass-cron.py --check
```

Exécuter **une fois**, manuellement et sans élargissement du scope :

```bash
sudo bash scripts/security/run-ctem-amass-truenas.sh --run
sudo ls -l /mnt/cpool/ctem/amass/reports/
```

Le script emploie `flock` pour éviter le chevauchement, `--pull never` pour
éviter toute mise à jour implicite, et crée un fichier `summary-<UTC>.json`
(agrégats uniquement) ainsi qu'un fichier `candidates-<UTC>.json`
(permissions 0600, noms et associations, **strictement privé**).
Aucun détail n'est téléversé dans un artifact GitHub ni dans FastAPI public.
Chaque exécution possède des noms de fichiers distincts ; sans preuve
`OBSERVED_NOT_CERTIFIED`, résultat `INCOMPLETE` ou code non nul, conserver
le rapport et investiguer, ne pas le convertir en actif ou vulnérabilité.

Une fois ce smoke validé, enregistrer le job Cron natif **désactivé** :

```bash
sudo python3 scripts/truenas/reconcile-ctem-amass-cron.py --apply
sudo python3 scripts/truenas/reconcile-ctem-amass-cron.py --check-live
# Après revue explicite de la première sortie privée et des ressources :
sudo env CTEM_AMASS_CRON_APPROVED=YES \
  python3 scripts/truenas/reconcile-ctem-amass-cron.py --enable
# Arrêt de l'ordonnancement :
sudo python3 scripts/truenas/reconcile-ctem-amass-cron.py --disable
```

La cadence choisie est **dimanche 05:35 heure locale de l'appliance**, dans
une tâche distincte de `scripts/cron.sh` (horaire, Git sync / FastAPI).
Le statut attendu de ce nouveau Cron est **CODED / NOT_INSTALLED / DISABLED**.
N8n (déclaré actif via `apps/n8n/compose.yml`) peut être utilisé plus tard
pour notifier, créer un ticket ou faire approuver des findings, **pas** pour
exécuter à distance des commandes root ou accéder au socket Docker.
Ne pas exposer les rapports CTEM via ses webhooks publics ;
l'exception de politique Access pour le webhook n8n existe déjà et doit
rester bornée. Le fonctionnement effectif de n8n doit être confirmé par
`midclt call app.query` et non déduit du catalogue.

### Amass — inventaire passif, pas un scanner de vulnérabilités

Le profil manuel `discovery` utilise Amass v5.1.3 (archive Linux amd64
vérifiée par SHA-256 publié dans la release). Le moteur v5 utilise
127.0.0.1:4000 : ne pas le lancer sur la workstation LiteLLM, ni partager
le réseau hôte TrueNAS. Le runner GitHub éphémère ou une VM dédiée suffit.
Aucun port entrant, aucun secret fournisseur, aucune connexion à Neo4j
Security. La découverte passive est limitée aux apices du fichier
`config/security/public-mail-domains.json` (inventaire encore partiel);
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

`config/security/public-mail-domains.json` contient albandrieu.com,
albanandrieu.com, bababou.com. Tous sont encore `unverified`; la liste
n'atteste pas toutes les zones détenues. Ajouter domaines d'envoi, domaines
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
