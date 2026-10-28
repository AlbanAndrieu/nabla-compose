# ADR-WKS-001 — Répartition des configurations workstation et sauvegarde Option A

- **Statut : accepté** (décision utilisateur du 27 octobre 2026).
- **Portée :** `dotfiles`, `ansible-workstation`, `nabla-compose`.
- **Décideur :** propriétaire de la workstation ; **responsables d'implémentation :** dépôts propriétaires ci-dessous.

## Problème

`$HOME` est un checkout Git des dotfiles : il sauvegarde les configurations utilisateur **versionnées**, pas la configuration active Ubuntu hors home. `ansible-workstation` contient encore un playbook d'installation historique, un inventaire matériel daté et un bundle YubiKey/PAM peu sûr ; `nabla-compose` dispose déjà d'outils de diagnostic YubiKey beaucoup plus complets. Il faut restaurer après sinistre sans fuite de secrets ni duplication des responsabilités.

## Décision : Option A

1. **dotfiles** : configuration utilisateur déclarative et testable (`.bashrc`, terminal, Git, unités systemd utilisateur). Un script d'inventaire système peut rester temporairement comme compatibilité ; sa source canonique migre vers Ansible.
2. **ansible-workstation** : souhait OS, collecte filtrée, constat de dérive, audit/read-only par défaut, packages, service système, DNS/pfSense, SSH, firewall, mounts et politique Restic. Les actions `apply` sont explicitement opt-in.
3. **nabla-compose** : gouvernance inter-dépôts, infrastructure homelab, propriétaire des procédures matérielles **YubiKey** (OTP2, FIDO2, OpenPGP, PIV, age, escrow), diagnostics et sauvegarde indépendante de clés. Pas de playbook PAM implicitement déclenché par Compose.
4. **Données privées** : snapshots techniques complets sous espace à permissions restreintes, hors Git ; Restic chiffré avec destination indépendante de la workstation et du NAS principal ; `restic check` et restauration isolée obligatoires avant de déclarer la reprise viable. Clés Restic et recovery codes hors Git, avec escrow séparé.
5. **État Git != état réel** : rapports publics réduits aux champs allowlistés, horodatés, sans hostname, IP, MAC, serial, UUID, chemins privés, secrets ou identifiants de carte.

## Matrice légère

| Livrable | Responsible (R) | Accountable (A) | Consulted (C) |
| --- | --- | --- | --- |
| Shell + dotfiles versionnés | dotfiles | propriétaire | ansible-workstation |
| Baseline Ubuntu + audit + drift | ansible-workstation | propriétaire | dotfiles, Compose |
| Sauvegarde Restic / test restore OS | ansible-workstation | propriétaire | Compose pour cible de stockage |
| YubiKey diagnostics/transactions/escrow | nabla-compose | propriétaire | ansible-workstation pour dépendances OS |
| PAM Ubuntu / prérequis système U2F | ansible-workstation (**audit seulement par défaut**) | propriétaire | nabla-compose |

## YubiKey : choix d'intégration

`ansible-workstation/tasks/yubikey.yml` a un ajout PPA inconditionnel et remplace `/etc/pam.d/common-auth` lorsque `pam_enabled=true`, ce qui crée un risque de verrouillage. Une nouvelle PR Ansible retire le **chemin historique** du rôle général (et les deux templates PAM devenus orphelins). Ce retrait dans Git ne supprime pas les outils déjà installés et ne rétablit pas la configuration PAM active : l'état système reste à auditer séparément. Si les packages `libfido2`/`pcscd`/`opensc` sont nécessaires, un futur rôle *prérequis OS seulement* sera opt-in, sans gestion de slots/cartes.

**NO-GO matériel** conservé : pas d'opération sur PIV82, AES256, OTP2, PIN/PUK, F9, OpenPGP ou des clés privées avant preuves indépendantes d'escrow et validation physique avec carte unique. Les runbooks existants Compose restent l'autorité ; aucun import de secrets dans Ansible.

## Alternatives rejetées

- Stocker un dump complet de `/etc`, `/var` ou des Ansible Facts dans GitHub : fuites et bruit de drift.
- Mettre les YubiKey sous contrôle d'un playbook Ubuntu global : mutation involontaire de PAM et matériel.
- Centraliser tout dans `dotfiles` : impossible d'attester l'OS et ses services hors `$HOME`.
- Considérer un inventaire en JSON comme une sauvegarde restaurable : manque les fichiers, secrets, tests et la copie indépendante.

## Conséquences et déploiement

Trois roadmaps **non dupliquées** : `dotfiles/docs/roadmap-workstation.md`, `ansible-workstation/docs/roadmap-workstation.md`, `nabla-compose/docs/roadmap-workstation-yubikey.md`. Chaque dépôt possède ses validations et sa PR Draft.

Déploiement recommandé : (1) documentation, (2) retrait du code YubiKey/PAM historique *sans apply*, (3) audit de l'état actif, (4) modèle d'état voulu, (5) Restic chiffré/restauration testée. Ne jamais lancer le `workstation.yml` historique pour collecter les faits. Commits `[skip ci]`, tests local-first, pas d'automerge.

## Réversibilité

Le retrait du code Ansible se restaure par Git et ne touche pas le système actuel. La future bascule du collecteur doit comparer son JSON avec celui des dotfiles avant retrait de l'ancien. Pour les sauvegardes, restaurer hors de `/etc` actif puis faire relire chaque fichier par le module propriétaire ; tester et documenter le rollback avant apply.
