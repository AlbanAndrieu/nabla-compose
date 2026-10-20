# DefectDojo — collecteur privé GitHub Actions sur TrueNAS

## Gate contractuel ZAP entre producteurs et collecteur — 19 octobre 2026

**Source de vérité :** Site Alban #236 produit désormais, dans sa branche PR,
`zap-production-report/report_json.json` à schéma réduit. Le collecteur #263
rejette **avant toute écriture privée** les anciens JSON ZAP bruts :
objet `site` seul, chaque site `@name` (origine HTTPS autorisée) et `alerts`,
chaque alerte HIGH seulement `pluginid`, `riskcode=3` et
`alert="ZAP passive rule <pluginid>"`. La conversion XML interne reste
nommée **`ZAP Scan`**, jamais un téléchargement/archivage de requêtes HTTP.
L'ancienne action `zaproxy/action-baseline` de Site Alban téléversait des
preuves brutes ; un filtrage **après** le téléchargement n'aurait pas protégé
l'artefact GitHub. Son remplacement côté producteur est **INCOMPLETE**
tant qu'aucune exécution de `master` avec le nouveau workflow n'est vérifiée.
Le workflow ZAP Bababou n'a pas encore été mis en conformité à la source :
son import doit rester **NOT_RUN / rejeté**, non contourné par une exception.

| Contrôle | État | Motif |
| --- | --- | --- |
| Contrat source Site Alban JSON minimal | **INCOMPLETE** | Correctif proposé en PR #236, aucune exécution sur master du nouveau workflow |
| Contrat collecteur JSON minimal → XML `ZAP Scan` | **INCOMPLETE** | Code durci dans PR #263 et tests adaptés, quality gate du nouveau HEAD non encore attestée |
| Ancien JSON brut, y compris Bababou | **FAIL** (rejet attendu) | Champs HTTP/instances/non canoniques interdits, pas de repli permissif |
| GitHub App, Vaultwarden, RBAC, parser DefectDojo et Celery réels | **NOT_RUN** | Aucune activation/install/import sur TrueNAS |
| Retrait des rapports ZAP historiquement téléversés | **NOT_RUN** | Inventaire/expiration/purge à faire avec les droits opérateur |
| Confidentialité réseau DefectDojo et `ops.albandrieu.com` | **INCOMPLETE** | Modèle privé déclaré ; audit effectif DNS/Tunnel/WAN et JWT non attesté |

Aucune provenance de PR, rapport incomplet ou ancienne exécution réussie après
un scan récent en échec ne déclenche un import. Le collecteur reste **pull**
via GitHub App (`Actions:read`), exécutable **uniquement** sur TrueNAS ;
`--check` reste non mutant, `--pull` requiert sa configuration,
`--pull-and-import` garde son approbation distincte, son engagement préexistant
et sa validation RBAC. Aucun nouveau DAST sur PR ni collecteur applicatif.


**Contrat courant (19 octobre 2026).** Un seul collecteur déclaratif dans
`nabla-compose` : `scripts/security/poll-defectdojo-gh-artifacts.py`.
Aucun runner Github, collecteur par application, webhook entrant, Tunnel
public ou conteneur additionnel n'est requis. Les rapports de sécurité sont
produits **une seule fois** par leurs workflows existants, récupérés par
l'API GitHub `Actions:read` et importés séparément depuis le LAN.

## Sources configurées et contrats

| Source | Workflow courant | Type | Import |
| --- | --- | --- | --- |
| `alban` | `security-supply-chain.yml`, `nuclei-public.yml`, `master-dast.yml` | Trivy, Nuclei, ZAP | Validation/approbation distincte, ZAP minimal **après déploiement du producteur** |
| `bababou` | `production-dast.yml` | ZAP | **Refus tant que le rapport brut n'est pas minimisé à la source** |
| `compose` | `defectdojo-compose-handoff.yml` | Trivy | Contrat propriétaire existant |
| `fastapi-sample` | **`docker-build.yml`**, workflow **`Docker CI`** | **Trivy image JSON natif** | Stage uniquement ; import auto interdit |

Pour `fastapi-sample`, le même scan Trivy du workflow hebdomadaire
(`schedule`, mercredi) produit `trivy-results.json` et se convertit
ensuite en `trivy-results.sarif` sans second scan. Le ZIP GitHub
`defectdojo-fastapi-trivy-<sha40>` doit contenir **uniquement**
`trivy-results.json`, avec une rétention de **3 jours**, sur un run
`master` réussi. **Aucun exporteur/filtre spécifique DefectDojo**.
Les champs natifs des vulnérabilités sont transmis sans modification.
Le filtrage par sévérité est déjà celui du scanner `Docker CI`.

Le collecteur impose la provenance (repo/workflow/event/branche, SHA),
le ZIP exact, les limites de taille, un objet Trivy natif valide, et
le refus de blocs `Secrets`/`Misconfigurations`. Un rapport absents
ou une dernière exécution échouée doit rester `NOT_OBSERVED`, pas
une disponibilité ni un scan réussi. Aucun ancien artefact d'un run
réussi ne doit masquer la dernière exécution défaillante.

## Identités, permissions et réseau

1. **GitHub** : GitHub App installée seulement sur les dépôts autorisés,
   permissions `Actions:read`, jeton court (≤1 h), restreint à un dépôt
   pour chaque collecte ; pas de PAT permanent. Clef privée et config
   runtime dans `/mnt/cpool/secrets/runtime/defectdojo`,
   `root:root 0600`. L'authentification GitHub n'est jamais
   transmise au stockage ZIP après redirection HTTPS signée.
   Voir [configuration GitHub App](github-app-defectdojo.md).
2. **DefectDojo UI** : item Vaultwarden canonique `nabla/prod/defectdojo`.
   `scripts/secrets/bootstrap_defectdojo_admin.py --check` inspecte
   hors réseau ; `--apply` est volontaire et nécessite une session
   Vaultwarden déverrouillée **non-root**. Un compte initial peut être
   provisionné avec mot de passe CSPRNG sans écraser de secrets
   existants. Le bootstrap ne prouve pas qu'un compte existe en
   base de données. Les secrets `.env`/`.env.secrets` sont
   matérialisés uniquement par
   `scripts/truenas/prepare-security-tooling-secrets.sh`.
3. **Import API** : identité robot non-admin **distincte de l'UI**,
   jeton `0600` et Product/Engagement préexistants par dépôt.
   Vérifier un refus RBAC sur un autre Product/Engagement avant
   automatisation. Pas de création automatique de contexte.
4. **Réseau** : DefectDojo doit rester accessible seulement dans le LAN,
   via `defectdojo.int.albandrieu.com` et Traefik, sans DNS public,
   NAT, HAProxy WAN ni Cloudflare Tunnel. Le port interne
   `172.17.0.24:31085` doit avoir des ACL effectives. L'importeur
   `fastapi-sample` utilise TLS/SNI et vérifie l'origine LAN.
   Le script générique `import-scan-defectdojo.sh` utilise encore
   le port HTTP direct **interne** : prévoir sa migration vers HTTPS
   Traefik ou attester les ACL locales avant d'ouvrir l'automatisation.

## Exécution et économie CI

La tâche native TrueNAS est déclarée avec
`scripts/truenas/reconcile-defectdojo-artifact-cron.py`, à **06:50**
heure de l'appliance, **désactivée** initialement.
Activer la Cron uniquement avec l'approbation explicite
`DEFECTDOJO_GH_POLL_APPROVED=YES` et après contrôle des permissions.
Aucune modification de root crontab. Aucun DAST ni scan CI
supplémentaire n'est lancé par le collecteur.

```bash
# Local, sans GitHub, DefectDojo ni secret
python3 scripts/security/poll-defectdojo-gh-artifacts.py --check
python3 -m unittest tests.test_defectdojo_fastapi_handoff -v

# Sur TrueNAS uniquement, après configuration de la GitHub App
python3 scripts/security/poll-defectdojo-gh-artifacts.py \
  --source fastapi-sample --kind trivy --pull

# Ne pas lancer --pull-and-import avant validation RBAC/Celery
```

La validation locale **ne remplace pas** : récupération effective d'un
artefact `Docker CI` sur `master`, import DefectDojo au bon Engagement,
processing asynchrone Celery, déduplication, audit réseau WAN négatif
et rotation/révocation du token. HTTP 2xx signifie seulement accepté.

## Ce qui doit rester privé

Rapports Betterleaks/GitGuardian, secret matches, PII, SBOM,
licences détaillées, sorties DAST authentifiées, requêtes/réponses ZAP
et informations LAN ne vont jamais dans des artefacts GitHub publics
sans politique explicite. Garder la validation de formats/secret
dans `config/security/defectdojo-allowed-imports.json` et
`scripts/security/validate-defectdojo-report.py`, mais ne pas
transformer le JSON vulnérabilités natif pour l'adapter à DefectDojo.

Les diagnostics uniques de pfSense/Cloudflare/TrueNAS restent dans les
runbooks de `nabla-compose`. Les anciennes étapes déjà implémentées
sont consultables dans Git, sans être reprises dans ce document.
