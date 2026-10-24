# PR #274 — Quality gate locale en une seule exécution

**Entrée opérateur canonique :** cette procédure lance un **processus Bash
enfant**. Copier et exécuter le bloc entier. Un contrôle en échec renvoie au
terminal courant, sans mettre `set -e` dans le shell interactif.

Ne pas reprendre l'ancien worktree `/tmp/nabla-topology-pr274` : il est
éphémère. Ne pas faire `git worktree add -b` une seconde fois ni `git pull`
dans le checkout de la workstation.

## Bootstrap autonome — une seule action

Le bootstrap récupère le SHA exact de la branche Draft PR #274 et copie le
lanceur versionné depuis ce SHA. Il conserve un cache Git bare privé sous
`~/.local/share/nabla/git/nabla-compose.git`, protégé par `flock`.
Le lanceur crée son propre worktree détaché et privé ; il ne touche pas
au checkout opérateur, même si celui-ci contient des modifications.

~~~bash
bash <<'PR274_QUALITY'
set -Eeuo pipefail
umask 077

remote=https://github.com/AlbanAndrieu/nabla-compose.git
ref=refs/heads/fix/homelab-operator-diagnostics-followup-20261024
state="${NABLA_AGENT_STATE_DIR:-${HOME}/.local/share/nabla}"
cache="$state/git/nabla-compose.git"

[[ -d "$HOME" && ! -L "$state" && ! -L "$state/git" &&
   ! -L "$cache" && ! -L "$state/quality-reports" ]] ||
  { echo 'BLOCKED: unsafe persistent Git state' >&2; exit 2; }

mkdir -p -m 0700 "$state/git" "$state/quality-reports"
exec 9>"$state/.pr274-git.lock"
flock -w 20 9 || { echo 'BLOCKED: Git cache busy' >&2; exit 2; }

if [[ ! -d "$cache" ]]; then
  git init --bare -q "$cache"
fi
[[ "$(git --git-dir="$cache" rev-parse --is-bare-repository)" == true ]] ||
  { echo 'BLOCKED: invalid bare Git cache' >&2; exit 2; }

response="$(git ls-remote --exit-code "$remote" "$ref")"
IFS=$'\t' read -r sha returned_ref <<< "$response"
[[ "$sha" =~ ^[0-9a-f]{40}$ && "$returned_ref" == "$ref" ]] ||
  { echo 'BLOCKED: invalid remote PR reference' >&2; exit 2; }

if ! git --git-dir="$cache" cat-file -e "$sha^{commit}" 2>/dev/null; then
  git --git-dir="$cache" fetch --no-tags --no-write-fetch-head "$remote" "$ref"
fi
git --git-dir="$cache" cat-file -e "$sha^{commit}"

launcher="$(mktemp "$state/quality-reports/.pr274-runner.XXXXXXXX")"
trap 'rm -f -- "$launcher"' EXIT
git --git-dir="$cache" show \
  "$sha:scripts/workstation/run-pr274-local-quality.sh" > "$launcher"
flock -u 9

NABLA_PR274_EXPECTED_SHA="$sha" bash "$launcher"
PR274_QUALITY
~~~

Si le réseau ou le SHA a changé pendant l'opération, le bootstrap ou le
lanceur échoue sans mutation du checkout original.

## Actions du lanceur

1. Lit le SHA distant et valide `master` comme base exacte.
2. Réutilise le cache Git bare sans télécharger les objets déjà présents.
3. Crée un worktree temporaire privé unique sous un répertoire persistant.
4. Utilise un Python déjà équipé ou effectue un `uv sync --frozen --group dev`
   **uniquement dans ce nouveau worktree**.
5. Exécute les tests ciblés puis les trois contrôles de générateurs.
6. Si une projection est périmée, régénère uniquement les artefacts déclaratifs,
   sans démarrer de conteneur.
7. Exécute `just agent-skills-check` puis `just quality` et s'arrête au
   premier échec, sans masquer de gate.

En sortie, lire `PR274_QUALITY_RESULT`, `FIRST_FAILURE`,
`EVIDENCE_DIR` et, si des fichiers sont modifiés, `REVIEW_WORKTREE`.
Les logs privés sont sauvegardés avec `umask 077`. Les worktrees propres
créés par cette exécution sont supprimés. Les worktrees contenant des
modifications générées sont **conservés** pour revue.

**Aucun commit, push, merge, déploiement TrueNAS, reset Kafka, changement de
secrets ou GitHub Actions n'est effectué.** Une gate `just quality` réussie
ne constitue pas une attestation L3 : il faut encore la gate locale
`agent-pre-push` au commit exact avant de déclarer la publication prête.

## Contrats du lanceur

Depuis un checkout de développement contenant la PR :

~~~bash
just pr274-local-quality-test
~~~

Les contrats vérifient la syntaxe Bash, la sortie anticipée sans tuer le
terminal parent, le pin SHA, le cache Git isolé, le contrôle strict et
l'absence d'actions destructives.
