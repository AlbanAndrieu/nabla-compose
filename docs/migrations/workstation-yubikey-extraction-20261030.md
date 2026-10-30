# Inventaire de transfert Workstation / YubiKey — 30 octobre 2026

> **État Git du 30/10/2026 :** PR Compose #295 **fusionnée** ; PR nabla-openclaw #1 et PR ansible-workstation #16 **fusionnées** ; PR nabla-yubikey #1 **Draft**. Les 14 politiques Workstation sont dans `ops/openclaw-workstation/` et **4** fichiers sandbox restent dans `apps/openclaw/`. La migration du Gateway et du matériel n'est pas attestée. [Suivi actif](../roadmap-openclaw-yubikey-extraction-20261030.md).

**Lecture seule.** Cette matrice distingue emplacement actuel et
propriétaire cible, sans déplacer les fichiers. Source de décision :
[ADR](../adr/adr-repository-split-workstation-yubikey-20261030.md).

| Chemins Compose actuels | Cible proposée | État / restriction |
| --- | --- | --- |
| `scripts/workstation/diagnose-openclaw-*`, `check-openclaw-*`, `openclaw-ops.sh`, `tests/test_openclaw_*` | **nabla-openclaw** pour logique Gateway/cron cible ; **Ansible** pour audit OS de la source | Examiner les imports TrueNAS/stockage, ne pas copier le Gateway Workstation en bloc |
| `apps/openclaw/workstation/` | **nabla-openclaw `policies/`** pour heartbeat/cron ; Ansible garde l'OS | Premières politiques importées en PR #1, inactives ; ne pas transférer les sessions ni fichiers secrets |
| `apps/openclaw/compose.yml`, `apps/litellm/`, `scripts/truenas/*litellm*` | **Reste Compose** | Serveurs, modèles TrueNAS, clés scoped, DB, quotas, NFS |
| `scripts/workstation/diagnose-*-dns*.py`, `workstation-split-dns-*` | ansible-workstation | Reprendre les audits existants, PAS de second collecteur équivalent |
| `scripts/workstation/*yubikey*`, `*age-escrow*`, `*sops*` | nabla-yubikey PR #1 | Tri manuel par effet et tests ; pas de clés, PIN ou configs chiffrées |
| `tests/test_yubikey_*` et `docs/runbooks/yubikey-*` | futur nabla-yubikey | Transférer ensemble avec scripts, fixtures et avertissements |
| `scripts/workstation/*nfs*escrow*` | YubiKey **client**, Compose **serveur TrueNAS** | Conserver une interface de sonde et les contrôles de ACL NFS |
| `docs/roadmap-workstation-yubikey.md` | roadmap YubiKey indépendante | Lien/alias d'historique dans Compose après extraction |
| `secrets.env.sops`, `.sops.yaml`, `~/.openclaw/`, fichiers `*.age` privés | **Jamais copiés dans les nouveaux dépôts** | Secrets/snapshots/profiles dans le coffre existant, usage sous autorisation |

## Audit de dépendances avant tout changement

Exécuter en local depuis le checkout Compose, sans requêtes GitHub ni
opérations matérielles :

```bash
python3 scripts/ops/plan-repository-split.py
python3 -m unittest discover -s tests -p 'test_repository_split_plan.py' -v

# Références cross-repo, lire sans les modifier :
git grep -n -E 'scripts/workstation|apps/openclaw/workstation|yubikey-' \
  -- justfile docs scripts tests apps | head -n 100
```

Les comptes sont des *candidats* (patterns nominaux), pas un ordre de
copie ni une preuve de sécurité. Après extraction : mise à jour des
références, comparaison des résultats, tests locaux et parité de
découverte `just --list` avant suppression de recettes.

## Arbitrages

- Le dépôt YubiKey est **pertinent** : cycle de vie matériel,
  procédures de reprise sensibles et 84 recettes indépendantes.
  Préférer `nabla-yubikey` avec revue explicite des licences et
  de l'historique Git. Ne pas créer un repo public directement
  depuis une copie de l'ancien historique sans analyse des secrets.
- `ansible-workstation` est le bon propriétaire de l'OS, **pas**
  du runtime persistant `~/.openclaw` ni des secrets. Le modèle est
  **plan → dry-run → sauvegarde privée → apply explicite → verify/rollback**.
- Un `justfile` global court peut conserver temporairement
  `just workstation-check` et `just yubikey-check` comme
  dispatchers **non silencieux**, mais ne doit pas importer tous
  les fichiers des nouveaux dépôts.

## Dépôts réellement créés et transfert initial

- [nabla-yubikey PR #1](https://github.com/AlbanAndrieu/nabla-yubikey/pull/1) : collecteur autonome de dépendances avec test hermétique, aucun matériel.
- [nabla-openclaw PR #1](https://github.com/AlbanAndrieu/nabla-openclaw/pull/1) : **fusionnée** (merge `dd304743`) ; politiques `HEARTBEAT` et digest inactives, contrat cible TrueNAS sans image/dataset validés.
- [ansible-workstation PR #16](https://github.com/AlbanAndrieu/ansible-workstation/pull/16) : audit `systemd --user` de la source Workstation, ancien template OpenClaw Node 25 interdit au déploiement.

**Submodules :** chemin canonique OpenClaw : `apps/openclaw` directement.
Ce chemin ne contient plus que **quatre fichiers suivis** (sandbox) :
les 14 artefacts Workstation ont déjà été relocalisés temporairement
sous `ops/openclaw-workstation/`, et leurs scripts/tests ont été adaptés.
Le déplacement des quatre fichiers restants vers `apps/openclaw-sandbox/`
reste bloqué en attendant le préflight TrueNAS global et la revue
des consommateurs. Le submodule ne sera ajouté
qu'après parité locale, avec un commit testé épinglé. Emplacement YubiKey
proposé : `security/nabla-yubikey`, séparé des applications Docker.
Pas de checkout direct dans les datasets de runtime, ni de
`git submodule update --remote` automatisé.


### Lot 1 — migration structurelle engagée (30 octobre 2026)

Les **14 fichiers de politiques/artefacts Workstation** ont été
transférés de `apps/openclaw/workstation/` vers
`ops/openclaw-workstation/` dans `nabla-compose`, avec modification
des chemins dans les scripts Python et tests associés. Les
références précédentes à l'ancien chemin décrivent désormais la
source historique, pas la localisation courante. Le dossier
`apps/openclaw` conserve **quatre fichiers du sandbox** :
`Dockerfile`, `catalog-info.yaml`, `compose.yml`, `test-docker.sh`.
Le **futur submodule direct `apps/openclaw` n'est pas encore ajouté** :
sa libération doit attendre la validation des références TrueNAS
vers le sandbox. Aucune application n'a été redéployée.
