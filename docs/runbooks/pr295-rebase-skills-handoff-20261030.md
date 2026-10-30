# PR #295 — rebase conservateur et skills manuels

**Date : 30 octobre 2026. Statut : protocole opérateur, aucun push/rebase exécuté ici.**

## État Git observé avant ce runbook

- PR Draft [#295](https://github.com/AlbanAndrieu/nabla-compose/pull/295),
  branche `fix/openclaw-diagnostics-fail-closed-20261030`.
- Au moment du contrôle : 121 commits PR en avance, 4 commits de
  `master` en retard ; **aucun chemin commun** dans les changements
  finaux des deux branches (88 contre 10). Un rebase peut néanmoins
  rencontrer un conflit logique ou des tests en échec.
- Les 96/96 configurations TrueNAS Apps ont été lues sans référence à
  `apps/openclaw/compose.yml` ; c'est une preuve sur les *configurations
  des apps*, pas un feu vert pour déplacer le sandbox ou ajouter le gitlink.
- Le runner de cet agent ne peut résoudre `github.com` directement,
  et le connecteur disponible ne fournit pas l'action rebase native.
  **Ne pas remplacer un rebase par un merge déguisé**, ne pas squasher
  les commits, ni réécrire les auteurs.

## Rebase exact, à exécuter sur Workstation

Sur la **Workstation uniquement** (pas de Git/apt de maintenance sur les
nœuds Talos, et aucun déploiement TrueNAS), préparer un checkout isolé
qui ne modifie pas le worktree principal :

```bash
set -Eeuo pipefail
cd ~/w/nabla-compose

BR=fix/openclaw-diagnostics-fail-closed-20261030
git fetch origin master "$BR"

# Le SHA sert de lease explicite ; ne pas ignorer un push concurrent.
OLD="$(git rev-parse "refs/remotes/origin/$BR")"
BASE="$(git rev-parse refs/remotes/origin/master)"
printf 'head=%s\nmaster=%s\n' "$OLD" "$BASE"

# La branche sauvegarde permet de retrouver tous les commits originaux.
git branch "backup/pr295-before-rebase-$(date +%Y%m%d-%H%M%S)" "$OLD"

WT="$(mktemp -d /tmp/nabla-pr295-rebase.XXXXXX)"
rmdir "$WT"
git -c submodule.recurse=false worktree add --detach "$WT" "$OLD"
printf 'rebase_worktree=%s\n' "$WT"

# Depuis le nouveau worktree :
cd "$WT"
git -c submodule.recurse=false rebase --no-autostash "$BASE"

# Ne pas pousser tant que ces commandes ne sont pas PASS.
python3 -m unittest discover -s tests -p 'test_openclaw_sandbox_global_binding.py' -v
python3 -m unittest discover -s tests -p 'test_openclaw_policy_relocation.py' -v
just openclaw-migration-evidence-test
just agent-skills-check
git diff --check "$BASE"...HEAD
git status --short
```

Si conflit : `git status`, résoudre manuellement la zone concernée,
puis `git rebase --continue` et **rejouer les tests**. Utiliser
`git rebase --abort` si la correction n'est pas évidente.
Éviter `git rebase -X theirs` / `-X ours` : des données
documentaires et politiques peuvent être perdues silencieusement.

Seulement après validation et relecture des commits :

```bash
# À lancer depuis le worktree rebasé :
# Vérifier l'identité du BR/OLD dans la session où ils ont été définis.
git push --force-with-lease="refs/heads/$BR:$OLD" \
  origin "HEAD:refs/heads/$BR"
```

`--force-with-lease` échoue si un autre agent a poussé depuis le
`git fetch`. Dans ce cas **NE PAS** forcer ; refaire le fetch,
inspecter les commits concurrents puis rebaser à partir du nouveau
HEAD. Le push peut déclencher des workflows selon la configuration :
vérifier la politique de déclenchement Draft/skip CI avant ce push.
Ne jamais désactiver les quality gates ou utiliser `--force` simple.
Après push, dans le dépôt principal, faire `git fetch` et vérifier le
SHA avant `git pull` ; les checkouts existants peuvent conserver
l'ancien historique.

## Skills manuels retrouvés (pas encore installés par ce runbook)

Source canonique :
[agent-skills-architecture.md](../agent-skills-architecture.md)
et [roadmap](../roadmap.md).

- `docker/skills:docker-compose-patterns` — [Docker Compose Patterns](https://www.skills.sh/docker/skills/docker-compose-patterns).
- `jeffallan/claude-skills:kubernetes-specialist` — [Kubernetes Specialist](https://www.skills.sh/jeffallan/claude-skills/kubernetes-specialist), pour Kubernetes hébergé sur Talos.

```bash
# Workstation, projet nabla-compose ; inspection des sources, SANS installation
npx skills add docker/skills --list
npx skills add jeffallan/claude-skills --list

# INSTALLATION MANUELLE FUTURE APRÈS REVUE/ACCORD EXPLICITE :
# npx skills add docker/skills --skill docker-compose-patterns
# npx skills add jeffallan/claude-skills --skill kubernetes-specialist
```

Avant l'installation, lire `SKILL.md` et les scripts/références
de chaque projet upstream, examiner les audits de sécurité et les
dépendances transitives. Confirmer le scope projet, pas `-g`.
Aucun troisième skill Talos n'est nommé par cette décision. La
gestion des nœuds Talos reste sous `talosctl` et les runbooks Nabla ;
aucun SSH, package manager, `kubectl apply` ou `helm upgrade`
implicite n'est autorisé.

Après installation **manuelle et approuvée** :
`just agent-skills-check`, `just quality` puis inspection du
`skills-lock.json` et du `git status`; ne pas générer de nouveaux
fichiers dans la PR sans revue.
