# OpenClaw / LiteLLM — P0 diagnostic et heartbeat avant migration TrueNAS

**30 octobre 2026 — PR Compose #300.** Exécuter sur la **Workstation** sauf mention TrueNAS. Ce runbook est un protocole de collecte : ni redémarrage, ni création de clés, ni appel au modèle, ni réactivation du heartbeat. Le propriétaire final du Gateway et des politiques est `nabla-openclaw`; Compose conserve le proxy LiteLLM TrueNAS et les dépendances infrastructure.

## 0. Reprendre la branche et vérifier le contrat local

Un checkout sale ne doit pas être écrasé. Préférer un worktree détaché de la branche exacte :

```bash
cd ~/w/nabla-compose
git fetch origin docs/consolidate-openclaw-yubikey-handoff-20261030
WT="$(mktemp -d /tmp/nabla-openclaw-p300.XXXXXX)"
rmdir "$WT"
git -c submodule.recurse=false worktree add --detach "$WT" \
  origin/docs/consolidate-openclaw-yubikey-handoff-20261030
cd "$WT"
git status --short
python3 -m unittest discover -s tests -p 'test_openclaw_migration_evidence.py' -v
python3 -m unittest discover -s tests -p 'test_openclaw_heartbeat_restoration.py' -v
python3 -m unittest discover -s tests -p 'test_openclaw_heartbeat_legacy_recovery_contract.py' -v
pre-commit run developer-tooling-contract --all-files
```

Le hook `developer-tooling-contract` doit disposer de `PyYAML==6.0.3` dans son environnement isolé `language: python`, et non compter sur Python 3.14 de mise. Aucun `pip install` global n'est requis. Exécuter ensuite `just quality` **localement** une fois les contrôles ciblés verts ; ne pas lancer de CI GitHub payante.

## 1. Collecte Workstation — indépendante, à échec fermé

Les sondes n'envoient aucune requête de génération. Ne pas interrompre la collecte au premier code 2 : **2 signifie preuve absente / non vérifiée**, pas toujours panne.

```bash
# Workstation, dans le worktree #300
umask 077
just openclaw-migration-evidence-tests
just openclaw-migration-evidence-inventory

# Chaque commande reste indépendante : un code 2 ne masque pas les autres.
for recipe in \
  openclaw-gateway-readiness \
  openclaw-runtime-alignment-check \
  openclaw-nabla-migration-check \
  openclaw-recovery-readonly \
  openclaw-migration-evidence-check \
  openclaw-429-triage-no-admin \
  openclaw-429-attribution \
  openclaw-rate-limit-evidence-check \
  openclaw-litellm-dual-logs-check \
  openclaw-truenas-tunnel-check \
  openclaw-truenas-model-keys-check \
  openclaw-truenas-virtual-keys-status \
  openclaw-truenas-virtual-keys-quota \
  openclaw-cron-parent-check \
  openclaw-cron-recovery-plan \
  openclaw-digest-top-check \
  openclaw-digest-gitops-plan \
  openclaw-heartbeat-copies-check \
  openclaw-heartbeat-modes-check; do
  printf '\n===== %s =====\n' "$recipe"
  just "$recipe"
  rc=$?
  printf 'RESULT recipe=%s exit=%s\n' "$recipe" "$rc"
done
```

Pour étendre la fenêtre LiteLLM et observer les signatures 429/401/502 **sans afficher les journaux** :

```bash
python3 scripts/workstation/diagnose-openclaw-litellm-dual-logs.py --hours 24
python3 scripts/workstation/observe-openclaw-rate-limits.py
python3 scripts/workstation/openclaw-route-metadata.py
systemctl --user show openclaw-gateway.service -p ActiveState -p SubState -p Result
curl --noproxy '*' -sS --connect-timeout 2 --max-time 6 \
  -o /dev/null -w 'gateway_readyz=%{http_code}\n' \
  http://127.0.0.1:18789/readyz
curl --noproxy '*' -sS --connect-timeout 2 --max-time 6 \
  -o /dev/null -w 'litellm_workstation=%{http_code}\n' \
  http://127.0.0.1:4000/health/liveliness
```

**Interprétation 429 :** les dépenses des deux clés Workstation inférieures aux caps n'excluent ni une saturation RPM/TPM, ni une autre couche de quota, ni une limitation upstream. `openclaw-route-metadata.py` décrit la configuration **statique**, pas la route réellement utilisée par une session. Les motifs dans les logs démontrent des **indices**, pas l'identité du requérant. Les événements structurés du Gateway et les métadonnées de la requête échouée restent nécessaires.

## 2. Accès LiteLLM TrueNAS, modèles et clés

Depuis la Workstation, diagnostiquer explicitement le défaut observé `docker_permission_denied`. **Ne jamais ajouter un utilisateur au groupe docker pour contourner le diagnostic.** Si un droit `sudo -n docker logs` existe déjà et est approuvé :

```bash
# Workstation : opt-in à un sudo non interactif existant sur TrueNAS.
python3 scripts/workstation/diagnose-openclaw-litellm-dual-logs.py \
  --hours 24 --truenas-sudo-logs

# Sans modification du tunnel ; confirmer qu'il appartient au processus SSH attendu.
just openclaw-truenas-tunnel-check
# Après validation de l'authentification et du tunnel uniquement :
just openclaw-truenas-model-keys-tunnel-prompt
```

**Depuis TrueNAS** (terminal d'administration, checkout canonique, pas d'installation apt) :

```bash
midclt call system.version
cd /mnt/cpool/compose/nabla-compose
just litellm-workstation-upstream-auth-check
just openclaw-truenas-secret-provenance
just openclaw-truenas-virtual-keys-plan
just openclaw-truenas-virtual-keys-status
just openclaw-truenas-virtual-keys-quota

# Vérifier UNIQUEMENT le droit de lecture Docker préexistant, sans journaux bruts :
sudo -n docker logs --since 2h --tail 50 litellm >/dev/null
```

Les clés `main` et `cron` doivent rester distinctes, scoped par modèles et budget, jamais des master keys. Les alias réellement offerts par `/v1/models` doivent correspondre à ceux des agents. La configuration actuelle ne garantit **pas** que `gpt-4.1` et `gpt-4.1-mini` existent sur LiteLLM TrueNAS. `workstation-qwen` est un proxy de modèle disponible **à confirmer en runtime** ; son upstream Workstation GPU et sa clé d'amont ne sont pas automatiquement équivalents à une route `gpt-4.1`.

**NO-GO** pour le cutover tant que les modèles, le droit d'accès aux deux logs, le quota de chaque clé et la persistance du tunnel ne sont pas démontrés. Un `200` sur `/health/liveliness` seul ne prouve pas l'autorisation `/v1/models` ni l'inférence fonctionnelle.

## 3. Heartbeat : état natif, sauvegarde privée et optimisation

Ne pas déduire l'identité du job actif de l'UUID historique. Confirmer les commandes offertes par la **version installée** avant toute opération. `automations` est un alias de `cron` dans la documentation OpenClaw actuelle ; la compatibilité runtime doit être vérifiée.

```bash
# Workstation. Commandes d'inspection seulement.
just openclaw-runtime-alignment-check
openclaw automations --help
openclaw automations scratch --help
openclaw config validate
just openclaw-heartbeat-copies-check
just openclaw-heartbeat-modes-check

# Les réponses natives peuvent contenir des informations privées : fichiers 0600.
umask 077
OUT="$HOME/.local/state/nabla-compose/openclaw/p300-evidence"
install -d -m 0700 "$OUT"
openclaw automations list --all --json > "$OUT/automations.json"
openclaw automations runs --all --status error --limit 20 --json \
  > "$OUT/failed-runs.json"
chmod 0600 "$OUT/"*.json

# Inspecter PRIVÉMENT le bon job via les noms et l'état enabled/disabled.
# Identifier le vrai HB_ID à partir des données natives, puis :
# HB_ID='<identifiant-vérifié>'
# openclaw automations get "$HB_ID" --json > "$OUT/heartbeat-before.json"
# openclaw automations scratch "$HB_ID" --json > "$OUT/scratch-before.json"
```

**Candidat conservé, NON activé :** `ops/openclaw-workstation/HEARTBEAT-RESTORED.candidate.md` et `heartbeat-restoration.policy.json`. Paramètres proposés : `every=2h`, `08:00-22:00 Europe/Paris`, `lightContext=true`, `isolatedSession=true`, `skipWhenBusy=true`, `target=none`. Seuls Gatus/Prometheus et les diagnostics **déjà disponibles** servent de base ; pas de requêtes d'inférence pour vérifier une alerte. Les **14 fonctions historiques** restent désactivées, les notifications sont dédupliquées et le digest est un job indépendant.

La documentation moderne distingue le **heartbeat système**, dont la cadence est pilotée par les préférences de l'agent, et les **automations ordinaires** issues d'une migration. Ne pas modifier une ligne interne du scheduler si le monitor reste propriété du système. `openclaw doctor --fix` **migre/modifie l'état** et n'appartient pas à ce lot read-only.

L'application d'un scratch est une **mutation séparée** : `plan -> sauvegarde privée 0600 -> révision CAS -> apply explicite -> verify -> rollback`. Ne jamais exécuter `automations scratch --file`, `automations edit`, `doctor --fix`, `automations enable` ni `openclaw-heartbeat-modes-apply` dans cette collecte.

## 4. Réparer les erreurs réelles dans un ordre sûr

1. **401/403** : confirmer l'identité effective et la route de la requête, puis vérifier clé virtuelle, audience et modèle ; ne jamais afficher le Bearer.
2. **429** : attribuer à la clé, au modèle et au proxy via métadonnées structurées, observer RPM/TPM et cooldown ; ne pas accroître automatiquement les limites.
3. **LiteLLM TrueNAS logs** : tenter le lecteur sudo déjà autorisé, sinon conserver `partial_or_unverified`.
4. **`agent:cron:main` absent** : l'agent `cron` existe mais la session de référence est absente des 21 sessions inspectées. Créer une conversation `cron` depuis l'UI **après validation de l'identité**, pas en altérant SQLite.
5. **Digest top** : `just openclaw-digest-gitops-plan` puis relire la cible et l'empreinte ; le `--apply` existant est opt-in et refusé si l'ancien template ne correspond pas.
6. **Heartbeat** : tester le modèle et les coûts prévus par la policy, puis promouvoir le candidat dans `nabla-openclaw` ; pas de démarrage parallèle avec la Workstation.
7. **Cutover** : exiger image/digest, ZFS/ACL/backup restauré, modèle équivalent, scoped keys et tunnel/HTTPS durable ; bascule `cron` puis `main`, avec rollback de chacun.

## 5. Preuves de réception GO / NO-GO

- Contrats locaux Compose et `nabla-openclaw` PASS, sans CI GitHub.
- Deux proxies observés ; modèle `main` et `cron` réellement disponible, autorisé par la bonne clé.
- Origine des 429 attribuée ou explicitement documentée `NOT_VERIFIED` ; pas de faux succès.
- Heartbeat unique, cadencé et mesuré, sans activation des 14 tâches historiques ; journal d'exécutions et livraison vérifiés après un futur cutover approuvé.
- Gateway TrueNAS non-root et persistant ; aucune double exécution ; rollback Workstation éprouvé.

**État au 30 octobre 2026 : NO-GO runtime.** La preuve disponible établit `gateway_verdict=ready`, `cron_main_reference=absent_in_reported_complete_catalog`, `digest_state=skill_template_range_int_mismatch` et `coverage=partial_or_unverified` pour les deux LiteLLM.

Références : [migration inter-dépôts](../roadmap-openclaw-yubikey-extraction-20261030.md), [runbook précédent](openclaw-end-to-end-migration-20261030.md), [OpenClaw heartbeat](https://docs.openclaw.ai/heartbeat), [OpenClaw automations CLI](https://docs.openclaw.ai/cli/cron).
