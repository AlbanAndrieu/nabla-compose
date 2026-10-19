# DefectDojo — ingestion privée de scans sans exposition Internet

## Ingestion sélective Site Alban depuis GitHub Actions (`master`)

**Préparé, non activé** — suivi [Site Alban #236](https://github.com/AlbanAndrieu/nabla-site-alban/pull/236)
et [Compose #263](https://github.com/AlbanAndrieu/nabla-compose/pull/263).

Un runner GitHub-hosted ne doit pas appeler
`defectdojo.int.albandrieu.com` directement et n'a pas de token
d'import. Le collecteur `scripts/security/pull-site-alban-security-report.py`
tourne côté TrueNAS : il télécharge uniquement les artefacts de
**workflows nommés précisément**, dont la run a réussi sur `master`.
L'identité GitHub ne doit avoir que **Actions:read** sur Site Alban, sans
droit de commit ni secret DefectDojo.

**Modes (exemples sans effet runtime)** :

```bash
python3 scripts/security/pull-site-alban-security-report.py --kind trivy --run-id 123
python3 scripts/security/pull-site-alban-security-report.py --kind nuclei --run-id 123
python3 scripts/security/pull-site-alban-security-report.py --kind zap --run-id 123
```

Le mode par défaut fait un **contrôle de configuration sans réseau ni
lecture de jeton**. Une fois l'accès au réseau TrueNAS et au dépôt GitHub
explicitement autorisé, ajouter `--pull` prépare un fichier filtré dans
`/mnt/cpool/defectdojo/imports/site-alban` sous permissions root-only :

- **Trivy** : seul le JSON de vulnérabilités `HIGH/CRITICAL` est conservé.
  Les licences, misconfigurations et le SBOM sont exclus de l'import
  automatique.
- **Nuclei** : seules les lignes `high/critical`, ciblant les hôtes
  HTTPS de Site Alban déjà autorisés par le validateur, sont préparées.
- **ZAP production** : seules les alertes `riskcode=3` sont préparées.
  Le parser installé doit s'appeler **`Zed Attack Proxy`**.
- Aucun CodeQL, Semgrep, GitGuardian, BetterLeaks, artifact PR,
  événement non-`master`, run échouée ou archive expirée ne doit
  être accepté par ce parcours.

Le collecteur **n'importe jamais** dans DefectDojo. Une personne
autorisée vérifie le fichier, le scanner, le produit/engagement,
puis passe séparément à
`scripts/security/import-scan-defectdojo.sh --check`.
L'import `--apply` exige encore root, approbation explicite et jeton
dédié dans le coffre. Le `--check` de l'importeur valide la policy
`config/security/defectdojo-allowed-imports.json`.

**Confidentialité** : les artifacts de scans attachés à un dépôt GitHub
public peuvent être consultables par d'autres acteurs autorisés sur
le dépôt; ne pas y stocker de captures HTTP authentifiées, tokens,
headers, captures de chemins internes ou résultats confidentiels.
Pour les rapports complets DAST, faire les scans et leur import
directement dans le homelab, ou chiffrer les artefacts avant upload et
ne garder la clé de déchiffrement que sur TrueNAS. Le collecteur
actuel ne déchiffre pas encore de tels rapports; **ne pas lui attribuer
une conformité de confidentialité non prouvée**.

**Règle de clôture** : `GH_TOKEN` lecture seule depuis le fichier privé,
provenance workflow/master/SHA vérifiée, taille plafonnée, ZIP contrôlé,
fichier root-only, parser DefectDojo vérifié, import/reimport testé dans
un engagement dédié, déduplication et absence de fuite confirmées,
puis seulement planification éventuelle sous contrôle et alertes.


> **Préparation uniquement.** Le service DefectDojo est déclaré dans
> `apps/defectdojo/compose.yml` sur `172.17.0.24:31085`. Ce port est
> une liaison LAN/host TrueNAS, **pas** un endpoint Internet nécessaire
> à l'import ; vérifier son ACL réelle. Aucun tunnel, DNS ou API publique
> n'est créé par ce runbook.

## Architecture

```text
Build/CI interne / scanner Syft + Trivy (sans socket Docker brut)
  | 1. SBOM CycloneDX/SPDX (inventaire, non vulnérabilité)
  | 2. Rapport SCA Trivy/Grype (findings candidats)
  v
Job importateur à privilèges minimaux sur TrueNAS / réseau intranet
  POST /api/v2/reimport-scan/ (Authorization: Token ...)
  → http://172.17.0.24:31085 (TrueNAS host) → DefectDojo existant
  → PostgreSQL/Redis internes
  ↛ Cloudflare Access / Tunnel / Internet / navigateur public
```

### Pourquoi cela ne nécessite pas DefectDojo public

L'API DefectDojo est une API HTTP disponible **dans le réseau privé**.
Le producteur de scans doit pouvoir joindre l'IP/port de DefectDojo
depuis ce même réseau. L'API n'a pas besoin d'être accessible à Vercel
ou GitHub Actions hébergés pour que TrueNAS ou un runner interne fasse
l'import. Les scans restent privés, tout comme l'UI et la base.

Si des runners GitHub hébergés doivent importer plus tard, les options
sont (par ordre de préférence) un runner **self-hosted isolé et protégé**
dans le homelab, un tunnel privé de sortie/overlay zero-trust à contrôle
fort, puis éventuellement l'hostname `defectdojo-ci` sous Cloudflare
Access réservé exclusivement aux identités de service. Ne jamais
ouvrir directement le port 31085 sur le WAN.

**Attention :** le port actuel du Compose est HTTP, non chiffré.
Limiter l'ingestion à l'hôte TrueNAS ou un réseau isolé ; pour traverser
le LAN ou un autre domaine de confiance, ajouter TLS interne avec
vérification du certificat et ACL. Le script préparé cible délibérément
l'origine interne existante, mais ce n'est pas une validation de son
état réseau ni de son chiffrement.

## API et secrets

La documentation officielle recommande le **réimport** :
`/api/v2/reimport-scan/` réutilise le Test compatible et limite les
doublons. L'import `/api/v2/import-scan/` crée plutôt des Tests nouveaux.
Avant d'utiliser `reimport-scan`, vérifier les noms des scanners et les
permissions dans l'OpenAPI de l'instance :
`http://172.17.0.24:31085/api/v2/oa3/swagger-ui/`.

Créer dans DefectDojo une identité *ingestion* spécifique avec droits
seulement sur le produit et l'engagement retenus. Garder une identité
distincte **lecture seule** pour le futur reporting CTID.

Placer le jeton dans
`/mnt/cpool/secrets/runtime/defectdojo/import-token`
en `root:root 0600`. Il est passé à curl par fichier de configuration
temporaire `0600` et jamais affiché. Le script ne journalise pas les
corps HTTP ni les contenus des rapports et refuse les fichiers >10 Mo.

### Préflight reproductible

```bash
cd /mnt/cpool/compose/nabla-compose
# Utiliser un rapport JSON déjà produit par Trivy sur un périmètre autorisé.
DEFECTDOJO_SERVICE_ID=postgresql \
DEFECTDOJO_ENGAGEMENT_ID=123 \
DEFECTDOJO_SCAN_TYPE='Trivy Scan' \
bash scripts/security/import-scan-defectdojo.sh --check /chemin/prive/rapport-trivy.json
```

L'ID `123` est un **exemple**, pas l'ID de ton DefectDojo. Les
variables doivent reprendre un engagement réel de l'instance. Le
préflight n'ouvre aucune connexion réseau et ne lit aucun jeton.

### Import explicite, après acceptation

```bash
sudo -E env DEFECTDOJO_IMPORT_APPROVED=YES \
  DEFECTDOJO_SERVICE_ID=postgresql \
  DEFECTDOJO_ENGAGEMENT_ID=<ID_REEL> \
  DEFECTDOJO_SCAN_TYPE='Trivy Scan' \
  bash scripts/security/import-scan-defectdojo.sh --apply /chemin/prive/rapport-trivy.json
```

Le script impose `auto_create_context=false`,
`close_old_findings=false`, `verified=false` et une identité de Test
stable par service/type de scan. **L'HTTP 200/201/202 indique réception,
pas forcément ingestion terminée** : vérifier l'état de traitement,
le nombre de findings, la déduplication et les erreurs de parser via
l'interface/API privée.

Une nomenclature Syft seule peut créer des entrées Info, mais ne
constitue pas un scan de vulnérabilités ; confirmer le parser compatible
(CycloneDX, Syft, Trivy ou Grype) avant import. L'API spécialisée
`sbom-import` pour Assets/Locations est une fonctionnalité décrite
dans DefectDojo Pro : ne pas la présumer sur OSS.

## Obligations de sécurité, tests et retour arrière

- Aucune publication publique brute de findings, de CVE de service
  identifiée, d'IP, de version installée, de clés, d'URLs internes.
- Ne pas lancer de scan actif agressif depuis GitHub Actions ; stocker
  scans, SBOM et archives dans un dataset privé avec TTL, ACL et backup.
- Ne jamais faire de `close_old_findings=true` ou
  `auto_create_context=true` sans validation explicite.
- Vérifier le compte/produit/engagement, le parser, la provenance image
  digest + purl/CPE + version, le mapping aux service IDs canoniques.
- Export CTID futur : agrégat minimal revu, daté, authentifié côté
  ingestion serveur. Aucun proxy public générique de l'API DefectDojo.
- Rollback : désactiver le job d'import, révoquer le token sans toucher
  aux données déjà ingérées ; traiter manuellement les doublons.
- Aucun scan réel ni token généré dans cette PR.

**Acceptation ultérieure** : preuve d'un scan SCA sur un service non
critique, import privé, vérification du statut final et déduplication,
mesures de visibilité nulle depuis Internet. Remettre l'automatisation
périodique après cette acceptance.

Sources :
- https://docs.defectdojo.com/automation/api/api-v2-docs/
- https://docs.defectdojo.com/import_data/import_scan_files/api_pipeline_modelling/
- https://docs.defectdojo.com/supported_tools/parsers/


## Lien avec FreshRSS : réseau et segmentation

La publication RSS du site est **indépendante** du pipeline DefectDojo.
Les appels Google Reader passent par les seuls comptes FreshRSS publics ;
**aucune** donnée SBOM ni finding DefectDojo ne doit être placée dans
ces abonnements. Les jobs Syft/Trivy et l'importeur `reimport-scan`
restent dans le domaine interne TrueNAS/runner privé : un token d'ingestion
DefectDojo n'autorise **pas** le serveur Next.js, FreshRSS ou un agent MCP
à lire les résultats. L'authentification du futur reporting doit être
séparée (jeton read-only, minimisation, revue des exports) avant toute
mise en ligne.


### Contrat d'import effectif (18/10/2026) — TrueNAS LAN uniquement

Le script `scripts/security/import-scan-defectdojo.sh` pointe actuellement sur
`http://172.17.0.24:31085/api/v2/reimport-scan/`, conformément au bind
déclaré dans `apps/defectdojo/compose.yml`. Cela **remplace l'ancien
contrat loopback** du 12 octobre (qui n'est plus applicable à ce script).
Le script impose le checkout canonique sur TrueNAS, la présence effective de
`172.17.0.24` sur l'hôte, `root:root 0600` sur le token privé,
`curl --noproxy '*'`, zéro redirection et une confirmation explicite.
L'accès LAN HTTP reste une frontière de confiance à auditer : le contrat
n'implique **pas** que TLS externe, pfSense NAT ou ACL soient validés.

Cible plus stricte : importateur dédié sur réseau Docker privé, ou publication
locale loopback réelle et prouvée par `docker inspect` / `ss`, suivie
d'une modification atomique de Compose + importeur + tests. Ne pas substituer
127.0.0.1 tant que le socket n'y est pas réellement écouté. Un runner distant
ou Kubernetes exige un chemin privé avec TLS vérifié, identité dédiée et RBAC.

Le rapport `scan-repo-trivy.py` ne traite **que les fichiers versionnés au
commit HEAD** via une archive Git extraite avec filtre d'extraction sécurisé.
Les fichiers `.env` ignorés, documents privés et autres états non versionnés
ne sont pas scannés ni copiés dans l'artefact. Ce périmètre de SCA ne remplace
pas l'audit de configuration runtime, image OCI ou le SAST CodeQL.

## Contrat réel des artefacts Site Alban — réconciliation du 19 octobre 2026

Le collecteur est **préparé mais non activé** : aucune installation de la
GitHub App, aucun Cron ni import réel n'est prouvé par ces commits.

| Source (workflow `master`) | ZIP et fichier GitHub | Fichier dans l'inbox TrueNAS | Import |
| --- | --- | --- | --- |
| `Supply Chain Security (Trivy)` | `trivy-master-<sha>` / `trivy-security.json` | `site-alban-<run>-trivy.json` : uniquement CVE npm lockfile High/Critical | `Trivy Scan`, JSON |
| `Nuclei public DAST (Site Alban)` | `nuclei-public-<run>` / `nuclei-results/nuclei.jsonl` ; projection réduite à la source dans Site #236 | `site-alban-<run>-nuclei.json` : JSONL minimal, URL limitée à l'origine HTTPS | `Nuclei Scan`, JSONL |
| `Production DAST` | `zap-production-report` / `report_json.json` | `site-alban-<run>-zap.xml` : conversion locale privée **JSON → XML** avec seuls plugin ID, titre, sévérité 3 et origine HTTPS | `Zed Attack Proxy`, XML |

**Point de compatibilité important** : le parser OSS `Zed Attack Proxy`
accepte le rapport **XML** de ZAP, pas le JSON de `action-baseline`.
Le collecteur transforme ce JSON dans l'inbox privée et l'importeur envoie
`application/xml`. Ne pas changer `scan_type` pour masquer une erreur
de format. Sans test effectif de la version DefectDojo installée, ce
contrat n'est **pas** une preuve d'ingestion réussie.

Le poll recherche chaque workflow par **fichier identifié** et branche
`master` avec dix dernières exécutions sans filtre `status=success`.
La dernière exécution échouée, annulée ou incomplète ne doit **jamais**
laisser importer un succès plus ancien. Un run absent vaut `NOT_OBSERVED`,
pas `PASS`.

Les rapports minimisés excluent requêtes/réponses HTTP, cookies, tokens,
paramètres d'URL, détails de topologie, licences et SBOM. Trivy ne fournit
dans ce parcours que des vulnérabilités de `package-lock.json`. Aucun
rapport vide ou sans finding admissible ne doit être importé.

**Gate de confidentialité ZAP non levée** : l'action GitHub ZAP de Site
Alban téléverse actuellement son propre rapport brut. La conversion
dans TrueNAS ne rend **pas rétroactivement privé** cet artefact GitHub ;
celui-ci peut inclure des requêtes/authentifications de scan. Avant de
rendre ZAP automatique, remplacer ce dépôt brut par une sortie
pré-expurgée ou lancer ce scan dans l'environnement privé. Vérifier la
version du parser OSS sur l'instance et l'absence d'en-tête de bypass.
Ce point reste ouvert, sans changer la fréquence des scans.

