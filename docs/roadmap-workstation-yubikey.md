# Roadmap nabla-compose — YubiKey et intégrations workstation

**Date : 27 octobre 2026**. Ceci est le volet de la roadmap **propre à Compose**, sans recopier les actions système ou shell d'autres dépôts. Décision : [ADR Option A](adr/adr-workstation-option-a.md). Références déjà existantes : [inventaire des capacités](workstation-yubikey-full-capabilities.md), [runbook secondaire cinq chantiers](runbooks/yubikey-backup-five-execution.md) et [roadmap PIV/GPG](workstation-yubikey-gpg-vault-roadmap.md).

| Priorité | Action | Validation / gate | État |
| --- | --- | --- | --- |
| P0 | Maintenir **un seul owner** pour les diagnostics OTP2, FIDO2, SSH-sk, PIV, GPG/OpenPGP, age, escrow | Tous les scripts matériels restent sous `scripts/workstation/` ; aucun write automatique | Déjà centralisé ; intégration Ansible à retirer |
| P0 | Consolider les runbooks PIV82 et escrow en statut NO-GO tant que les preuves manquent | Deux restaurations escrow réellement indépendantes, roundtrip de récupération isolé | **Bloqué**, ne pas modifier le matériel |
| P0 | Contrat inter-dépôts pour PAM / dépendances YubiKey | Compose ne touche pas `/etc/pam.d` ; Ansible audite PAM sans muter | Documentation acceptée |
| P1 | Harmoniser les commandes de préflight YubiKey dans les runbooks actifs | Un seul chemin `--readonly` sans SCD, PIN, PUK ni mutation de slots | À consolider |
| P1 | Proposer à Ansible la liste minimale de prérequis OS sans les installer automatiquement | Matrice versions/dépendances (pcscd, libfido2, opensc, ykman) expurgée | À faire |
| P1 | Définir sauvegarde indépendante des artefacts de récupération sensibles | Restic chiffré ou coffre chiffré validé, copie hors NAS, restauration prouvée | À faire sans sauvegarder les secrets sur Git |
| P2 | Débloquer éventuellement PIV82 après les gates et décision humaine explicite | Génération supervisée 0x82 seulement ; OTP2/PIV9A inchangés | **NO-GO** jusqu'aux preuves |
| P2 | Intégrer les preuves autorisées au catalogue sécurité | Métadonnées de conformité seulement, aucune identité unique de carte | À faire |

**Propriétaires des autres étapes :** `dotfiles` pour shell/terminal et `ansible-workstation` pour OS, système PAM, paquets, réseau, snapshots et sauvegarde Restic. Les runbooks hardware de Compose ne deviennent pas des rôles Ansible.

**Sans consentement :** aucune rotation de PIN/PUK, clé PIV AES256, changement OTP2, reset PIV, export de clés GPG ou activation PAM. Pas d'automerge ni de CI payante, tests offline avant manipulation supervisée.
