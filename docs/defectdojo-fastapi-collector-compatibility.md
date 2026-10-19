# fastapi-sample → collecteur GitHub DefectDojo : contrat isolé

**Préparation non déployée.** Le collecteur actuel de cette PR interroge
uniquement `AlbanAndrieu/nabla-site-alban`. Il faut conserver son
GitHub App, son cron, sa liste de workflows et son Engagement inchangés.

La PR [fastapi-sample #353](https://github.com/AlbanAndrieu/fastapi-sample/pull/353)
ajoute un export Trivy minimal hors réseau :
`scripts/security/export_defectdojo_collector_trivy.py`.
Il exige un reçu `master/complete`, puis produit deux fichiers
(`trivy-fastapi-master.json`, `trivy-fastapi-master.manifest.json`)
dans un répertoire privé, **sans publier sur GitHub**.

L'export est limité aux vulnérabilités HIGH/CRITICAL de `uv.lock`,
avec identifiant, nom/version du paquet, sévérité et version corrigée
optionnelle. Aucun secret, rapport brut, licence, SBOM, PII, DAST,
capture HTTP ou URL interne dans l'artefact GitHub candidat.

## Raccordement requis ultérieurement

1. Source distincte `AlbanAndrieu/fastapi-sample`, installation
   GitHub App `Actions:read` uniquement sur ce dépôt. Jamais élargir
   implicitement les jetons du collecteur Site Alban.
2. Workflow `DefectDojo Trivy Handoff (FastAPI)` à créer, manuel au
   démarrage, sur master immuable. Artefact nommé
   `defectdojo-fastapi-trivy-<sha40>`, ZIP avec **uniquement** les deux
   fichiers ci-dessus.
3. Contrôler run `master` réussi, workflow exact, SHA du run égal
   à `revision` du manifeste, checksum `artifact_sha256`, archive
   bornée, aucune entrée ZIP supplémentaire ou symlink, et parser
   `Trivy Scan` autorisé dans la policy.
4. Stage limité à `/mnt/cpool/defectdojo/imports/fastapi-sample`,
   fichiers root 0600 ; `--pull` initialement, import manuel par
   identité DefectDojo dédiée à l'Engagement du même projet.
5. Ne pas déclarer PASS quand `policy_status=needs_review` :
   les CRITICAL bloquent la gate sécurité même si le scan est terminé.
   Un ZIP reçu ne prouve pas l'ingestion Celery ni la déduplication.

La politique `config/security/defectdojo-allowed-imports.json` autorise
déjà `Trivy Scan` pour `fastapi-sample`, mais n'autorise pas
automatiquement ses rapports SBOM, ZAP ou Nuclei. Le validateur commun
refuse maintenant tout bloc Trivy `Secrets`, même issu d'un producteur
au préalable filtré.

**Sans centralisation des rapports** : chaque dépôt garde ses scans,
ses credentials et son engagement ; les rapports complets de
`fastapi-sample` restent importables directement dans le LAN par
son propre script avec HTTPS/SNI vérifié. Aucun accès public à
`defectdojo.int.albandrieu.com` n'est requis ni créé ici.

Tests d'acceptation encore nécessaires : GitHub App limitée au dépôt,
archive exacte, test du parser sur l'édition installée, autorisation
négative sur un autre Engagement, import Celery complet et vérification
WAN négative. Aucun cron activé ni rapport transféré.
