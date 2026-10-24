# Homelab — registre des refactorings risqués

> 25 octobre 2026 · PR #276 Draft · **aucun changement de runtime**.
> Chaque ligne décrit une hypothèse de risque et les preuves nécessaires,
> pas une autorisation de redéploiement.

[Roadmap active](../roadmap.md) ·
[Acceptation runtime](homelab-runtime-acceptance.md) ·
[Skill local-first](../../.agents/skills/local-first-quality/SKILL.md).

## Classification des risques

| ID | Risque | Effet indésirable | Mesure appliquée / décision | Critère de passage |
| --- | --- | --- | --- | --- |
| R-01 **Élevé** | Extraction du registre de `finish-migrations-20261024.sh` | Sections absentes, checks sautés, mauvais ordre, `--apply-*` non protégé | Le module `migration-diagnostic-sections.sh` est **sourcé après** vérification de l'origine canonique, de `master` et de la propreté Git en mode mutation ; fichier manquant ou symlink = `BLOCKED` ; plan/apply restent dans le script original | Tests de toutes les sections et négatifs, refus des sources non sûres, `bash -n`, ShellCheck, L3 au SHA exact |
| R-02 **Élevé** | Réponse DNS publique DefectDojo inaccessible | `no public A record` présenté à tort comme exposition privée vérifiée | Échec `dig`, RCODE `SERVFAIL`/`REFUSED`, RCODE absent et réponse périmée `EDE: 3` classés FAIL ; seules réponses vérifiables `NOERROR`/`NXDOMAIN` sont acceptées | Mocks Pi-hole/Unbound/Cloudflare ; public timeout ≠ PASS ; sortie expurgée |
| R-03 **Moyen** | Regroupement du parseur MIME/HTTP DefectDojo | HTTP 200 JSON ou code malformé faussement accepté | Normalisation des seuls codes numériques et `text/html` dans `classify_html_probe`, jamais de Content-Type brut dans les logs | 200 HTML PASS, 200 JSON FAIL, 401/403 FAIL, transport 000 FAIL et code invalide FAIL |
| R-04 **Très élevé, différé** | Scinder les opérations `--apply-wave`, `--apply-step`, `--apply-csi-smoke` | Redémarrage non autorisé, dérive de plan, perte de données | **Ne pas déplacer** ces opérations avant preuve L3 ; conserver acknowledgements et garde-fous du checkout canonique | Injection d'échecs, planHash TOCTOU, approbation, dirty tree, refus en worktree, rollback vérifiés |
| R-05 **Élevé, différé** | Mutualisation des états Docker entre Sentry, OpenRAG et diagnostics | Confusion `RUNNING`/healthy, fuite de DSN/tokens par `.State.Health.Log.Output` | Maintenir la lecture métadonnée-only et les sélecteurs fixes ; ne pas exposer `docker inspect` JSON brut | Contrats sans credentials, cas missing/ambiguous, healthy/starting/unhealthy |
| R-06 **Élevé, différé** | Migration de secrets et retrait de chemins hérités | Invalidation des clés OpenSearch, Langflow, LiteLLM ; corruption du corpus | **Aucune migration** implicite ; pas de génération de secret ni de réindexation `cpool/bababou` | Snapshots, comparateur constant-time si nécessaire, restauration fonctionnelle opérateur |
| R-07 **Moyen, différé** | Généralisation des lanceurs PR #274 | Checkout principal écrasé, shell interactif fermé, CI payante involontaire | Conserver les scripts datés jusqu'à remplacement testé ; Bash enfant uniquement | PID shell parent conservé en échec, worktree isolé, HEAD pin, `uv --locked`, L3 local |

## Contrat de qualité pour un changement à risque élevé

1. Vérifier le HEAD de la PR Draft et le diff complet contre `master`.
2. Exécuter les tests synthétiques **positifs et négatifs** de la zone modifiée.
3. Vérifier `bash -n`, ShellCheck et le contrôle de non-divulgation.
4. Exécuter les tests de refactoring de l'orchestrateur, puis les suites voisines.
5. Exécuter `just agent-skills-check` et `just quality` dans un worktree
   non-root avec `.venv` unique à ce worktree.
6. Épingler le HEAD testé et exécuter la publication locale complète
   `agent-pre-push` avant de retirer le statut Draft.
7. Séparer ensuite l'**acceptation runtime TrueNAS** : les tests offline
   ne prouvent ni le fonctionnement de Sentry/OpenRAG, ni celui de DefectDojo.

Un échec `QG_LARGE_DELETION`, un hook ShellCheck ou une gate de secrets
**bloque** la publication. Ne pas le désactiver. Ne jamais exécuter
`--apply-*` pour tester un refactoring documentaire.

## État d'exécution vérifiable

La PR #276 contient l'extraction du registre, les tests d'absence/symlink,
la correction DNS fail-closed et les tests HTTP négatifs.
Le présent document **n'atteste pas** une exécution de `pytest`,
`just quality` ou une acceptation sur le matériel TrueNAS.
Les états de gate restent `NOT_RUN` tant que les sorties ne sont pas
collectées au commit exact et que l'identité du HEAD n'est pas vérifiée.

**Rollback code** : revenir à la révision précédente de la PR dans un
worktree isolé ; ne pas effectuer de reset du checkout TrueNAS.
Le retour arrière d'une opération de production doit être planifié
séparément et n'est pas couvert par cette procédure documentaire.
