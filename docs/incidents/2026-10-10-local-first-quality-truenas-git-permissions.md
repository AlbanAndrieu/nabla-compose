# Incident — Local-first quality gate, Git modes et TrueNAS (2026-10-10)

## Contexte et portée

- Dépôt : `AlbanAndrieu/nabla-compose`, PR [#251](https://github.com/AlbanAndrieu/nabla-compose/pull/251), branche `fix/agent-compose-gate-offline-followup`.
- Poste opérateur : TrueNAS, checkout `/mnt/cpool/compose/nabla-compose` ; la workstation et l'environnement isolé de l'agent ne garantissent pas les mêmes permissions, montages, outils ni références Git.
- Objectif : faire converger `just loop` puis `just pre-push` **local-first**, sans supprimer les hooks ni consommer inutilement GitHub Actions. Ne jamais merger automatiquement.
- **État constaté le 10 octobre 2026** : `python3 -m pytest -q tests/test_agent_quality_gate_contract.py --tb=short` → **20 passed, 22 subtests passed** ; `pre-commit run shellcheck --files scripts/agent-quality-gate.sh` → **PASS** ; `python3 -m unittest tests.test_truenas_app_lifecycle_contract -q` → **60 tests OK**. Ces validations L1 ne prouvent pas `just pre-push` (L3).

## Symptômes, cause et remède

| Symptôme | Cause établie / incertitude | Action durable |
| --- | --- | --- |
| `QG_BASE_STALE` malgré `git pull: Already up to date` | `git pull` de la branche PR ne garantit pas l'intégration du dernier `origin/master`. Un commit de `master` manquait à `HEAD`. | `git fetch origin master <branche>` ; vérifier `git log --oneline HEAD..origin/master` ; intégrer `origin/master`, puis `git merge-base --is-ancestor origin/master HEAD`. Ne jamais ignorer le contrôle. |
| `git merge` refuse un fichier OpenClaw alors que seuls les modes changent | Diff local/index `100644 → 100755` sur `backup-openclaw.sh` ou `diagnose-openclaw-errors.sh` ; Git protège les modifications locales. | Comparer `git diff --cached --summary` et les deux diffs (index/worktree) ; préserver tout changement de contenu avant restauration ciblée, intégration distante, puis enregistrement du mode. Aucun `reset --hard`. |
| Git affiche `100755`, `stat` peut afficher `700` sur TrueNAS | Git ne mémorise pas tous les bits POSIX ; seul le caractère exécutable est versionné. Des permissions effectives restrictives peuvent être légitimes. Pour `deploy-autokuma.sh`, l'opérateur a ensuite confirmé `755` et les ACL `rwx/r-x/r-x` ; `core.fileMode=true`. | Contrôler séparément `git ls-files --stage`, `stat`, `getfacl`, `git config --get core.fileMode`. Test portable : `S_IXUSR` et mode Git `100755`, **pas** `S_IXGRP`/`S_IXOTH` imposés à tous les checkouts. |
| Le gate modifiait silencieusement des permissions `0700 → 0755` | Ancienne implémentation `chmod 755`, y compris une fonction `check_exec_bits()` définie deux fois (la seconde définition Bash prévalait). | Garder une seule définition de chaque fonction critique ; examiner tout le Git index pour détecter les fichiers à shebang avec mode `100644` ; corriger avec `git add --chmod=+x` et, seulement si nécessaire, `chmod u+x`. Jamais `chmod 755` automatique. |
| Contrats TrueNAS en échec (`AssertionError: 0 is not true`) | Plusieurs tests exigeaient indûment l'exécution par groupe et autres alors que les fichiers étaient en `0700` ; **d'autres** échecs provenaient d'assertions de chemins secrets obsolètes. | Contrôler mode propriétaire + Git ; mettre à jour les attentes vers `/mnt/cpool/secrets/runtime/sentry/.env.migrator.secrets` et `/mnt/cpool/secrets/runtime/scrutiny/.env.secrets`. Ne pas relâcher les contrôles sur les secrets. |
| Cinq tests Scanopy aboutissent à `Scanopy image inventory is empty` | Le faux exécutable Docker n'a pas produit l'inventaire attendu ; montage `/tmp` `noexec` **suspecté, non prouvé** ; variables/fonctions Bash héritées sont d'autres facteurs possibles. | Installer la fixture dans un répertoire temporaire sur le filesystem du dépôt, écrire l'inventaire dans un fichier, neutraliser `BASH_ENV` / `BASH_FUNC_*`, et vérifier le mock. Le validateur d'images reste fail-closed. Re-test opérateur : 26 tests ciblés passent. |
| `QG_FIX_STALLED` après une passe sans diff | Hook en échec sans autofix ; répéter les passes ne réparera pas un contrat logique. `just loop` peut afficher « no changed files require ... » alors que `just pre-push` exécute une couverture plus large. | Lire l'extrait et le journal privé `/tmp/tmp.*`, corriger le hook ciblé, puis reprendre L1 → L2 → L3. Ne pas transformer un L2 vert en prétendue validation complète. |
| Erreur `NameError: AGENT_GATE` dans un test ajouté | Test utilisait une constante non déclarée. | Employer `ROOT / "scripts" / "agent-quality-gate.sh"` ; exécuter le test exact **avant** publication. Re-test TrueNAS : 20 tests/22 subtests OK. |
| ShellCheck `SC2250` et sortie très volumineuse | Style Bash exige `${var}`; pré-commit peut produire des logs détaillés. | Appliquer les accolades, capturer le résultat dans `mktemp` et afficher un résumé borné sans perdre le journal ; ne pas utiliser `SKIP`, `--no-verify` ou désactiver ShellCheck. |
| Test avec exécutable temporaire : « UNREACHABLE » au lieu de wrapper attendu | Le mock peut ne pas s'exécuter ; hypothèse `/tmp noexec` **non vérifiée** et possibilité de variables d'environnement héritées. | Mettre le wrapper sur un FS exécutable et utiliser `bash -ec` pour rendre les erreurs d'exécution visibles, avec un environnement isolé. |

## Procédure de triage courte et non destructive

```bash
cd /mnt/cpool/compose/nabla-compose
git status --short --branch
git diff --cached --summary
git diff --check
git diff --cached --check

# Distinguer l'index Git de l'état du filesystem et des ACL.
git ls-files --stage -- scripts/agent-quality-gate.sh
stat -c '%a %U:%G %n' scripts/agent-quality-gate.sh
getfacl -cp scripts/agent-quality-gate.sh
git config --get core.fileMode

# Détecter une définition accidentellement dupliquée.
grep -nE '^((check_exec_bits|collect_changed_files|run_compact)\(\))' \
  scripts/agent-quality-gate.sh

# Garder une sortie compacte et conserver les erreurs détaillées.
log="$(mktemp)"
if pre-commit run shellcheck --files scripts/agent-quality-gate.sh >"${log}" 2>&1; then
  printf 'ShellCheck PASS\n'
  rm -f "${log}"
else
  rc=$?
  printf 'ShellCheck FAIL (%d), journal : %s\n' "${rc}" "${log}"
  grep -E '^In .* line [0-9]+:|SC[0-9]{4}|^- hook id:' "${log}" | head -60 || true
fi

python3 -m pytest -q tests/test_agent_quality_gate_contract.py --tb=short
```

Si un merge est bloqué : **ne pas** écraser les modifications locales ; vérifier index et worktree, sauvegarder un patch des seuls fichiers concernés et résoudre leur mode/contenu avant de fusionner la branche distante.

## Prévention / critères de validation

1. L'exécutable de qualité est défini une seule fois par fonction ; un test de régression bloque toute duplication.
2. Les fichiers à shebang suivis dans l'index Git doivent être `100755`, même hors diff de la PR ; une correction de mode doit être visible dans l'index. Le contrôle ne doit pas élargir implicitement les droits POSIX.
3. Les fixtures d'exécutables sont hermétiques et compatibles avec un montage TrueNAS `/tmp` potentiellement `noexec`.
4. L1 : tests ciblés et linters ; L2 : `just loop` ; L3 : **`just pre-push` après commit et checkout propre**, puis publication sans bypass. L2 n'est pas L3.
5. En cas d'échec, conserver le journal local privé en mode restrictif ; ne pas y publier de secrets dans une PR ou dans un commentaire.

## Suivi

- **Validé par l'opérateur** : tests de contrat qualité 20/20 (+22 subtests), ShellCheck qualité PASS, contrat de cycle TrueNAS 60 tests OK ; auparavant Scanopy/OpenClaw 26 tests (+6 subtests) PASS.
- **Non encore attesté sur le HEAD publié** : quality gate L3 `just pre-push`, pre-commit complet, absence de modifications indexées locales.
- **À réinvestiguer si reproduit** : montage `/tmp` `noexec`, divergence `core.fileMode` entre workstation/TrueNAS, effet des fonctions Bash exportées, hook `shfmt` échouant sur un autre fichier que celui testé isolément.
