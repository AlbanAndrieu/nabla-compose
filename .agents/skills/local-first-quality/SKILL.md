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
6. **Rapport :** HEAD, fichiers, L0/L1/L2/L3 réellement atteints,
   validations NOT_RUN, risques restants et **un seul bloc opérateur**
   pour les contrôles impossibles côté agent.

**Optimiser le coût d'exécution :** privilégier les outils déjà installés,
un appel groupé aux fichiers liés et un seul lot de commits cohérent.
Après un échec déterministe, ne pas relancer des commandes identiques.
Ne pas confondre compilation syntaxique, tests ciblés, gate complète et
preuve sur le matériel réel.

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
- Échouer immédiatement et clairement à la première étape bloquante ;
  ne jamais poursuivre vers le matériel après un test en erreur.
  Réutiliser les preuves publiques cryptographiquement validées ;
  pas de PIN, de génération PIV82 ou de mutation SOPS implicite.

La référence d'implémentation est
\`scripts/workstation/run-age-yubikey-pr274-readonly.sh\`.
Lire \`docs/runbooks/yubikey-piv82-postmerge-diagnostics.md\` pour le
bootstrap Git **sans dépendance à /tmp**.

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

