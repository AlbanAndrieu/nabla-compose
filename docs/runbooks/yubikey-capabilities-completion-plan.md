# YubiKeys — plan de finition, preuves et décisions

**Owner :** nabla-compose. **Branche de travail :** PR #280.
**Périmètre :** secondaire 22916048 puis principale 23501671.
**Principe :** un diagnostic en lecture seule n'autorise aucune configuration.

## État établi / état non établi

| Domaine | Preuve acquise | Ce qui manque pour considérer terminé |
| --- | --- | --- |
| KeePassXC / OTP2 | Sur la secondaire, OTP2 est PROGRAMMED_TYPE_UNVERIFIED (25/10/2026) ; historique de challenge équivalent sur les deux cartes | Test KeePassXC supervisé après validation du plan de récupération ; ne jamais reprogrammer le slot 2 |
| PIV / F9 | Certificat F9 secondaire validé avec racine Yubico épinglée | Ne constitue pas une attestation de clé PIV82 |
| PIV / 9A | RSA2048 importé et certificat Nabla Root CA historiquement expiré (22/01/2025) | Dépendances PKI/Vault et usages du certificat réellement prouvés, sans écrasement |
| PIV / 82-83 | 82 confirmé vide sur la secondaire ; 83 vide selon inventaire antérieur | Deux sauvegardes récupérables, authentification AES256 autorisée, certificat interop age, roundtrip sur documents synthétiques |
| SOPS / age | Identité logicielle et procédures de récupération documentées | Deux supports de secours effectivement distincts et restauration indépendante testée |
| GnuPG / PostgreSQL | GPG utilisé pour signatures et sauvegardes ; incident scdaemon / pcsc historique | Correspondance des sous-clés, correction du transport, déchiffrement et restauration PostgreSQL isolée |
| FIDO2 / passkeys | PIN FIDO2 historiquement actif sur la secondaire | Inventaire d'état public, authentification/inscription indépendante sur les deux cartes, codes de récupération |
| SSH FIDO2 | Chemin recommandé, non considéré comme enrôlé | Deux clés distinctes, tests ssh, voie d'accès de secours avant durcissement |
| OpenPGP | Application présente historiquement ; gpg --card-status a échoué | Diagnostic PC/SC, présence des sous-clés, sauvegarde hors ligne et test GPG |
| OATH | Applet présent historiquement, protection désactivée | Politique de protection et inventaire de récupération, sans publier comptes ni TOTP |
| PIV 9C/9D/9E | Slots historiquement vides sur la secondaire | Décider des usages S/MIME/PDF/PKCS#11 avant toute génération |
| PAM U2F / GNOME keyring | Non provisionné en tant que gate du poste | Deux tokens testés + session de secours ; PAM/keyring seulement après procédure de rollback |

Ce tableau distingue une **observation ponctuelle** d'une recette validée. Une clé
fournissant des métadonnées n'est pas une identité SSH/GPG utilisable.

## Diagnostic applicatif additionnel — sans PIN ni secret

Exécuter les deux YubiKeys **séparément** depuis un worktree de la PR :

- `just yubikey-applications-secondary-readonly` : carte 22916048 seule.
- `just yubikey-applications-primary-readonly` : carte 23501671 seule.
- `just yubikey-applications-test` : tests synthétiques, sans matériel.

Le diagnostic `inspect-yubikey-applications-readonly.py` vérifie d'abord
l'unicité du token, son numéro de série et le firmware 5.4.3 ; puis lit
uniquement `ykman fido info`, `ykman oath info`,
`ykman openpgp info`, `ykman piv info` et
`ykman piv keys info` pour 9A, 9C, 9D, 9E et 83.
Il n'interroge **pas** OTP2, F9 ou PIV82 déjà observés. Il n'utilise ni
commandes de compte OATH/FIDO, ni credential list, ni certificat brut,
ni GPG privé, ni challenge OTP. Entrée standard fermée et timeout.

Le JSON n'imprime jamais les sorties `ykman` brutes. Une applet
`RESPONDS_METADATA_ONLY` n'est pas configurée/validée par ce seul fait.
Un slot `EMPTY_CONFIRMED` ne peut pas être provisionné sans accord ;
`OCCUPIED_METADATA` ne prouve pas qu'une clé privée est utilisable ;
`UNKNOWN` bloque. La clé de gestion PIV doit rester
`AES256_PIN_PROTECTED` et 9A doit conserver des métadonnées de clé.
Même un diagnostic code 0 retourne toujours `status=NO-GO` et
`hardware_mutation_authorized=false`. Les réponses personnelles
et certificats ne sont pas recopiés dans les logs publics.

## Ordre d'exécution des configurations futures

1. **P0 — Sauvegardes et perte de carte.** Identifier les deux copies
   chiffrées d'escrow et leurs supports physiques. Inspecter seulement
   leurs métadonnées avec le script existant ; effectuer une restauration
   dans un environnement isolé lors d'une séance autorisée. Prouver
   l'accès GPG aux anciennes sauvegardes et restaurer un PostgreSQL jetable.
   Ne pas déplacer de sous-clés avant ce résultat.
2. **P0 — PKI / 9A.** Cartographier la confiance actuellement utilisée.
   Ne pas remplacer le certificat historique expiré : définir root
   hors ligne et intermédiaire Vault/OpenBao, politique de révocation
   et récupération, puis approuver séparément l'architecture.
3. **P1 — AES256 et PIV82 secondaire.** Contrôler publiquement la
   politique du slot ; obtenir l'autorisation d'une seule authentification
   supervisée. Planifier distinctement génération P-256, certificat
   compatible avec le plugin age, import, attestation et roundtrip
   sur fixture. Aucune exécution implicite ni récupération PIN automatique.
4. **P1 — PIV82 principale.** Seulement après roundtrip secondaire
   réussi et restauration logicielle prouvée. Chaque token a une clé
   privée différente ; chiffrer pour les deux destinataires avant
   changement SOPS.
5. **P1 — OpenPGP et FIDO2.** Réparer d'abord la visibilité GPG/PCSC,
   préserver la clé de signature et le chiffrement PostgreSQL.
   Choisir SSH FIDO2 ou PIV après inspection des dépendances ;
   inscrire les deux clés séparément, tester et prévoir les secours.
   Les passkeys sont à enregistrer par relying party, sur chaque clé.
6. **P2 — OATH, 9C/9D/9E, PAM et keyring.** Examiner les usages
   réels avant d'activer une protection OATH ou une signature PDF/S/MIME.
   Tester les deux tokens et un compte secours avant toute modification
   de `/etc/pam.d`. Le trousseau GNOME n'est pas automatiquement
   débloqué par FIDO2.

## Critères de sortie

- `L1` : diagnostics en lecture seule, tests hermétiques et gate locale PASS.
- `L2` : état de **chaque** carte observé (pas inféré du modèle voisin).
- `L3` : restauration age/SOPS **et** PostgreSQL/GPG validées isolément.
- `L4` : transaction PIV82 secondaire approuvée étape par étape et
  véritable roundtrip age. Recontrôler OTP2 et 9A **après** transaction.
- `L5` : principale validée indépendamment, destinataires de secours
  documentés, SSH/FIDO2/OpenPGP acceptés séparément, plan de rollback PAM.

Chaque phase mutante demande une approbation explicite. Les résultats
actuels ne satisfont pas les critères L3-L5.

## Références et runbooks

- [Inventaire YubiKey existant](../workstation-yubikey-full-capabilities.md)
- [GPG, PostgreSQL et Vault](../workstation-yubikey-gpg-vault-roadmap.md)
- [Diagnostic F9, PIV82 et escrow](yubikey-piv82-postmerge-diagnostics.md)
- [Reprise AES256](yubikey-piv82-aes256-handoff.md)
- [Yubico ykman commandes](https://docs.yubico.com/software/yubikey/tools/ykman/)


## Diagnostic du poste (sans aucune commande YubiKey)

`just yubikey-workstation-readonly` examine exclusivement la présence
des outils locaux (`gpg`, `gpgconf`, `age`, `sops`,
`age-plugin-yubikey`, `ykman`, `pcsc_scan`, `ssh-keygen`,
`pamu2fcfg`, `keepassxc`, `cryptsetup`, `lsblk`).
Il inspecte uniquement les métadonnées de quatre emplacements
conventionnels : identité age SOPS (mode 0600, utilisateur courant),
socket gpg-agent, poignée publique SSH FIDO2 et mapping PAM U2F.
Il **n'ouvre aucun fichier**, n'énumère aucun compte, ne lance pas
`gpg --card-status`, ne demande aucun PIN ni mot de passe et
n'interroge pas la carte. Les chemins et contenus ne sont pas imprimés.

`just yubikey-workstation-test` valide ces règles hors matériel.
La présence d'une commande, d'un socket ou d'un fichier public n'est
**jamais** une preuve d'authentification, de déchiffrement, ni de
restauration de sauvegardes. Le JSON reste `status=NO-GO`.


## Diagnostic agrégé du poste et des applications

Exécuter `just yubikey-diagnostics-test` puis `just yubikey-diagnostics-secondary-readonly` pour une seule observation sans mutation. Les étapes GPG/scdaemon, escrow, PostgreSQL, PIV82, FIDO2/SSH et PAM conservent `NOT_VERIFIED`. L'OTP2 n'est pas revérifié par défaut. [Runbook](yubikey-readonly-batch.md).


La cible `just yubikey-diagnostics-all-secondary` inclut une sonde GPG-agent `GETINFO version` avec `--no-autostart`, sans PIN et sans toucher à scdaemon ni aux clés. Un agent joignable ne suffit pas à valider OpenPGP ou la restauration des sauvegardes PostgreSQL. Elle comprend 95 méthodes de test au total. **Preuve opérateur du 25/10/2026 : 95/95 PASS** depuis le HEAD local `d4f1afbd`, avec `gpg_agent=RESPONDS_GETINFO_ONLY`. Le HEAD distant peut avoir évolué : ces résultats ne valent pas validation d'un commit ultérieur. **Statut de récupération : NO-GO** (scdaemon/OpenPGP, PostgreSQL/GPG, escrow age, PIV82 et PAM non validés). Voir le [rapport de diagnostic groupé](yubikey-readonly-batch.md#preuve-opérateur--diagnostic-groupé-du-25-octobre-2026).

## Exécution parallèle des préparations (PR #280)

Pour réduire le chemin critique, les chantiers P0/P1 sont préparés en
**quatre flux simultanés** : (A) GPG-agent/scdaemon/OpenPGP,
(B) sauvegardes GPG/PostgreSQL et escrow age/SOPS, (C) FIDO2/SSH/KeePassXC,
(D) PKI/9A et plan PIV82/AES256. Aucun flux ne doit attendre la fin des autres
pour préparer ses contrats, runbooks, preuves et tests hermétiques.

- `just yubikey-parallel-test` : 13 tests (dont 2 nouveaux contrats de complétude),
  vérifiant la concurrence, toutes les réponses attendues et l'absence de mutation.
- `just yubikey-dependencies-test` : 11 tests hermétiques indépendants sur
  les états GPG/scdaemon/PCSC, SSH-agent public et outils PostgreSQL/age/SOPS.
- `just yubikey-dependencies-readonly` : métadonnées locales uniquement,
  sans démarrage de daemon, sans secrets ni inventaire matériel.
- `just yubikey-parallel-host-readonly` : six familles de tests en parallèle,
  puis vérifications workstation/GPG-agent/dépendances en parallèle.
- `just yubikey-parallel-secondary-readonly` : même lot, puis **un seul**
  inventaire public de la secondaire, sans concurrence sur le périphérique.

**Barrière transversale conservée** : les configurations qui écrivent ou qui
utilisent des secrets ne sont pas incluses dans l'orchestrateur. Les opérations
OpenPGP, PIV82, PIN/AES256, OTP2, PAM et SOPS ne sont jamais déclenchées
implicitement. Avant configuration réelle, démontrer restauration indépendante,
préservation 9A/OTP2, moyens de secours et approbation de l'opération ciblée.
La présence d'une carte, le succès d'un test ou une réponse Assuan ne suffit pas.

**Preuve locale hors matériel** : au 25/10/2026, compilation Python et **11/11
nouveaux tests PASS** sur copies strictement identiques aux blobs Git publiés :
`run-yubikey-parallel-readonly.py@823111e8` et
`test_yubikey_parallel_readonly.py@4b6ebd29`. Ce résultat ne teste ni
la recette réelle `just` du worktree, ni le périphérique de la workstation.
Le statut de récupération et de configuration reste **NO-GO**.

**Point d'avancement P0 (25/10/2026)** : diagnostic du poste étendu,
sans toucher aux clés. Les 11 tests du collecteur de dépendances ont réussi
sur copie locale strictement identique à GitHub ; la recette parallèle
élargie (13 tests de contrat, six suites puis trois sondes) reste à exécuter
sur la workstation. Les étapes mutantes restent soumises à des accords
séparés ; aucune vérification GPG/OpenPGP, escrow ou restauration PostgreSQL
ne peut être déclarée terminée par simple présence d'un daemon.

### Validation suivante — agent scdaemon et récupération PostgreSQL

La workstation au SHA `aa2bdedd` confirme les processus
`scdaemon`/`pcscd` et les identités publiques SSH, mais pas l'accès
OpenPGP. `initdb` et `pg_ctl` sont absents du `PATH` seulement.

Le collecteur de dépendances étendu teste désormais, sans démarrage :
`GETINFO scd_running` via GPG-agent existant `--no-autostart`, puis
les métadonnées des binaires PostgreSQL versionnés standards. **17/17
contrats PASS en local sur blobs Git exacts** ; lecture sur workstation
du nouvel état encore `NOT_RUN`. Éviter d'installer un nouveau serveur
PostgreSQL avant d'avoir qualifié l'installation actuelle et défini un
espace de restauration isolé. Les deux copies d'escrow et les archives
GPG/PostgreSQL restent non inventoriées ou non restaurées dans ces
preuves : aucun changement du statut `NO-GO`.


### Prochaine étape concrète : première preuve PostgreSQL fonctionnelle isolée

- **Contexte validé (`32209b38`)** : 21/21 dépendances, 13/13 contrats
  parallèle PASS sur la workstation. `GETINFO scd_running` reste
  `NOT_CONFIRMED`; les clients PostgreSQL sont présents mais pas les
  exécutables serveur locaux. Les anciennes sauvegardes restent intactes.
- **Correctif GPG** : classifieur Assuan plus robuste pour un message
  d'accueil et distinction explicite de `ERR`, sans requête `SCD`.
  Les 3 nouveaux contrats GitHub attendent validation sur workstation.
- **Récupération PostgreSQL sur fixture** : le nouveau script
  `verify-postgres-fixture-recovery.sh` peut prouver le roundtrip
  `pg_dump` → `pg_restore` **sans aucune sauvegarde personnelle**,
  avec un conteneur local isolé, opt-in, SHA image imposé et cleanup.
  **5/5 tests hermétiques PASS en local sur blobs exacts** ; test Docker
  fonctionnel réel `NOT_RUN`. Un succès éventuel ne satisfait pas L3
  avant une restauration d'archive réelle explicitement autorisée.
- **En parallèle** : conserver l'inventaire des dépendances PKI/9A,
  FIDO2/SSH, escrow age et GPG/OpenPGP. Ne pas déduire un `GO`
  matériel du smoke PostgreSQL.

Voir [runbook des diagnostics](yubikey-readonly-batch.md#diagnostic-gpg-renforcé-et-restauration-postgresql-synthétique--25102026).

## Cinq opérations demandées — exécution conjointe (25 octobre 2026)

La demande opérateur couvre **PIV82/age, OpenPGP/GPG, FIDO2/SSH,
KeePassXC/OTP2 et SOPS/escrow/PostgreSQL**. Leur préparation peut
être menée en parallèle, mais les opérations sur matériel réel ne
peuvent pas être lancées depuis l'agent sans lecteur ni secrets locaux.

Livré en #280 : `scripts/workstation/prepare-yubikey-backup-five.py`,
`tests/test_yubikey_backup_five_workstreams.py` et recettes
`just yubikey-backup-five-{test,readonly,secondary-readonly}`.
Le collecteur réutilise les outils existants, refuse de reproduire
les sorties brutes et conserve `status=NO-GO`. Il ne configure
pas automatiquement PIV, FIDO, OpenPGP, OTP2 ni SOPS.

| Piste | Prochaine preuve d'acceptation |
| --- | --- |
| PIV82/age | attestation P-256, certificat interopérable, roundtrip réel sur la secondaire |
| OpenPGP/GPG | accès réel à la carte et test de signature/déchiffrement supervisé |
| FIDO2/SSH | création locale d'une identité backup distincte puis login vérifié et secours |
| KeePassXC/OTP2 | ouverture d'une copie de base KDBX avec les deux clés, sans reprogrammer OTP2 |
| SOPS/age/escrow | deux voies indépendantes de récupération, déchiffrement et restauration PostgreSQL isolée |

**Contrats :** 10 tests hermétiques de l'orchestrateur exécutés
sur une copie locale avant publication ; la validation des nouvelles
recettes sur workstation reste `NOT_RUN`. L'inventaire
matériel et les étapes mutantes doivent rester séparés.
Ne pas interpréter le code de sortie 0 d'un diagnostic comme une
autorisation d'opération irréversible.

[Runbook détaillé des cinq chantiers](yubikey-backup-five-execution.md).

## Mise à jour : OTP2 secondaire programmé — KeePassXC en attente (26/10/2026)

La commande opérateur `just yubikey-otp2-secondary-readonly` a confirmé
`otp2=PROGRAMMED_TYPE_UNVERIFIED` pour la YubiKey de secours
`22916048`. `keepassxc_verified=false`,
`otp2_hmac_sha1_verified=false`, `escrow=NOT_CHECKED`,
`status=NO-GO`. **Ne pas reprogrammer OTP2** : `ykman otp info`
ne révèle pas le type ou le secret HMAC existant.

**Jalon KeePassXC à exécuter localement** : ouvrir la même **copie
chiffrée KDBX**, sans jamais enregistrer, une fois avec la principale
`23501671` seule, puis une fois avec la secondaire `22916048`
seule, en conservant les mêmes autres facteurs.
Conditions de clôture : `PRIMARY_UNLOCK=PASS` et
`SECONDARY_UNLOCK=PASS`, plus moyen de récupération disponible.
Si aucune base existante n'utilise HMAC-SHA1 challenge-response,
le jalon reste `NOT_CONFIGURED`, sans changer la protection
de la base principale.

[Procédure OTP2/KeePassXC](yubikey-backup-keepassxc-otp2-verification.md).

**Autres chantiers à ne pas confondre** : signature SSH/FIDO2 locale
déjà démontrée (SSHSIG), login SSH distant non testé ; OpenPGP
répond publiquement mais pas de preuve de clé privée ; PIV82 non
provisionné ; récupération SOPS/GPG/PostgreSQL réelle et escrows non
vérifiés. Ces chantiers gardent leurs critères de validation propres.

## Transfert vers PR #285 — récupération age/SOPS validée, escrows à inventorier (26/10/2026)

Le test KeePassXC/OTP2 est **reporté à la demande de l'opérateur** ;
la seule observation actuelle reste `PROGRAMMED_TYPE_UNVERIFIED`.
Pas de nouveau challenge, aucune reprogrammation.

**Validation opérateur déjà obtenue** sur `feat/yubikey-software-recovery-20261026` :
`just yubikey-software-recovery-test` **9/9 PASS** ;
`just yubikey-software-recovery-check` :
`SYNTHETIC_TOOLS_PRESENT_NOT_EXECUTED` ;
`just yubikey-software-recovery-run` :
`AGE_AND_SOPS_SYNTHETIC_ROUNDTRIP_PASS`, avec
`synthetic_software_roundtrip_verified=true`.
Cela démontre le roundtrip synthétique avec des binaires réels du
poste, **pas** la récupération d'une sauvegarde personnelle.

**Consolidation demandée dans PR #285** : reprise des mêmes blobs
de script et de 9 tests age/SOPS depuis #287, en préservant les
corrections secrètes de la PR #285. Ajout d'un collecteur facultatif
`yubikey-escrow-pair-inspect` à saisie masquée, sans chemins en
arguments ou logs, ni accès aux contenus. Les 8 contrats hermétiques
de cet outil sont **PASS en environnement agent** ; une exécution
de métadonnées sur les deux vrais escrows reste **NOT_RUN**.

**Prochaines preuves séparées :**
- Sélectionner deux archives `.age` déjà existantes sur la workstation.
- Observer `TWO_FILES_DIFFERENT_FILESYSTEMS_UNVERIFIED` (stat-only),
  sans confondre plusieurs filesystems avec deux supports physiques.
- Vérifier la récupération indépendante de chaque copie dans un
  environnement isolé, sans publication des secrets.
- Lancer une restauration isolée GPG/PostgreSQL seulement après
  validation des prérequis, avec preuve expurgée.
- Autoriser ensuite, phase par phase, PIV82/age (génération, attestation,
  certificat et roundtrip matériel), en préservant PIV9A et OTP2.

Voir [runbook de récupération synthétique et escrows](yubikey-software-recovery-20261026.md).

## Deux emplacements age connus — preuve opérateur et recherche automatique (26/10/2026)

Le logiciel a désormais un mode `--discover` qui examine uniquement
les deux répertoires suivants (sans récursion et sans ouverture du contenu) :

- `~/.local/share/nabla/age-backups/`
- `/media/backup/lab/secret/`

La découverte fait correspondre les fichiers `.age` **par nom
identique** dans les deux répertoires. Elle refuse de choisir une paire
si plusieurs noms correspondent et ne suit aucun lien symbolique.
`just yubikey-escrow-pair-discover` renvoie seulement un statut
JSON, sans afficher les noms ni chemins.
`just yubikey-escrow-pair-inspect` propose la paire unique après
confirmation `[o/N]`, sinon conserve la saisie manuelle masquée.
Les tests hermétiques de cette interface sont passés de **8 à 17**
et attendent une validation sur la workstation.

**Preuve utilisateur** : même chemin fourni deux fois
→ `SAME_FILE`, refus correct. Après copie `cp` vers le support monté,
deux inspections des deux chemins ont renvoyé
`TWO_FILES_DIFFERENT_FILESYSTEMS_UNVERIFIED`.
La copie destination apparaît en `-rw-------+` et contient
389 octets. Cela ne prouve ni identité des contenus, ni supports
physiquement indépendants, ni déchiffrement/restore.
L'ACL `+` devra être contrôlée localement.

**Suite** : vérifier l'identité binaire de la copie puis restaurer en
environnement isolé à partir du support de sauvegarde, sans exposer
la clé age ou le texte déchiffré. Aucune génération PIV82 ou mutation
SOPS autorisée à ce stade. Test KeePassXC/OTP2 toujours reporté.

## Escrow chiffré — deux copies repérées et comparaison de contenu à faire (26/10/2026)

**Preuve opérateur au HEAD `41e2b099` :** découverte de la
copie locale et de la copie sur support monté
`TWO_FILES_DIFFERENT_FILESYSTEMS_UNVERIFIED` par
`just yubikey-escrow-pair-discover`, puis la même classification
confirmée après réponse `o` à `just yubikey-escrow-pair-inspect`.
**17/17 tests de la découverte PASS sur workstation.**

La prochaine preuve est l'égalité **octet par octet** des deux
archives `.age` chiffrées, sans clé, sans déchiffrement ni
publication de hash. Nouveau programme :
`compare-yubikey-escrow-pair-readonly.py`, recette explicite
`just yubikey-escrow-compare-run`, avec contrôle et
**11/11 tests hermétiques PASS en environnement agent**.
Le test des **vraies copies** reste `NOT_RUN`.

Une réponse `ENCRYPTED_COPIES_IDENTICAL_RESTORE_UNVERIFIED` permettra
de considérer la copie chiffrée comme identique au moment du contrôle,
mais **pas** comme récupérable, indépendante physiquement ou source
d'une seconde identité age. L'ACL `+` sur la destination et la
restauration réelle doivent encore être vérifiées.

La génération PIV82 et les changements de destinataires SOPS restent
**NO-GO**. Le test KeePassXC/OTP2 demeure reporté.

[Procédure](yubikey-software-recovery-20261026.md).

## Escrows — diagnostic de découverte et comparaison manuelle (26/10/2026)

La suite du comparateur a **11/11 PASS sur la workstation**, et son
précontrôle `--check` confirme qu'aucun contenu n'est lu. Mais le
premier `just yubikey-escrow-compare-run` réel a renvoyé
`DISCOVERY_NO_MATCHING_PAIR`, avec
`encrypted_content_read_attempted=false`.
Ce résultat ne signifie pas que les archives diffèrent ou sont
indéchiffrables : aucune comparaison de contenu n'a eu lieu.

Le collecteur et le comparateur partagent l'inventaire des répertoires
`~/.local/share/nabla/age-backups` et `/media/backup/lab/secret`.
Pour distinguer HOME incohérent, dossier manquant, absence de fichier
ou absence de nom commun, exécuter le nouveau
`just yubikey-escrow-pair-diagnose`. Il produit uniquement les
états des deux répertoires, les compteurs bornés de fichiers `.age`
et le nombre de noms correspondants. Aucun chemin n'est publié.

Si la découverte reste absente malgré l'existence des fichiers,
`just yubikey-escrow-compare-manual` permet une sélection par
saisie terminale masquée, sous le même contrôle de métadonnées,
avec autorisation explicite. La comparaison **lit les contenus
chiffrés**, sans déchiffrer, écrire ou afficher les fichiers.
Les contrats ont été étendus à **22 tests d'inventaire** et
**18 tests de comparaison** ; la validation complète de ces nouveaux
contrats sur workstation est `NOT_RUN`.

**Toujours NO-GO** pour la restauration réelle, l'identité d'un
second moyen de récupération age, toute écriture PIV82 et toute
modification du SOPS de production. KeePassXC/OTP2 reste reporté.

[Diagnostic et procédure](yubikey-software-recovery-20261026.md).

## Escrow NFS — copie absente côté serveur, snapshots à examiner (26/10/2026)

La workstation a validé **12/12 contrats** du probe NFS/TrueNAS ;
`SERVER_EXPECTED_COPY_MISSING` a été observé depuis le serveur
dans `/mnt/cpool/backup/lab/secret`. Le fichier est également absent
de la vue cliente NFS, tandis que la source locale `.age`
reste identifiable. **La disparition permanente n'est pas démontrée.**

Nouveau jalon non destructif : `just yubikey-escrow-history-test`,
`just yubikey-escrow-history-check`, puis
`just yubikey-escrow-history-probe` supervisé.
Le programme examine les métadonnées de trois racines de snapshots
ZFS candidates, **au plus 32 entrées par racine**, sans scan récursif
général, contenu privé ou commande ZFS à privilèges.
**10 tests hermétiques PASS dans l'environnement agent** ;
preuve workstation réelle `NOT_RUN`.

L'ordre des opérations reste : identifier la copie/snapshot
historique éventuel → confirmer intégrité → restaurer
dans un espace isolé → vérifier les moyens de récupération.
Aucun rollback ZFS, copie, changement de destinataire SOPS ni
provisionnement PIV82 autorisé. KeePassXC/OTP2 reste différé.

Voir [runbook](yubikey-software-recovery-20261026.md).
