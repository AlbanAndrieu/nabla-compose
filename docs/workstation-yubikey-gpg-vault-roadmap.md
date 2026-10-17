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

### Validation opérateur : configuration restaurée (17 octobre 2026)

`cmp -s scdaemon.conf scdaemon.conf.before-reader-port` : **identiques**.
`gpgconf --check-options scdaemon` : entrée
`scdaemon:Smartcards:/usr/lib/gnupg/scdaemon:1:1:` (pas de
message d'erreur explicite). Le rollback précédent a restauré les
octets du fichier ; cela ne valide pas l'accès matériel OpenPGP.

Pour éviter qu'une erreur n'interrompe le terminal interactif,
**ne jamais coller `set -e` dans le shell de l'opérateur**. Utiliser
un script dédié en sous-processus avec contrôle des préconditions,
pas une séquence interactive qui continue après l'échec d'un
`test`. La sauvegarde existante est à conserver ; aucune routine
ne doit l'écraser. Avant un essai réel, confirmer que le poste
n'effectue ni signature Git ni déchiffrement GPG.

## Architecture PC/SC et hypothèse reader-port — décision P0 (17 octobre 2026)

### À quoi sert PC/SC ?

**PC/SC** (Personal Computer/Smart Card) est l'interface standard
permettant aux logiciels Linux d'utiliser les lecteurs de cartes à puce.
Sur Ubuntu, `pcscd` expose les lecteurs CCID et arbitre leur accès via
`libpcsclite`. `pcsc_scan` **énumère le lecteur et voit la carte** :
il ne démontre pas que GnuPG a sélectionné l'application OpenPGP.

Le chemin recherché est :
`gpg --card-status` → `gpg-agent` → `scdaemon` →
bibliothèque PC/SC → `pcscd` → interface USB CCID →
applet OpenPGP de la YubiKey.

`ykman openpgp info` constitue un contrôle **indépendant** : son
succès confirme que le périphérique et l'applet répondent par le
chemin choisi par ykman, pas nécessairement que `scdaemon` sait
utiliser le même lecteur.

### Que fait reader-port ?

Dans `~/.gnupg/scdaemon.conf`, `reader-port` indique **quel
lecteur** scdaemon doit sélectionner. En mode PC/SC, la valeur
peut correspondre au nom du lecteur (à confirmer sur la machine).
Ce n'est ni un port TCP, ni un port USB physique, ni un secret,
et ce n'est **pas une modification sur la YubiKey**.

`disable-ccid` demande à scdaemon de ne pas employer son
pilote CCID intégré et de privilégier la pile PC/SC. L'absence
de `reader-port` est normalement valide : scdaemon sait
chercher un lecteur. L'essai d'une sélection explicite est donc
**un test d'hypothèse, pas un correctif présumé**.

### Pourquoi le tester dans notre cas ?

Observations confirmées sur workstation : lecteur
`Yubico YubiKey OTP+FIDO+CCID 00 00` et carte visibles par
`pcsc_scan`, applet visible par `ykman`, `scdaemon`
répond à `GETINFO version`, mais `SCD SERIALNO` et
`gpg --card-status` répondent `No such device`.
Un `SCD GETINFO reader_list` terminé par `OK` ne confirme
pas la sélection de l'applet. Seahorse n'était pas actif lors du
dernier échec ; ses SIGSEGV PC/SC antérieurs ne prouvent
pas qu'il soit la cause du blocage actuel.

### Protocole, garde-fous et critères d'acceptation

1. **Préflight déjà réussi :** `scdaemon.conf` et
   `scdaemon.conf.before-reader-port` sont strictement identiques ;
   aucun `reader-port` actif ; `pcsc_scan` voit la carte.
   Préserver la sauvegarde préexistante sans jamais l'écraser.
2. **Essai supervisé uniquement sur workstation :** terminer les
   opérations utilisant GPG ; vérifier le nom PC/SC exact ; appliquer
   *une seule* directive `reader-port` dans une procédure isolée
   qui contrôle toutes les erreurs. **Ne jamais activer `set -e`
   dans le terminal interactif de l'opérateur.**
3. **Rafraîchir seulement scdaemon** si et seulement si l'essai est
   autorisé ; comparer `SCD SERIALNO` et `gpg --card-status`
   avant/après, avec délai borné. Ne toucher ni à `pcscd`, ni
   aux PIN, ni aux slots OpenPGP/PIV/OTP.
4. **Succès :** la carte OpenPGP est affichée par
   `gpg --card-status`; vérifier séparément les deux YubiKeys
   sans transférer ou supprimer de sous-clé.
5. **Échec :** restaurer la sauvegarde octet pour octet, rafraîchir
   uniquement scdaemon, vérifier `cmp`, consigner les résultats
   et investiguer les traces PC/SC/GnuPG sans exfiltrer les dumps.

La continuité **Git signing, git-crypt et restauration des sauvegardes
PostgreSQL** est une condition préalable à tout futur transfert de
clé via `keytocard` ; ce chantier ne réalise aucun transfert.

Documentation de référence :
https://www.gnupg.org/documentation/manuals/gnupg/Scdaemon-Options.html

### P0 — Essai transactionnel de reader-port (agent, 17 octobre)

Le script `scripts/workstation/test-gpg-reader-port.sh` sépare
`--check` (lecture seule) de `--apply` (essai supervisé).
Il contrôle l'égalité byte-à-byte du `scdaemon.conf` courant avec
`scdaemon.conf.before-reader-port`, la présence du lecteur,
`disable-ccid`, et l'absence de directive `reader-port`.
Il refuse root, ne remplace jamais la sauvegarde et ne modifie
aucune clé, certificat ou PIN.

`--apply` utilise un fichier temporaire dans le même répertoire
avec permissions préservées, sélectionne temporairement le lecteur
`Yubico YubiKey OTP+FIDO+CCID 00 00`, rafraîchit uniquement
`scdaemon` et teste `gpg --card-status` avec un délai borné.
Un trap restaure ensuite la sauvegarde et rafraîchit `scdaemon`,
même si le test réussit. Le script est exécuté dans un processus Bash
séparé : il ne change jamais `errexit` dans le terminal parent.
Les terminaisons brutales non interceptables (SIGKILL, coupure secteur)
ne permettent pas un rollback automatique : dans ce cas utiliser la
sauvegarde préexistante avant tout nouvel essai.

**Gates :** `bash -n`, test de contrat Python et mode Git 100755
dans l'environnement agent ; `--check` et `--apply` à exécuter
uniquement sur workstation une fois les opérations GPG terminées.
Si `--apply` annonce le succès, une décision explicite distincte
sera nécessaire avant toute configuration persistante.

### P0 — Résultat de l'essai transactionnel reader-port (17 octobre 2026)

Résultats de la workstation :
- `test-gpg-reader-port.sh --check` : préflight PASS ;
- `test-gpg-reader-port.sh --apply` : PC/SC PASS, mais
  `gpg --card-status` ne sélectionne pas la carte avec
  `reader-port Yubico YubiKey OTP+FIDO+CCID 00 00` ;
- le script annonce la **restauration réussie** de
  `scdaemon.conf` original. Ne pas répéter le même test.

**Conclusion :** la sélection explicite du lecteur ne suffit pas.
La cause reste non identifiée. Prochaines pistes : vérifier la
bibliothèque PC/SC réellement chargée par `scdaemon`, examiner
les journaux bornés `scdaemon` lors d'une seule tentative,
et tester séparément (sur un profil GnuPG isolé, sans clés privées)
le chemin CCID intégré versus PC/SC, avec contrôle de retour arrière.
Ne pas redémarrer `pcscd` arbitrairement ni modifier les clés,
les PIN, KeePassXC OTP, PIV ou Git-crypt.

### P0 — Liaison dynamique scdaemon / PC/SC (17 octobre, 14:19)

Le `ldd /usr/lib/gnupg/scdaemon` de la workstation retourne
`libgcrypt.so.20`, `libassuan.so.9` et `libusb-1.0.so.0`,
mais pas `libpcsclite.so.1`. Ce n'est **pas une preuve d'absence
de PC/SC** : scdaemon peut charger ce pilote dynamiquement.

`gpgconf --list-options scdaemon` confirme :
- `reader-port` (lecteur sélectionné explicitement, déjà essayé sans succès),
- `pcsc-driver` (valeur par défaut `libpcsclite.so.1`),
- `disable-ccid` (déjà présent dans la configuration),
- `disable-pinpad` (sans rapport démontré avec la sélection).

**Nouvelle hypothèse vérifiable :** pilote PC/SC mal résolu ou échec
lors du chargement dynamique ou de l'appel PC/SC par scdaemon.
Contrôles en lecture seule sur la workstation :

```bash
ldconfig -p | grep -F libpcsclite.so.1 || true
readlink -f /usr/lib/x86_64-linux-gnu/libpcsclite.so.1
pgrep -a -u "$(id -u)" -x scdaemon || true
# En cas de processus scdaemon actif, confirmer le pilote chargé
for pid in $(pgrep -u "$(id -u)" -x scdaemon); do
  grep -F libpcsclite /proc/"$pid"/maps || true
done
```

La présence de la bibliothèque sur disque confirme sa disponibilité
pour le chargeur ; son absence dans `/proc/PID/maps` **à cet instant**
ne prouve pas qu'elle n'a jamais été chargée. L'essai `reader-port`
a échoué avec rollback réussi ; ne pas le répéter à l'identique.
Aucune réinitialisation ou transfert de clés.

### P0 — Vérification bibliothèque disponible, processus absent (17 octobre)

`ldconfig -p` résout `libpcsclite.so.1` vers
`/usr/lib/x86_64-linux-gnu/libpcsclite.so.1`, et
`readlink -f` confirme le même chemin. La boucle
`pgrep -u "$(id -u)" -x scdaemon` n'a affiché aucun PID au
moment du contrôle : impossible de consulter `/proc/PID/maps`.
Ne pas conclure à une bibliothèque manquante ou non chargée.

Prochain diagnostic : interroger l'état de scdaemon immédiatement
après une tentative OpenPGP, dans **une seule session de commandes**
sans `set -e` interactif. Interroger `gpg-connect-agent` avec un
timeout, puis regarder les PIDs et mappings. Ne pas utiliser
`gpgconf --kill all`, ne pas créer de profil avec des secrets
et ne pas modifier `scdaemon.conf`.

### P0 — Scdaemon vivant, /proc/PID/maps restreint (17 octobre 2026)

L'opérateur a exécuté `SCD GETINFO version` : `D 2.4.8`,
`OK`. `gpg --card-status` échoue `No such device`. Un
`scdaemon --multi-server` PID 1053989 reste actif. Lire
`/proc/1053989/maps` comme l'utilisateur produit `Permission denied`.
Cela **ne prouve pas** que `libpcsclite` manque : accès `/proc`
potentiellement limité par les protections noyau/ptrace.
L'essai root `pgrep -u "$(id -u)"` cherchait UID 0, pas
l'instance UID 1000 : aucune conclusion possible de sa sortie vide.

Prochain contrôle sans privilèges : `gpgconf --list-options scdaemon`,
`ldconfig -p` et statut `pcscd` sont déjà validés. Si un contrôle
de mapping est indispensable, cibler le bon UID/PID, sans désactiver
les protections du noyau. Préférer ensuite un diagnostic isolé
`GNUPGHOME` temporaire pour comparer transport CCID intégré et
PC/SC, sans importer de clés privées, sans toucher aux slots, et
sans interrompre le profil GnuPG utilisateur.

### P0 — Comparatif isolé PC/SC / CCID intégré

`scripts/workstation/compare-gpg-card-transports.sh` compare deux
profils GnuPG temporaires (`GNUPGHOME`) sans clé importée :
- `pcsc` avec `disable-ccid` ;
- `ccid` sans `disable-ccid` (pilote CCID intégré).

`--check` valide les prérequis ; `--run` effectue deux lectures
`gpg --batch --card-status` bornées à 18 secondes chacune.
Les résultats masquent les identifiants de carte. À la fin,
les agents des **profils temporaires uniquement** sont arrêtés,
les répertoires temporaires supprimés, et le vrai profil
`~/.gnupg` reste inchangé. Ce test ne touche pas aux clés ni
aux PIN ; il accède cependant à la même interface USB physique,
donc ne pas effectuer en parallèle de signature ou déchiffrement.

```bash
./scripts/workstation/compare-gpg-card-transports.sh --check
./scripts/workstation/compare-gpg-card-transports.sh --run
```

Résultats à interpréter :
- PC/SC OK, CCID KO : défaut plutôt côté accès CCID intégré ;
- PC/SC KO, CCID OK : défaut probablement dans le chemin PC/SC ;
- tous deux KO : examiner contention, permissions du lecteur,
  configuration GnuPG, journal des erreurs scdaemon ;
- tous deux OK : défaut propre au profil utilisateur.

Le succès de `--run` ne migre aucune clé GPG. Ne pas
exécuter `keytocard`. En cas d'arrêt non interceptable, des
agents temporaires peuvent nécessiter une inspection avant nettoyage.

### P0 — Résultat comparatif transports, 17 octobre 2026

L'opérateur a exécuté `compare-gpg-card-transports.sh --check` :
PASS. L'essai `--run` sur deux homes GnuPG isolés a retourné
`No such device` avec **PC/SC** (`disable-ccid`) **et CCID
intégré** (sans `disable-ccid`). Le script a terminé avec le
nettoyage des profils temporaires. La configuration originale
et les clés privées restent inchangées.

**Décision :** ne pas reproduire l'essai `reader-port` et
ne pas refaire à l'identique le comparatif. Les deux pilotes
ont échoué dans le même environnement matériel/logiciel ;
cela oriente vers une cause commune (accès au périphérique,
contention de client, état USB, règles udev, journal scdaemon)
mais ne prouve pas une cause déterminée.

**Prochaine investigation P0, lecture seule :**
1. Contrôler les processus détenteurs d'une interface USB CCID :
   `lsusb` et `lsusb -t` (sans dump de descripteur privé),
   `fuser` ou `lsof` sur le périphérique USB sélectionné,
   ne pas déconnecter arbitrairement la clé.
2. Examiner `journalctl -u pcscd --since '10 minutes ago'`
   et les éventuelles erreurs CCID/scdaemon associées à
   une seule tentative **bornée**. Filtrer et anonymiser tout
   identifiant de carte avant publication.
3. Distinguer problème de droits (udev, groupe, ACL)
   d'une contention active ; ne pas désactiver la sécurité
   du système, ne pas réinitialiser PC/SC.
4. Si nécessaire, préparer une capture de debug scdaemon
   **isolée et expurgée** sans carte privée, jamais en mode
   `set -x`, avant toute autre action matérielle.

Ne pas modifier YubiKey OTP/HMAC KeePassXC, OpenPGP, PIV,
ni perturber signature Git, git-crypt ou restaurations.

### P0 — USB visible et client GUI YubiKey actif (17 octobre)

L'opérateur observe `1050:0407` (YubiKey 4/5 composite) sur
Bus 001, Device 044 ; interface 2 `Chip/SmartCard` utilisant
`usbfs` — comportement normal pour l'interface CCID pilotée en
espace utilisateur, pas une panne. `pcscd.socket` et
`pcscd.service` sont actifs. Aucun événement dans
`journalctl -u pcscd --since '20 minutes ago'` : ce silence
ne démontre ni fonctionnement parfait ni panne.

**Nouvel élément important :** `ykman-gui` est actif
(PID 2114157), simultanément à `scdaemon` (PID 1053989).
Il s'agit d'un **concurrent potentiel**, pas d'une preuve
de verrouillage. Le diagnostic détecte désormais ce client.

**Prochain test discriminant P0 :** terminer normalement
`ykman-gui` via son interface (ne pas `kill -9`) ;
attendre qu'il n'apparaisse plus dans `pgrep`, puis exécuter
une seule fois `gpg --card-status`. Ne pas débrancher la clé,
ne pas redémarrer `pcscd`, ne pas modifier les PIN ni
répéter les essais `reader-port`. Si toujours KO, investiguer
les journaux scdaemon et permissions USB, avec collecte expurgée.

### P0 — ykman-gui fermé, échec GnuPG persistant (17 octobre 2026)

Après fermeture normale de `ykman-gui`, `pgrep -a -u "$(id -u)" -f '[y]kman-gui'` est vide ; une nouvelle exécution de `timeout 15 gpg --card-status` retourne toujours :
`selecting card failed: No such device` et
`OpenPGP card not available: No such device`.

**Conclusion :** `ykman-gui` actif n'est pas une condition nécessaire de l'échec. Ne pas le désigner comme cause démontrée. Les hypothèses `reader-port`, comparatif PC/SC/CCID et fermeture GUI ont été testées sans résolution.

**Prochaines observations sûres :**
- Droits et type du nœud USB : `stat -c '%A %U:%G %n' /dev/bus/usb/001/044` (numéro de device susceptible de changer).
- Identité des clients actifs via `pgrep`, et messages `journalctl -u pcscd` (sans assurance que le journal soit rempli).
- Journal du démon GnuPG à capturer de manière bornée et expurgée, de préférence avec un homedir GnuPG isolé ; ne pas activer un niveau de trace qui expose les APDU, PIN, numéros de série ou secrets.
- Ne pas exécuter de nouvelle manipulation des slots, réinitialisation, redémarrage `pcscd`, ou changement de permissions globales.

### P0 — ACL USB validées, pas de concurrent identifié (17 octobre 2026)

`lsusb -d 1050:0407` : YubiKey détectée sur bus 001 device 044.
Nœud `/dev/bus/usb/001/044` : `crw-rw-r-- root:pcscd` et
ACL explicite `user:albandrieu:rw-` (masque `rw-`).
`pgrep` : seulement `pcscd` PID 4605 et `scdaemon`
PID 1053989 parmi les clients recherchés.

Les permissions DAC/ACL du nœud USB sont suffisantes pour
l'utilisateur ; ne pas modifier les ACL, groupes ou règles udev
sans autre indice. Cette constatation ne prouve pas l'absence
d'un éventuel blocage LSM ou protocolaire.

**Prochaine étape discriminante :** déployer un diagnostic
`scdaemon` sur home GnuPG isolé, journaux de statut minimaux,
sans `debug-level guru`, `debug-ccid-driver`, `log-file`
contenant des APDU ni traces d'authentification. Tester
`SCD SERIALNO` et sa valeur de retour dans une session bornée
sans divulguer le numéro de série. Prioriser la vérification
de la pile GnuPG/pcsc-lite et des anomalies du processus,
pas de changements aux clés ou à l'interface USB.

### P0 — GETINFO reader_list retourne un identifiant CCID (17 octobre)

L'opérateur obtient `SCD GETINFO version` → `D 2.4.8`, `OK`,
et `SCD GETINFO reader_list` → `D 1050:0407:X:0%0A`,
`OK`. Aucune entrée USB/CCID/AppArmor n'est visible dans
`journalctl -k` filtré sur les 30 dernières minutes.

La chaîne `1050:0407:X:0` ressemble à l'identifiant de
lecteur USB CCID exposé par scdaemon ; elle prouve que le lecteur
est **énuméré**, mais pas que l'application OpenPGP a été
sélectionnée. Le suffixe `%0A` est l'encodage Assuan du
saut de ligne. Ne pas interpréter `X:0` comme un code d'erreur
sans preuve. Documentation GnuPG :
https://www.gnupg.org/documentation/manuals/gnupg/Scdaemon-Options.html

**Contrôle suivant :** distinguer lecteur énuméré et session
applicative en demandant les statuts GnuPG à faible verbosité
et en examinant uniquement le **code** `SCD SERIALNO`.
Ne pas exposer les numéros de série ni utiliser de trace APDU,
`debug-level guru`, dump mémoire, ou opération `keytocard`.

### P0 — Code d'erreur SCD confirmé ; comparaison amont GnuPG (17 octobre)

`gpg-connect-agent 'SCD SERIALNO' /bye` retourne
`ERR 100696144 No such device <SCD>` (numéro de carte non
divulgué). Il s'agit de l'erreur de **scdaemon**, et non d'une
erreur d'accès du shell à `/dev/bus/usb`.

Documentation amont pertinente :
- https://lists.gnupg.org/pipermail/gnupg-users/2024-April/067055.html :
  un utilisateur observe **le même code 100696144** avec
  GnuPG 2.3/2.4, mais un fonctionnement avec 2.2 ; cela établit
  un précédent, **pas la cause de notre panne**.
- https://lists.gnupg.org/pipermail/gnupg-users/2022-January/065855.html :
  `1050:0407:X:0` est une chaîne typique d'énumération
  de lecteur CCID. Un seul lecteur n'exige pas forcément
  `reader-port`.
- https://dev.gnupg.org/T5632.html : pas de fallback
  automatique CCID vers PC/SC depuis GnuPG 2.3 ;
  notre comparatif isolé a déjà testé les deux chemins.

**Prochaine action prioritaire :** capturer uniquement les lignes
de diagnostic non sensibles de `scdaemon` sur un profil
temporaire, ou comparer une version GnuPG distribuée et
supportée dans un environnement totalement isolé sans modifier
les binaires système. Ne pas conseiller downgrade global, compilation
non contrôlée ou `debug-level guru`.

### P0 — Proposition de mise à niveau scdaemon, YubiKey débranchée

L'utilisateur autorise la préparation d'une mise à niveau `scdaemon`
et peut débrancher la YubiKey. **Aucune intervention sur son poste
n'a été exécutée à distance.** Version runtime actuelle
`scdaemon` / `gpg` : 2.4.8.

Ubuntu 26.04 (`resolute-updates`) publie le paquet `scdaemon`
`2.4.8-4ubuntu3.1` (même version GnuPG amont 2.4.8).
Ne pas promettre que ce rafraîchissement corrigera
`ERR 100696144 No such device <SCD>`.
Sources : https://packages.ubuntu.com/resolute-updates/scdaemon
et https://ubuntu.com/security/notices/USN-8720-1 .

**Gate de préinstallation sur workstation, clé retirée, sans modifier :**
```bash
. /etc/os-release
printf 'OS: %s (%s)\n' "$PRETTY_NAME" "$VERSION_CODENAME"
dpkg-query -W -f='${Package} ${Version}\n' scdaemon gpg-agent gnupg gpg 2>/dev/null || true
apt-cache policy scdaemon gpg-agent gnupg gpg
sudo apt-get -s --only-upgrade install scdaemon gpg-agent
```
Vérifier que le solveur ne planifie ni suppression ni changement
de distribution, et que `scdaemon` et `gpg-agent` ont des
versions compatibles. Si aucune version candidate supérieure,
**STOP** : ne pas forcer un downgrade/upgrade externe.

Après validation explicite de la simulation uniquement, procéder
à une mise à jour via paquets officiels Ubuntu :
`sudo apt-get --only-upgrade install scdaemon gpg-agent`.
Reporter toute signature/déchiffrement GPG pendant
l'opération. Ne pas remplacer manuellement le binaire,
ne pas changer PIN, slots OpenPGP, OTP HMAC ou PIV.
Une fois les paquets installés, redémarrer seulement
`scdaemon` si nécessaire (`gpgconf --kill scdaemon`)
après fermeture des sessions GPG, reconnecter la YubiKey
et comparer `gpg --card-status`. Conserver les résultats
et les versions installées. Toute mise à niveau majeure de
GnuPG requiert un test séparé en environnement isolé.

### P0 — Mise à niveau Ubuntu indisponible (17 octobre 2026)

L'opérateur a confirmé Ubuntu **26.04.1 LTS resolute**.
`gnupg`, `gpg`, `gpg-agent` et `scdaemon` sont déjà installés
en **2.4.8-4ubuntu3.1**. `apt-cache policy` montre la même version
comme candidate depuis `resolute-updates`/`resolute-security`.
La simulation puis la commande effective
`apt-get --only-upgrade install scdaemon gpg-agent` retournent
`0 upgraded, 0 newly installed, 0 to remove` ;
**aucun paquet GnuPG n'a été changé**.

**Décision :** fermer l'action « mettre à niveau scdaemon via apt »
comme *sans objet* sur ce poste. Ne pas répéter l'installation,
ne pas rétrograder globalement GnuPG, ni installer un paquet/ppa non
validé. Garder 19 autres mises à jour en attente hors périmètre P0.
Continuer par une investigation scdaemon à faible exposition
des données ; envisager une version alternative uniquement dans
un environnement isolé et vérifié.

### P0 — Nouvelle session scdaemon sans effet (17 octobre 2026)

Après la vérification que tous les paquets GnuPG et scdaemon sont
à jour sur Ubuntu 26.04.1 (`2.4.8-4ubuntu3.1`), l'opérateur a
exécuté `gpgconf --kill scdaemon` puis
`timeout 15 gpg --card-status`. La nouvelle session répond encore
`gpg: selecting card failed: No such device` et
`gpg: OpenPGP card not available: No such device`.

**Conclusion :** redémarrer scdaemon ne corrige pas la sélection
OpenPGP. Ne pas recommander une répétition des tests
`reader-port`, PC/SC contre CCID, fermeture GUI, mise à niveau APT
ou simple relance du démon sans nouvelle hypothèse.

**Prochaine piste :** comparer de façon contrôlée les capacités
de découverte / ouverture de l'applet OpenPGP de `ykman` avec
celles de GnuPG, en évitant toute écriture, APDU sensible, PIN,
dumps ou journalisation de secrets. Si une trace scdaemon est
nécessaire, configurer un home temporaire avec une journalisation
minimale et des résultats filtrés, sans toucher aux fichiers du
profil utilisateur. Ne pas conclure à une régression 2.4.8 sans
preuve expérimentale.

### P0 — RESTART scdaemon accepté, SERIALNO échoue (17 octobre 2026)

Sur la workstation, `ykman openpgp info` confirme que l'applet
OpenPGP 3.4 répond (firmware/app 5.4.3, compteurs PIN et Admin
PIN à 3). Dans la même session,
`gpg-connect-agent 'SCD RESTART' 'SCD SERIALNO' /bye`
retourne `OK`, puis
`ERR 100696144 No such device <SCD>`.

Il s'agit d'un différentiel confirmé entre deux clients :
`ykman` dialogue avec l'application OpenPGP mais
`scdaemon` ne parvient pas à la sélectionner.
`SCD RESTART OK` indique que la commande a été acceptée,
non que la sélection a réussi.

**Décision :** arrêter les essais redondants de redémarrage,
`reader-port`, basculement PC/SC/CCID et mise à niveau apt.
Ne pas changer les PIN ni réinitialiser l'applet. Préparer une
instrumentation minimale et isolée de `scdaemon` avant
toute nouvelle manipulation de la carte, sans logs APDU
ni extraction de secrets.

## Recherche amont approfondie — piste pcsc-shared (17 octobre 2026)

**Priorité P0 suivante :** tester `disable-ccid` **avec**
`pcsc-shared` dans un `GNUPGHOME` jetable et isolé.
Les essais déjà réalisés n'incluaient pas `pcsc-shared`.
Il ne s'agit pas de répéter le comparatif PC/SC/CCID :
le nouveau facteur expérimental est **le mode d'ouverture PC/SC**.

### Éléments amont et limites des preuves

- https://dev.gnupg.org/T5712 — un cas YubiKey 5 NFC a été
  amélioré en activant `pcsc-shared`.
- https://lists.gnupg.org/pipermail/gnupg-users/2022-January/065739.html —
  un utilisateur YubiKey 5 confirme le retour de `gpg --card-status`
  après `pcsc-shared`.
- https://dev.gnupg.org/T5436.html — un autre utilisateur avait
  besoin de `pcsc-shared` pour contourner `No such device`,
  mais a rencontré des problèmes de cache PIN.
- https://lists.gnupg.org/pipermail/gnupg-users/2024-April/067055.html —
  GnuPG 2.4.5 échouait dans un cas alors que 2.2.42 fonctionnait ;
  **l'auteur indique que `pcsc-shared` ne corrigeait pas son cas**.
- https://dev.gnupg.org/T6383.html — le même `ERR 100696144`
  peut aussi masquer `LIBUSB_ERROR_ACCESS` ; le code n'identifie
  pas à lui seul le défaut.
- https://gnupg.org/documentation/manuals/gnupg26/scdaemon.1.html —
  `pcsc-shared` est un mode **explicitement déconseillé par défaut**
  par GnuPG : sélection d'applet et état du PIN peuvent devenir
  incohérents lorsqu'il y a d'autres clients.
- https://dev.gnupg.org/T5484 — détails sur interférence des
  clients PC/SC et invalidation des états OpenPGP/PIV.

### Protocole proposé, sans intervention sur les clés

1. Préflight côté agent : vérifier l'existence de l'option dans
   `scdaemon --dump-options` (ou `gpgconf --list-options scdaemon`).
2. Dans un dossier temporaire `GNUPGHOME` mode 0700, écrire
   uniquement `disable-ccid` et `pcsc-shared`.
   Ne copier aucun `gpg-agent.conf`, trousseau ou secret de
   `~/.gnupg`. Ne pas stopper le daemon utilisateur principal.
3. Demander une unique lecture `gpg --batch --card-status`
   à délai borné, en supprimant l'affichage de l'identifiant de
   carte. Fermer uniquement l'agent temporaire, supprimer ses
   fichiers et vérifier que le profil principal est inchangé.
4. **Si succès :** `pcsc-shared` est un contournement possible,
   pas une résolution prouvée de la cause racine. Réévaluer le
   risque de concurrence et de PIN avant toute activation durable.
5. **Si échec :** ne pas persister l'option. Préparer des logs
   `scdaemon` filtrés (sans APDU, PIN ou secrets) et comparer
   les versions GnuPG dans un espace isolé, pas en remplaçant
   les paquets Ubuntu.

**Ne pas** modifier OpenPGP/PIV/OTP, installer de PPA,
changer les ACL USB, tenter un PIN, activer `debug-level guru`
ou désactiver les mécanismes de protection.

### P0 — Correction du contrôle de disponibilité pcsc-shared

La commande initiale `scdaemon --dump-options | grep -E
'^pcsc-shared$|^disable-ccid$'` a retourné une sortie vide.
**Ce résultat ne permet pas de conclure que l'option est absente :**
`--dump-options` peut afficher le préfixe `--` que le filtre
rejetait. La source GnuPG documente explicitement
`--pcsc-shared` et `--disable-ccid` :
https://gnupg.org/documentation/manuals/gnupg26/scdaemon.1.html

Contrôles corrigés **lecture seule**, compatibles avec les deux
formes de sortie et sans risquer `set -e` interactif :

```bash
/usr/lib/gnupg/scdaemon --dump-options 2>&1 |
  grep -E -- '(^|[[:space:]])--?(pcsc-shared|disable-ccid)([[:space:]]|$)'
gpgconf --list-options scdaemon | grep -E '^(pcsc-shared|disable-ccid):'
```

Ne lancer aucun essai `pcsc-shared` avant d'avoir vérifié la
disponibilité sur le binaire installé. Sa documentation signale
des risques d'incohérence d'état et de cache PIN en mode partagé :
préférer, si applicable, un `GNUPGHOME` jetable sans clé.

### P0 — Validation options pcsc-shared (17 octobre 2026)

La workstation confirme via `scdaemon --dump-options` les deux directives `--pcsc-shared` et `--disable-ccid`. L'absence de `pcsc-shared` dans `gpgconf --list-options scdaemon` ne suffit pas à contredire le binaire.

Un mode **`--pcsc-shared`** est ajouté à `scripts/workstation/compare-gpg-card-transports.sh`. Il crée un seul `GNUPGHOME` temporaire, contenant seulement `disable-ccid` et `pcsc-shared`, tente une lecture `gpg --batch --card-status` bornée, ne publie pas les données de la carte, puis ferme uniquement l'agent temporaire et nettoie. Ne pas utiliser de profil ou de clés privées réels. Le mode partagé est expérimental et peut affecter l'état de sélection et de PIN si d'autres clients sont actifs ; n'envisager aucune activation permanente sans analyse de risque.

```bash
./scripts/workstation/compare-gpg-card-transports.sh --check
./scripts/workstation/compare-gpg-card-transports.sh --pcsc-shared
```

### P0 — Succès expérimental confirmé avec pcsc-shared (17 octobre 2026)

**Résultat réel workstation :**
`./scripts/workstation/compare-gpg-card-transports.sh --pcsc-shared`
→ `✅ pcsc-shared: OpenPGP card detected`, suivi du nettoyage du
`GNUPGHOME` temporaire. Les deux essais précédents sans
`pcsc-shared` (PC/SC exclusif et CCID intégré) retournaient
`No such device`. Cela identifie le mode d'accès partagé PC/SC
comme **contournement fonctionnel pour la détection**, et non
comme résolution démontrée de la cause racine.

**Phase P0b — Acceptation avant activation durable :**
1. Conserver le profil habituel intact. Vérifier après l'essai :
   `cmp -s ~/.gnupg/scdaemon.conf
   ~/.gnupg/scdaemon.conf.before-reader-port` (si sauvegarde
   toujours présente), puis noter le résultat sans publier de
   données de carte.
2. Tester les deux YubiKeys séparément avec le profil temporaire
   si l'opérateur souhaite les utiliser pour OpenPGP. Ne copier
   aucune clé dans le profil de test.
3. Examiner les avertissements amont de `pcsc-shared` : une
   autre application PC/SC peut modifier la sélection de l'applet
   et l'état de vérification du PIN. Préférer l'absence de clients
   concurrents lors des opérations cryptographiques sensibles.
4. Ne **pas** conclure que la signature Git, la récupération
   `git-crypt` ou les sauvegardes chiffrées fonctionneront :
   la carte a été détectée mais ces opérations n'ont pas été
   validées ; en outre elles peuvent dépendre de clés différentes.
5. Une activation durable doit être une décision explicite,
   avec sauvegarde préservée, préflight, rollback automatisé,
   et tests de non-régression adaptés, sans `keytocard`,
   sans PIN ni changement de slots.

État : **P0 détection dans profil isolé = PASS** ;
**P0 intégration au profil principal et acceptation sécurité =
EN ATTENTE**. Aucun changement sur l'utilisateur réel.

### P0 — Contrôle final de non-régression du profil principal (17 octobre 2026)

Après la réussite de l'essai `--pcsc-shared` dans un
`GNUPGHOME` temporaire, l'opérateur a confirmé :

```text
cmp -s ~/.gnupg/scdaemon.conf \
  ~/.gnupg/scdaemon.conf.before-reader-port
✅ Configuration GnuPG principale inchangée
```

**Résultat validé :** le contournement `pcsc-shared` permet
à GnuPG de détecter l'applet OpenPGP 3.4 de la YubiKey en
mode PC/SC partagé, tandis que le profil GnuPG principal
reste identique à sa sauvegarde de référence.

**Statut opérationnel exact :**
- ✅ `ykman openpgp info` : applet accessible ;
- ❌ `gpg --card-status` sur le profil habituel : erreur
  `ERR 100696144 No such device <SCD>` constatée avant l'essai ;
- ❌ profil isolé PC/SC exclusif et pilote CCID intégré :
  `No such device` ;
- ✅ profil isolé `disable-ccid` + `pcsc-shared` :
  carte OpenPGP détectée ;
- ✅ configuration utilisateur d'origine préservée, comparaison
  binaire avec la sauvegarde réussie.

**Décision :** conserver ce contournement comme candidat
documenté, sans le présenter comme une correction persistante.
La cause racine du rejet de l'accès exclusif PC/SC reste
indéterminée. `pcsc-shared` peut exposer des risques d'état
de sélection d'applet / cache de PIN avec d'autres clients PC/SC.
Avant de modifier `~/.gnupg/scdaemon.conf`, préparer une
procédure transactionnelle réversible, identifier les clients
concurrents, confirmer le fonctionnement du lecteur sans prompt
PIN, puis faire accepter les impacts sur Git signing,
`git-crypt` et sauvegardes PostgreSQL. Ne pas lancer
`keytocard`, changer les PIN, ni altérer OTP HMAC/PIV.

### P0b — Essai d'intégration au profil principal, réversible (17 octobre)

Le script `scripts/workstation/trial-gpg-pcsc-shared.sh`
prépare un test du **profil GnuPG principal** :
- `--check` : préflight en lecture seule (non-root, sauvegarde
  historique existante et identique aux octets du fichier actif,
  présence `disable-ccid`, absence de `reader-port` et
  `pcsc-shared`, prise en charge binaire de `pcsc-shared`) ;
- `--trial` : créer un fichier de configuration provisoire dans
  le même répertoire et avec les permissions de l'original, ajouter
  `pcsc-shared`, rafraîchir **seulement** `scdaemon`,
  exécuter `gpg --batch --card-status` avec délai borné
  et **restaurer systématiquement** la configuration sauvegardée,
  même lorsque le test réussit.

Le script ne touche ni aux sous-clés, ni aux PIN, ni aux applets
OpenPGP/PIV/OTP. Il ne doit pas être exécuté pendant une
signature, un déchiffrement, ou lorsqu'une application concurrente
utilise la YubiKey. `SIGKILL`/panne électrique ne déclenchent pas
de trap ; le backup historique permet alors une restauration
manuelle. L'activation durable **n'est pas incluse** et
demandera une décision distincte après le retour d'expérience.

```bash
cd ~/w/nabla-compose && git pull --ff-only
./scripts/workstation/trial-gpg-pcsc-shared.sh --check
./scripts/workstation/trial-gpg-pcsc-shared.sh --trial
cmp -s ~/.gnupg/scdaemon.conf ~/.gnupg/scdaemon.conf.before-reader-port \
  && echo 'Configuration restaurée'
```

**Acceptation P0b :** succès de détection dans le profil utilisateur
et restauration du fichier, sans intervention sur les clés.
La disponibilité cryptographique de la signature Git et de
`git-crypt` reste à établir indépendamment ; ne pas introduire
de PIN pendant ce test.

### P0b — Validation opérateur du profil GnuPG principal (17 octobre)

Le script `trial-gpg-pcsc-shared.sh --check` a confirmé le
préflight et la prise en charge binaire de `pcsc-shared`.
Le mode `--trial` a ensuite produit :
`✅ Main GnuPG profile detects OpenPGP with pcsc-shared enabled temporarily`.
Le trap a indiqué `✅ Historical configuration restored byte-for-byte`.
Un contrôle `cmp -s ~/.gnupg/scdaemon.conf
~/.gnupg/scdaemon.conf.before-reader-port` indépendant a
également confirmé `✅ Configuration d'origine restaurée`.

**P0b validé :** mode partagé PC/SC efficace dans le profil
GnuPG usuel pour l'énumération de la carte, sans persistance.
**État du système :** `pcsc-shared` reste désactivé dans la
configuration réelle après rollback. Ne pas affirmer que
les signatures Git ou déchiffrements sont vérifiés.

**Prochain jalon P0c :** préparer une activation durable
idempotente et réversible avec sauvegarde immuable,
contrôles `gpg --card-status` et procédure
`--rollback` explicite. Analyser le risque
d'état PC/SC partagé ; validation des usages Git et
git-crypt distincte, sans transférer de clés ou dévoiler
de secrets. L'opérateur doit lancer volontairement
l'activation sur sa workstation.

### P0c — Activation persistante contrôlée et retour arrière (17 octobre)

Nouveau script : `scripts/workstation/manage-gpg-pcsc-shared.sh`
avec `--check`, `--apply` et `--rollback`. Il **ne touche
pas aux clés privées, PIN ou slots**. Avant toute écriture il
vérifie la sauvegarde historique immuable
`scdaemon.conf.before-reader-port`, puis compare le fichier
courant soit avec les octets de cette référence, soit avec la
version exactement dérivée par l'ajout de `pcsc-shared`.
Toute autre modification déclenche un arrêt (drift guard).
Le script ne remplace pas la sauvegarde historique.

`--apply` ajoute l'option au profil usuel, rafraîchit seulement
`scdaemon`, puis teste `gpg --batch --card-status` avec timeout ;
un échec de détection entraîne un rollback automatique vers la
sauvegarde. `--rollback` restaure la version originale vérifiée.
Les deux actions sont idempotentes lorsque l'état est déjà cible.
Une extinction brutale peut interrompre la transaction : la copie
historique reste disponible pour la restauration.

**Exécution supervisée, workstation uniquement**, après avoir
arrêté toute opération utilisant GPG et tout autre client CCID :
```bash
cd ~/w/nabla-compose && git pull --ff-only
./scripts/workstation/manage-gpg-pcsc-shared.sh --check
./scripts/workstation/manage-gpg-pcsc-shared.sh --apply
./scripts/workstation/manage-gpg-pcsc-shared.sh --check
# Retour arrière sur demande :
./scripts/workstation/manage-gpg-pcsc-shared.sh --rollback
```

**Point de vigilance sécurité :** le mode PC/SC partagé laisse
d'autres clients communiquer avec la carte et potentiellement
modifier la sélection d'applet ou l'état de validation du PIN.
Éviter les clients simultanés pendant les opérations sensibles.
Le PASS de `gpg --card-status` ne valide pas les opérations de
signature Git, `git-crypt` ou les restaurations PostgreSQL.
P1 doit les valider sans migration de clés. L'activation réelle
n'a pas été effectuée par l'agent.

### P0c — Activation persistante validée par l'opérateur (17 octobre 2026)

Après un `git pull --ff-only`, l'opérateur a exécuté :
- `manage-gpg-pcsc-shared.sh --check` → `Current managed state: original`, contrôle PASS ;
- `manage-gpg-pcsc-shared.sh --apply` → `Persistent pcsc-shared enabled and OpenPGP detected` ;
- `manage-gpg-pcsc-shared.sh --check` → `Current managed state: shared`, contrôle PASS.

**P0c PASS :** configuration principale désormais en
`disable-ccid` + `pcsc-shared`, carte détectée, état persistant
confirmé. La sauvegarde `scdaemon.conf.before-reader-port`
n'a pas été réécrite. En cas de régression :
`./scripts/workstation/manage-gpg-pcsc-shared.sh --rollback`.

**P1 à faire :** ne pas assimiler l'énumération OpenPGP à une
signature ou un déchiffrement réussi. Commencer par
`gpg --card-status`, puis relever les empreintes de sous-clés
disponibles et vérifier la configuration de signature Git
sans divulguer de clés privées. Toute signature de challenge
doit être explicitement supervisée et peut déclencher un PIN ;
vérifier l'identité du bon jeton avant d'autoriser une opération.
`git-crypt` et restauration PostgreSQL sont des validations
séparées. Ne pas essayer `keytocard`.

### P1 — Régression après activation persistante (17 octobre 2026)

Le profil principal annonce toujours `Current managed state: shared`
après `--apply` et `--check`, mais un test ultérieur
`timeout 15 gpg --card-status` retourne de nouveau
`No such device`. La configuration Git est
`commit.gpgsign=true`, avec une clé de signature déclarée.
**L'intégration P1 n'est donc pas validée ; la configuration
persistante n'implique pas une disponibilité persistante.**

Une explication plausible est une interaction PC/SC après le premier
succès : GnuPG avertit que `pcsc-shared` peut laisser un autre
client modifier la sélection d'applet ou l'état de la carte.
Un rapport de développement de juin 2026 signale un état
incohérent après passage de KeePassXC sur un Nitrokey 3 ;
**cela ne démontre pas le même défaut sur YubiKey**.
Sources :
https://gnupg.org/documentation/manuals/gnupg26/scdaemon.1.html
https://lists.gnupg.org/pipermail/gnupg-devel/2026-June/036307.html

Le script `manage-gpg-pcsc-shared.sh` offre désormais
`--verify` pour tester **l'accès réel** sans modifier la config.
`--check` reste uniquement une comparaison du fichier avec
le modèle attendu ; `--apply` sur configuration déjà active
valide désormais le fonctionnement au lieu d'annoncer un succès
sur la seule présence de l'option.

Investigation recommandée, sans redémarrage :
```bash
./scripts/workstation/manage-gpg-pcsc-shared.sh --check
./scripts/workstation/manage-gpg-pcsc-shared.sh --verify
pgrep -a -f '[p]cscd|[s]cdaemon|[y]kman|[s]eahorse|[k]eepassxc' || true
```
Ne pas utiliser `keytocard`, ne pas déclencher de signature
ni de saisie de PIN. Si la disponibilité n'est pas stable,
réexaminer le contournement avant toute validation Git.

### P0c — Clarification finale : carte volontairement retirée (17 octobre 2026)

**Correction d'interprétation :** l'opérateur explique avoir
volontairement retiré la YubiKey pour raisons de sécurité lors du
précédent `gpg --card-status` négatif. Le retour
`No such device` à ce moment **n'est pas une régression démontrée**
de `pcsc-shared` ; il est cohérent avec l'absence de carte.

Après réinsertion de la YubiKey de secours (numéro masqué dans
les sorties publiables), les contrôles sont tous positifs :
- `gpg --card-status` détecte un lecteur Yubico, applet
  OpenPGP 3.4 ;
- `manage-gpg-pcsc-shared.sh --check` annonce `shared` ;
- `manage-gpg-pcsc-shared.sh --verify` annonce
  `Live OpenPGP selection operational` ;
- `pcscd`, `scdaemon` et KeePassXC sont actifs.
  Ceci établit la coexistence pendant ce contrôle ponctuel,
  sans prouver la sécurité de toutes leurs opérations simultanées.

**Point de sécurité :** les trois emplacements OpenPGP
(signature, encryption, authentication) de cette carte sont
`[none]`. Ne pas confondre carte détectée et sous-clé GPG
stockée dessus. Le compte Git a `commit.gpgsign=true` et
`user.signingkey` configuré, mais l'usage de cette identité
sur carte n'est pas démontré. Aucune commande `keytocard`,
aucun changement de PIN, aucune écriture sur carte.

**Statut :** P0 accès OpenPGP **PASS pour la carte connectée** ;
P1 signature Git, récupération git-crypt et chiffrement/
restauration PostgreSQL **non validés**.

### P1 — Inventaire clés GnuPG et disponibilité de la carte (17 octobre 2026)

Sur la workstation, `gpg --list-secret-keys --keyid-format LONG`
pour l'identité Git configurée renvoie une clé principale
`sec rsa4096` de capacité `[SC]` (créée en avril 2022),
et une sous-clé `ssb rsa4096` de capacité `[E]`.
**Les marqueurs `sec` et `ssb` (sans `#` ni `>`)
indiquent la présence des composants secrets dans le trousseau
GnuPG habituel**, non un stub exclusif de smartcard.
`manage-gpg-pcsc-shared.sh --verify` renvoie toujours
`Live OpenPGP selection operational`.

La carte YubiKey de secours précédemment inspectée dispose
de trois slots OpenPGP vides. La clé logicielle Git et la
détection de l'applet YubiKey sont **deux faits distincts**.

**P1 — étape suivante :** valider une signature GPG locale sur
un message de test non sensible, puis vérifier cryptographiquement
sa signature avec la clé publique (sans faire de commit Git
ni écrire dans le dépôt). Cette opération peut exiger la
phrase de passe GPG et doit être explicitement supervisée.
Vérifier séparément la capacité à déchiffrer une fixture de test
pour la sous-clé `[E]` ; ne pas utiliser de sauvegarde
PostgreSQL de production ni de secret réel comme fixture.
Ne pas exporter les clés secrètes ni effectuer `keytocard`.

### P1 — Signature GPG logicielle : PASS (17 octobre 2026)

L'opérateur a signé une phrase de test non sensible via
`gpg --local-user <empreinte de signature Git> --armor --clearsign`,
puis validé le résultat avec `gpg --verify`.
GnuPG confirme `Good signature`, signée le 17 octobre 2026
avec la clé RSA principale `[SC]` attendue et confiance
`[ultimate]`. **P1 signature GPG logicielle = PASS.**

Ce résultat prouve la capacité à signer avec la clé privée
logicielle installée et à vérifier la signature ; il ne prouve
pas encore la signature d'un commit Git, ni la capacité à
déchiffrer via la sous-clé `[E]`, ni une récupération
`git-crypt`/PostgreSQL. Aucun slot YubiKey n'a été modifié.

Étape suivante : fixture de chiffrement éphémère et non
sensible, `gpg --encrypt --recipient <empreinte>`
puis `gpg --decrypt` et comparaison stricte de la sortie.
Utiliser un répertoire temporaire en permissions 0700
et nettoyage après contrôle ; ne pas écrire un secret réel,
ne pas inclure `--passphrase` sur la ligne de commande.

### P1 — Chiffrement GPG PASS et contrat du diagnostic enrichi (17 octobre)

L'opérateur a exécuté une fixture temporaire avec
`gpg --encrypt --recipient <identité Git>`, suivie de
`gpg --decrypt` et d'un `cmp` strict. GnuPG a confirmé
l'emploi de la sous-clé `rsa4096/87E6B8E5021D2E36`
datée du 22 avril 2022 ; le test affiche
`✅ P1 chiffrement/déchiffrement GPG validé`.
Ce test et la vérification précédente `Good signature`
valident l'usage **logiciel** de ces clés, pas leur présence
sur une YubiKey ni une restauration de backup de production.

**Diagnostic mis à jour :**
- `scripts/workstation/diagnose-gpg-smartcard.sh --check` :
  marque `pcsc-shared` comme directive de contournement
  attendue, précise la distinction GnuPG logiciel / carte,
  et vérifie sans export la présence de la clé secrète Git
  et d'une sous-clé secrète ;
- `scripts/workstation/audit-yubikey-capabilities.sh` :
  inventorie les slots OpenPGP de **la carte actuellement
  connectée** sans exposer les identifiants, signale le
  slot OTP 2 HMAC KeePassXC historiquement validé,
  et inspecte seulement la disponibilité de `ssh-agent`
  sans afficher les clés publiques ni leurs empreintes.

| Zone | État connu / attendu | À confirmer |
| --- | --- | --- |
| YubiKey secours | OpenPGP applet 3.4, clés Signature/Encryption/Auth vides lors de l'observation précédente | Nouvelle observation au diagnostic |
| OTP | Slot 2 HMAC-SHA1 KeePassXC testé sur les deux YubiKeys | Vérification facultative `--challenge`, attention au touch |
| GPG logiciel | Clé principale RSA4096 [SC] et sous-clé RSA4096 [E] présentes | Aucune migration `keytocard` |
| GPG signature | Signature locale cryptographiquement vérifiée | Commit Git signé encore à tester |
| GPG chiffrement | Roundtrip fixture non sensible validé avec sous-clé E | Récupération git-crypt et sauvegardes PostgreSQL |
| GPG carte | `disable-ccid` + `pcsc-shared` : `--verify` PASS si carte insérée | Test séparé de la clé principale/backup ; absence physique ≠ régression |
| SSH | `ssh-add -l` peut indiquer une identité chargée | Origine FIDO2/PIV/logicielle, usages SSH et FIDO2 non établis |
| PIV | Certificat 9A historique expiré et inapproprié pour une nouvelle CA | Inventaire par carte, sans reset |
| OATH/FIDO2 | Application accessible selon capacité matérielle | Identifiants et usages réels non inventoriés |

**Prochain gate P1 :** tester la signature Git dans un
repository jetable sans push et sans toucher à la branche
courante, puis contrôler séparément la récupération
`git-crypt` / sauvegardes à partir de fixtures non sensibles.
Ne jamais confondre clé GPG logicielle, carte OpenPGP, clé SSH
et clé PIV. Ne pas publier numéros de série, fingerprints SSH,
réponses HMAC, clés privées, PIN ou certificats non expurgés.

## P2 — Identité age matérielle YubiKey pour SOPS / fastapi-sample (étude du 17 octobre 2026)

Source consultée : `AlbanAndrieu/fastapi-sample@master:.sops.yaml`
(https://github.com/AlbanAndrieu/fastapi-sample/blob/master/.sops.yaml).
Elle définit un destinataire `age1...` **X25519 logiciel** pour
`.*\\.env\\.sops$`, YAML et JSON ; une règle
`secrets.*\\.yaml` associe age et AWS KMS dans un même groupe.
**Attention :** le nom littéral `.env.secret` ne correspond pas
à la règle `.*\\.env\\.sops$` ; vérifier les noms réellement
chiffrés et leurs métadonnées SOPS avant toute migration.

**Faisabilité : OUI, sous réserve d'un slot PIV disponible et
du support `age-plugin-yubikey`.** Une YubiKey 5 NFC peut héberger
une nouvelle clé matérielle age (clé P-256 via PIV et plugin).
Cela n'est pas une importation de l'identité X25519 existante :
elle doit rester disponible comme mécanisme de récupération.
SOPS récent peut accepter un destinataire
`age1yubikey1...` fourni par le plugin ; il faut vérifier la
version réelle `sops` et sa capacité à lire une identité
`AGE-PLUGIN-YUBIKEY-...` avant modification.

**Occupation constatée sur la YubiKey de secours :**
- OTP slots 1 et 2 **programmés** ; slot 2 HMAC KeePassXC : à préserver ;
- PIV 9A : clé RSA2048 + certificat CA historique expiré ; ne pas écraser ;
- PIV 9C / 9D / 9E : état **non connu**, ne pas présumer libres ;
- OpenPGP Sign/Enc/Auth observés vides : namespace distinct de PIV ;
- FIDO2, OATH et SSH : vérifier les usages sans provisionnement automatique.

`age-plugin-yubikey` emploie PIV (et ses emplacements supportés)
sans consommer les deux slots OTP ni les slots OpenPGP. Avant tout
provisionnement, contrôler les options de slots et leurs correspondances
dans la **version installée** du plugin. Préférer un slot PIV libre
compatible avec les usages du plugin, en évitant 9A. Un certificat
expiré sur 9A ne signifie pas que cet emplacement peut être effacé
sans conséquence.

**Séquence secure-by-design :**
1. Inventaire **lecture seule** par carte et par slot :
   `ykman piv info` (sortie à expurger),
   `command -v age-plugin-yubikey`,
   `command -v sops`, `sops --version`,
   `age-plugin-yubikey --help` si installé ; aucun `--generate`.
2. Vérifier sauvegarde/recovery de l'identité age actuelle
   **sans exporter ni divulguer la clé secrète**. Faire un test
   de déchiffrement de fixture existante sur stockage temporaire,
   jamais de dump des `.env.secret`.
3. Uniquement après décision explicite, provisionner une identité
   PIV age **nouvelle** dans un emplacement réellement libre,
   avec PIN non trivial et touch policy adaptée ; ne jamais reset PIV.
4. Ajouter son destinataire public comme **destinataire additionnel**
   (pas en remplacement de l'existant) dans les règles SOPS
   applicables. Attention aux groupes SOPS et à leur threshold.
   Tester d'abord une fixture, puis appliquer `sops updatekeys`
   aux fichiers chiffrés existants et valider le déchiffrement
   via clé logicielle **et** YubiKey séparément.
5. Stratégie de secours : seconde YubiKey avec identité distincte
   et destinataire additionnel si désiré, plus identité age
   logicielle protégée hors ligne. Documenter l'usage CI/serveurs :
   **ne pas** rendre le déchiffrement automatique dépendant
   d'une YubiKey physiquement absente.

**Ne jamais** copier `AGE-SECRET-KEY` dans Git, logs ou chat ;
ne pas écraser 9A, OTP2, PIV, OpenPGP ou SSH pour faire de la place.
Sources : https://github.com/str4d/age-plugin-yubikey ,
https://getsops.io/docs/reference/ ,
https://github.com/getsops/sops/blob/main/age/keysource.go .

### P2 — Relevé opérateur SOPS et correction du slot age (17 octobre 2026)

L'opérateur confirme `sops 3.13.3` installé via
`~/.local/share/mise/installs/sops/3.13.3/sops`,
`age-plugin-yubikey` **absent du PATH**, et
`ykman piv info` fonctionnel. Le PIN et PUK PIV affichent
3/3 essais ; la management key est AES256 et protégée par PIN.
Le slot 9A contient la clé RSA2048 et son certificat historique
expiré le 22 janvier 2025. **Ne pas modifier ce slot.**

**Correction de la première recommandation 9D :**
`age-plugin-yubikey` utilise normalement les slots PIV
*Retired Key Management* **82 à 95**, pas nécessairement 9D.
Le code du plugin accepte `--slot` en tant que slot retired.
La prochaine sélection devra donc porter sur un slot 82–95
réellement libre (par exemple 82, seulement après inventaire).
`ykman piv info` ne listant ici que 9A n'établit pas
l'absence de matériel cryptographique dans les slots retired ;
ne pas interpréter cette sortie comme une autorisation d'écrire.

**P2 phase préparatoire, lecture seule :**
1. Installer le plugin par une source/version vérifiée, idéalement
   paquet reproductible avec empreinte ou release signée ;
   ne pas lancer l'interface interactive par défaut si elle
   propose de provisionner la clé.
2. `age-plugin-yubikey --help`, puis `--list`
   pour inventorier les identités age existantes ;
   **pas de `--generate`, `--force` ou reset PIV**.
3. Vérifier le support des destinataires `age1yubikey1...`
   sous SOPS 3.13.3 via une fixture isolée, tout en conservant
   la clé X25519 actuelle comme destinataire.
4. Inventorier les slots 82–95 avant toute écriture.
   Ne pas publier CHUID, numéros de série ou certificats bruts.

Sources :
https://github.com/str4d/age-plugin-yubikey
https://github.com/str4d/age-plugin-yubikey/blob/main/src/main.rs
https://github.com/Yubico/Yubico.NET.SDK/blob/develop/docs/users-manual/application-piv/slots.md/

### Préparation outillage age-plugin-yubikey (17 octobre 2026)

Le bootstrap workstation existant `scripts/workstation/bootstrap-yubikey-manager.sh`
installe désormais **age-plugin-yubikey 0.5.1** (version épinglée)
avec `cargo install --locked`, ainsi que `libpcsclite-dev` et
`pkg-config` nécessaires à la compilation Linux. Prérequis : un
outil `cargo` approuvé et présent dans le PATH ; le script échoue
explicitement s'il manque. Le binaire Cargo est lié sous
`~/.local/bin/age-plugin-yubikey`. Mode `--check` : aucun changement.
Mode `--apply` : installation d'outillage uniquement, **aucune**
génération de clé, opération PIV ni modification OTP.

```bash
cd ~/w/nabla-compose && git pull --ff-only
bash scripts/workstation/bootstrap-yubikey-manager.sh --apply
bash scripts/workstation/bootstrap-yubikey-manager.sh --check
age-plugin-yubikey --help
age-plugin-yubikey --list
```

L'installation du plugin n'a pas été exécutée sur la workstation par
l'agent. Le résultat de `--list` doit être traité comme un inventaire,
non une autorisation de provisionner un emplacement PIV. Référence :
https://github.com/str4d/age-plugin-yubikey (prérequis PC/SC et Cargo).

### Installation age-plugin-yubikey : échec Cargo PC/SC et correction (17 octobre 2026)

L'opérateur a lancé `bootstrap-yubikey-manager.sh --apply`.
Ubuntu a confirmé `libpcsclite-dev 2.4.1-1` et
`pkg-config 2.5.1-4` déjà installés ; Cargo 1.93.1 a téléchargé
`age-plugin-yubikey 0.5.1`, puis la compilation s'est arrêtée
sur `pcsc-sys 1.2.1` : `Could not find a PCSC library`.
Le contrôle `--check` a ensuite justement signalé le plugin
absent. Le plugin **n'est pas encore installé** sur le poste.

Le bootstrap exécute désormais un contrôle préalable sur
`/usr/lib/$(dpkg-architecture -qDEB_HOST_MULTIARCH)/pkgconfig/libpcsclite.pc`
et teste explicitement la résolution par `/usr/bin/pkg-config`.
Pour le sous-processus Cargo uniquement, il neutralise
`PKG_CONFIG_LIBDIR` et `PKG_CONFIG_SYSROOT_DIR`, et fournit
`PKG_CONFIG_PATH` pointant sur les répertoires pkg-config
système. Aucune variable globale de la session n'est modifiée.
Les avertissements Cargo sur les dépendances `yanked`
du lockfile ne sont **pas** la cause directe de ce build failed ;
un audit de dépendances reste recommandé.

Après récupération de la branche :
```bash
cd ~/w/nabla-compose
git pull --ff-only
bash scripts/workstation/bootstrap-yubikey-manager.sh --apply
bash scripts/workstation/bootstrap-yubikey-manager.sh --check
command -v age-plugin-yubikey
age-plugin-yubikey --version
age-plugin-yubikey --list
```

Si le préflight PC/SC échoue encore, remonter la sortie précise
du nouveau contrôle et `/usr/bin/pkg-config --modversion libpcsclite`,
sans retirer la carte, modifier les slots, réinitialiser PIV ou
fournir de PIN. Compilation locale non vérifiée par l'agent.
