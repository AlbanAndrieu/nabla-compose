# OpenClaw — registre des consommateurs du sandbox avant gitlink (30 octobre 2026)

> **Périmètre :** décision documentaire dans la PR Compose #300. Aucun fichier
> applicatif déplacé, aucun `midclt app.update`, aucun runtime modifié.
> Source de vérité pour l'exécution : [runbook de préflight TrueNAS](../runbooks/openclaw-sandbox-submodule-preflight-20261030.md).
> Contrat cible : [nabla-openclaw](https://github.com/AlbanAndrieu/nabla-openclaw/blob/master/docs/migration.md).

## Conclusion immédiate : NO-GO pour déplacer les quatre fichiers

Le chemin `apps/openclaw` **n'est pas libre** : il contient
`compose.yml`, `Dockerfile`, `catalog-info.yaml` et `test-docker.sh`.
Il s'agit de **openclaw-sandbox**, une application de développement,
**pas** du futur Gateway TrueNAS. Le service Docker se nomme
`openclaw-sandbox`, l'image `openclaw-sandbox:bookworm-slim`.
Son `compose.yml` monte notamment des chemins de Workstation
`/home/albandrieu/.openclaw/workspace/skills` et de calendrier ;
il ne doit pas devenir le manifeste du Gateway cible.

### Consommateurs réellement identifiés dans Git

| Chemin ou consommateur | Référence constatée | Traitement avant déplacement |
| --- | --- | --- |
| `build.sh` | `docker compose -f apps/openclaw/compose.yml up -d --build` dans la branche Workstation | Repointage vers `apps/openclaw-sandbox/compose.yml` ; vérifier qu'un build classique ne démarre pas le Gateway cible |
| `catalog/services.json` | `openclaw-sandbox.sourcePath = apps/openclaw/compose.yml` | Corriger la **source canonique** du catalogue puis régénérer les données dérivées selon le pipeline existant |
| `catalog/service-topology.json` | `sourcePath` et `evidence` vers l'ancien chemin | Recalculer la topologie, préserver l'identifiant de service `openclaw-sandbox` |
| `apps/openclaw/catalog-info.yaml` | annotation `backstage.io/source-location` vers `apps/openclaw/` | Déplacer avec le sandbox et corriger l'annotation ; vérifier l'owner et le cycle de vie sans les réinventer |
| `catalog/generated/*`, `apps/homarr/generated/apps.json` | Copies dérivées de l'ancien chemin et identité | Régénération **après** correction des sources ; ne pas modifier uniquement des snapshots générés |
| `scripts/truenas/check-openclaw-sandbox-binding.py` | Sentinelle de l'ancien include `/apps/openclaw/compose.yml` | **Conserver** durant la transition pour détecter les configurations encore liées à l'ancien emplacement |
| TrueNAS `app.config` | Chemin historique potentiellement référencé par une App, non confirmé par inventaire runtime | `--all-apps` sur TrueNAS obligatoire ; absence de preuve = NO-GO |
| `apps/openclaw/Dockerfile`, `test-docker.sh` | Contexte de build et conteneur `openclaw-sandbox` | Conserver le contexte et les tests après déplacement, sans déployer |
| `docs/`, `tests/`, `scripts/` | Plusieurs références historiques ou de compatibilité | Inspecter tous les consommateurs actifs ; préserver les références servant de sentinelle et annoter les archives |

Ce tableau est fondé sur les chemins effectivement présents dans Git
au contrôle du 30 octobre 2026. **Il n'atteste pas tous les
consommateurs runtime ou externes**. Le chemin peut encore exister
dans une app TrueNAS, un orchestrateur, une commande manuelle,
un clone non synchronisé ou une application tierce.

### Vérifications sans mutation

Depuis un **worktree propre** de la branche PR #300 :

```bash
python3 scripts/ops/plan-repository-split.py
python3 -m unittest discover -s tests -p 'test_repository_split_plan.py' -v
python3 -m unittest discover -s tests -p 'test_openclaw_policy_relocation.py' -v
python3 -m unittest discover -s tests -p 'test_openclaw_sandbox_binding.py' -v
python3 -m unittest discover -s tests -p 'test_openclaw_sandbox_global_binding.py' -v

# Exposer uniquement des chemins/numéros de lignes de code versionné.
git grep -n -F 'apps/openclaw/compose.yml' -- build.sh apps catalog scripts tests docs
git ls-files -- apps/openclaw
```

Depuis **TrueNAS**, uniquement si `midclt` est disponible :

```bash
cd /mnt/cpool/compose/nabla-compose
python3 scripts/truenas/check-openclaw-sandbox-binding.py --all-apps
```

Ce script **retourne toujours 2 par conception** : examiner le JSON
redigé, notamment `sandbox_relocation`, `app_inventory_count`,
`app_configs_unverified` et `old_path_reference_observed`.
`blocked_legacy_include_in_use` = NO-GO ;
`unverified_incomplete_app_scan` = NO-GO ;
`manual_review_no_app_reference_observed` = *revue des autres
consommateurs encore nécessaire*, **pas** autorisation de migration.
Ne jamais publier les réponses brutes `app.config` (secrets possibles).

### Ordre de bascule et preuve de retour arrière

1. **GO conditionnel** uniquement après preuve des consommateurs :
   préparer sur une branche dédiée un déplacement `git mv` des **quatre
   fichiers** vers `apps/openclaw-sandbox` et la correction des sources
   `build.sh` + catalogue + scripts de build concernés.
2. Régénérer catalogue/topologie puis vérifier invariants
   `id=openclaw-sandbox`, `composeService=openclaw-sandbox`,
   category `development`, références documentaires et tests.
3. Préparer le changement TrueNAS `custom_compose_config.include`
   avec sauvegarde privée, chemin de restauration, et application
   **explicite et séparée**. Ne pas lancer depuis cette PR documentaire.
4. Vérifier le chemin d'exécution sur Workstation et TrueNAS,
   et la possibilité de revenir à l'ancien include ; **STOP** si
   une App ou un script référence toujours le chemin à déplacer.
5. **Seulement après** déblocage, envisager un gitlink
   `apps/openclaw` épinglant un commit testé de `nabla-openclaw`.
   `git pull` ne déploie rien ; pas de `submodule update --remote`.

**Contrat cible supplémentaire à remettre à jour dans nabla-openclaw :**
`deploy/truenas/target-contract.json` sur `master` indique encore
`submodule.current_tracked_file_count=18`, valeur **historique**
antérieure à la relocation des 14 politiques. Le comptage actuel
confirmé dans Compose est **4**. Corriger la source cible après
validation, plutôt que de présenter le contrat historique comme
état runtime ou de modifier ce dépôt depuis la PR #300.

**NO-GO absolu :** aucun déploiement du Gateway, migration de sessions,
heartbeat/cron, copie de `~/.openclaw` ou hausse des budgets pour
réparer un test de chemin. Préserver la Workstation comme source
opérationnelle et le sandbox séparément.
