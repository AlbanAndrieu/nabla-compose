# OpenClaw Gateway 2026.10.7 — readiness après migration (26 octobre 2026)

## Preuves Workstation

- 33/33 tests sous umask habituel et 33/33 tests sous `umask 0002` : **PASS**.
- `package_permissions_hardened=4`, `package_check=verified`.
- `existing_package_verified=yes`, `owned_dropin=yes`, `gateway_running=no` avant bascule.
- `package_selection=verified`, `service_node=24.22.1`, `service_openclaw=2026.10.7`.
- Le démarrage systemd n'a pas signalé d'erreur immédiate.
- **`repair=gateway_readiness_unverified`** après les sondes : le Gateway n'est pas encore déclaré opérationnel.
- Aucun nouvel appel npm, LLM ou sauvegarde supplémentaire dans la procédure.

## Attribution avant réparation

La documentation officielle distingue :

| HTTP | Signification |
| --- | --- |
| `/healthz` | serveur HTTP en vie |
| `/startupz` | initialisation sidecars et inspection agent DB terminées |
| `/readyz` | admission des agents et comptes de canaux fonctionnelle |

Une instance peut répondre `200` à `/healthz` et `503` à `/readyz`. Ne pas relancer ou rétrograder automatiquement : des migrations SQLite/plugin peuvent être en cours ou non réversibles.

Dans la PR #285, `scripts/workstation/diagnose-openclaw-gateway-readiness.py` ne fait que trois GET sur `127.0.0.1:18789`, refuse les redirects et proxys, borne les données et imprime uniquement des **catégories fixes**, sans noms de canaux, identifiants de compte, corps HTTP ou secrets.

## Prochaine commande (lecture seule)

```bash
cd ~/w/nabla-compose
git fetch origin fix/code-password-dotenv-fixture-20261026
WT="$(mktemp -d /tmp/nabla-oc-readiness.XXXXXX)"
rmdir "$WT"
git -c submodule.recurse=false worktree add --detach "$WT" origin/fix/code-password-dotenv-fixture-20261026
cd "$WT"
just openclaw-gateway-node-test
just openclaw-gateway-readiness
```

- `healthz_status=unreachable` : service/port/transport à inspecter ; aucun restart automatique.
- `healthz_status=200`, `startupz_status=503` : initialisation ou inspection en cours, vérifier le stade.
- `startupz_status=200`, `readyz_status=503` : examiner `readiness_blocker` (base partagée, agent database, plugin reload, canal).
- Tous les statuts à `200` avec `gateway_service=active` : admission HTTP validée ; les canaux et la mémoire restent à vérifier séparément.

Le script de reprise imprime désormais ces diagnostics s'il ne reçoit pas de readiness, mais ne redémarre plus un Gateway déjà actif lors d'une relance manuelle.

Sources :
- https://docs.openclaw.ai/gateway/health
- https://github.com/openclaw/openclaw/issues/183599 (régression possible non attribuée à cette instance)
