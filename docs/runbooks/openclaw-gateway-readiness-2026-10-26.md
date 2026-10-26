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


## 21:42 — Échec du processus, pas de l'admission HTTP

Nouvelle preuve Workstation : les neuf contrats du diagnostic readiness
passent, puis l'exécution réelle retourne
\`gateway_service=failed\`, \`healthz_status=unreachable\`,
\`startupz_status=unreachable\`, \`readyz_status=unreachable\`,
\`gateway_verdict=service_not_active\`.
Cette preuve signifie que le service user n'est pas opérationnel.
Les canaux ne peuvent pas être diagnostiqués via HTTP tant que le
processus ne reste pas vivant. Ne pas relancer \`openclaw update\`,
ne pas recréer de staging et ne pas redémarrer en boucle.

### Diagnostic du démarrage (lecture seule)

Ajout à la PR #285 :
\`scripts/workstation/diagnose-openclaw-gateway-service-failure.py\`
et recette \`just openclaw-gateway-service-failure\`.
Elle lit des champs **bornés et autorisés** de
\`systemctl --user show\` : état, sous-état, résultat, code de sortie,
nombre de redémarrages et identité binaire/paquet attendue.
Elle classe jusqu'à 160 lignes de journal user sur les 30 dernières
minutes en familles prédéfinies, notamment \`state_owner_contention\`,
\`state_migration\`, \`node_runtime\`, \`port_conflict\`,
\`missing_dependency\`, \`filesystem_permission\`,
\`configuration\`, \`plugin_initialization\`,
\`authentication\`, \`out_of_memory\`.
Elle **ne publie pas** le journal brut, les valeurs de secrets, les
fichiers SQLite, les noms des agents ou les chemins privés.
Une correspondance de journal n'est qu'un indice, pas une preuve
définitive de causalité.

\`\`\`bash
cd ~/w/nabla-compose
git fetch origin fix/code-password-dotenv-fixture-20261026
WT="$(mktemp -d /tmp/nabla-oc-failed.XXXXXX)"
rmdir "$WT"
git -c submodule.recurse=false worktree add --detach \
  "$WT" origin/fix/code-password-dotenv-fixture-20261026
cd "$WT"
python3 -m unittest discover -s tests \
  -p 'test_openclaw_gateway_service_failure.py' -v
just openclaw-gateway-service-failure
\`\`\`

Le sélecteur ne s'exécute **pas** dans cette procédure. Les réparations
dépendront du résultat de systemd et du journal classifié ; ne jamais
supprimer \`openclaw.sqlite\`, \`-wal\`, \`-shm\` ou forcer une migration
sur la seule base du code d'erreur HTTP.

Le recovery existant fournit désormais le diagnostic systemd en cas
d'échec du \`systemctl --user start\` ou de perte de l'activité après
une sonde \`/readyz\`, sans refaire l'installation ni redémarrer le
Gateway automatiquement.
