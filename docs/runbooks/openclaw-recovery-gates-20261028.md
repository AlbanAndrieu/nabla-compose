# OpenClaw Workstation — gates runtime, 429, digest et session cron

**28 octobre 2026 — Code prêt pour validation, aucun déploiement runtime attesté.**
Responsable : `nabla-compose` ; commandes exécutées **sur la Workstation uniquement**.
Aucun script ne réinstalle npm, ne redémarre le Gateway, ne modifie une
clé, un budget, un job cron, une session ou un fichier SQLite. Aucun modèle
n'est appelé par les nouveaux diagnostics.

## 1. Avant upgrade et après reboot — versions de Node et OpenClaw

```bash
cd ~/w/nabla-compose
git pull --ff-only
just openclaw-runtime-alignment-test
just openclaw-runtime-alignment-check
```

`runtime-contract.json` contient la paire Node/OpenClaw approuvée. Le
contrôle vérifie son alignement avec `mise.toml`, puis les fichiers
installés, la version du paquet et le `ExecStart` **effectif** de systemd
user. `PASS` exige les trois preuves. `BLOCKED` ou `UNVERIFIED`
interdisent une mise à jour ou un cutover automatique. Les chemins du
préfixe historique ou un Node actif dans le shell ne prouvent rien sur le
Gateway.

**Upgrade futur** : mettre à jour `mise.toml`, le contrat versionné, puis
adapter les scripts historiques encore épinglés à la version antérieure,
installer dans un préfixe isolé, tester le nouvel artefact hors service,
examiner le plan de changement, activer **uniquement après consentement**,
puis vérifier `ExecStart` et `/readyz`. Ne jamais lancer
`npm install -g` ou `openclaw update` au reboot.

### Garde systemd facultatif (PAS installé par la PR)

Le modèle `apps/openclaw/workstation/systemd/30-nabla-runtime-alignment.conf.example`
peut être installé **uniquement après** un `PASS` réel, vérification que
`%h/w/nabla-compose` est le checkout stable et revue de l'unité effective.
Il fait échouer le démarrage si le contrat est incohérent. Ne pas activer
ce garde avant un test de redémarrage supervisé, car un faux positif
bloquerait un Gateway sain. L'installation et le rollback restent
manuels ; la PR n'effectue ni `daemon-reload` ni redémarrage.

## 2. Rate limit 429 — preuves et confidentialité

```bash
just openclaw-429-triage-test
just openclaw-429-triage-no-admin
just openclaw-rate-limit-evidence-check
```

Le collecteur consulte les **150 derniers événements** journald du
Gateway, sur **30 minutes**, sans imprimer le contenu brut. Il ne classe
que des événements JSON structurés contenant un marqueur d'erreur HTTP
explicite et un code numérique. Les messages libres qui mentionnent
`429` ne sont **pas** des preuves. Si la sortie vaut
`attribution=unverified`, cela ne signifie pas que le Gateway n'a connu
aucun 429 : la version du Gateway peut ne pas émettre ce schéma JSON.
Corroborer avec les traces structurées LiteLLM avant toute RCA.

Pour enregistrer volontairement ces seules catégories :

```bash
just openclaw-rate-limit-evidence-capture
```

Quand aucun événement structuré n'est trouvé, le collecteur annonce
`store=not_written_no_structured_events` : cela **ne prouve pas**
l'absence de 429. En cas de journal inaccessible, le stockage n'est
pas revendiqué et la commande échoue clairement.

Le magasin est local, privé, sous
`~/.local/state/nabla-compose/openclaw/rate-limit-events.jsonl` :
dossier `0700`, fichier `0600`, déduplication par curseur journal
haché. Aucune clé, prompt, réponse du fournisseur, URL ou identifiant
de session n'est conservé. Ne pas publier les journaux bruts. Le
timer optionnel dans `apps/openclaw/workstation/systemd/` **n'est
pas activé** ; le vérifier d'abord au niveau runtime, sans requête
facturable.

Un cooldown désigne une temporisation d'un profil ou d'un modèle
après rejet. Un code HTTP 429 ne prouve pas à lui seul que le budget
est épuisé. Ne pas effacer des cooldowns ni hausser les quotas sans
`request_id`, source, modèle, clé virtuelle (identifiée uniquement
privément), motif de limitation et fenêtre de réinitialisation.

## 3. Digest quotidien — drift du skill

Contrat documenté : le tag upstream `v3.16.0` demande
`ITEMS_PER_SECTION = 3-5`, son template injecte ce paramètre dans
`--top`, alors que `summarize-merged.py` exige un entier. Le
job déclaratif du dépôt demande `ITEMS_PER_SECTION = 5`, mais
`review_only_no_automatic_reconcile` : ce n'est pas une mutation runtime.

```bash
just openclaw-digest-top-test
just openclaw-digest-top-check
just openclaw-cron-recovery-plan
```

Si `digest_action=review_items_per_section_5_in_ui`, ouvrir **le job
existant** dans la Control UI, conserver le template/version installés
et remplacer uniquement le paramètre par `5` après comparaison du
job. Retirer les injonctions `--top 5` dupliquées qui avaient été
ajoutées au prompt. Ne pas créer un deuxième job, ni changer les
destinations. La présence du hash upstream dans le contrat prouve la
version *étudiée*, **pas** la version installée. Une exécution
planifiée ultérieure devra produire un rapport réel avant DONE.

## 4. `agent:cron:main` — recréer le bon parcours, pas le SQLite

```bash
just openclaw-cron-parent-test
just openclaw-cron-parent-check
just openclaw-cron-session-maintenance-check
just openclaw-cron-recovery-test
just openclaw-cron-recovery-plan
```

Le plan lit les agents configurés et le catalogue de sessions via
la CLI native, sans afficher les clés de session. Si `cron_agent=present`
et `cron_main_reference=absent_in_reported_complete_catalog`, la
bonne action est `create_new_cron_conversation_in_ui` : ouvrir une
**nouvelle** conversation associée à l'agent `cron` dans l'UI
supported de la version installée, sans réutiliser l'URL orpheline.
Si l'agent n'est pas configuré, **revoir d'abord la configuration**.
Une maintenance `sessions cleanup` réussie ne crée pas de session
principale. Le plan n'exécute jamais `doctor --fix`, `/new` sur
l'ancien lien, `cron run`, `sessions delete`, ni de SQL direct.

**DONE** : `cron` identifié, session principale créée via le parcours
natif supporté puis visible dans un catalogue complet ; chat fonctionnel
vérifié séparément (une vérification de modèle pourrait coûter des tokens).

## Sources

- https://docs.openclaw.ai/cli/sessions
- https://docs.openclaw.ai/cli/cron
- https://docs.openclaw.ai/help/faq-models
- https://github.com/draco-agent/tech-news-digest/blob/v3.16.0/references/digest-prompt.md
- https://github.com/draco-agent/tech-news-digest/blob/v3.16.0/scripts/summarize-merged.py

## 5. Une commande de diagnostic transverse (sans apply)

```bash
just openclaw-recovery-readonly-test
just openclaw-recovery-readonly
```

La recette exécute indépendamment l'alignement du runtime, les états de
cooldown des modèles, les événements 429 structurés et le plan du digest /
de la session principale cron. **Chaque section est tentée**, même si
une précédente échoue. `probe_failures=0` signifie uniquement que les
commandes ont terminé avec un code 0 ; cela ne prouve pas l'absence de
429 ni le bon fonctionnement du chat. Les sondes restent en lecture seule.

## Durcissement des preuves (30 octobre 2026)

Les commandes `diagnose-openclaw-model-cooldowns.py` et
`diagnose-openclaw-cron-parent.py` retournent maintenant un état
**non nul** lorsque l'information essentielle manque : CLI absente,
schéma `unusableProfiles` inaccessible, ou session principale `cron`
non démontrée. Il est possible qu'une sortie en lecture seule
précédemment classée `completed` apparaisse désormais `failed`
dans l'agrégateur. Cela signale une preuve manquante ou un incident
encore ouvert, **pas** nécessairement une nouvelle panne du Gateway.

Les CLI des sondes cooldown, cron, digest et maintenance sont
résolues par `scripts/workstation/openclaw_runtime_paths.py` en
comparant `mise.toml` au contrat `runtime-contract.json`.
Si les versions divergent, aucun exécutable ancien trouvé dans
`PATH` ne doit être invoqué ; le diagnostic se déclare non vérifié.
Le récupérateur historique d'upgrade reste explicitement versionné :
ne pas l'exécuter comme simple sonde.

Pour valider **uniquement le code** dans la Workstation :

```bash
just openclaw-recovery-quality
```

Ensuite, pour la preuve runtime (lecture seule, aucune génération
de modèle) :

```bash
just openclaw-recovery-readonly
```

La création d'une nouvelle session `cron` est un **tour d'agent**
pris en charge par OpenClaw (CLI `openclaw agent --agent cron` ou
Control UI), qui consomme potentiellement des tokens. Ce n'est pas une
conséquence de `sessions cleanup` et le présent runbook ne l'exécute
pas. Référence : https://docs.openclaw.ai/cli/agent

## Heartbeat historique — réintégration déclarative (30 octobre 2026)

L'original **complet** du `HEARTBEAT.md.before-fix` et le clone git-crypt
ne sont pas présents dans ce dépôt. Les 14 capacités ci-dessous proviennent
de l'inventaire déjà rédigé dans `LEGACY_HEARTBEAT_RECOVERY.md` : Workboard,
CalDAV, santé, Gmail, WhatsApp, Obsidian, doctor, documentation,
Loki, velocity, brainstorm, briefing, digest et contrôle hebdomadaire.
Le fichier `heartbeat-restoration.policy.json` garde les fréquences
originelles comme **références**, sans prétendre avoir récupéré des secrets.

Le candidat `HEARTBEAT-RESTORED.candidate.md` conserve une
checklist concise en lecture seule, sans bloc `tasks:` actif : la
configuration du monitor et les tâches planifiées natives doivent être
revues séparément selon la version installée (le scratch en base peut
remplacer `HEARTBEAT.md`). La politique propose 2h pour le heartbeat,
6h pour le suivi Workboard et 12h pour les diagnostics, non activés ;
les connecteurs privés CalDAV/Gmail/WhatsApp/Obsidian restent des jobs
séparés et inactifs tant que leurs ACL et destinataires ne sont pas vérifiés.
Le vrai `HEARTBEAT.md` demeure **comment-only** pour éviter un réveil
LLM récurrent à 30 minutes. **Ne pas appliquer** le candidat avec le
GitOps actuel : il faut d'abord attester la version OpenClaw active,
les cooldowns et le budget, puis revoir une config effective avec
`every=2h`, `isolatedSession=true`, `lightContext=true`,
`skipWhenBusy=true`, `target=none` et `activeHours=08:00–22:00`
Europe/Paris. La version OpenClaw peut utiliser un scratch en base :
un simple fichier copié ne prouve pas son activation.

```bash
just openclaw-heartbeat-restore-test
just openclaw-litellm-dual-logs-test
just openclaw-litellm-dual-logs-check
just openclaw-recovery-readonly
```

### Diagnostics des deux LiteLLM

La collecte distingue explicitement :
- **Workstation** : Docker `litellm-litellm-1` ou `litellm`, puis
  `journalctl --user -u litellm.service` ;
- **TrueNAS** : lecture des logs de `litellm` par SSH vers
  `albandrieu@172.17.0.24:9922`, host key vérifiée, BatchMode et
  agent forwarding désactivé ; jamais d'appel `sudo` automatique.

Le résultat `coverage=both` exige deux sources réellement lisibles ;
`partial_or_unverified` (code 2) interdit de conclure que l'autre proxy
est sain ou sans erreurs. Les catégories (rate-limit, budget, auth,
upstream, timeout) sont des **indices textuels** et ne prouvent pas
l'identité d'un appelant ; conserver la corrélation request_id/alias
privée pour une RCA des 429.

**Préconditions SSH** : un accès clé SSH non interactif déjà autorisé,
une host key connue, et le droit **préexistant** de lire les logs Docker
sur TrueNAS. Ne pas placer l'utilisateur dans le groupe `docker`
automatiquement : cette appartenance donne des privilèges importants.
Si le compte ne peut pas lire `docker logs`, conserver `unverified` et
privilégier l'API TrueNAS `app.container_log_follow` avec un rôle
`APPS_READ` dédié lors d'un futur changement de transport authentifié.
Cette API nécessite de confirmer le conteneur et un client adapté ; le
présent diagnostic **n'invente pas** une disponibilité ou une ACL.

Le collecteur ne sauvegarde ni n'imprime les logs bruts ou credentials,
limite la fenêtre à 1–24 heures et les 300 dernières lignes, et n'envoie
aucune inférence. Une cause 429 n'est établie qu'après corrélation
structurée, pas avec des compteurs de texte.

Un échec d'accès affiche désormais seulement un code de raison fixe parmi
`ssh_host_key_unverified`, `ssh_auth_denied`, `docker_permission_denied`,
`container_missing`, `timeout`, `command_unavailable`, `log_window_oversized`
ou `unverified`. Aucun texte d'erreur distant n'est reproduit.
