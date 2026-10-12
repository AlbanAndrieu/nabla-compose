# DefectDojo — ingestion privée de scans sans exposition Internet

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
  → http://172.17.0.24:31085 → DefectDojo existant (interne)
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
