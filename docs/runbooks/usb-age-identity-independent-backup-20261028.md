# Sauvegarde indépendante de l'identité privée age sur SanDisk — PR #289

**Objectif P0 :** conserver une copie chiffrée sur la workstation et une copie
chiffrée sur TrueNAS. Ces deux copies sont des supports distincts d'un
**même** secret, pas deux identités age indépendantes.

## Conditions de sécurité

- Brancher **physiquement la SanDisk originale** et déverrouiller son LUKS2
  avant le précontrôle ou la sauvegarde USB. Ne jamais écrire sur ce support.
- Requiert une session terminal locale interactive, `age`, `age-keygen`,
  `findmnt`, Python 3 et le montage NFS `nabla:/mnt/cpool/backup/lab`
  sur `/media/backup/lab`.
- La phrase secrète `age -p` doit être indépendante de la SanDisk, des clés
  SOPS et des autres identifiants. Ne pas la mettre dans la commande, une
  variable d'environnement, un fichier texte ou les journaux. La stocker
  séparément dans un support de récupération approuvé.
- Seules les archives `*.age` chiffrées sont sauvegardées. Les répertoires
  de destination doivent appartenir à l'UID opérateur et être en `0700`,
  les archives en `0600`. Le répertoire local parent ne doit pas être
  accessible en écriture par le groupe ou les autres.
- Les ACL NFS4 effectives du fichier et des parents restent un contrôle
  distinct, non démontré par les seuls bits POSIX.

## Étapes opérateur (workstation, pas GitHub Actions)

1. Mettre à jour la branche de PR #289 en avance rapide, sans écraser
   les modifications locales.
2. Préparer si besoin le répertoire local privé :
   `install -d -m 0700 "$HOME/.local/share/nabla"`.
   Vérifier **manuellement** que `/media/backup/lab/secret` est le
   répertoire NFS prévu, privé et propriétaire UID correct. Ne pas modifier
   les permissions du NFS à l'aveugle.
3. Exécuter `just yubikey-usb-identity-backup-test` et
   `just yubikey-usb-identity-restore-test`. Les suites utilisent uniquement
   des fixtures et mocks.
4. SanDisk physiquement présente, déverrouillée et montée : exécuter
   `just yubikey-usb-identity-backup-check`. Exiger
   `BACKUP_PREFLIGHT_READY`. Tout autre état est un **NO-GO**.
5. Lancer **une seule fois** `just yubikey-usb-identity-backup`.
   Choisir/saisir la phrase secrète indépendante au prompt TTY.
   Exiger `ENCRYPTED_LOCAL_AND_NFS_BACKUPS_IDENTICAL`.
   Ne jamais réexécuter l'ancienne commande NFS `--copy`.
6. Déconnecter la SanDisk originale **après** la sauvegarde.
   Exécuter `just yubikey-usb-identity-restore-check` et exiger
   `BACKUP_RESTORATION_PREFLIGHT_READY`.
7. Exécuter `just yubikey-usb-identity-restore-verify` depuis un TTY privé.
   Fournir la phrase secrète aux prompts `age` pour chacune des copies.
   Exiger `BOTH_BACKUPS_RESTORED_WITH_HISTORICAL_RECIPIENT` et
   `two_encrypted_backups_restored=true`.

## Portée exacte des preuves

`backup-check` ne lit pas la clé. `backup` lit l'identité USB uniquement
depuis son descripteur ouvert en lecture et produit deux fichiers chiffrés.
`restore-check` vérifie les métadonnées sans lire les archives.
`restore-verify` compare les octets chiffrés, déchiffre chaque copie
séparément dans la mémoire des processus et dérive le destinataire public
historique avec `age-keygen -y`. La clé privée n'est ni publiée ni écrite
dans un fichier par cet outil. Ne pas activer le tracing shell, les core dumps,
la capture de session ou des outils de débogage de processus pendant l'opération.
La mémoire de processus reste soumise aux politiques de swap du système.

Un PASS prouve que **les deux copies ont pu être déchiffrées** et que leur
identité correspond au destinataire age historique. Il ne constitue pas un
nouveau test de déchiffrement SOPS de production ni un audit des ACL NFS4.
Il ne démontre pas une indépendance géographique ou une restauration après
perte du NFS.

Si une étape échoue : arrêter. Ne pas supprimer les archives, les réécrire,
faire tourner les clés, modifier PIV9A/PIV82/OTP2 ou relancer la sauvegarde.
Conserver l'état `NO-GO` et diagnostiquer uniquement en lecture seule.

**État de publication :** scripts et tests ajoutés dans la PR. La création
réelle des deux copies et leur restauration sur workstation doivent encore
être attestées par les sorties opérateur, sans secrets.
