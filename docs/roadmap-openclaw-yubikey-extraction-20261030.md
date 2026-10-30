# Migration inter-dépôts — OpenClaw et YubiKey (30 octobre 2026)

> **Point d'entrée de coordination pour `nabla-compose`**. Le détail des tâches et les commandes propres à chaque outil appartiennent à ses roadmaps dédiées : [OpenClaw](https://github.com/AlbanAndrieu/nabla-openclaw/blob/master/docs/migration.md) et [YubiKey](https://github.com/AlbanAndrieu/nabla-yubikey/pull/1). Les PRs Draft de consolidation peuvent précéder leur fusion : [OpenClaw #2](https://github.com/AlbanAndrieu/nabla-openclaw/pull/2), [YubiKey #1](https://github.com/AlbanAndrieu/nabla-yubikey/pull/1). Les docs historiques restent consultables mais ne priment pas sur ce tableau.

## Avancement vérifié dans les dépôts

| Dépôt | Propriété pérenne | Git / statut | Runtime |
| --- | --- | --- | --- |
| `nabla-compose` | LiteLLM TrueNAS, volumes ZFS, NFS, réseau, interfaces cross-host et futur gitlink | PR #295 **fusionnée** ; 14 artefacts Workstation sous `ops/openclaw-workstation/`, 4 fichiers sandbox sous `apps/openclaw/` | **Aucune migration Gateway attestée** |
| `nabla-openclaw` | Gateway Docker cible TrueNAS, heartbeat et cron déclaratifs, tests, runbooks | PR #1 **fusionnée**, PR #2 de consolidation Draft ; politiques candidates et contrat cible | **Non déployé**, automations inactives |
| `nabla-yubikey` | Diagnostics YubiKey client, FIDO2/SSH-sk/OpenPGP/PIV, age/SOPS/USB escrow, recovery | PR #1 **Draft** ; lot 1 dépendances readonly seulement | Aucun matériel modifié |
| `ansible-workstation` | Pré-requis OS, audits source systemd/Node/mise/DNS, sécurité Ubuntu | PR #16 **fusionnée** ; audit YubiKey sans PAM | Audit OS déjà attesté, pas de provisionnement matériel |
| `dotfiles` | Shell, Terminator, Starship, configuration utilisateur interactive | Hors transfert | Inchangé |

## P0 — tâches immédiates, dans cet ordre

| Ordre | Responsable | Action restante | Preuve pour DONE |
| --- | --- | --- | --- |
| 1 | **OpenClaw + Compose** | Attribuer les erreurs 429 (budget vs RPM/TPM vs upstream), 401/403 et modèles ; diagnostiquer **les deux** LiteLLM et les clés scoped, sans génération | Rapports Workstation/TrueNAS datés, aucun faux PASS, clés main/cron distinctes, modèle réellement disponible |
| 2 | **OpenClaw** | Importer les scripts/contrats Gateway/cron pertinents par lots et leurs tests, en maintenant les wrappers Compose | Parité des interfaces, sorties, exit codes et redaction ; `just test` et tests Compose ciblés PASS |
| 3 | **OpenClaw** | Réconcilier heartbeat candidat avec CLI native effectivement installée, mettre sous contrôle cadence/coût/session, séparer digest et tâches privées | `plan → sauvegarde privée → apply explicite → verify → rollback` ; 14 capacités non réactivées par défaut |
| 4 | **YubiKey** | Migrer les collecteurs strictement readonly avec tests (host/GPG/PCSC puis FIDO2/PIV), vérifier provenance/licences et imports | Commandes `just` équivalentes sur Workstation ; aucun PIN, PUK, OTP, PIV ou données de carte dans Git |
| 5 | **YubiKey + Compose** | Transférer par lots les contrats client age/SOPS/USB, en conservant le diagnostic de l'export/dataset NFS côté Compose | Deux **supports distincts** contenant la même identité age chiffrée, restauration de chaque copie déjà prouvée ; phrase secrète disponible **hors SanDisk/workstation/NAS non attestée** ; parité des recettes et tests avant retrait ; **NO-GO matériel** |

## P0 — réception NFS/escrow et passation Compose ↔ YubiKey (30/10)

**Preuves déjà reçues ; ne pas recommencer les sauvegardes :**
- Deux copies chiffrées identiques de **la même identité age** sur deux supports distincts (workstation et NFS TrueNAS), chacune réellement déchiffrée ; 14/14 tests de sauvegarde et 13/13 de restauration PASS. Ce ne sont pas deux méthodes cryptographiques indépendantes.
- Contrôle NFS4 quatre niveaux : 11/11 tests PASS ; une autorisation non propriétaire *potentielle* sur la racine de l'export, aucune sur les deux répertoires sensibles et le fichier.
- Contrôle des modes côté TrueNAS : 9/9 tests PASS ; répertoires `0700/0700`, archive `0600`, propriétaire uniforme. Cela **ne prouve pas** le mapping d'identité ni les droits effectifs d'un client privilégié.
- Audit `sharing.nfs.query` : 10/10 tests PASS sur workstation, `EXPORT_MATCHED` en lecture seule ; export actif, accessible en écriture, **sans filtre** `hosts` ou `networks`, `maproot/mapall=UNSET`, `security=DEFAULT_UNVERIFIED`. Trois avertissements attestés : `NO_NFS_HOST_OR_NETWORK_FILTER`, `NFS_SECURITY_FLAVOR_DEFAULT_UNVERIFIED`, `EXPORT_WRITABLE`. Une sécurité par défaut **ne démontre pas** l'absence d'authentification `sec=sys`.
- Inventaire TCP/2049 : 8/8 tests hermétiques PASS sur l'ancienne version, mais sondage TrueNAS `SS_RESPONSE_UNVERIFIED` (code 3), donc **aucun nombre de clients observé**. Correctif de parseur `ss` à 4/5 colonnes et couverture IPv4-mappée versionnés en #295, **sans sortie de revalidation workstation fournie**. Il ne faut pas déclarer `TCP_SNAPSHOT_OBSERVED`.

**Contrat inter-dépôts :** `nabla-compose` garde l'export TrueNAS, ses ACL, le réseau, les scripts d'audit serveur et les dépendances NFS inter-hôtes ; `nabla-yubikey` reçoit progressivement les diagnostics client et les procédures de restauration age/SOPS avec les tests et garde-fous. Les wrappers Compose doivent rester fonctionnels tant que la parité n'est pas prouvée. Aucune copie de clé privée, identité PIV, PIN, archive age ou fichier SOPS n'entre dans un dépôt public.

**Consommateurs identifiés par le code** : un montage workstation `nabla:/mnt/cpool/backup/lab` → `/media/backup/lab` déjà observé ; les scripts OpenClaw (`backup-openclaw-nfs.py`, `copy-openclaw-backups-nfs.sh`) écrivent dans `infra/openclaw` ; l'escrow age écrit exceptionnellement dans `secret` ; un script de reprise heartbeat et des archives pfSense font également référence au partage. Cela ne prouve **ni** que pfSense est un client NFS, **ni** que ces jobs sont actuellement actifs.

**Gate P0 de reprise sans mutation, depuis un worktree propre de Compose :**

```bash
just yubikey-usb-identity-nfs-consumers-test
just yubikey-usb-identity-nfs-consumers-check
just yubikey-usb-identity-nfs-consumers-probe
```

Cette sonde n'est qu'un instantané des sessions TCP/2049 de **tous** les exports du NAS ; elle ne peut ni attribuer les sessions à `lab` ni découvrir les clients hors ligne ou intermittents. `all_clients_enumerated=false` et `consumer_allowlist_verified=false` doivent rester vrais. Corréler ensuite, hors automatisme, montages et automounts de chaque hôte, cron/backups, besoins d'écriture et filtrage pare-feu. **NO-GO** pour `sharing.nfs.update`, `ro=true`, une allowlist dérivée du seul `ss`, `chmod` ou une nouvelle sauvegarde tant que ces dépendances ne sont pas documentées avec un rollback.

**PRA encore ouvert :** débranchement physique de la SanDisk pendant un exercice supervisé, accès réel à la phrase secrète indépendamment **des trois systèmes** (SanDisk, workstation, TrueNAS) et test d'accès NFS négatif sous identité dédiée. Ne pas publier la phrase, le nom du coffre, les UID/GID ou les adresses clientes.

Traçabilité : [preuves et runbook USB age](runbooks/usb-age-identity-independent-backup-20261028.md), [inventaire d'extraction](migrations/workstation-yubikey-extraction-20261030.md), [PR #295 fusionnée](https://github.com/AlbanAndrieu/nabla-compose/pull/295).

## P1 — construction et intégration

| Ordre | Responsable | Action restante | Condition |
| --- | --- | --- | --- |
| 6 | **OpenClaw + Compose** | Sélectionner image/digest non-root, stockage privé ZFS, ACL, réseau/egress et sauvegarde avec restauration hors prod | Contrat TrueNAS et recovery PASS ; aucune autoactivation de cron/heartbeat |
| 7 | **Compose** | Déplacer les **4** fichiers du sandbox `apps/openclaw/` dans `apps/openclaw-sandbox/` avec revue consommateurs | `git ls-files -- apps/openclaw` vide, catalogue et scripts corrigés, tests verts |
| 8 | **Compose** | Ajouter `nabla-openclaw` en submodule **piné** directement à `apps/openclaw` | SHA vérifié, aucune dépendance au dossier privé `~/.openclaw` |
| 9 | **OpenClaw + Compose** | Démarrer en parallèle sur TrueNAS, sans doubles automations, puis basculer `cron` et `main` un par un | End-to-end, budgets, reprise et rollback Workstation prouvés |
| 10 | **YubiKey + Compose** | Évaluer ensuite le lien `security/nabla-yubikey` et déprécier les recettes Compose | Parité des 84 recettes sélectionnées/compat wrappers ; pas de transfert opaque ni secrets |

## P2 — clôture / nettoyage

- Retirer **seulement après parité** les scripts, wrappers, politiques et docs obsolètes de Compose ; ne pas supprimer des interfaces TrueNAS ou NFS utilisées par d'autres consommateurs.
- Éviter de maintenir deux sources de vérité : roadmap Gateway dans `nabla-openclaw` ; YubiKey dans `nabla-yubikey` ; OS dans `ansible-workstation`. Compose ne conserve que l'état des dépendances et les décisions cross-host.
- Mettre à jour les liens depuis `docs/roadmap.md`, le catalogue et les runbooks, puis marquer les notes précédentes « historique ».

## Gate local (sans CI GitHub)

```bash
# nabla-compose, worktree propre :
python3 scripts/ops/plan-repository-split.py
python3 -m unittest discover -s tests -p 'test_repository_split_plan.py' -v
just openclaw-migration-evidence-tests
just openclaw-migration-evidence-check
just openclaw-litellm-dual-logs-check

# nabla-openclaw :
just test && just plan

# nabla-yubikey (PR #1) :
just test && just dependencies-readonly
```

Les sorties runtime ne sont pas attestées par la seule existence des scripts. Un `exit=2` faute d'observabilité reste `UNKNOWN/NOT_VERIFIED`, pas une panne certaine.

**Sécurité non négociable :** aucun PIN/PUK/OTP2/PIV/GPG ou manipulation carte ; aucun secret, session SQLite, fichier `~/.openclaw`, identité age, archive privée ou fichier SOPS copié dans Git public ; aucune activation de clés, hausse de quotas, heartbeat ou Gateway sans gate et application explicite. Pas de CI payante, de merge automatique, de `git submodule update --remote` ni de migration implicite sur `git pull`.

**DONE global** = deux propriétaires spécialisés réellement autonomes + tests locaux et runtime validés + Gateway TrueNAS/heartbeats sans doublons + plan de rollback éprouvé + escrow restaurable avec deux supports indépendants + Compose débarrassé des seuls doublons devenus inutiles.

Références : [ADR séparation](adr/adr-repository-split-workstation-yubikey-20261030.md), [inventaire des chemins](migrations/workstation-yubikey-extraction-20261030.md), [migration OpenClaw](runbooks/openclaw-end-to-end-migration-20261030.md), [propriété Workstation](adr/adr-workstation-option-a.md).
