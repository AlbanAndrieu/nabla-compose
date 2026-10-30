# ADR — Extraire Workstation et YubiKey de nabla-compose (proposé)

**Statut : PROPOSED — 30 octobre 2026.** Ne déplace encore aucun fichier ni ne modifie le runtime.

## Constat vérifié

Sur la branche de la PR #295 : `justfile` compte **370 recettes**,
dont **84** `yubikey-*`, **98** `openclaw-*` et **15**
`workstation-*`, soit 197 recettes nommées explicitement pour ces
domaines. Les 84 et 98 recettes représentent à elles seules 49,2 %
du fichier ; le problème est structurel, pas seulement cosmétique.
Le dépôt contient 1 740 fichiers suivis, dont ~100 chemins liés
à YubiKey/age/escrow et plus de 300 chemins associés à la Workstation
et à OpenClaw (inventaires par nom, **pas** liste approuvée à copier).

`AlbanAndrieu/ansible-workstation` existe et comprend déjà le rôle,
les tâches mise/uv, les audits Ubuntu et les templates systemd.
Sa PR Draft #16 applique l'**Option A** : OS dans Ansible, dotfiles
utilisateur dans dotfiles, hardware YubiKey et homelab actuellement
dans Compose. La suppression du `tasks/yubikey.yml` et des templates
PAM de la PR #16 reste voulue : **ne pas les réintroduire**.

Attention au template historique
`ansible-workstation/templates/openclaw-gateway-systemd.sh-Ubuntu.j2` :
il pointe vers Node **25.4.0** et OpenClaw **2026.4.15** alors que
le runtime déclaré/observé au 30/10 utilise Node 24 et OpenClaw
2026.10.7. Ce template NE DOIT PAS être appliqué tel quel.
`ansible-workstation/workstation.yml` reste un vieux playbook global
potentiellement mutateur ; ne pas l'utiliser pour réaliser la migration.

## Décision proposée

1. **nabla-compose** : état désiré des services TrueNAS/Compose,
   LiteLLM serveur et upstreams, pfSense, Talos/Kubernetes, CSI/NFS,
   topologie, catalogues de services et règles de sécurité inter-hôtes.
   Les probes *serveur* TrueNAS restent ici.
2. **ansible-workstation** : audits OS Ubuntu, installations contrôlées,
   systemd `--user` OpenClaw/LiteLLM, Node/mise, DNS et réseau locaux,
   et déploiement explicite des artefacts NON SECRETS de la Workstation.
   Les services utilisateurs doivent être gérés sans `become: true`
   global, avec préflight de version et sauvegarde/rollback.
3. **dotfiles** : configuration utilisateur interactive, notamment
   Starship, Terminator, configuration shell. Ne pas la copier dans Ansible.
4. **futur dépôt dédié `nabla-yubikey` (pas encore créé)** :
   runbooks et contrôles matériels FIDO2/SSH-sk, OpenPGP,
   PIV/AES256, age/SOPS, escrow USB et backups, tests hermétiques.
   L'identité réelle, les clés privées et archives chiffrées restent
   hors des dépôts publics. Un rôle Ansible de **prérequis logiciels
   uniquement**, opt-in, peut fournir `pcscd`, `libfido2`,
   `ykman`, `opensc` sans PAM ni provisionnement matériel.
5. Les actions nécessitant **les deux hôtes** (ex. logs LiteLLM
   TrueNAS depuis OpenClaw Workstation, NFS escrow) gardent un
   contrat dans Compose ; le client local appartient au dépôt
   spécialisé, le serveur/dataset à Compose.

## Séquencement et critères GO/NO-GO

| Phase | Contenu | Critère pour continuer |
| --- | --- | --- |
| 0 | Inventaire des chemins, recettes, import Python, shells, docs, secrets, perms et versions | Résultats reproductibles sans accès matériel |
| 1 | `ansible-workstation` : rôle `openclaw-runtime` opt-in + audit de dérive, sans activation | CLI/Node et systemd identiques à la Workstation, `changed=0` en audit ; template 25.x neutralisé |
| 2 | Contrats de probes et commandes locales dans `ansible-workstation`, diagnostics TrueNAS conservés Compose | Parité de sortie, mêmes exit codes et redaction, test LAN |
| 3 | Créer `nabla-yubikey` (repo privé si données locales sensibles ; public seulement après revue) ; copier scripts+tests dans PR Draft | 100 % tests hermétiques YubiKey, pas de PIN/PIV/PAM, hardware checks toujours opt-in |
| 4 | Reconnecter via wrappers de compatibilité, migration des consommateurs externes | Pas de `command not found`, plus aucune importation vers l'ancien chemin, aucun secret Git |
| 5 | Déprécier et seulement ensuite retirer les anciennes recettes/code | Validation sur deux hôtes, plan/rollback documentés et revue manuelle |

Les **84 recettes YubiKey ne sont pas 84 services Ansible** : elles
doivent devenir un `justfile` propre au dépôt YubiKey, avec 2 à 4
points d'entrée ergonomiques. Même règle pour OpenClaw Workstation.
Ne pas créer de sous-module Git simplement pour contourner le
`justfile` volumineux : un submodule multiplie les conflits et
crée une nouvelle dépendance de synchronisation. Préférer des
checkouts frères et des wrappers explicites pendant la transition.

## Sécurité et rollback

- AUCUN reset/reconfiguration de YubiKey, PIN, PUK, PIV, OTP, PAM,
  enrolment SSH ou déchiffrement SOPS/age.
- `git mv` entre dépôts n'existe pas : reprise avec attribution
  historique, inventaire de licence et commits de provenance ; ne
  jamais déplacer les éléments cryptographiques privés.
- Ne pas faire converger un client Workstation via un playbook
  privilégié TrueNAS ou via le vieux template systemd.
- Garder les anciennes recettes et points d'entrée jusqu'à parité
  attestée ; les erreurs de bord restent UNKNOWN et non DOWN.
- Commits `[skip ci]`, tests locaux seulement, PRs Draft, jamais
  de merge automatique.
