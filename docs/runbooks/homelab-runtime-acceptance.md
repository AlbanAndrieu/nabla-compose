# Homelab — acceptation runtime (25 octobre 2026)

**Statut :** procédure courante, lecture seule. Cette procédure ne confirme
**aucun état runtime** sans nouveaux résultats opérateur.

[Roadmap](../roadmap.md) · [Opérateur de migration](truenas-migration-operator.md) · [Index des runbooks](README.md) ·
[skill local-first](../../.agents/skills/local-first-quality/SKILL.md).

## Périmètre et garde-fous

- Exécuter les sondes **sur TrueNAS**, depuis une révision contenant les
  scripts, **sans écraser** le checkout canonique ou un worktree sale.
- `--check` ne lance pas `app.start`, `app.redeploy`, restauration,
  migration ni redémarrage ; des **rapports privés** peuvent être créés
  sous `/mnt/cpool/var/nabla/migration-20261024` (permissions `0600`).
- Ne pas installer `midclt` sur la workstation. Sans `midclt`, noter
  `NOT_RUN` plutôt que `DOWN`.
- Ne pas réinitialiser Kafka, effacer ClickHouse ou les TSDB/WAL,
  réindexer `cpool/bababou`, régénérer des secrets, ni exposer DefectDojo
  sur l'Internet public.
- Un résultat `PASS` sur un transport, `HTTP 403` sur l'API ou
  `App RUNNING` **n'atteste pas** le fonctionnement métier.
- Exécuter les changements et `--apply-*` seulement après autorisation,
  plan, sauvegarde, preuve préalables et rollback ciblé. **Ne pas
  transformer ce runbook en script de remédiation automatique.**

## Procédure courte

**Étape 1 — Lire la révision.** Vérifier la provenance du checkout et
les scripts de diagnostic. Ne jamais faire `git pull` sur un checkout
TrueNAS sale ni copier une PR Draft dans un bind-mount applicatif.

**Étape 2 — Exécuter la collecte groupée.** Dans le shell TrueNAS
positionné à la racine d'une révision contenant ces scripts :

```bash
sudo bash scripts/truenas/migration-operator.sh --check --section critical
```

Le contrôle regroupe OpenRAG, Sentry, DefectDojo, Prometheus et Akvorado
sans redéploiement. Il **peut retourner 1** si une gate échoue ; ne
pas masquer ce code de sortie.

**Étape 3 — Lire les résultats.** Consulter le résumé PASS/FAIL et les
journaux privés correspondant **sur TrueNAS**. Partager uniquement
des classes d'erreurs, les codes de retour et les états expurgés.

**Étape 4 — Isoler les échecs.** Exécuter seulement la section concernée :

```bash
sudo bash scripts/truenas/migration-operator.sh --check --section openrag
sudo bash scripts/truenas/migration-operator.sh --check --section sentry
sudo bash scripts/truenas/migration-operator.sh --check --section defectdojo
sudo bash scripts/truenas/migration-operator.sh --check --section prometheus
sudo bash scripts/truenas/migration-operator.sh --check --section akvorado
```

Chaque ligne est **une action indépendante**, à lancer séparément seulement
si elle sert au diagnostic. La liste n'est pas un bloc de commandes
à exécuter intégralement.

**Étape 5 — Qualifier la cause.** Utiliser ce tableau et le runbook ciblé :

| Domaine | Preuve nécessaire | Ce qui n'est pas une preuve suffisante |
| --- | --- | --- |
| OpenRAG | App RUNNING et backend/frontend running+healthy ; auth OpenSearch/Langflow/LiteLLM | App RUNNING seule ; HTTP 401 sur LiteLLM |
| Sentry | Deux consommateurs healthy ; ingestion edge → Relay → Kafka → ClickHouse après accord | Logs vides ou `docker ps` seul |
| DefectDojo | Origine LAN HTML, uWSGI, A privés Pi-hole/Unbound, TLS/SNI HTTPS fonctionnels | API anonyme en 403, HTTP 200 JSON |
| Prometheus | Règles saines + jobs individualisés ; authentification scrape applicable | Serveur RUNNING seul |
| Akvorado | Métadonnées exporter et ifIndex correctes, flux récents et inserts ClickHouse datés | Compteurs historiques cumulés |

**Étape 6 — Valider le retour fonctionnel.** Pour Sentry, lancer le
smoke E2E déjà prévu uniquement après que la stack est prête.
Pour OpenRAG, attendre la disponibilité Docling avant toute ingestion ;
tester d'abord un document synthétique. Pour Akvorado, exiger des
insertions SQL récentes.

**Étape 7 — Renseigner la roadmap.** Noter l'heure, le SHA de code, la
classe d'erreur, la gate et le prochain acte. Ne jamais transformer
une observation historique en état courant.

## Services optionnels et post-migration

Pour contrôler les services après une vague approuvée, utiliser
[les sections postmigration et apisix](truenas-migration-operator.md).
APISIX n'est pas inclus dans `critical` tant que le service n'est pas
déployé et accepté. `--section apisix` vérifie uniquement les
métadonnées Docker ; `just apisix-smoke` valide la route et
l'authentification séparément.

## Qualité du code avant changement

Sur un **worktree de développement séparé**, non-root :

```bash
just agent-skills-check
just quality
```

Pour chaque exécution, respecter le
[skill local-first](../../.agents/skills/local-first-quality/SKILL.md) :
`uv` verrouillé, `.venv` distincte, tests ciblés, cas négatifs et
gate finale au HEAD exact. Ces deux commandes sont distinctes ;
ne pas les soumettre aveuglément comme un bloc dans un shell interactif.
La CI GitHub payante reste suspendue sur les PR Draft.

## Historique préservé

Les scripts de migration du 24 octobre conservent leurs sous-commandes
`--plan-wave`, `--apply-wave` et `--apply-step`, mais **ne sont
pas autorisés** par la simple lecture de ce document.
Pour les critères de planHash, les vagues et les preuves d'origine,
consulter le [runbook historique des migrations](2026-10-24-truenas-migration-acceptance.md).
Les observations datées sont conservées dans le
[compte rendu opérateur historique](2026-10-24-homelab-operator-next-commands.md).
