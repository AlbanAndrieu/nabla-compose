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

## P0 — Test réversible du choix du lecteur PC/SC (17 octobre 2026)

Constat confirmé sur la workstation : `pcsc_scan` voit un lecteur
`Yubico YubiKey OTP+FIDO+CCID 00 00` avec carte insérée ; `ykman`
lit l'applet OpenPGP ; `gpg-connect-agent 'SCD GETINFO version'`
réussit, mais `SCD SERIALNO` et `gpg --card-status` renvoient
`No such device`. Un processus `scdaemon` tourne ; `disable-ccid`
est déjà activé. L'erreur de sélection n'est **pas** encore expliquée.

**Ne pas confondre** `SCD GETINFO reader_list` terminé par `OK`
avec une preuve que l'applet OpenPGP est sélectionnée. Ne pas
automatiser une correction non vérifiée sur le serveur TrueNAS.

### Préparation sur Linux (lecture seule)

```bash
gpgconf --list-dirs homedir
gpg-connect-agent 'SCD GETINFO app_list' /bye
gpg-connect-agent 'SCD GETINFO reader_list' /bye
timeout 5 pcsc_scan -n
grep -nE '^[[:space:]]*(disable-ccid|reader-port|pcsc-driver)' \
  ~/.gnupg/scdaemon.conf
```

La liste de lecteurs peut révéler un identifiant matériel ; ne pas
transmettre la sortie brute. Le lecteur PC/SC observé est
`Yubico YubiKey OTP+FIDO+CCID 00 00` ; vérifier le nom **exact**
localement avant tout essai de `reader-port`. D'après le manuel GnuPG,
`reader-port` accepte un nom de lecteur pour PC/SC ; son absence
n'est pas intrinsèquement une erreur, car le lecteur par défaut est
normalement le premier trouvé.

### Correction du runbook interactif (2026-10-17)

**Attention :** le bloc d'essai précédent commençait par `set -e`
dans le shell interactif. Si `test ! -e "$BACKUP"` échoue parce
que le fichier existe, Bash peut fermer le terminal. De même,
`gpg --card-status` renvoie un code non nul tant que la carte
n'est pas sélectionnée. **Ne pas lancer `set -e` directement dans
le terminal.** Pour désactiver ce mode dans la session :
`set +e`.

Une sauvegarde `scdaemon.conf.before-reader-port` existe déjà
sur la workstation. Ne pas l'écraser ni présumer de son contenu.
La restauration opérateur a réussi; contrôler les directives
actuelles en lecture seule avant un nouvel essai :

```bash
bash scripts/workstation/plan-gpg-reader-port.sh --check
grep -nE '^[[:space:]]*(disable-ccid|reader-port|pcsc-driver)' \
  "$(gpgconf --list-dirs homedir)/scdaemon.conf" || true
```

Pour éviter toute sortie intempestive d'une session interactive,
effectuer le diagnostic de la carte en conditionnelle :

```bash
if gpg --card-status; then
  echo '✅ Carte accessible'
else
  printf '⚠️ Carte inaccessible (code %s)\n' "$?"
fi
```

Le `dmesg` partagé comporte **quatre segfaults dans
`libpcsclite_real.so.1` le 16 octobre**. Leur nom de thread
(`pool-0`, `pool-1`, `pool-3`) ne permet pas
d'attribuer l'incident à `scdaemon` sans identification du
processus via `coredumpctl` et les événements système.
Ces erreurs sont antérieures aux manipulations USB volontaires
du 17 octobre. Priorité à une identification non destructive :

```bash
coredumpctl list --since '2026-10-16 00:00:00' --no-pager \
  2>/dev/null | grep -E 'libpcsclite|pool-|gpg|scdaemon' || true
journalctl -k --since '2026-10-16 00:00:00' --until '2026-10-17 00:00:00' \
  --no-pager | grep -F 'libpcsclite_real.so.1' || true
```

Ne pas transmettre de dump mémoire ni lancer `coredumpctl dump` :
un processus lié à GPG peut contenir des informations sensibles.

### Essai supervisé (modifie uniquement scdaemon.conf local)

Ce test est à exécuter seulement après avoir terminé les opérations
Git signées ou les sauvegardes qui utilisent GPG :

```bash
umask 077
# Stopper manuellement si le backup existe, sans activer set -e dans le shell.
if [[ -e ~/.gnupg/scdaemon.conf.before-reader-port ]]; then
  echo '⚠️ Sauvegarde existante : interrompre et vérifier avant toute modification.'
else
  cp -p ~/.gnupg/scdaemon.conf ~/.gnupg/scdaemon.conf.before-reader-port
  echo '✅ Sauvegarde créée ; les étapes suivantes sont à lancer séparément.'
fi
# Vérifier que le nom du lecteur correspond exactement à pcsc_scan.
printf '%s\n' 'reader-port Yubico YubiKey OTP+FIDO+CCID 00 00' \
  >> ~/.gnupg/scdaemon.conf
gpgconf --kill scdaemon
gpg --card-status
```

Si le test échoue, **rollback** après vérification que le fichier
`.before-reader-port` est bien la sauvegarde de cet essai :

```bash
cp -p ~/.gnupg/scdaemon.conf.before-reader-port ~/.gnupg/scdaemon.conf
gpgconf --kill scdaemon
gpg --card-status
```

Ne pas utiliser `gpgconf --kill all`, `systemctl restart pcscd`,
`keytocard`, ni reprogrammer la carte dans le cadre de cet essai.
Ne pas répéter ce test si la configuration contient déjà un
`reader-port` ou si une sauvegarde du même nom existe : préserver
les modifications précédentes et arbitrer manuellement.

Source : https://www.gnupg.org/documentation/manuals/gnupg/Scdaemon-Options.html

### Observation PC/SC du 17 octobre à 12:33

`timeout 5 pcsc_scan -n` détecte `Yubico YubiKey OTP+FIDO+CCID 00 00`
et un ATR identique lors de deux lectures. Le scanner affiche
successivement `Card inserted, Shared Mode`, puis `Waiting for the
first reader` avant de retrouver la carte. **L'opérateur a explicitement débranché et rebranché la clé** pour
vérifier la détection : cette réénumération USB est attendue et
**ne constitue pas un indice d'instabilité matérielle**.

Prochain contrôle en lecture seule : relevé ciblé des événements
`journalctl -k --since '-10 min' --no-pager` et
`journalctl -u pcscd.service --since '-10 min' --no-pager` autour
d'une seule tentative `gpg --card-status`. Inspecter localement
les identifiants et chemins avant de partager les journaux.
Ne pas redémarrer PC/SC et ne pas changer de slot.

### Clarification opérateur — 17 octobre 2026, 12:36

Les déconnexions/reconnexions USB de 12:33 sont **volontaires**.
Les erreurs PC/SC `SCardConnect ... Not Found` à 12:33:28
correspondent à la période de réénumération et ne prouvent
aucune panne persistante du lecteur. Une nouvelle tentative
`gpg --card-status` à 12:36:31 échoue toujours par
`No such device` alors que la carte est connectée.

**Priorité corrigée :** investiguer la sélection de l'applet par
`scdaemon` et la configuration GnuPG/PCSC, plutôt que l'USB.
Ne pas demander d'autres cycles de débranchement ni redémarrer
`pcscd` sans justification. La procédure réversible `reader-port`
reste une hypothèse à tester, non une correction confirmée.

### Préflight automatisé, strictement en lecture seule

Avant l'essai manuel de `reader-port`, exécuter sur la workstation :

```bash
bash scripts/workstation/plan-gpg-reader-port.sh --check
```

Ce préflight vérifie `disable-ccid`, l'absence de `reader-port` déjà
configuré, l'absence de sauvegarde homonyme et la visibilité du lecteur
YubiKey avec carte insérée. Il **ne modifie rien**, n'émet aucun
identifiant de carte et ne lance pas `gpgconf --kill`. Il refuse
également d'agir comme root ou de remplacer une ancienne sauvegarde.

Le journal USB observé à 12:33 correspond à une reconnexion volontaire,
pas à une panne USB prouvée. Une réussite du préflight ne garantit
pas la correction de `SCD SERIALNO`; elle autorise seulement la
préparation d'un essai supervisé et réversible.

### Corrélation coredump — 17 octobre 2026

L'opérateur confirme `errexit` inactif après restauration de la
configuration et présence du backup `scdaemon.conf.before-reader-port`.
Ne pas recommencer un essai de configuration avant examen du backup.

`coredumpctl list --since '2026-10-16 00:00:00'` identifie :
- Seahorse (`/usr/bin/seahorse`) SIGSEGV à 00:23:19, 09:02:49, 09:12:17 ;
- Nemo SIGSEGV à 02:39:18 et VS Code SIGSEGV à 18:40:09.

Le `dmesg` observait un segfault dans `libpcsclite_real.so.1`
**exactement à 00:23:19** : le processus correspondant est Seahorse.
Cette corrélation suggère un défaut ou usage problématique de la
bibliothèque PC/SC côté client GNOME. Elle ne démontre pas
que Seahorse bloque scdaemon lors des échecs GnuPG du 17 octobre.

Investigation non intrusive :
```bash
pgrep -a -u "$(id -u)" -f 'seahorse|scdaemon|gpg-agent' || true
coredumpctl info 2655324 --no-pager | grep -E 'Executable:|Signal:|Stack trace|libpcsclite' || true
```
Ne pas lancer `coredumpctl dump` ni partager la mémoire du processus.
Éviter `killall`, `gpgconf --kill all` et les redémarrages systemd
avant d'avoir identifié les clients concurrents.

### Résultat 17 octobre, 13:18 — Seahorse non actif

`pgrep` ne trouve que `scdaemon --multi-server` et
`gpg-agent --supervised`. Aucun processus Seahorse actif.
`coredumpctl info 2655324` confirme le crash de Seahorse dans
`libpcsclite_real.so.1`, fonction `SCardGetStatusChange`.
Les plantages antérieurs du client Seahorse sont avérés, mais ne
constituent pas une explication établie du `No such device` actuel.

Le diagnostic GPG a toujours les résultats suivants :
`ykman openpgp info` OK, `pcsc_scan` OK, `SCD SERIALNO` échoue.
Prochaine étape : contrôler les options applicables de `scdaemon`
et, si l'opérateur le souhaite, un essai contrôlé du seul `reader-port`
après inspection du backup préexistant. Ne pas lancer `set -e`
dans le terminal interactif. Éviter les opérations sur les clés
et les modifications PAM/USB.
