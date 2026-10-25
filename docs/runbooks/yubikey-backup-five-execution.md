# YubiKey secondaire — cinq chantiers simultanés et preuves d'acceptation

État : **préparation seulement — matériel NO-GO**. PR #280 Draft.
Carte secondaire : `22916048`, firmware `5.4.3`. Principale `23501671` : ne pas toucher pendant cette session.

## Point d'entrée unique, sans écriture

```bash
cd ~/w/nabla-compose
git pull --ff-only
git rev-parse HEAD
just yubikey-backup-five-test
just yubikey-backup-five-readonly
# Uniquement avec la secondaire branchée et une seule carte :
just yubikey-backup-five-secondary-readonly
```

Le programme `prepare-yubikey-backup-five.py` exécute quatre collecteurs
indépendants simultanément (GPG-agent, workstation, dépendances, plan PIV82),
puis, sur option, **un seul** inventaire public PIV82 de la carte secondaire.
Il n'interroge pas OTP2, ne lance pas de challenge ni de commande SCD.
Il refuse de classer le résultat `GO`. Les informations brutes des outils
et les emplacements privés ne sont pas affichés.

Les pistes ci-dessous peuvent être préparées en parallèle. La création de clés
ou une action demandant un PIN restent des opérations locales **par phase**,
avec la carte et l'opérateur physiquement présents. Ne jamais transmettre PIN,
PUK, clé de gestion ni secret HMAC dans le chat, GitHub ou les logs.

## 1 — PIV82 + age (écriture sur la YubiKey)

**État connu** : PIV82 vide au précédent inventaire, PIV9A occupé avec certificat
historique expiré, gestion PIV `AES256_PIN_PROTECTED`. F9 validé hors ligne.
L'attestation F9 ne prouve pas une clé PIV82.

La phase matérielle est bloquée jusqu'à la preuve indépendante de deux
récupérations d'escrow logiciel **et** d'un déchiffrement GPG/PostgreSQL
sur environnement isolé. Valider ensuite :
```bash
python3 scripts/workstation/plan-age-yubikey-piv82-transaction.py --serial 22916048 --json
python3 scripts/workstation/inspect-age-yubikey-piv82-secondary.py --serial 22916048 --json
bash scripts/workstation/verify-age-yubikey-offline.sh
```

Séquence de configuration future **supervisée, transaction par transaction** :
vérification PIN/AES256 sans auto-retry ; génération P-256 non exportable
dans 0x82 uniquement ; attestation F9 + politiques PIN/touch ; certificat
interopérable age-plugin-yubikey ; import dans 0x82 ; lecture retour et
roundtrip age synthétique avec la **même** carte. Ne jamais exécuter
`age-plugin-yubikey --generate` sur l'installation 0.5.1 utilisée dans
ce projet : gestion AES256 non couverte par ce chemin. Ne pas écrire en 9A
ni 83, ne pas réinitialiser PIV. Le script de planification existant décrit
les sept phases ; il n'a pas de mode `--apply`.

**Acceptation** : identité matériel PIV82 utilisable pour déchiffrer une
fixture age, attestation et SPKI vérifiés, PIV9A et OTP2 inchangés.

## 2 — OpenPGP / GPG

**État connu** : agent GPG accessible, scdaemon et pcscd présents mais
`agent_scdaemon=NOT_CONFIRMED` lors du dernier relevé.
Cela ne prouve pas l'accès à la carte. Préparer hors connexion :
```bash
just yubikey-dependencies-readonly
bash scripts/workstation/diagnose-gpg-smartcard.sh --host-only
```

Une fois l'environnement de récupération garanti, utiliser une séance
interactive sur la carte secondaire pour vérifier `gpg --card-status`
sans déplacer les sous-clés. Si nécessaire, comparer le mode PC/SC à CCID
et l'agent réellement utilisé. Ne pas exécuter `gpg --edit-key`,
`keytocard`, `gpgconf --kill` ou une rotation de clé automatiquement.

**Important :** `diagnose-gpg-smartcard.sh --check` n'est pas
un contrôle strictement sans effet : il exécute actuellement des
commandes `SCD` et `gpg --card-status`, ce qui peut démarrer
scdaemon et accéder au lecteur. Ne lancer `--check` que pendant
une séance matérielle supervisée, après validation des sauvegardes.
Pour le diagnostic sans contact, utiliser `--host-only`.

Pour faire évoluer le diagnostic sans utiliser de clé privée,
`just yubikey-backup-openpgp-test` valide sept contrats hermétiques,
puis `just yubikey-backup-openpgp-check` vérifie uniquement les outils
présents. Avec **une seule** secondaire connectée et sur une session
interactive supervisée, la commande facultative
`just yubikey-backup-openpgp-probe` vérifie le numéro de série via
`ykman` et appelle `gpg --batch --no-tty --card-status`.
Les sorties brutes (numéros de carte, métadonnées et erreurs détaillées)
restent masquées. **Cette commande peut démarrer scdaemon** ; elle ne doit
pas être ajoutée aux sondes hôte parallèles et ne signe ni ne déchiffre.

Même un `GPG_CARD_STATUS_RESPONDS_PUBLIC_ONLY_IDENTITY_UNVERIFIED`
ne prouve pas que l'applet répondante soit la secondaire attendue
sans une preuve de liaison cryptographique, ni que les clés privées
historiques fonctionnent. En cas de `OPENPGP_TRANSPORT_NOT_CONFIRMED`,
préserver la configuration existante et examiner les conflits PC/SC
avant de relancer.

**Acceptation** : visibilité de l'applet OpenPGP et correspondance des
sous-clés publiques sans régression de signature Git ni de l'accès aux
anciennes archives. Une signature/déchiffrement réel nécessite un test
supervisé distinct.

## 3 — FIDO2, passkeys et SSH

**État connu** : applet FIDO répond ; SSH-agent possède des identités,
mais leur type et l'enrôlement sur la secondaire ne sont pas démontrés.
Avant tout enrôlement, conserver un accès SSH de secours et tester
`ssh-keygen -Q key` ou la capacité ed25519-sk du client.

**Session opérateur — enrôlement SSH FIDO2 distinct**
(aucune autre YubiKey connectée ; terminal interactif) :

```bash
just yubikey-backup-ssh-test
just yubikey-backup-ssh-check
# Uniquement après résultat READY_FOR_INTERACTIVE_ENROLLMENT :
just yubikey-backup-ssh-enroll
```

La commande `--check` ne contacte pas la carte et n'écrit aucun fichier.
La commande `--enroll`, explicitement nommée dans la recette, vérifie
`ykman list --serials` == **22916048**, exige un terminal et produit
une nouvelle poignée SSH `ed25519-sk` dans le dossier dédié
`~/.ssh/nabla-yubikey-backup-22916048`. Ce dossier doit être absent :
aucun écrasement ni retry automatique, y compris après une exécution
partielle. Le PIN et le touch restent gérés localement par `ssh-keygen`
si nécessaire. Aucune modification de `~/.ssh/config`,
`authorized_keys`, serveur SSH, PAM ou GitHub n'est effectuée.

Une poignée SSH locale **n'est pas un login validé**. Conserver
la clé de secours existante et enregistrer manuellement la nouvelle
clé publique sur chaque destination. Les passkeys WebAuthn nécessitent
également leur propre inscription sur chaque service.

**Acceptation** : authentification réelle testée sur chaque destination,
avec seconde voie de secours disponible. Les passkeys ne sont pas copiées
d'une YubiKey à l'autre ; inscrire les deux cartes par service.

## 4 — KeePassXC / OTP2

**État connu** : OTP slot 2 programmé sur la secondaire, mais son type
HMAC-SHA1 et le déverrouillage de la base réelle ne sont pas prouvés
par ces diagnostics. **Ne jamais écrire le slot 2.**

Avec une **copie locale** de la base KeePassXC et sa méthode de récupération,
tester la connexion dans l'interface KeePassXC avec la principale, puis avec
la secondaire, **séparément**, sans tenter de reprogrammer OTP2.
Une base utilisant un challenge-response HMAC-SHA1 doit être associée
au même secret HMAC sur les deux cartes pour être interchangeable.

**Acceptation** : même base de test déverrouillée avec chacune des cartes et
méthode de secours fonctionnelle. Aucune valeur HMAC ou mot de passe ne doit
être recopié dans les sorties.

## 5 — SOPS / age / deux escrows / sauvegardes PostgreSQL-GPG

**État connu** : identité SOPS logicielle présente, mais pas de déchiffrement
ou de restauration indépendante vérifiés dans les rapports récents.

Inspecter **seulement les métadonnées de deux copies existantes**
après avoir identifié leurs vrais chemins privés :
```bash
python3 scripts/workstation/prepare-yubikey-backup-five.py \
  --escrow-a /CHEMIN/EXISTANT/A.age --escrow-b /AUTRE/SUPPORT/B.age
```
Deux systèmes de fichiers distincts ne prouvent pas deux supports
physiquement indépendants. Procéder ensuite à une récupération hors ligne
sur une machine ou un environnement jetable, en conservant les originaux
en lecture seule. Vérifier la restauration GPG/PostgreSQL et un déchiffrement
SOPS/age à partir d'une copie récupérée, sans afficher les données.

Le test `just yubikey-postgres-fixture-test` ne porte que sur une
**fixture synthétique** ; il ne prouve aucune restauration d'archive réelle.
L'exécution Docker est facultative et doit rester locale, avec une image
PostgreSQL préalablement validée et épinglée par identifiant SHA256.

**Acceptation** : restauration indépendante de chacune des deux voies
d'escrow, lecture contrôlée des archives GPG/PostgreSQL et déchiffrement
SOPS/age. Ne pas modifier les destinataires SOPS avant un roundtrip avec
**les deux** YubiKeys et une voie logicielle de secours.

## Critères communs

- Ne jamais déduire `GO` d'un exit code zéro d'un diagnostic.
- Une seule carte interrogée à la fois. Ne pas paralléliser les écritures
  ou les accès PIN sur un même périphérique.
- Enregistrer le SHA du dépôt, l'opération effectuée, le résultat redigé
  et le rollback. Ne pas stocker de secret ni de contenu privé.
- PIV9A, OTP2, PIN/PUK, clés GPG existantes et destinataires SOPS : préserver
  jusqu'à preuve d'une récupération indépendante.
- Les cinq chantiers peuvent avancer en préparation, mais restent
  **NOT_VERIFIED/NOT_CONFIGURED** tant que les recettes fonctionnelles
  correspondant à chaque opération n'ont pas été exécutées sur workstation.

Références :
[Yubico PIV CLI](https://docs.yubico.com/software/yubikey/tools/ykman/PIV_Commands.html),
[KeePassXC User Guide](https://keepassxc.org/docs/KeePassXC_UserGuide),
[Plan PIV82 détaillé](yubikey-capabilities-completion-plan.md).

## Preuve opérateur — identité SSH FIDO2 créée, OpenPGP intermittent (26/10/2026)

La workstation a généré effectivement une nouvelle poignée SSH FIDO2
`ed25519-sk` sur la secondaire **22916048** (commande
`just yubikey-backup-ssh-enroll`). Une première tentative de PIN FIDO2
était incorrecte, la suivante a abouti à la génération. Ne pas relancer
l'enrôlement, ne pas multiplier les essais de PIN. Une passphrase SSH
a été saisie et confirmée localement ; elle ne doit jamais être copiée
dans les journaux ni dans GitHub. Le fichier existe dans
`~/.ssh/nabla-yubikey-backup-22916048/id_ed25519_sk_backup`
et la clé publique existe à côté.

Empreinte publique attestée par `ssh-keygen -lf` :
`SHA256:42+Klqmv8gwQZB+1OxRjkye3nEQF1PsMjTQwXwzoSwQ`
(`ED25519-SK`).
**Il s'agit uniquement d'une identité SSH locale créée.**
La signature matérielle d'une fixture et l'authentification distante
sur les serveurs/GitHub sont encore `NOT_VERIFIED`.

La séance OpenPGP s'est déroulée avec **deux résultats différents** :
- Première exécution `GPG_CARD_STATUS_RESPONDS_PUBLIC_ONLY_IDENTITY_UNVERIFIED`.
- Deuxième exécution `OPENPGP_TRANSPORT_NOT_CONFIRMED` (exit 3).

On ne peut pas affirmer la cause sans diagnostic : scdaemon, CCID,
PC/SC, lecteur ou contexte agent concurrent restent des hypothèses.
Ne pas redémarrer/arrêter GPG-agent, scdaemon ou pcscd et ne pas
éditer `scdaemon.conf` automatiquement. L'état OpenPGP reste **NO-GO**.

### Nouvelle classification OpenPGP, sans divulgation

La sonde `probe-yubikey-backup-openpgp.py` refuse désormais
un succès GPG si la sortie ne comporte pas un identifiant d'applet
OpenPGP de forme canonique `D27600012401...`.
Une réponse GPG vide avec code 0 n'est **pas** une preuve d'accès carte.

Les échecs sont catégorisés dans le JSON sans imprimer stdout/stderr :
`OPENPGP_DEVICE_NOT_AVAILABLE`, `OPENPGP_READER_BUSY_UNVERIFIED`,
`OPENPGP_SCDAEMON_OR_AGENT_UNAVAILABLE`,
`OPENPGP_CARD_OR_READER_ERROR`, `OPENPGP_PROBE_TIMEOUT` et
`OPENPGP_TRANSPORT_NOT_CONFIRMED`.
Une réussite reste `GPG_CARD_STATUS_RESPONDS_PUBLIC_ONLY_IDENTITY_UNVERIFIED`,
**pas** une preuve de sous-clé privée ou d'identité liée à 22916048.

Le script et ses 15 contrats hermétiques ont été vérifiés sur copies
locales dont les blobs Git correspondent exactement aux versions publiées :
`probe-yubikey-backup-openpgp.py@e11a7d26` ;
`test_yubikey_backup_openpgp_probe.py@94f5fb2e`.
**15/15 PASS local ; workstation sur cette nouvelle version NOT_RUN.**

```bash
cd ~/w/nabla-compose
git pull --ff-only
git rev-parse HEAD
just yubikey-backup-openpgp-test
just yubikey-dependencies-readonly
bash scripts/workstation/diagnose-gpg-smartcard.sh --host-only
# Puis, seulement avec la secondaire et une session terminal supervisée :
just yubikey-backup-openpgp-probe
```

Si la sonde renvoie à nouveau une erreur, noter **uniquement son état
JSON** et ne pas la répéter immédiatement. Analyser ensuite le type
d'erreur avant de changer une option PC/SC ou relancer un daemon.
Ne jamais publier une sortie GPG complète contenant identifiants
de lecteurs, clés, UID, chemins ou données sensibles.
