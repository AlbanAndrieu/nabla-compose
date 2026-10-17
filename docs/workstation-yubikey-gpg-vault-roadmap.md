# Roadmap YubiKey : GnuPG, signatures Git, sauvegardes PostgreSQL, Vault

## Situation vérifiée (2026-10-16)

- Les deux YubiKeys ont leur OTP slot 2 HMAC-SHA1 fonctionnel pour KeePassXC.
- La clé GPG prioritaire pour Git et git-crypt est `F4C4B79A80826A5E5ADAD2C8B12DECD437E9E1C8`.
- La clé GPG FlowCrypt n'est plus utilisée, mais doit être conservée pour lire d'anciennes données si nécessaire.
- Les sous-clés GPG semblent locales (GnuPG `sec`/`ssb`); rien ne prouve leur présence sur la carte.
- Sur le poste Linux, GnuPG 2.4.8 et pcscd sont actifs. `ykman openpgp info` fonctionne,
  mais `gpg --card-status` renvoie `No such device` même après activation de `disable-ccid`.
- Le journal scdaemon rapporte `ccid open error: skip`. Le diagnostic doit distinguer
  conflit PCSC, sélection du lecteur, permissions et régression GnuPG; ne pas attribuer
  une cause unique sans preuve.
- Le certificat PIV Nabla Root CA dans slot 9A est autosigné, RSA2048,
  `CA:TRUE,pathlen:0`, `keyCertSign/cRLSign`, et expiré le 2025-01-22.
  Il ne permet pas une CA intermédiaire classique pour Vault; ne pas le réutiliser
  comme racine du futur chemin intermédiaire.

## Ordre d'exécution, sans mutation automatique

### P0 — Stabiliser GnuPG/PCSC et protéger les clés

- [x] Créer `scripts/workstation/diagnose-gpg-smartcard.sh --check`, lecture seule, sortie colorée.
- [ ] Comparer le résultat avec chacune des deux clés, une à la fois.
- [ ] Inspecter `systemctl status pcscd.service`, `journalctl --user -u gpg-agent`
      et les périphériques lecteurs. Les logs doivent être nettoyés avant partage.
- [ ] Après sauvegarde de `scdaemon.conf`, tester sur poste une seule variable
      à la fois : sélection du lecteur, puis option CCID/PCSC. Ne jamais désactiver
      un service système utilisé par d'autres applications sans étude d'impact.
- [ ] Définir un rollback local documenté et retester `gpg --card-status`.

**Critère de fin :** la carte répond depuis GnuPG sur les deux YubiKeys;
les logs ne contiennent plus d'erreur bloquante. Pas de rotation de PINs.

### P0 — Signature Git et déchiffrement des sauvegardes PostgreSQL

- [ ] Identifier les sous-clés de signature, de chiffrement et les destinataires
      exacts de Git-crypt et des sauvegardes PostgreSQL.
- [ ] Réaliser une sauvegarde privée hors ligne de GPG et une restauration contrôlée,
      avant tout `keytocard`.
- [ ] Confirmer `git commit -S` et `git verify-commit`, `git-crypt unlock`
      depuis une copie et déchiffrer/restaurer une sauvegarde PostgreSQL isolée.
- [ ] Concevoir deux identités matérielles utilisables après panne d'une seule clé.
      Une clé privée déjà installée sur la carte ne s'exporte pas; des clés de secours
      doivent provenir d'un escrow hors ligne ou d'une architecture de destinataires multiples.

**Critère de fin :** signature Git et restauration PostgreSQL opérationnelles
avec preuve de récupération indépendante du matériel.

### P1 — PKI Nabla Root CA et futur Vault / OpenBao

- [ ] Recenser les consommateurs historiques de la CA PIV expirée.
- [ ] Vérifier si un fichier CA historique existe et correspond à la clé publique
      PIV; sa présence n'est pas une preuve de sauvegarde valide.
- [ ] Concevoir une **nouvelle** CA racine hors ligne avec `pathlen` compatible
      avec la CA intermédiaire de Vault et rotation/révocation documentées.
- [ ] Concevoir des sauvegardes chiffrées et un test de signature hors ligne.
- [ ] Mettre en place une CA intermédiaire Vault/OpenBao séparée,
      sans dépendance circulaire au déverrouillage de Vault.

**Critère de fin :** test d'émission, chaîne complète validée,
récupération hors ligne démontrée; ancien slot 9A conservé jusqu'à décision.

### P2 — SSH, PAM, age, keyring

- [ ] SSH FIDO2/PIV : identités distinctes par clé et recovery.
- [ ] PAM U2F : enregistrer deux clés avant de rendre la vérification obligatoire.
- [ ] age-plugin-yubikey : identifier les slots PIV libres, tester des destinataires multiples.
- [ ] GNOME Keyring : étudier l'auto-unlock sans dépendance circulaire au login FIDO2.

## Procédure manuelle et retour arrière pour scdaemon

Le diagnostic n'effectue aucune correction automatique :

```bash
bash scripts/workstation/diagnose-gpg-smartcard.sh --check
```

Pour revenir à l'état antérieur de la modification déjà effectuée
sur `~/.gnupg/scdaemon.conf`, **inspecter d'abord** `scdaemon.conf.bak`
et le fichier actuel; si la sauvegarde correspond réellement au bon état
antérieur, la restauration se fait manuellement après décision explicite.
Le redémarrage de scdaemon affecte les sessions GPG en cours, donc doit
être fait en dehors des opérations Git/backup. Ne pas exécuter de
`gpg --edit-key`, `keytocard`, `ykman piv reset`, ni d'édition PAM
comme diagnostic.

Documentation : https://www.gnupg.org/documentation/manuals/gnupg/Scdaemon-Options.html
et https://developer.hashicorp.com/vault/docs/secrets/pki

## TrueNAS : exécution sans YubiKey locale (retour opérateur)

Sur TrueNAS, GnuPG 2.4.7 est installé et GNUPGHOME pointe vers
`/mnt/cpool/home/albandrieu/.gnupg`. `ykman` est absent, `pcscd`
est inactif et le contexte systemd utilisateur n'a pas répondu.
Aucun accès matériel YubiKey n'est confirmé. Dans cet environnement,
`gpg --card-status` échoue normalement s'il n'y a ni lecteur connecté,
ni passthrough CCID. Cela **ne prouve pas** une panne GPG du serveur.

Exécuter le mode hôte (aucun appel matériel) :

```bash
bash scripts/workstation/diagnose-gpg-smartcard.sh --host-only
```

Ne pas installer `ykman` ni activer `pcscd` sur TrueNAS uniquement
pour faire réussir ce test. Réserver l'audit matériel au poste Linux
ayant la clé branchée. Pour les sauvegardes PostgreSQL, TrueNAS
devrait normalement pouvoir chiffrer vers une clé **publique**,
sans héberger la clé privée GPG ni avoir besoin de la YubiKey.
Vérifier l'architecture réelle avant de changer les jobs de backup.

## Workstation 22916048 — second diagnostic (2026-10-16)

Operator output: `pcscd.socket` and `pcscd.service` active,
`gpg-agent` active, GnuPG 2.4.8, `disable-ccid` configured,
`ykman openpgp info` succeeds, `SCD GETINFO version` succeeds,
but `gpg --card-status` still reports `No such device`.
This narrows the problem to the **selection/use of a smartcard reader**,
not to the existence of the OpenPGP applet.

Next steps, keeping the OTP HMAC slot 2 and PIV 9A untouched:

1. Run the updated read-only diagnostic, which probes
   `SCD GETINFO reader_list`, `SCD SERIALNO`, and `pcsc_scan` if
   installed. No card numbers or raw ATR are printed.
2. Check for unrelated processes holding the PC/SC reader (browser,
   SSH-agent alternatives, smartcard middleware), ideally with all
   browser and certificate UI clients closed before retrying.
3. If there is an identified reader name, evaluate a *manual,
   reversible* `reader-port` configuration on the workstation; test
   a single variable per run and retain the previous config.
4. Investigate GnuPG 2.4.x specific CCID/PCSC behavior and the
   GnuPG upstream issue T4998. Do not enable `pcsc-shared` blindly;
   concurrent clients could invalidate scdaemon's cached state.
5. Do not attempt `keytocard` until `gpg --card-status` works,
   GPG escrow is validated, and PostgreSQL backup restore passes.

Known relevant upstream reports:
- https://dev.gnupg.org/T4998
- https://github.com/LudovicRousseau/PCSC/issues/215
- https://www.gnupg.org/documentation/manuals/gnupg/Scdaemon-Options.html

## 2026-10-17 — lecteur PC/SC confirmé sur workstation

- `pcsc-tools` installé sur Ubuntu workstation (`pcsc_scan` v1.7.4).
- Le lecteur `Yubico YubiKey OTP+FIDO+CCID 00 00` est bien reconnu
  avec carte insérée en **Shared Mode** et ATR décodé.
- `gpg --card-status` échoue toujours `No such device`.
  **Conclusion : l'absence de lecteur PC/SC est écartée**. Investiguer
  le chemin scdaemon→PC/SC→sélection applet OpenPGP, les conflits
  d'accès concurrent ou la configuration GnuPG 2.4.8.
- Le bootstrap workstation `bootstrap-yubikey-manager.sh --apply`
  installe désormais `pcsc-tools` et `--check` vérifie
  `pcsc_scan`. Ne pas effectuer cette installation sur TrueNAS.
- Une mise à jour noyau Ubuntu (7.0.0-34 en exécution, 7.0.0-38 installé)
  est en attente, avec services redémarrés différés. Prévoir un reboot
  contrôlé de la workstation hors sessions et travaux en cours ;
  ne pas attribuer le problème de carte au noyau sans nouvelle preuve.

**Gate suivante :** `gpg --card-status` fonctionne sur la workstation,
puis test de signature avec clé de test / contrôle de clé existante sans
`keytocard`, sans migration de sous-clé et sans réinitialisation.
