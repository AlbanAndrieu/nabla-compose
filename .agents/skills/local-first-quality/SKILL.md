---
name: local-first-quality
description: Converge formatter, lint, generated artifacts, targeted contracts and the final publication gate locally before consuming remote CI.
---

# Local-first quality

## Consignes de rédaction (inspirées de l'ASD-STE100)

Explique les diagnostics et les procédures en français clair. Utilise
des phrases simples et directes. Décris **une seule action par étape de
procédure**. Évite les synonymes inutiles et conserve les noms exacts
des commandes, paramètres, chemins, services et états. Distingue les
faits observés, les mesures non vérifiées et les actions proposées.

Cette règle s'inspire de l'ASD-STE100. Elle ne prétend pas établir une
conformité formelle à la norme.

## Environnements d'exécution Nabla (obligatoire)

Distinguer **l'hôte où tourne la commande** avant de proposer une recette
Docker, OpenClaw ou LiteLLM :

| Hôte | Checkout canonique | Exécution des opérations TrueNAS |
| --- | --- | --- |
| TrueNAS | `/mnt/cpool/compose/nabla-compose` | locale : `sudo -n python3 scripts/truenas/...` |
| Workstation Ubuntu | `~/w/nabla-compose` | distante : alias SSH `truenas` (port 9922) |

- Ne jamais appeler `ssh truenas` **depuis TrueNAS** pour administrer
  `litellm`. Ne pas supposer SSH port 22 ni un forward local 14000 sur TrueNAS.
- Le checkout canonique TrueNAS et les recettes `just` sont des chemins
  d'exploitation, pas des worktrees temporaires de développement.
- Pour `openclaw-truenas-virtual-keys-plan|apply|status`, utiliser
  `scripts/truenas/dispatch-openclaw-litellm-keys.py` : le script reconnaît
  le checkout TrueNAS et utilise Docker local, sinon il utilise SSH depuis
  la Workstation. `status` ne crée aucune clé.
- Donner le **chemin du checkout** dans le bloc opérateur et éviter de
  mélanger les commandes de tunnel Workstation et les commandes locales
  TrueNAS. Vérifier les deux chemins par des tests hors ligne, y compris
  un cas négatif qui refuse SSH sur TrueNAS.
- Exécuter les **tests unitaires Python sur Workstation par défaut**.
  Ne pas demander leur répétition sur TrueNAS : les tests hors ligne
  simulent les deux environnements. Réserver TrueNAS aux preuves runtime
  (Docker, PostgreSQL, clés virtuelles) et aux actions locales qui en dépendent.
  Depuis Workstation, les recettes runtime utilisent le dispatch SSH existant.

## Workflow IA — chemin court

**Décision en six actions, avant toute modification :**

1. **Périmètre :** lire la PR choisie par l'utilisateur, sa branche et
   son HEAD exact. Refuser toute écriture si elle est fusionnée ou fermée.
2. **Contexte minimal :** lire seulement les fichiers utiles et le premier
   test en erreur. Ne pas explorer toute la roadmap ou les logs CI PASS.
3. **Isolation :** travailler sur un worktree unique par agent ; garder
   le dépôt Git canonique et les preuves hors des répertoires éphémères.
4. **Preuve :** reproduire d'abord l'échec, corriger puis exécuter le test
   concerné avec au moins un cas négatif. Élargir à la gate locale après PASS.
5. **Publication :** revérifier le HEAD GitHub puis mettre à jour la **même
   PR** avec un fast-forward et une comparaison du SHA attendu. Utiliser
   [skip ci] si la CI payante est explicitement suspendue.
   Utiliser une **optimistic file update** (SHA attendu) pour toute édition
   via GitHub : ne pas écraser le contenu modifié par un autre agent.

6. **Rapport :** HEAD, fichiers, L0/L1/L2/L3 réellement atteints,
   validations NOT_RUN, risques restants et **un seul bloc opérateur**
   pour les contrôles impossibles côté agent.

**Optimiser le coût d'exécution :** privilégier les outils déjà installés,
un appel groupé aux fichiers liés et un seul lot de commits cohérent.
Après un échec déterministe, ne pas relancer des commandes identiques.
Ne pas confondre compilation syntaxique, tests ciblés, gate complète et
preuve sur le matériel réel.

## Mode rapide Node 22 / npm 10 (compatibilité, local-only)

Le dépôt conserve **Node 24** dans `.nvmrc` et `mise.toml`. Si l'agent
dispose de **Node 22.x et npm 10.x**, exécuter `just node22-fast` depuis
un worktree isolé. Sans `just`, exécuter
`npm --offline run test:fast:node22`.

Ce mode utilise uniquement `node:test` et la bibliothèque standard.
**Ne pas lancer** `npm install`, `npm ci`, `npx`, un workflow GitHub ou
un téléchargement automatique pour ces contrats. Refuser une version
différente plutôt que modifier la configuration Node du dépôt.
Le test ne démarre aucun conteneur et ne touche pas aux secrets.

La preuve du mode Node est **L1 rapide**, pas la quality gate.
Exécuter ensuite les tests Python/Compose/Shell ciblés et `just quality`
sur le HEAD exact. S'il n'existe pas de checkout complet accessible,
ne pas attribuer au HEAD une validation faite sur une fixture partielle.
Lire le [runbook Node rapide](../../../docs/runbooks/node22-local-fast-tests.md)
pour les contrôles et limites.

## Shell parent et isolation uv entre worktrees (P0)

**Ne jamais appliquer set -euo pipefail au shell interactif du client.**
Ce shell peut être Bash ou zsh. Un échec ou une variable non définie peut
fermer le terminal. Tout bloc multi-commandes doit s'exécuter dans un
**Bash enfant** (heredoc bash avec marqueur entre apostrophes, ou script
versionné lancé avec bash). Un script exécutable doit d'abord refuser
d'être sourcé ; appliquer set -Eeuo pipefail uniquement ensuite.
Tester un échec intermédiaire : les commandes suivantes ne doivent pas
tourner, le code de sortie doit être non nul et **le shell parent doit
rester utilisable**. Ne pas donner un bloc opérateur qui suppose un cwd
particulier, un repo sous /tmp ou une branche déjà active.

**Contrat Python multi-agent approuvé :**
- Lire les versions depuis mise.toml/.python-version et les dépendances
  depuis pyproject.toml + uv.lock, sans changer le lockfile pour un test.
- Utiliser uv sync --locked dans chaque worktree de développement.
  Conserver **une .venv dédiée à chaque worktree** ; ne jamais partager
  une .venv ou VIRTUAL_ENV entre agents.
- Partager **seulement le cache de téléchargement uv**
  (typiquement $HOME/.cache/uv). Le cache est réutilisable, les paquets
  installés et les fichiers du worktree ne le sont pas.
- Exécuter explicitement le Python de la .venv sélectionnée. Un python3
  dans PATH avec pytest/PyYAML manquants est un prérequis BLOCKED,
  **pas** une régression du générateur.
- Ne pas sourcer .envrc ni activer direnv automatiquement, car cela peut
  installer des outils ou charger des secrets. Ne pas installer dans
  le Python global ni lancer mise install global.
- Vérifier les dépendances avant les tests ; exécuter les générateurs
  en mode --check et les tests ciblés avant la gate large. Ne jamais
  interpréter un échec d'environnement comme un PASS de quality gate.

## Exécution opérateur : reprise et persistance

- Le répertoire **/tmp est éphémère** : ne jamais le considérer comme un
  checkout permanent après un redémarrage. Le chemin
  /tmp/nabla-yubikey-pr259 est uniquement une référence historique.
- Stocker la base Git durable sous
  \`$HOME/.local/share/nabla/git/nabla-compose.git\` (dépôt bare), ou
  dans \`$NABLA_AGENT_STATE_DIR/git/nabla-compose.git\` si un volume
  persistant explicite est nécessaire. Documenter si HOME n'est pas durable.
- Exécuter \`git ls-remote\` pour identifier le HEAD exact de la PR.
  Ne lancer \`git fetch\` que si l'objet Git n'est pas présent dans le
  dépôt bare ; ne jamais se fier au \`FETCH_HEAD\` partagé.
- Créer un worktree **détaché**, privé et unique (\`mktemp -d\`, mode
  0700), associé à un SHA précis. Verrouiller les opérations sur les
  métadonnées Git avec \`flock\`. Un worktree n'isole pas la base
  d'objets Git commune ; ne pas y faire de rebase/GC/force-push concurrents.
- Garder le checkout original intact, même s'il est sale ou en detached
  HEAD. Ne jamais tenter \`git pull\` automatiquement dans cet état.
  Ne jamais utiliser \`reset --hard\`, \`clean -fd\`, \`switch -f\` ou
  \`worktree prune\` pour supprimer des modifications d'autrui.
- Supprimer seulement le worktree temporaire propre créé par
  **l'exécution courante**. Préserver et signaler un worktree modifié
  ou un nettoyage impossible. Ne jamais supprimer les fichiers publics
  ou les sauvegardes sans demande explicite.
- En cas de premier démarrage sans dépôt, le script doit créer un dépôt
  bare privé et télécharger le SHA de la PR, puis lancer les tests.
  Ne pas demander un clonage manuel. Fournir **un seul bloc Bash**
  indépendant du répertoire courant pour amorcer le script versionné.
- **Ne pas confondre dérive fast-forward et réécriture d'historique.**
  Si la PR avance entre deux lectures pendant un bootstrap, exécuter les
  tests sur le SHA initial épinglé **sans le remplacer**. Vérifier avec
  `git merge-base --is-ancestor SHA_PINNÉ SHA_OBSERVÉ` que la branche
  n'a avancé que par fast-forward. Bloquer si l'objet n'est pas disponible,
  si la branche diverge ou si l'historique a été forcé. Indiquer le SHA
  réellement testé et le HEAD plus récent dans le rapport ; ne jamais
  déclarer la gate verte pour un HEAD différent.
- **Limiter un pin SHA opérateur au bootstrap.** Après avoir comparé
  le SHA distant au commit attendu, ne pas transmettre
  `NABLA_PR274_EXPECTED_SHA` aux tests imbriqués : leurs dépôts Git
  synthétiques possèdent leurs propres SHA. Supprimer aussi ce pin de
  l'environnement copié par leurs fixtures. Conserver un test explicite
  de rejet de SHA incorrect avant toute opération.
- **Toute commande opérateur proposée en un bloc est exécutée d'un coup.**
  Ne jamais laisser un `set -euo pipefail` isolé dans le shell interactif,
  ni une série de commandes dont les suivantes seraient lancées après un
  échec. Placer les actions dans un processus enfant `bash <<'TAG'`,
  ou dans un script versionné exécuté avec `bash`. Rendre le code de
  retour, le premier échec, le chemin des journaux privés et le chemin
  du worktree préservé. Valider au moins un scénario négatif qui
  **laisse le shell parent vivant**.
- Pour la qualité de la PR #274, utiliser le [bootstrap en une étape]
  (../../../docs/runbooks/2026-10-24-pr274-local-quality-one-shot.md)
  et le lanceur `scripts/workstation/run-pr274-local-quality.sh`.
  Le launcher utilise `QUALITY_BASE_REF` égal au vrai `master` épinglé,
  jamais `HEAD~1` sur un worktree détaché. La régénération locale
  des projections ne permet pas de passer `--publish` automatiquement.
- Échouer immédiatement et clairement à la première étape bloquante ;
  ne jamais poursuivre vers le matériel après un test en erreur.
  Réutiliser les preuves publiques cryptographiquement validées ;
  pas de PIN, de génération PIV82 ou de mutation SOPS implicite.

La référence d'implémentation est
\`scripts/workstation/run-age-yubikey-pr274-readonly.sh\`.
Lire \`docs/runbooks/yubikey-piv82-postmerge-diagnostics.md\` pour le
bootstrap Git **sans dépendance à /tmp**.

## Worktree Python : dépendances verrouillées avant la gate

**Détecter d'abord l'environnement** : un worktree Git est un checkout
de fichiers, pas une copie de .venv, des caches ou de l'autorisation
direnv/mise. Évaluer les prérequis **avant** d'interpréter les erreurs
PyYAML/pytest comme une régression applicative.

Séquence obligatoire pour une tâche Python/topologie :

1. L0 : vérifier pyproject.toml, uv.lock, .python-version, la branche,
   l'emplacement du checkout et les exécutables Python/uv disponibles.
   Préférer just preflight (Git-only) avant une installation.
2. Préparer **uniquement** l'environnement Python du worktree :
   scripts/quality/with-worktree-python.sh installe le groupe dev
   (incluant test et pre-commit) du uv.lock avec uv sync --locked --no-install-project.
   N'autoriser aucun changement de uv.lock, de pyproject.toml ou de
   configuration globale pour contourner un prérequis.
3. Le lanceur utilise .venv propre au worktree et le cache partagé de
   téléchargements uv. Il contrôle un marqueur de hash uv.lock +
   pyproject.toml + version du Python ; il évite la resynchronisation à chaque commande
   quand la preuve de dépendances reste valide.
4. L1 : exécuter les 3 générateurs en mode --check, puis les tests
   ciblés. Ne jamais régénérer automatiquement Homarr/Gatus/AutoKuma
   pendant un contrôle. Si un générateur échoue, lire son premier
   diagnostic ; distinguer MISSING_DEPS, TOOL_MISSING et DRIFT.
5. L2/L3 : lancer la gate complète seulement après un préflight
   Python PASS. Si elle détecte une dérive réelle, préserver le diff
   et ne lancer la régénération qu'avec une décision explicite.

**Commande canonique (une seule, dans un worktree)** : just topology-qa.
Cette recette prépare la .venv puis enchaîne les contrôles et
just quality ; elle s'arrête au premier échec. La commande
just quality prépare également son environnement Python avant
d'exécuter le gate existant. Utiliser --check pour l'audit, et
topology-artifacts-refresh uniquement pour un changement intentionnel
des projections.

**Choix d'outils** : uv est l'autorité des dépendances Python versionnées
(pyproject.toml + uv.lock). mise.toml sélectionne les exécutables
(python, uv, just) déjà installés ; ne pas effectuer un mise install global
ni modifier mise.lock pour un contrôle de topologie. .envrc peut exécuter
des commandes de mise en place et charger des fichiers secrets :
ne jamais déclencher direnv allow, de source .envrc, de curl | bash ou
une activation automatique dans un agent sans revue explicite.
Si uv manque, afficher BLOCKED et la dépendance précise, sans installer
de binaire depuis une source non revue. Ne pas utiliser pip install
dans le Python global ou le --break-system-packages.

Un défaut de prérequis ne prouve **jamais** que le générateur a produit
des fichiers erronés. Après un échec, n'élargir ni les tests ni la CI
avant d'avoir rétabli l'environnement et reproduit le premier défaut
sur le SHA exact.

## Skills externes : contrôle local avant installation

`AGENTS.md` et `docs/agent-skills-architecture.md` définissent la
priorité des instructions. Avant de proposer l'installation d'un skill
externe, lire le `SKILL.md` et ses scripts, vérifier les autorisations,
les accès réseau et les alertes de sécurité. Demander **l'accord explicite**
de l'utilisateur pour chaque skill, même si la roadmap le prévoit.

Préférer une installation **limitée au projet de développement**, jamais
directement sur TrueNAS/Talos. Ne jamais lancer de mutation, de
redéploiement ou de CI payante pour valider une documentation de skill.
Exécuter `just agent-skills-check` pour détecter une dérive des règles
du dépôt avant une PR Ready, puis les contrôles locaux applicables.

## Efficiency for multi-repository security changes

- Inspect the exact selected PR head and only relevant files and failed checks.
  For the very large roadmap, read only bounded section ranges.
- Batch related edits into one Git tree/commit, use expected-HEAD compare-and-swap
  updates and reconcile a concurrent writer by comparing changed paths.
- Run offline targeted tests and formatting before a commit whenever possible;
  do not repeatedly poll GitHub checks without new evidence.
- Fetch only the failing job's relevant log lines, never full successful logs.
  CI remains a security gate: do not silence BetterLeaks, CodeQL, Trivy,
  Checkov, formatter or executor-mode failures to save time.
- Distinguish static preparedness, CI success at exact HEAD and actual
  TrueNAS/Vaultwarden/DefectDojo runtime acceptance.


Use this skill for CI failures, quality-gate work, PR continuation, formatter/linter
fixes, or any task where remote CI should remain a safety net rather than the
edit loop.

## Branch and environment ownership (mandatory)

- Resolve the **user-selected open PR and its head branch** before editing.
  When the user specifies a branch, use exactly that branch for all writes.
- **Never push, commit or update refs directly on `master` or another
  protected base branch.** Use a reviewed feature branch and its open PR;
  do not merge unless explicitly requested.
- Do not switch to a different PR for thematic reasons without the
  operator's explicit authorization. Code already merged into master
  remains available to the PR through its base; do not duplicate it merely
  because it is absent from the PR's *Files changed* tab.
- Make code, documentation and Git file-mode changes in the **agent
  environment first**. Run available syntax and targeted contract tests,
  publish to the chosen PR, and verify the exact remote HEAD and Git
  `100755` index modes before declaring completion.
- Request actions on TrueNAS, a workstation or production **only as a
  last resort**, for hardware-dependent/runtime acceptance or a proven
  agent-side blocker. Prefer read-only validation; never delegate ordinary
  repository edits and chmod fixes to the operator by default.
- If the agent's GitHub branch write fails, report the exact failure and
  avoid claiming publication. Recover within agent tools before proposing
  a minimal, reversible operator workaround.

## Principle

Use the cheapest deterministic evidence that can falsify the current patch, then
widen only after it is green:

```text
just context
  -> just preflight
  -> targeted test/config check
  -> just loop
  -> review deterministic diff
  -> commit logical batch
  -> mise run agent-pre-push
  -> one push
  -> inspect existing remote checks without rerunning them
```

Never claim the complete local gate is green unless `agent-pre-push` (or the
equivalent complete gate) actually passed on the exact published HEAD.

Use explicit evidence levels in reports:

- **L0 · static**: exact-HEAD file/config inspection only;
- **L1 · targeted**: narrow unit/contract/config checks executed;
- **L2 · loop**: deterministic fixes plus changed-file Pre-commit contracts converged;
- **L3 · publication**: full local `agent-pre-push` passed on the exact HEAD.

Only L3 may be summarized as the complete local quality gate being green.

## Iteration loop

Before installing dependencies or widening the test scope, get bounded context
and run the Git-only safety gate:

```bash
just context
just preflight
# equivalent: mise run agent-context && mise run agent-preflight
```

This catches protected-branch, stale-base, destructive-diff and executable-bit
problems before spending time on Python/tool installation. Preflight is
branch-wide; it sees the complete PR delta against the comparison base.

After one bounded edit batch, run:

```bash
mise run agent-loop
# or
just loop
```

`agent-loop` runs `scripts/agent-quality-gate.sh --loop`. Its validation
scope is deliberately limited to the uncommitted working tree, staged files and
untracked files; already-committed PR history is revalidated by preflight and
the final publication gate. It:

- preserves the branch/base guard and checks destructive/executable-bit changes
  in the current edit batch;
- regenerates deterministic service artifacts;
- converges safe formatter/autofixer hooks on changed files;
- executes pre-commit contracts selected by the changed paths;
- runs expensive topology/runtime-primitive checks only when their inputs changed;
- deliberately defers the complete repository pytest suite to the publication gate.

If a deterministic tool modifies files, review that compact diff. Keep only
changes caused by the logical batch; do not accept unrelated generated churn.

If a check fails without changing files, fix the first concrete failure. Do not
repeat the same command and do not switch to GitHub Actions for diagnosis.

## Publication gate

Once the logical batch is committed:

```bash
mise run agent-pre-push
# or
just pre-push
```

This is the authoritative local publication evidence. It reruns deterministic
fixes, the complete unit/contract suite and the canonical formatter/linter/security
gate, and requires a publication-clean superproject.

If it exits with `QG_AUTOFIX_APPLIED`, review and commit/amend only those
changes, then rerun the same local command. Do not push before it is green.

## Remote CI policy

Remote checks are evidence, not an editor:

- inspect current PR/check status before starting another improvement when useful;
- never manually rerun a workflow merely to discover deterministic formatting,
  lint or unit-test failures that are reproducible locally;
- when the task explicitly requests no CI or credits are constrained, keep
  iterative commits CI-silent (for example with the repository's accepted
  `[skip ci]` convention) and rely on the local publication gate;
- after a push, inspect only the first failing workflow/job/step and widen logs
  only when necessary;
- do not weaken hooks, tests, security checks or generated-contract validation.

For the October 2026 TrueNAS/Git permission anomalies, duplicated Bash functions,
failed mocked executables and local-first troubleshooting, see
[`docs/incidents/2026-10-10-local-first-quality-truenas-git-permissions.md`](../../../docs/incidents/2026-10-10-local-first-quality-truenas-git-permissions.md).

## Annexes : chargement à la demande

Le skill principal reste court. Les règles détaillées et les précédentes
preuves opérateur sont conservées intégralement dans
[references/advanced-diagnostics.md](references/advanced-diagnostics.md).

Lire la section concernée **seulement après avoir classé l'incident** :

- Permissions Git, mode 100755, ACL et /tmp noexec : « Git executable »
  et « TrueNAS noexec ».
- Environnement Node, Python, pre-commit ou source indisponible :
  « Node.js », « Mandatory reproduction », « Mandatory executable »
  et « Exact-HEAD source recovery ».
- DNS, réseau, GitHub API, absence de dépendances : « Disconnected »,
  « API-only fallback » et « Tooling choice ».
- Dagger, ergonomie shell : sections correspondantes de l'annexe.

L'annexe n'est pas une liste d'étapes obligatoires pour chaque PR.
Ne pas en charger la totalité par défaut. La reproduction et
l'interdiction de mutations non autorisées restent obligatoires.

