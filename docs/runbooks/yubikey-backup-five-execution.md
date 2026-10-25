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
bash scripts/workstation/diagnose-gpg-smartcard.sh --check
```

Une fois l'environnement de récupération garanti, utiliser une séance
interactive sur la carte secondaire pour vérifier `gpg --card-status`
sans déplacer les sous-clés. Si nécessaire, comparer le mode PC/SC à CCID
et l'agent réellement utilisé. Ne pas exécuter `gpg --edit-key`,
`keytocard`, `gpgconf --kill` ou une rotation de clé automatiquement.

**Acceptation** : visibilité de l'applet OpenPGP et correspondance des
sous-clés publiques sans régression de signature Git ni de l'accès aux
anciennes archives. Une signature/déchiffrement réel nécessite un test
supervisé distinct.

## 3 — FIDO2, passkeys et SSH

**État connu** : applet FIDO répond ; SSH-agent possède des identités,
mais leur type et l'enrôlement sur la secondaire ne sont pas démontrés.
Avant tout enrôlement, conserver un accès SSH de secours et tester
`ssh-keygen -Q key` ou la capacité ed25519-sk du client.

**Session opérateur — clé SSH FIDO2 distincte** (seulement après contrôle
que `ykman list --serials` retourne **exactement** `22916048`) :
```bash
umask 077
test ! -e "$HOME/.ssh/id_ed25519_sk_backup" || exit 3
test ! -e "$HOME/.ssh/id_ed25519_sk_backup.pub" || exit 3
ssh-keygen -t ed25519-sk -f "$HOME/.ssh/id_ed25519_sk_backup" -C 'yubikey-backup-22916048'
```
Toucher la carte et saisir le PIN uniquement dans la boîte locale de l'outil
si demandé. Cette opération génère un **nouvel identifiant FIDO** ; elle
n'enregistre pas automatiquement la clé auprès des serveurs.
Configurer ensuite chaque destination (GitHub, serveur, fournisseur de
passkeys) individuellement avec la **clé publique**, sans retirer les
accès existants. Ne modifier ni PAM, ni `authorized_keys` ni les comptes
distants automatiquement.

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
