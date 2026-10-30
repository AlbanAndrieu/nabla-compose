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
| 5 | **YubiKey + Compose** | Migrer les contrats client escrow age/SOPS USB/NFS ; distinguer copies indépendantes et PRA réellement restauré | Deux copies indépendantes avec restauration isolée prouvée ; dataset/export/ACL restent dans Compose ; **NO-GO matériel** sinon |

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
