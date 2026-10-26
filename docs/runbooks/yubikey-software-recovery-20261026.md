# YubiKey — reprise récupération logicielle age/SOPS (26 octobre 2026)

**Périmètre** : `nabla-compose`, suite de la PR #280 fusionnée.
**KeePassXC / OTP2** : **DIFFÉRÉ à la demande de l'opérateur** ;
secondaire `22916048` avec `PROGRAMMED_TYPE_UNVERIFIED` (slot 2 programmé),
aucun challenge HMAC, aucune base KDBX ouverte, aucune modification OTP.
Il ne s'agit ni d'un test `PASS`, ni d'un test `FAIL`.

## État des cinq chantiers

| Voie | Preuve acquise | Reste |
| --- | --- | --- |
| PIV82/age | F9 public contrôlé, AES256 PIN-protected connu, slot 82 vide au dernier inventaire | Deux restaurations d'escrow et certificat âge/P-256 interopérable, attestation de la clé, véritable roundtrip matériel, aucune génération avant |
| OpenPGP/GPG | `gpg --card-status` a répondu publiquement sur la secondaire après échec intermittent | Correspondance des sous-clés, signature/déchiffrement fonctionnels, stabilité du transport |
| SSH/FIDO2 | Clé de secours ED25519-SK créée, fingerprint et `ssh-keygen -Y sign/verify` **PASS** ; 14/14 contrats sur workstation | Login SSH distant, inscription passkeys par service |
| KeePassXC/OTP2 | Slot 2 **programmé** sur secondaire | **DIFFÉRÉ** : test de déverrouillage de la même copie KDBX avec les deux cartes |
| SOPS/age/escrow | Outils logiciels age et sops présents au dernier inventaire workstation | Roundtrip logiciel synthétique, deux vrais escrows récupérables indépendamment et restauration GPG/PostgreSQL isolée |

**Aucun état PASS synthétique n'est une preuve de récupération réelle.**
Conserver les destinataires SOPS actuels, PIV9A historique, OTP2 et les clés
GPG ; aucune modification matérielle automatique.

## Test logiciel synthétique — aucun secret personnel

Nouveau script `verify-yubikey-software-age-sops-fixture.py` :
- `--check` n'exécute aucun outil ni accès au matériel : vérifie seulement
  que `age`, `age-keygen` et `sops` existent.
- `--run` crée un répertoire temporaire 0700, une **nouvelle clé age
  éphémère**, et une fixture JSON **publique synthétique** ;
  chiffrement/déchiffrement age, puis chiffrement/déchiffrement SOPS
  avec **uniquement** cette clé temporaire.
- Le sous-processus reçoit un environnement isolé avec `HOME`,
  `XDG_CONFIG_HOME`, `GNUPGHOME` et `SOPS_AGE_KEY_FILE` temporaires.
  Les variables de secrets du shell, les identités réelles,
  `.sops.yaml` du dépôt et les profils cloud ne sont pas propagés.
- Les erreurs brutes, clés et contenus ne sont pas imprimés. Le
  répertoire et l'identité synthétiques sont détruits à la sortie.
  En cas d'erreur, la classification retourne un **état borné**,
  sans tentative automatique ni fallback vers une vraie identité.

### Procédure workstation

```bash
cd ~/w/nabla-compose
git fetch origin
git switch feat/yubikey-software-recovery-20261026
git pull --ff-only
git rev-parse HEAD

just yubikey-software-recovery-test
just yubikey-software-recovery-check

# Seulement si les binaires sont présents et si l'opérateur autorise
# un test cryptographique logiciel utilisant une clé jetable :
just yubikey-software-recovery-run
```

La sortie attendue pour le test logiciel effectif est
`AGE_AND_SOPS_SYNTHETIC_ROUNDTRIP_PASS`, avec
`synthetic_software_roundtrip_verified=true`, mais **toujours**
`status=NO-GO`, `real_escrow_restoration_verified=false` et
`piv82_decrypt_verified=false`.

Le script possède **9 tests hermétiques PASS** en environnement agent
sur copies correspondant bit-à-bit aux blobs Git publiés.

**Preuve opérateur workstation reçue** : `just yubikey-software-recovery-test`
**9/9 PASS**. Le contrôle `-check` a renvoyé
`SYNTHETIC_TOOLS_PRESENT_NOT_EXECUTED`.
L'exécution réelle `just yubikey-software-recovery-run` a ensuite
renvoyé **`AGE_AND_SOPS_SYNTHETIC_ROUNDTRIP_PASS`** et
`synthetic_software_roundtrip_verified=true` avec les vrais
binaires du poste. Aucun secret utilisateur ni YubiKey n'a été utilisé.
**Deux véritables archives d'escrow : toujours NOT_VERIFIED.**

## Deux escrows age réels — contrôle de métadonnées uniquement

Une alternative interactive évite de placer les chemins privés dans
l'historique du shell ou la ligne de commande d'un processus :

```bash
just yubikey-escrow-pair-test
just yubikey-escrow-pair-check
# Recherche automatique locale de deux fichiers *.age de même nom :
just yubikey-escrow-pair-discover
# Pour utiliser la paire détectée après confirmation (ou saisie masquée
# manuelle si la découverte ne trouve pas exactement une paire) :
just yubikey-escrow-pair-inspect
```

Le script recherche désormais les fichiers `.age` non récursivement dans
les deux répertoires connus de la workstation :

- `~/.local/share/nabla/age-backups/` (origine locale)
- `/media/backup/lab/secret/` (copie du support monté)

`--discover` vérifie uniquement les noms et métadonnées accessibles, puis
retourne un état sans publier le nom des fichiers ni leurs chemins.
Il sélectionne automatiquement **une seule** paire de noms identiques.
Deux paires possibles donnent `DISCOVERY_MULTIPLE_MATCHING_PAIRS` :
aucun choix arbitraire n'est effectué. Les répertoires et fichiers
symboliques sont rejetés, et le nombre d'entrées parcourues est limité.

`--inspect` exige un terminal interactif. Quand une paire est reconnue,
il propose son inspection avec une confirmation `[o/N]`, sans montrer le
chemin des fichiers. Si l'opérateur refuse ou si la découverte échoue,
il demande les deux chemins absolus en **saisie masquée** comme auparavant.
Les sorties JSON ne contiennent jamais ces chemins. L'outil délègue à
`inspect-yubikey-recovery-readonly.py`, qui vérifie uniquement
les métadonnées (type de fichier, taille non nulle, inode,
filesystem, liens symboliques) ; il n'ouvre et ne déchiffre pas les
archives. L'état
`TWO_FILES_DIFFERENT_FILESYSTEMS_UNVERIFIED` n'atteste **pas**
l'indépendance physique des supports ni leur récupérabilité.
Les tests de cette nouvelle recette doivent être validés sur workstation.

Avec les **deux vrais chemins absolus** choisis localement par l'opérateur,
le script déjà présent permet un inventaire de fichiers sans ouvrir
ni déchiffrer les sauvegardes :

```bash
python3 scripts/workstation/inspect-yubikey-recovery-readonly.py \
  --escrow-a '/SUPPORT_A/backup.age' \
  --escrow-b '/SUPPORT_B/backup.age'
```

Seule la sortie `TWO_FILES_DIFFERENT_FILESYSTEMS_UNVERIFIED` indique
deux fichiers distincts sur deux systèmes de fichiers distincts ;
**ce n'est pas une preuve de deux supports physiques ni de leur
restauration**. Si les fichiers n'existent pas, ou si les chemins sont
des liens symboliques, conserver `UNKNOWN` et ne pas créer de faux
fichiers pour réussir le contrôle. Ne pas mettre ces chemins en clair
dans un ticket public ou une PR.

**Preuves opérateur du 26/10/2026** : le premier essai avait fourni
deux fois le même chemin : `SAME_FILE`, refus normal. L'opérateur a
ensuite copié une archive `.age` de l'origine locale vers le support
monté avec `cp` et utilisé un chemin dans chaque répertoire. Deux
exécutions ont produit `TWO_FILES_DIFFERENT_FILESYSTEMS_UNVERIFIED`.
La copie du support apparaît comme fichier de 389 octets,
`-rw-------+` : le signe `+` indique une ACL à examiner séparément.
Ces observations **ne prouvent pas** que les contenus sont identiques,
que le support est physiquement indépendant ou que la clé de
déchiffrement est récupérable. Il s'agit de deux copies d'une même
archive chiffrée, non de deux identités de récupération distinctes.

Pour vérifier ensuite uniquement l'identité binaire des deux copies,
l'opérateur peut utiliser `cmp -s --` localement, avec les chemins
réels, sans afficher le contenu. Ce test **lit** les deux fichiers
(à la différence de l'inventaire stat-only) mais n'écrit rien.
Une égalité binaire ne valide toujours pas le déchiffrement.

Après un contrôle de métadonnées réussi, le prochain jalon est
une récupération supervisée de chacune des deux archives sur un espace
isolé, dans le respect des accès et des supports originaux. Aucune
restauration réelle ni aucun changement de destinataire SOPS n'est
initié par ce chantier.

## Préconditions avant toute écriture PIV82

1. Vérifier deux moyens de récupération logiciels réellement
   fonctionnels **et indépendants du token secondaire**.
2. Vérifier un déchiffrement d'archive GPG existante et une
   restauration PostgreSQL isolée, sans changer les originaux.
3. Refaire l'inventaire public PIV82/9A/AES256 avec **une seule carte**
   pour confirmer que 82 est toujours vide et 9A inchangé.
4. Suivre les sept phases de `plan-age-yubikey-piv82-transaction.py`
   en séance supervisée, avec autorisation par opération et
   pas de nouvelle tentative PIN automatique.
5. Tester un roundtrip age **réel sur PIV82**, puis l'autre YubiKey
   séparément, avant toute modification des destinataires SOPS.

Références : [SOPS age](https://getsops.io/docs/usage/identities/age/),
[age-keygen](https://manpages.debian.org/testing/age/age-keygen.1.en.html),
[plan YubiKey](yubikey-capabilities-completion-plan.md),
[runbook de 5 chantiers](yubikey-backup-five-execution.md).

## Contrôle supplémentaire — identité binaire des deux escrows chiffrés

**Preuve workstation acquise au HEAD `41e2b099` (26/10/2026)** :
`just yubikey-escrow-pair-test` **17/17 PASS**,
`just yubikey-escrow-pair-discover` et
`just yubikey-escrow-pair-inspect` avec confirmation `o`
ont tous deux renvoyé
`TWO_FILES_DIFFERENT_FILESYSTEMS_UNVERIFIED`.
L'inventaire ne lit jamais le contenu des archives : ce résultat
ne prouve donc pas leur identité binaire.

Pour comparer leurs **octets chiffrés uniquement**, exécuter une commande
**distincte** : elle lit les fichiers, contrairement à l'inventaire
précédent. Elle exige une autorisation explicite. Aucune clé age,
carte YubiKey ni passphrase n'est utilisée.

```bash
just yubikey-escrow-compare-test
just yubikey-escrow-compare-check
# Après validation des tests et de la présence des deux fichiers :
just yubikey-escrow-compare-run
```

Le programme `compare-yubikey-escrow-pair-readonly.py` réutilise la
découverte d'**une seule paire** de noms identiques dans les deux
répertoires connus. Il vérifie l'appartenance des fichiers à
l'utilisateur, les tailles non nulles (maximum 16 Mio), le type
regular, les liens multiples et les identifiants de fichiers. Il ouvre
les deux fichiers avec `O_NOFOLLOW`, puis compare les octets par
blocs de 64 Kio en mémoire. Il détecte un changement de
métadonnées pendant la lecture, refuse les fichiers sur un même
filesystem et nettoie les descripteurs ouverts.

Le résultat JSON ne contient jamais de chemin, de hash, de contenu,
de clé ou de secret. Les états principaux sont :

| État | Interprétation |
| --- | --- |
| `ENCRYPTED_COPIES_IDENTICAL_RESTORE_UNVERIFIED` | Les deux fichiers chiffrés ont été lus et les octets comparés sont identiques, sans changement détecté pendant la lecture |
| `ENCRYPTED_COPIES_DIFFER` | Contenu ou taille différents : ne pas utiliser la copie comme preuve de redondance identique |
| `ENCRYPTED_COPY_CHANGED_DURING_READ` | Source ou copie modifiée pendant le contrôle : arrêt, pas de conclusion |
| `ENCRYPTED_COPY_UNVERIFIED` | Permissions, type, métadonnées ou accès non conformes |
| `DISCOVERY_MULTIPLE_MATCHING_PAIRS` | Plusieurs noms correspondants : il faut traiter l'ambiguïté avant de lire |
| `COPIES_NOT_ON_DISTINCT_FILESYSTEMS` | Le test exige deux systèmes de fichiers différents |

Même si les octets sont identiques, les deux fichiers représentent
**la même archive chiffrée recopiée**, et non deux clés de récupération
distinctes. Ce test ne démontre ni le déchiffrement de l'identité
`age`, ni un stockage sur deux supports physiques indépendants,
ni la récupération réelle d'un secret SOPS, ni l'autorisation de créer
une clé PIV82.

Le nouveau comparateur et **11 tests hermétiques ont été exécutés en
local par l'agent** sur des fichiers synthétiques. L'exécution
sur les deux vraies archives de workstation n'est **pas encore faite**.
Les tests existants du collecteur ont été validés par l'opérateur
(**17/17 PASS**).

**Suite** : vérifier localement l'ACL du fichier de destination
(`getfacl` ; ne pas publier les chemins si confidentiels), puis
préparer une restauration isolée de la sauvegarde à partir de la copie
sur support, avec ses moyens de déchiffrement réels et une preuve
expurgée, avant toute transaction PIV82.

## Investigation d'une découverte intermittente — 26/10/2026

**Preuve opérateur :** `just yubikey-escrow-compare-test` **11/11 PASS**
et `just yubikey-escrow-compare-check` =
`ENCRYPTED_CONTENT_NOT_READ`. Cependant
`just yubikey-escrow-compare-run` a renvoyé
`DISCOVERY_NO_MATCHING_PAIR`, avec
`encrypted_content_read_attempted=false`. Aucune archive n'a été lue
par cette dernière commande.

Les deux outils (inventaire et comparateur) réutilisent la **même**
fonction `discover_pair(Path.home())`, qui exige **un unique nom
de fichier .age commun** entre les répertoires source et backup.
Les relevés antérieurs avaient réussi ; la cause du désaccord actuel
n'est pas démontrée. Possibilités à vérifier : répertoire `HOME`
différent, montage de backup indisponible, copie déplacée ou renommée,
absence momentanée de fichier, ou changement de son type.
Le code ne doit pas assimiler l'absence de paire à un échec de
déchiffrement.

### Diagnostic sans divulguer de chemin

```bash
just yubikey-escrow-pair-test
just yubikey-escrow-compare-test
just yubikey-escrow-pair-diagnose
just yubikey-escrow-pair-discover
```

La nouvelle recette `yubikey-escrow-pair-diagnose` n'ouvre aucun
fichier chiffré. Elle renvoie un nombre borné de fichiers `.age`
et l'état d'accès à chaque répertoire connu (`ACCESSIBLE`,
`DIRECTORY_MISSING`, `PERMISSION_DENIED`, `DIRECTORY_UNAVAILABLE`,
`TOO_MANY_ENTRIES`, `SYMLINK_DIRECTORY_UNTRUSTED`), ainsi que
`matching_age_filenames` et
`home_location_consistent_with_account`.
Aucun nom, chemin, octet chiffré ou contenu de clé n'est affiché.
Une valeur `matching_age_filenames=0` explique le refus
`DISCOVERY_NO_MATCHING_PAIR` à l'instant du contrôle, sans en prouver
la cause historique.

Pour vérifier la disponibilité du support monté sans modifier les
données, un opérateur peut aussi exécuter localement :
```bash
findmnt -T /media/backup/lab/secret -o TARGET,FSTYPE
```

### Comparaison manuelle en lecture seule

Si la découverte automatique échoue **mais que les deux archives
existent**, utiliser **une commande distincte**, avec une session
terminale interactive et l'autorisation explicite :

```bash
just yubikey-escrow-compare-manual
```

Les deux chemins absolus sont demandés en **saisie masquée**
(sans argument en ligne de commande ni historique shell).
Le programme vérifie d'abord avec l'inspecteur existant que les
deux fichiers sont réguliers, non symboliques, distincts et
sur des systèmes de fichiers différents, puis applique le même
contrôle d'octets chiffrés avec `O_NOFOLLOW`, owner/métadonnées
et limites de taille. **Il lit les données chiffrées**, mais
ne déchiffre rien, ne modifie aucun fichier et ne publie
ni chemin ni empreinte.

Un `ENCRYPTED_COPIES_IDENTICAL_RESTORE_UNVERIFIED` prouvera
seulement l'égalité des deux copies au moment de la lecture.
Un `NO-GO` de comparaison doit conduire au diagnostic,
pas à une copie `cp` supplémentaire ni à une rotation de clé.
Deux copies identiques de la même archive ne constituent toujours
pas deux identités indépendantes de récupération.
Le test KeePassXC/OTP2 reste reporté, et la génération PIV82
reste bloquée.

## Diagnostic confirmé — destination accessible sans fichier .age (26/10/2026)

**Logs opérateur :** les deux suites récentes sont vertes :
`just yubikey-escrow-pair-test` **22/22 PASS**,
`just yubikey-escrow-compare-test` **18/18 PASS**.
Le dernier contrôle `just yubikey-escrow-pair-diagnose` a retourné :

- `source_directory.state=ACCESSIBLE`, `age_files=1`.
- `backup_directory.state=ACCESSIBLE`, `age_files=0`.
- `matching_age_filenames=0`.
- `home_location_consistent_with_account=true`.
- `files_opened=false` et `restoration_verified=false`.

`just yubikey-escrow-pair-discover` a renvoyé
`DISCOVERY_NO_MATCHING_PAIR`. La tentative
`just yubikey-escrow-compare-manual` a renvoyé `UNKNOWN`
avant d'ouvrir le contenu chiffré
(`encrypted_content_read_attempted=false`).
**Aucune preuve que les deux archives aient été comparées ou restaurées.**

Le répertoire `/media/backup/lab/secret` est donc **accessible**,
mais aucune entrée régulière se terminant par `.age` n'a été
recensée au moment du test. Cela peut correspondre à un fichier
absent, renommé, à un lien symbolique ignoré ou à une cible de
montage devenue inaccessible à son contenu habituel.
Le diagnostic ne prouve pas à lui seul un démontage du disque.

### Prochaine vérification — aucun changement de fichiers

```bash
# Vérifier le filesystem effectif associé au chemin sauvegarde :
findmnt -T /media/backup/lab/secret -o TARGET,FSTYPE

# Diagnostiquer les entrées attendues SANS lire le contenu age :
just yubikey-escrow-pair-diagnose
```

Attention : `findmnt -T` peut identifier simplement le filesystem
parent (par exemple `/`) même si le disque de sauvegarde n'est plus
monté. Comparer la valeur de `TARGET` au point de montage attendu.

Le champ `diagnostic.expected_backup_copy_state` classe désormais,
en lecture de métadonnées uniquement, le fichier de même nom que
l'unique archive `.age` locale :

| Valeur | Interprétation |
| --- | --- |
| `EXPECTED_COPY_MISSING` | Aucun fichier de ce nom au chemin de sauvegarde |
| `EXPECTED_COPY_IS_SYMLINK` | Entrée présente, mais lien symbolique refusé |
| `EXPECTED_COPY_EMPTY` | Entrée régulière vide ; copie non valide |
| `EXPECTED_COPY_NOT_REGULAR` | Objet autre qu'un fichier régulier |
| `EXPECTED_COPY_REGULAR_NONEMPTY` | Entrée régulière non vide présente ; **pas** une preuve d'intégrité |
| `EXPECTED_COPY_ACCESS_DENIED` | Métadonnées inaccessibles |
| `NO_UNIQUE_SOURCE_FILE` | Plusieurs fichiers locaux possibles ; ne pas choisir arbitrairement |
| `NOT_EVALUATED` | Un des répertoires n'a pas passé l'inventaire |

Le champ ne présente ni nom ni chemin, ne calcule aucun hash
et n'ouvre aucun contenu. Les tests du nouveau champ sont publiés
dans la PR ; leur exécution complète sur workstation est `NOT_RUN`.

**Ne pas répéter `cp` avant d'avoir vérifié le montage attendu.**
Écrire dans le répertoire sous-jacent d'un disque non monté risquerait
de donner l'impression d'une sauvegarde externe alors que les données
sont restées sur le disque local.

Une fois le support et l'archive attendus retrouvés, relancer
l'inventaire, puis seulement la comparaison chiffrée. Cela ne vaut
toujours pas restauration indépendante. Pas de modification des
destinataires SOPS, d'OTP2, de PIV9A ni de génération PIV82.
KeePassXC reste reporté.

## NFSv4 confirmé ; archive attendue manquante — suite (26/10/2026)

**Preuve opérateur sur checkout PR #285** : `just yubikey-escrow-pair-test`
**26/26 PASS**, `just yubikey-escrow-pair-diagnose` :
`source_directory.age_files=1`,
`backup_directory.state=ACCESSIBLE`,
`backup_directory.age_files=0`,
`expected_backup_copy_state=EXPECTED_COPY_MISSING`,
`matching_age_filenames=0`. La commande
`findmnt -T /media/backup/lab/secret -o TARGET,FSTYPE` a retourné
**`/media/backup/lab nfs4`**.

Ceci confirme que **le chemin de sauvegarde est actuellement situé
sous un montage NFSv4 actif**. Il ne s'agit pas d'une simple écriture
sous `/` causée par un montage absent. Le diagnostic ne prouve pas
que l'export NFS actuel soit le même qu'au moment où le fichier
`.age` de 389 octets avait été observé, ni la présence du fichier
sur le serveur à un autre emplacement.

**Ajout PR** : `backup_mount_state` dans la commande
`just yubikey-escrow-pair-diagnose`, via `findmnt` sans exposer
`SOURCE`, options, adresse du serveur ou chemin de l'export. État
attendu : `EXPECTED_NFS4_MOUNT_PRESENT`.
4 tests hermétiques supplémentaires vérifient le format de la
réponse, le refus d'un point de montage parent et l'absence de
succès trompeur si `findmnt` est indisponible. Les tests doivent
être validés sur la workstation après récupération de la PR.

### Investigation locale de l'export (sans écriture)

```bash
# Afficher ces informations uniquement localement : ne pas coller
# la source/export, les ACL complètes ou la liste des secrets en PR.
findmnt -T /media/backup/lab/secret -o TARGET,FSTYPE,SOURCE,OPTIONS

# Vérifier la visibilité du répertoire, sans lecture d'archive chiffrée :
stat -c 'directory_type=%F mode=%a uid=%u gid=%g' /media/backup/lab/secret

# Relever les métadonnées et ACL du répertoire :
getfacl -cp /media/backup/lab/secret

# Comparer localement l'export indiqué par findmnt à l'export
# attendu côté serveur NFS (aucun remount automatique).
```

Si la source de montage est inattendue, corriger **l'identification
de l'export** d'abord ; ne pas recopier la sauvegarde vers un export
qui pourrait être incorrect. Si la source est la bonne, rechercher
sur le serveur NFS une suppression, un déplacement, un snapshot
antérieur ou un changement de dataset/ACL. Ne pas recréer
automatiquement l'archive avant d'avoir confirmé son sort.

**Critère de reprise** : le montage correct est identifié, l'archive
régulière `.age` attendue redevient visible, puis la comparaison
réelle des deux fichiers chiffrés renvoie
`ENCRYPTED_COPIES_IDENTICAL_RESTORE_UNVERIFIED`. Même cette preuve
n'autorise pas de mutation PIV82 ou de secrets SOPS : le déchiffrement
et la restauration restent des étapes séparées. KeePassXC/OTP2
reste reporté.

## Preuve NFS client et comparaison avec le serveur TrueNAS — 26/10/2026

**Preuve workstation au HEAD `1be4d5b2`** : la suite
`just yubikey-escrow-pair-test` a réussi **30/30 tests**.
Le diagnostic renvoie simultanément :
`backup_mount_state=EXPECTED_NFS4_MOUNT_PRESENT`,
`expected_backup_copy_state=EXPECTED_COPY_MISSING`,
`source_directory.age_files=1`,
`backup_directory.age_files=0`,
`matching_age_filenames=0`.
La commande `findmnt` sur la workstation identifie
`/media/backup/lab` comme point de montage `nfs4`
de `nabla:/mnt/cpool/backup/lab`, avec NFS version 4.2.
Cette preuve correspond à **un export NFS actif**, mais ne démontre
pas que la cible serveur correspond au dataset attendu ni qu'un
fichier a été effectivement supprimé : la visibilité côté serveur
n'a pas encore été interrogée.

### Nouvelle sonde à preuve séparée côté TrueNAS

Un contrôle non destructif a été ajouté sous
`scripts/workstation/inspect-yubikey-escrow-nfs-server.py`.
Il exige le montage `/media/backup/lab`, l'export
`nabla:/mnt/cpool/backup/lab` et un **unique nom `.age`**
dans l'emplacement local. Le nom attendu est transmis uniquement dans
le programme Python envoyé sur **stdin SSH**, jamais en argument ou
dans la sortie JSON. L'archive chiffrée n'est ni ouverte, ni copiée,
ni déchiffrée.

```bash
# Mode passif : identifie l'export et la source locale. Aucun SSH.
just yubikey-escrow-nfs-test
just yubikey-escrow-nfs-check

# Session volontaire : métadonnées uniquement côté TrueNAS.
# Utilise un hôte SSH connu, BatchMode=yes, pas de prompt mot de passe.
just yubikey-escrow-nfs-probe
```

Le probe exécute un Python fixe en lecture seule sur TrueNAS
(`/mnt/cpool/backup/lab/secret`) via
`albandrieu@172.17.0.24`. Il inspecte le répertoire, le nombre
borné d'archives `.age` et les métadonnées du **nom attendu**.
Il interdit les liens symboliques, n'ouvre aucun contenu et n'effectue
aucune modification NFS/TrueNAS. Aucune authentification SSH
interactive ni nouvelle clé d'hôte n'est acceptée automatiquement.
En cas de refus SSH, d'hôte inconnu ou d'absence de Python, il
renvoie un état borné de non-vérification, sans tentative en boucle.

| `server_state` | Suite |
| --- | --- |
| `SERVER_EXPECTED_COPY_MISSING` | Confirmer la disparition/rotation/migration/snapshot côté serveur ; ne pas recopier automatiquement |
| `SERVER_EXPECTED_COPY_REGULAR_NONEMPTY` | Fichier visible côté serveur mais pas côté NFS : analyser permissions UID/GID, export, cache et ACL |
| `SERVER_DIRECTORY_MISSING` | Investiguer dataset ou répertoire côté serveur |
| `SERVER_DIRECTORY_ACCESS_DENIED` | Vérifier les ACL côté TrueNAS avec accès autorisé |
| `SERVER_EXPECTED_COPY_SYMLINK` | Ne pas suivre ni utiliser le lien pour la preuve |
| `SSH_READONLY_PROBE_UNAVAILABLE` | Vérifier SSH/known_hosts/compte, sans redémarrage ni réessai automatique |

Les sorties conservent **`status=NO-GO`**,
`archive_opened=false`, `remote_write_performed=false`,
`restoration_verified=false` et `decryption_attempted=false`.
**11 tests hermétiques PASS en environnement agent**, mais le
probe SSH réel et la suite sur la workstation restent
**NOT_RUN** au moment de la création.
Ne pas traiter une réponse `SERVER_EXPECTED_COPY_MISSING` comme
une preuve de suppression définitive : d'autres datasets, snapshots
ou exports peuvent contenir la copie historique.

La vérification des copies et de leur déchiffrement est un jalon
distinct, prérequis avant toute écriture PIV82. KeePassXC/OTP2
reste différé à la demande de l'opérateur.
