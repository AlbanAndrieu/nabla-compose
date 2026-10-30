# Inventaire de transfert Workstation / YubiKey — 30 octobre 2026

**Lecture seule.** Cette matrice distingue emplacement actuel et
propriétaire cible, sans déplacer les fichiers. Source de décision :
[ADR](../adr/adr-repository-split-workstation-yubikey-20261030.md).

| Chemins Compose actuels | Cible proposée | État / restriction |
| --- | --- | --- |
| `scripts/workstation/diagnose-openclaw-*`, `check-openclaw-*`, `openclaw-ops.sh`, `tests/test_openclaw_*` | ansible-workstation, sous `scripts/openclaw/` et `tests/` | Découper les imports `scripts/truenas` et les fixtures du catalogue |
| `apps/openclaw/workstation/` | ansible-workstation `policies/openclaw/` et `templates/` | Surveiller owner, fichiers `HEARTBEAT`, cron, snapshots, secrets ; ne pas copier l'état privé |
| `apps/openclaw/compose.yml`, `apps/litellm/`, `scripts/truenas/*litellm*` | **Reste Compose** | Serveurs, modèles TrueNAS, clés scoped, DB, quotas, NFS |
| `scripts/workstation/diagnose-*-dns*.py`, `workstation-split-dns-*` | ansible-workstation | Reprendre les audits existants, PAS de second collecteur équivalent |
| `scripts/workstation/*yubikey*`, `*age-escrow*`, `*sops*` | futur nabla-yubikey | Tri manuel par effet et tests ; pas de clés, PIN ou configs chiffrées |
| `tests/test_yubikey_*` et `docs/runbooks/yubikey-*` | futur nabla-yubikey | Transférer ensemble avec scripts, fixtures et avertissements |
| `scripts/workstation/*nfs*escrow*` | YubiKey **client**, Compose **serveur TrueNAS** | Conserver une interface de sonde et les contrôles de ACL NFS |
| `docs/roadmap-workstation-yubikey.md` | future roadmap YubiKey | Lien/alias d'historique dans Compose après extraction |
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
