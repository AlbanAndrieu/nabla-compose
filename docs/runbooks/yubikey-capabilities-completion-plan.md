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
