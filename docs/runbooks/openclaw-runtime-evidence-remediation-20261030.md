# OpenClaw — corrections guidées par les preuves Workstation/TrueNAS (30/10/2026)

**PR #295**, pas de CI payante, pas d'automerge. Source des observations :
diagnostics exécutés par l'opérateur le 30 octobre. Les états `UNKNOWN`,
`UNVERIFIED` ou `exit=2` ne prouvent pas que le Gateway est DOWN.

## État attesté

- **Gateway READY** : healthz/startupz/readyz = HTTP 200, Node et systemd alignés ;
  0 profil en cooldown rapporté sur main/cron.
- Journaux Workstation : disponibles, **15 indices textuels d'erreurs auth**
  dans les dernières 300 lignes, pas de 429 textuel sur cet échantillon.
  Aucune attribution d'agent ni preuve d'absence historique de 429.
- TrueNAS : conteneur LiteLLM `litellm` running, `docker_permission_denied`
  pour l'utilisateur SSH. Cela ne signifie pas que LiteLLM est DOWN.
- TrueNAS : deux clés virtuelles existantes, scopes `openclaw-main` /
  `openclaw-cron` vérifiés, budget 2 chacune, spend 0, RPM/TPM **non rapportés**.
  Leurs modèles permis sont `workstation-qwen,qwen` (main) et
  `workstation-qwen` (cron) : ce n'est pas un grant `gpt-4.1`.
- `LITELLM_IDE_API_KEY` présent dans TrueNAS ; la clé
  **distincte** `LITELLM_FASTAPI_WORKSTATION_API_KEY` manque dans le
  conteneur : corriger l'injection FastAPI séparément. Les clés OpenClaw
  canoniques correspondent au runtime ; aucune régénération nécessaire.
- Cron : agent `cron` présent, `agent:cron:main` absent d'un catalogue
  complet de 21 sessions. Ne pas éditer SQLite.
- Digest : template `ITEMS_PER_SECTION=3-5` incompatible avec un entier
  `--top`. Valeur cible : `5`.
- Heartbeat : 100/100 exécutions ignorées car vide, aucune inférence
  ni livraison. Le comportement actuel est **volontaire**.
- Routes : `main` et `cron` pointent vers le LiteLLM GPU Workstation ;
  le modèle courant est `gpt-4.1`, absent du YAML TrueNAS. Embedding
  reste sur Workstation. Aucun cutover n'est attesté.

## A. Dépôt Git dirty : conserver les modifications

Depuis `~/w/nabla-compose` :

```bash
git status --short --untracked-files=no
git diff --name-only
git diff --cached --name-only
git submodule status --recursive
git -C fastapi-sample status --short
git -C apps/nabla-site-alban status --short
./scripts/truenas/update-application-submodules.sh --check
```

Le script `--check` classe désormais les changements suivis au lieu
de répondre seulement `Refusing...`. Le `--update` refuse toujours
un superprojet sale ; **ne pas** lancer `git reset --hard`,
`git clean -fd` ou stasher/supprimer automatiquement des modifications
internes de submodule. Pour mettre à jour des gitlinks, travailler sur
une branche propre, avec les modifications locales sauvegardées dans des
commits revus, ou un worktree isolé (déjà créé pour PR #295).

## B. Logs des deux LiteLLM

Sur la Workstation, depuis un checkout synchronisé de la PR :

```bash
just openclaw-litellm-dual-logs-test
just openclaw-litellm-dual-logs-check-sudo
OPENCLAW_TRUENAS_LOG_SUDO=1 just openclaw-migration-evidence-check
```

`--truenas-sudo-logs` est un **opt-in explicite** vers
`ssh ... sudo -n docker logs --since 2h --tail 300 litellm`.
Il exige une permission sudo **préexistante et non interactive** sur
TrueNAS. Aucun ajout au groupe Docker, aucun privilège accordé par le
script et aucune valeur de log brute imprimée. Si la politique sudo
exige un mot de passe, le résultat sera
`sudo_permission_unavailable` : ne pas demander au collecteur de le
contourner. Préférer ensuite un exporteur/compte en lecture seule
approprié.

La réussite du double collecteur signifie que deux sources de logs
sont lisibles. Les compteurs sont des indices textuels, **pas** une
corrélation 429 par request_id ou clé virtuelle.

## C. Clé admin TrueNAS déjà disponible

```bash
just openclaw-truenas-tunnel-check
just openclaw-truenas-master-env-check
# Lecture GET par tunnel SSH, pas de prompt ni secret affiché :
just openclaw-truenas-model-keys-tunnel-dedicated-nonstandard
```

Cette dernière recette utilise exclusivement la variable
`LITELLM_TRUENAS_MASTER_KEY` **exportée** dans le processus Workstation.
Elle n'accepte le préfixe non standard qu'avec l'opt-in explicite
`--allow-nonstandard-master` ; cela ne prouve pas que le serveur
acceptera la clé. Ne pas copier sa valeur dans le shell, le chat, la
sortie `env` ni Git. Un `401` signifie authentification non validée.

## D. Reconciliation des clés existantes

Sur TrueNAS seulement, avec le code GitOps actualisé :

```bash
cd /mnt/cpool/compose/nabla-compose
just openclaw-truenas-virtual-keys-test
just openclaw-truenas-virtual-keys-plan
just openclaw-truenas-virtual-keys-quota
```

Le `plan` utilise désormais `GET /key/info?key=<hash>` : si les
deux scopes et budgets sont attestés et non épuisés, il affiche
`provisioning=already_present_verified_noop` et réussit.
Même `--apply` n'émettrait aucun `POST /key/generate` dans cet état.
**Ne pas lancer apply**, les clés sont déjà installées.

Les budgets à 2 et une dépense nulle ne prouvent pas les limites RPM/TPM.
Les requêtes par clé, les limites fournisseur et les traces exactes
des 429 restent à corréler.

## E. Corriger le digest, puis la session cron

```bash
just openclaw-digest-top-check
openclaw automations edit --help
openclaw automations get 7ed5dd9a-da30-479f-b0eb-4cc494fb4966 --json > /dev/null
```

Dans **le job existant** via la Control UI (ne pas le dupliquer),
remplacer seulement `ITEMS_PER_SECTION = 3-5` par
`ITEMS_PER_SECTION = 5`. Vérifier que le template appelle `--top 5`,
puis relancer uniquement le contrôle `just openclaw-digest-top-check`.
Ne pas passer le prompt complet du job comme argument CLI : il pourrait
comporter des informations privées et apparaître dans la liste de
processus.

L'agent `cron` existe, mais sa session principale est absente.
La création d'une nouvelle conversation native peut consommer des tokens.
Ne la faire **qu'après** avoir vérifié le modèle effectivement utilisable
et la clé de l'agent. Pas de réparation SQLite ni de `doctor --fix`
automatique :

```bash
just openclaw-cron-recovery-plan
openclaw agents list
openclaw sessions --agent cron --limit 100 --json > /dev/null
```

Pour terminer, une conversation de test explicite via Control UI
sur l'agent `cron` avec session principale, puis nouveau diagnostic
`just openclaw-cron-parent-check`. Ne pas promettre qu'une simple
`sessions cleanup` recréera `agent:cron:main`.

## F. Heartbeat et bascule TrueNAS

Conserver le heartbeat **vide** pendant la correction digest/cron.
Les snapshots JSON du job et du scratch doivent être privés en 0600.
Vérifier leurs métadonnées et la révision du scratch sans afficher
leur contenu. Une restauration via `automations scratch --file`
et `--expected-revision` serait une **mutation** susceptible de
réactiver les inférences si le job est activé.

Préparer le nouveau modèle cible **avant** de modifier les routes :
les clés TrueNAS n'accordent actuellement pas `gpt-4.1`. Vérifier
l'alias exposé réellement, choisir `workstation-qwen` si pertinent,
conserver le GPU comme upstream, et faire le cutover `cron` puis
`main` avec SecretRef distinctes et rollback par agent.
Ne pas changer les embeddings simultanément.

Enfin, les deux warnings Slack du `openclaw config validate`
n'empêchent pas la readiness du Gateway. Les corriger après le P0,
sans `openclaw doctor --fix` non revu.
