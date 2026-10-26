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


## 23:31 — Code systemd 78 : configuration ou schéma de base

Nouvelle sortie Workstation : **7/7 tests PASS**, puis :

```text
service_state=failed
service_substate=failed
service_result=exit-code
service_exit_status=78
service_restart_count=0
service_target_binding=target_binding_confirmed
journal_pattern=no_recent_journal_evidence
journal_lines_inspected=0
```

Le code `78` correspond au mécanisme `EX_CONFIG` d'OpenClaw. Il
peut signaler une configuration invalide, une migration hors ligne
requise, ou une base d'état ayant un **schéma plus récent que la
version du Gateway**. Cette dernière situation inhibe volontairement
le redémarrage automatique sous systemd. La version binaire
`2026.10.7` et son chemin attendu semblent corrects ; cela ne
prouve pas que les versions de schéma SQLite sont compatibles.

**Ne pas lancer de `doctor --fix` ni restaurer le tar.gz à ce stade.**
Le journal précédent cherchait seulement dans les 30 dernières
minutes et n'a rien trouvé. L'absence de lignes récentes ne permet
donc pas de conclure à une absence de diagnostic initial.

La PR #285 ajoute deux replis **en lecture seule** :
1. `journalctl --user` : au plus 240 derniers événements de l'unité,
   sans limite temporelle si la fenêtre récente est vide.
2. Fichiers de log locaux : les fichiers datés du répertoire officiel
   `/tmp/openclaw` ou de son repli `/tmp/openclaw-UID`, avec
   propriétaire utilisateur, permissions non inscriptibles au groupe
   ni aux autres, absence de symlink, lecture bornée et ancienneté
   inférieure à 48 h.

Les sources et leurs contenus **ne sont jamais publiés**. Seuls des
codes fixes sont affichés :
`journal_source=recent_30m|historic_tail|private_file_tail|no_user_journal`,
`journal_pattern=newer_database_schema|offline_state_migration_required|
newer_written_config|invalid_configuration|...`,
et `exit_78_interpretation=classified|config_or_schema_unattributed`.
Une correspondance de journal est un indice, pas une réparation
automatique.

**Commande opérateur (lecture seule)** depuis le worktree PR #285 :

```bash
python3 -m unittest discover -s tests \
  -p 'test_openclaw_gateway_service_failure.py' -v
just openclaw-gateway-service-failure
```

La PR n'effectue aucune action supplémentaire sur le Gateway arrêté,
la base SQLite, les plugins, les secrets ou les index mémoire.
Si le diagnostic signale `newer_database_schema`, vérifier ensuite
les versions de schéma compatibles avant toute commande de migration.
Si `invalid_configuration`, contrôler la configuration avec la CLI
`2026.10.7` en mode lint sans écrire de correctif.

Documentation OpenClaw :
- https://docs.openclaw.ai/reference/database-schemas/versioning
- https://docs.openclaw.ai/cli/gateway/running
- https://docs.openclaw.ai/help/faq/logging-and-debugging


## 23:31 — Historique journald sans signature reconnue

Dernières preuves Workstation : **12/12 tests PASS** puis
`service_state=failed`, `service_result=exit-code`,
`service_exit_status=78`,
`service_target_binding=target_binding_confirmed`,
`journal_source=historic_tail`, `journal_lines_inspected=240`,
`journal_pattern=no_known_pattern`,
`exit_78_interpretation=config_or_schema_unattributed`.

Cela confirme que le diagnostic a analysé 240 lignes historiques sans
trouver de signature connue. **Il ne confirme pas la cause du code 78.**
Ne pas recommencer la migration, ne pas éditer les bases et ne pas
relancer le Gateway à l'aveugle.

### Attribution via Doctor en lecture seule

La documentation officielle recommande `openclaw doctor --lint --json`
pour inspecter la configuration et les schémas sans appliquer de
modifications. Contrairement à `openclaw doctor` seul ou
`doctor --non-interactive`, le mode `--lint` interdit les migrations
et corrections implicites. Voir :
https://docs.openclaw.ai/cli/doctor/lint et
https://docs.openclaw.ai/cli/doctor/running.

Une nouvelle recette `just openclaw-gateway-doctor-lint` exécute cette
commande avec `node@24.22.1` et le `openclaw.mjs` déjà validé de
l'installation `2026.10.7`. Elle ne publie que les champs de
diagnostic structurés, regroupés par `checkId` :
`gateway_config`, `schema_migration`, `plugin`,
`auth`, `session_storage` ou `other`, ainsi que les comptes
de résultats et `doctor_ok`. Les messages, noms de comptes,
fichiers privés, `fixHint` et sorties brutes sont volontairement
ignorés.

Les données de configuration utilisées sont les chemins de
l'environnement courant (avec des valeurs par défaut correspondant
aux chemins habituels sous `~/.openclaw`). S'il existe des
surcharges `EnvironmentFile` propres à systemd non reproduites dans
ce shell, le lint pourrait ne pas refléter exactement le contexte
du service. Dans ce cas, il faut vérifier séparément la parité
d'environnement **sans publier les secrets**.

Commande Workstation :

```bash
python3 -m unittest discover -s tests \
  -p 'test_openclaw_gateway_doctor_lint.py' -v
just openclaw-gateway-doctor-lint
```

Le rapport Doctor complet peut contenir des valeurs sensibles : ne pas
le copier dans la PR ou la conversation. La recette imprime uniquement
les catégories prédéfinies. Aucun `doctor --fix`, aucun modèle LLM,
aucun redémarrage ni installation npm n'est déclenché.

### Sauvegarde existante (ne pas restaurer sans décision explicite)

Avant la tentative de migration, l'opérateur a créé et vérifié
`~/Backups/openclaw/openclaw-20261026T000901Z-1138514.tar.gz`
(`files=107003`, empreinte SHA-256
`c9c6d6fff132924de7b83aa8d2f7c2af8e470520fdf517b780a4be5b76748882`),
puis a effectué une copie sous
`/media/backup/lab/infra/openclaw/`.
La copie hors répertoire initial n'a pas fait l'objet d'une
vérification SHA-256 transmise. Aucune nouvelle sauvegarde n'est
requise pour les diagnostics en lecture seule. Cette sauvegarde
précède les changements du service et la possible migration du
schéma ; ne pas la restaurer sur un état actif ou potentiellement
plus récent.


## Contrat systemd Node.js après mise à jour `mise` (26 octobre)

Le diagnostic de service ne dépend plus de **Node 24.22.1**
en dur : il accepte une version corrective de Node 24 installée
sous `~/.local/share/mise/installs/node/24.x.y/` lorsque
l'exécutable `bin/node` et le module
`lib/node_modules/openclaw/openclaw.mjs` proviennent **du même
répertoire de version**, avec `gateway --port 18789`.
Un chemin mixte entre deux versions reste
`different_or_unverified`. La commande `ExecStart` brute
n'est pas affichée et aucune réparation n'est appliquée.

Le diagnostic reste de **lecture seule** et ne prouve pas
la disponibilité `/readyz` ; utiliser ensuite le diagnostic
Gateway existant. Ces règles sont couvertes par des fixtures,
sans démarrage du Gateway par l'agent.

## 26 octobre — pourquoi un seul redémarrage manuel peut se justifier

Dernier rapport `doctor --lint --json` de la Workstation :
`doctor_exit=1`, `doctor_report=structured`, `doctor_checks_run=36`,
`doctor_findings_count=9`, `doctor_diagnosis=gateway_config`,
`doctor_gateway_config_findings=1`,
`doctor_schema_migration_findings=4`,
`doctor_other_findings=4`. **Ces données agrégées ne permettent
pas de distinguer warnings et errors** ; un exit 1 en lint signifie
qu'une finding a atteint le seuil, qui peut être `warning`.

Conformément à la documentation OpenClaw, code systemd `78`
(`EX_CONFIG`) est un arrêt intentionnel du Gateway en cas de
configuration invalide ou de migration hors ligne requise. Ce code
empêche généralement le redémarrage automatique en boucle,
mais n'empêche pas une tentative explicite d'un opérateur.
Sources :
- https://docs.openclaw.ai/cli/doctor/lint
- https://docs.openclaw.ai/cli/gateway/running

Dans la PR #285 :
- `just openclaw-gateway-doctor-lint` sépare maintenant
  `doctor_severity_error`, `doctor_severity_warning`,
  `doctor_severity_info`, et signale uniquement
  `doctor_gateway_mode_finding=yes|no`.
- `just openclaw-gateway-start-once` exécute **une seule commande**
  `systemctl --user start openclaw-gateway.service` lorsque le
  Gateway est `failed` ou `inactive`. Avant cette commande,
  il exige le Node/paquet `24.22.1 / 2026.10.7` déjà sélectionné
  et aucune propriété SQLite DB/WAL/SHM détectable.
  Le démarrage ne procède à aucune correction, réinstallation,
  migration forcée ou sauvegarde supplémentaire.
  Sur échec, il renvoie immédiatement les diagnostics systemd
  expurgés. Sur service actif, il teste les sondes HTTP, sans
  nouvelle tentative.
- Aucun `systemctl reset-failed`, `restart`, boucle de retry,
  `doctor --fix` ni retour automatique vers l'ancien binaire.

**Décision opérateur :** une unique tentative est possible ; elle
peut cependant réexécuter les contrôles et migrations de démarrage
propres à OpenClaw. La sauvegarde préexistante est intacte,
et les risques de migration non réversible restent présents.
Si le service quitte à nouveau avec `78`, ne pas relancer le
script. Examiner `doctor_severity_*`,
`doctor_gateway_mode_finding` et la catégorie systemd avant une
correction de configuration ou de schéma.

Depuis un worktree de la PR #285, tester d'abord :
```bash
python3 -m unittest discover -s tests -p 'test_openclaw_gateway_start_once.py' -v
just openclaw-gateway-doctor-lint
```

Pour tenter le démarrage explicitement **une seule fois** :
```bash
just openclaw-gateway-start-once
```

La PR ne prétend pas que le Gateway soit déjà fonctionnel.


## 27 octobre — Service de nouveau en échec avec code 78

La dernière inspection réseau a donné :
`gateway_service=failed`, `service_exit_status=78`,
`service_pid=absent`, `expected_port_listener=not_listening`,
et toutes les sondes HTTP `unreachable`. Ce résultat exclut
une simple erreur de lien `/chat/main` : **aucun serveur
n'est actuellement à l'écoute sur le port attendu**.

Doctor a précédemment trouvé **0 erreur, 9 avertissements**
sur 36 contrôles. Cela ne suffit pas à identifier la cause du
code 78, qui peut aussi signaler une configuration invalide ou un
état incompatible au démarrage. Le résultat
`journal_source=historic_tail`, `journal_pattern=no_known_pattern`
était insatisfaisant : le script ne consultait les fichiers de
logs OpenClaw que si journald ne renvoyait aucune ligne.

**Correction du diagnostic dans PR #285 :** la recherche de logs
privés se déclenche également si les 240 lignes historiques sont
présentes mais ne correspondent à aucune signature connue.
Le rapport conserve des catégories statiques :
`journal_source`, `file_log_fallback`, `journal_pattern`,
`exit_78_interpretation`. Aucun message brut, secret, identifiant
d'agent, chemin de configuration ou clé n'est affiché.

Une preuve issue du journal classé prime ; si le journal reste
inconclusif, une signature reconnue dans les logs OpenClaw remplace
le motif non reconnu. Si aucune signature n'est trouvée dans
les deux sources, l'état reste `config_or_schema_unattributed`.
Ce comportement est couvert par trois tests unitaires supplémentaires.

**Commande unique, en lecture seule :**

```bash
cd ~/w/nabla-compose
git fetch origin fix/code-password-dotenv-fixture-20261026
git show origin/fix/code-password-dotenv-fixture-20261026:scripts/workstation/diagnose-openclaw-gateway-service-failure.py | python3 -
```

Ne pas relancer `openclaw-gateway-start-once`, `openclaw update`,
`doctor --fix`, ni modifier SQLite pour l'instant.
La sauvegarde existante du 26 octobre est conservée.
