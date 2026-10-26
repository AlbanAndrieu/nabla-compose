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
sur copies correspondant bit-à-bit aux blobs Git publiés. Le test avec
les vrais binaires age/SOPS n'a **pas** été exécuté par l'agent
(ces exécutables sont absents de son environnement).
Ce résultat devra être fourni par la workstation.

## Deux escrows age réels — contrôle de métadonnées uniquement

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
