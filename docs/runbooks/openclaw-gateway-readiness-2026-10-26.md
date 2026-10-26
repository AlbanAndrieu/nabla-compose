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


## 27 octobre — log OpenClaw : state_owner_contention

La Workstation renvoie, après le repli vers les fichiers de logs privés :
\`service_state=failed\`, \`service_exit_status=78\`,
\`journal_source=private_file_tail\`,
\`journal_pattern=state_owner_contention\` avec 115 lignes analysées.
C'est un **indice sérieux** de conflit sur
\`~/.openclaw/state/openclaw.sqlite\`, mais ce log est historique.
Il ne suffit pas à démontrer qu'un PID détient toujours la base.

Le 26 octobre, le PID **3713** détenait l'état du Gateway ancien.
Ce PID pourrait être désormais terminé, réutilisé ou remplacé
par un autre processus. Il serait dangereux d'exécuter
\`kill 3713\`, \`pkill openclaw\` ou de supprimer les fichiers
SQLite, WAL, SHM ou de location simplement à partir du journal.

### Prochaine étape : recouper le journal avec la machine en lecture seule

La PR #285 contient désormais :
\`scripts/workstation/diagnose-openclaw-state-owner.py\` et
\`just openclaw-state-owner\`. Le script :
- récupère la **dernière** entrée de contention dans un log privé
  vérifié, sans afficher son contenu ni le PID ;
- inspecte sans modification le statut de ce PID sous \`/proc\` ;
- consulte \`fuser\` sur les fichiers SQLite existants, \`-wal\`
  et \`-shm\` sous \`OPENCLAW_STATE_DIR\` ;
- distingue \`historical_holder_no_current_opener\`,
  \`logged_holder_still_has_sqlite_open\`,
  \`different_sqlite_opener_observed\`,
  \`logged_pid_alive_without_sqlite_opener\` et
  \`current_owner_unverified\`.

Un PID actif peut avoir été **réutilisé**. Même si son numéro est
présent dans \`fuser\`, la relation de propriété durable n'est pas
prouvée sans vérifier la session/le bail d'OpenClaw.
Le contrôle \`fuser\` peut être incomplet pour des processus d'autres
comptes. L'absence d'un fichier ouvert au moment de la sonde
**n'autorise pas** une suppression de verrou ni une migration.

**Exécuter depuis la branche PR #285**, dans un worktree existant
ou fraîchement synchronisé, sans démarrage ni upgrade :

\`\`\`bash
python3 -m unittest discover -s tests \
  -p 'test_openclaw_state_owner.py' -v
just openclaw-state-owner
\`\`\`

En cas de détenteur actuel confirmé, identifier le service propriétaire
avant un éventuel arrêt ordonné. S'il n'existe plus, explorer le
contrôle de bail interne d'OpenClaw et les étapes de récupération
documentées ; ne pas conclure que la base est corrompue.

Aucune nouvelle sauvegarde, réinstallation npm, \`doctor --fix\`,
réparation de plugins, \`kill\`, \`systemctl restart\` ou modification
SQLite n'est réalisée.


### Précision : fichiers de verrou natifs OpenClaw

Le contrôle du détenteur examine aussi les fichiers réguliers
\`state.*.lock\` du répertoire
\`$OPENCLAW_STATE_DIR/state/locks/openclaw-state-owners/\`.
OpenClaw peut utiliser ces fichiers de verrou **en plus** de
\`openclaw.sqlite\`, \`-wal\`, \`-shm\`. Un PID qui ne détient plus
de descripteur SQLite peut encore détenir un verrou natif.
Les chemins sont limités, sans symlink et contrôlés par propriétaire.

Les sorties supplémentaires sont
\`native_lock_inventory=present|none_observed|unverified\`,
\`state_openers=present|none_observed|unknown\`,
\`logged_holder_in_state_openers=yes|no|unknown\` et
\`state_owner_diagnosis=<code fixe>\`.
Même \`none_observed\` **n'autorise pas** le nettoyage d'un
fichier de location ni ne prouve qu'un bail n'existe plus.
Les identifiants de PID restent volontairement non affichés.

Voir la documentation OpenClaw relative aux fichiers de lock natifs
et au contrôle d'admission de la base :
https://github.com/openclaw/openclaw/blob/main/docs/reference/database-schemas.md


## 27 octobre — Doctor a redémarré le Gateway après migration

**Nouvelle preuve opérateur.** \`openclaw doctor --fix\`, exécuté avec Node
24.22.1 et le paquet géré OpenClaw 2026.10.7, a terminé par :
\`Gateway restarted and verified after Doctor repair.\`

Ce n'est **pas** la preuve indépendante que le navigateur charge
\`/chat/main\` : confirmer ensuite le serveur HTTP. Éviter un nouveau
\`doctor --fix\`, \`openclaw update\`, ou redémarrage manuel tant que le
Gateway reste actif et que les sondes n'ont pas été relues.

### Modifications réellement observées

- Doctor a enregistré un état de récupération avant réparation
  (\`.openclaw.update-captures/doctor-.../manifest.json\`).
- Les bases SQLite des agents \`main\`, \`cron\` et \`openclaw\`
  ont été migrées **v21 → v25**, avec un fichier \`.bak\` pré-migration
  pour chacune, ainsi qu'un backup pré-migration de l'état partagé.
- Doctor a reconstruit deux index canoniques de l'état partagé
  et mis à jour les reçus de fermeture et de livraison cron.
- Il a réparé les liens npm des plugins, rafraîchi \`codex\` et
  \`searxng\`. La migration différée \`codex\` est indiquée achevée
  en fin d'exécution ; un avertissement de migration \`slack\`
  est toujours présent. Ne pas relancer \`openclaw update repair\`
  sur la seule base d'un avertissement intermédiaire.
- \`openclaw.json\` a été modifié avec une copie
  \`openclaw.json.bak\` créée.
- Des éléments de Skill Workshop retirés ont été supprimés lors
  de la migration ; ne pas restaurer sélectivement ces fichiers
  sur les nouveaux schémas.

**Sauvegarde antérieure déjà vérifiée :**
\`~/Backups/openclaw/openclaw-20261026T000901Z-1138514.tar.gz\`.
Une copie opérateur existe dans \`/media/backup/lab/infra/openclaw/\`
(empreinte de la copie non confirmée). Ne restaurer aucune de
ces sauvegardes sur un état migré et actif.

### Vérification d'acceptation — lecture seule uniquement

\`\`\`bash
systemctl --user show openclaw-gateway.service \
  -p ActiveState -p SubState -p MainPID -p Result -p ExecMainStatus
ss -ltn '( sport = :18789 )'
curl --noproxy '*' --connect-timeout 2 --max-time 6 \
  -sS -o /dev/null -w 'healthz_http=%{http_code}\n' \
  http://127.0.0.1:18789/healthz
curl --noproxy '*' --connect-timeout 2 --max-time 6 \
  -sS -o /dev/null -w 'readyz_http=%{http_code}\n' \
  http://127.0.0.1:18789/readyz
curl --noproxy '*' --connect-timeout 2 --max-time 6 \
  -sS -o /dev/null -w 'ui_root_http=%{http_code}\n' \
  http://127.0.0.1:18789/
\`\`\`

HTTP 200 sur \`healthz\` et \`readyz\`, unité \`active\` et
racine HTTP joignable constituent une validation du Gateway ;
l'authentification de l'interface et les canaux demandent des
contrôles fonctionnels séparés. Si la racine répond mais pas
\`/chat/main\`, inspecter la route de la nouvelle Control UI
sans conclure à une panne du service.

### Dette différée, sans redémarrage supplémentaire

- Doctor signale que le drop-in systemd **opérateur** utilise
  \`openclaw.mjs\` alors que l'entrée attendue est
  \`dist/index.js\`, et que le \`PATH\` du service ne contient pas
  le dossier Node mise. **Ne pas réécrire une unité active et saine
  pendant la validation.** Traiter cette dérive dans un correctif
  isolé, avec vérification du chemin réel et de la parité du service.
- La migration Slack peut nécessiter une intervention dédiée.
  Codex a déclaré une migration différée terminée ; vérifier son
  statut actuel avant réparation.
- Des plugins \`diagnostics-prometheus\`, \`discord\`, \`matrix\`
  et \`whatsapp\` étaient signalés à une ancienne version ; ne pas
  mettre à jour tous les plugins durant la récupération du Gateway.
- Le contrôle de sécurité indique des **secrets en clair dans
  \`openclaw.json\`** (auth Gateway, clés LiteLLM et jetons Slack).
  Prévoir une migration progressive vers SecretRefs, sans divulguer
  les valeurs et avec un contrôle \`openclaw secrets audit --check\`.
- \`browser.extensionRelay.allowLegacyAuth=true\` doit être retiré
  seulement après migration de ses clients vers l'authentification v2.
- Les journaux de captures temporaires volumineux sont conservés
  en attente d'un inventaire sûr ; ne pas les supprimer maintenant.

**Critère Done P0 :** Gateway \`active\`, \`/healthz=200\`,
\`/readyz=200\`, Control UI HTTP accessible, sans nouvelle contention
sur SQLite. La gestion des plugins, du service systemd et des
secrets reste une dette distincte et ne doit pas bloquer
l'acceptation du Gateway si celui-ci est sain.


## 27 octobre — P0 Gateway confirmé sain, UI racine HTTP 200

**Validation sur Workstation après `openclaw doctor --fix` :**

```text
ActiveState=active
SubState=running
Result=success
MainPID=3750286
healthz=200
startupz=200
readyz=200
root=200
chat/main=404
```

**Done P0 (Gateway et HTTP) :** service actif ; serveur HTTP,
initialisation, admission des agents et URL racine répondent tous
`200`. La restauration fonctionnelle des canaux, du chat authentifié,
des plugins et des index mémoire reste à confirmer séparément.
**Ne pas relancer `doctor --fix`, `openclaw update` ou
`systemctl restart` pour ce seul résultat.**

La documentation OpenClaw confirme `http://127.0.0.1:18789/`
comme adresse par défaut de la Control UI. Elle documente aussi
`/chat/main` comme chemin valide dans certains cas ; le `404`
obtenu avec la requête `curl` générique ne permet pas de conclure
que cette route est obsolète. L'interface peut appliquer un repli
SPA différent selon l'en-tête HTTP `Accept`. Ouvrir d'abord
la **racine dans le navigateur** et naviguer depuis l'interface.
Si l'authentification WebSocket est demandée, utiliser la procédure
de pairing OpenClaw ; ne pas imprimer ni transmettre le jeton.

Le diagnostic `openclaw-gateway-listener` est corrigé pour envoyer
`Accept: text/html` sur les routes de navigation `/` et
`/chat/main`. Quand l'état, `healthz`, `startupz`, `readyz`
et la racine sont sains, le `404` de `chat/main` est affiché
mais **ne marque plus le Gateway en échec**.

Les dettes post-récupération demeurent : parité systemd PATH/entrée,
migrations/plugins, SecretRefs et protection de l'interface.
Elles doivent être abordées séparément, avec tests locaux et
sans perturber l'instance opérationnelle.

Sources :
- https://docs.openclaw.ai/dashboard
- https://docs.openclaw.ai/web/urls
- https://docs.openclaw.ai/web/control-ui
