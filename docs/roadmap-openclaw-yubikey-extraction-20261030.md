# Séparation inter-dépôts — état au 6 novembre 2026

Ce document est le **point de coordination** dans Compose. Il ne répète plus
les étapes passées de migration. Les propriétaires et les décisions actives
sont [nabla-openclaw](https://github.com/AlbanAndrieu/nabla-openclaw/blob/master/docs/roadmap.md),
[nabla-yubikey](https://github.com/AlbanAndrieu/nabla-yubikey),
[ansible-workstation](https://github.com/AlbanAndrieu/ansible-workstation) et
la [roadmap Homelab](roadmap.md).

## Migrations réellement terminées

| Périmètre | État et preuve | Ce qui n'est pas impliqué |
| --- | --- | --- |
| YubiKey : code client | **DONE côté Git**, Compose [#317](https://github.com/AlbanAndrieu/nabla-compose/pull/317) fusionnée (124 fichiers et 87 recettes retirés ; renvois conservés) | Pas de mutation de PIN/PUK/OTP/PIV, ni suppression des sauvegardes escrow |
| OpenClaw : sous-module | **DONE côté Git**, Compose [#314](https://github.com/AlbanAndrieu/nabla-compose/pull/314) fusionnée ; `apps/openclaw` est un gitlink vers le dépôt dédié | `git pull` ne remplace pas `git submodule update` |
| OpenClaw : Gateway | **ACCEPTED (runtime)**, bascule TrueNAS du 03/11 et [pin Compose #323](https://github.com/AlbanAndrieu/nabla-compose/pull/323) | Slack et Discord non activés ; Workstation conservée comme rollback désactivé |
| OpenClaw : cron et heartbeat | **ACCEPTED (runtime)**, [OpenClaw #10](https://github.com/AlbanAndrieu/nabla-openclaw/pull/10) fusionnée le 05/11 ; digest Telegram et heartbeat observés | Aucun droit de démarrer un ancien cron Workstation en parallèle |

## Dernières actions P1

1. **OpenClaw Workstation** : retirer les scripts mutateurs et copies
   de politiques sans consommateurs, remplacer les recettes anciennes
   par le dépôt `nabla-openclaw`, puis vérifier localement leurs tests
   de non-régression. Le premier lot retire l'outil de scratch heartbeat
   pré-cutover et l'inventaire Git historique.
2. **Nabla Compose** : conserver LiteLLM TrueNAS, les modèles et quotas,
   l'API d'observation, la connectivité NFS/CSI, les scripts TrueNAS
   d'identité et les diagnostics **inter-hôtes** non dupliqués dans le
   dépôt OpenClaw. Ne jamais détruire le rollback encore utilisable.
3. **YubiKey / secrets** : garder la preuve de récupération age/SOPS
   sur deux supports. Ne pas recopier d'identités, de secrets, de
   sessions ni de clés dans Git. Le cycle PKI/YubiKey se gère dans
   son dépôt spécialisé.

## Problèmes passés à conserver

- **1er–2 novembre** : le `doctor` du Gateway TrueNAS bloquait sur une
  attente ZFS ; rollback Workstation réellement effectué. La reprise
  du 3 novembre a été réceptionnée sans Discord.
- **3–4 novembre** : la base PostgreSQL du LiteLLM Workstation n'était plus
  accessible par la publication LAN ; le réseau `intranet` a corrigé
  le chemin. Un port TCP joignable ne garantit pas une API de modèles
  fonctionnelle.
- **Digest** : un prompt imprécis provoquait Tool Search sur le nom du
  skill, des scripts inventés et `--top 3-5` invalide. Le cron utilise
  désormais une commande `exec` explicite, `--top 5` et supprime
  Twitter dont l'API répondait `402`.
- **Secrets OpenClaw / LiteLLM** : la présence des clés virtualisées dans
  la base ou dans un fichier n'implique pas la validité de la requête ;
  conserver les preuves main/cron et éviter l'usage de clés maîtresses.
- **Séparation des sources** : un artefact migré dans un sous-module doit
  conserver sa provenance Git, les chemin d'includes et son rollback ;
  `apps/openclaw` n'est pas un répertoire de code ordinaire après le
  cutover.

Les procédures détaillées sont conservées dans
[les incidents et diagnostics OpenClaw](runbooks/openclaw-litellm-429-attribution.md)
et la [roadmap Workstation archivée](openclaw-workstation-roadmap.md).
Une ancienne section « NO-GO / aucun Gateway TrueNAS » n'a plus de valeur
opérationnelle. Aucune activité en production n'est déclenchée par cette page.
