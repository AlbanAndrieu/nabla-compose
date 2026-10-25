# Diagnostic YubiKey consolidé — lecture seule (PR #280)

Objectif : produire **un seul rapport JSON** à partir des contrôles existants
sans mélanger observation matérielle et validation fonctionnelle.
Ce script ne déchiffre rien, ne modifie aucune carte et ne démarre pas GPG-agent.

## Point d'entrée unique

Sur le worktree actualisé de `feat/apisix-standalone-poc-20261025` :

```bash
just yubikey-diagnostics-test
just yubikey-diagnostics-secondary-readonly
```

La première recette exécute les **16 contrats synthétiques** du
coordinateur sans carte et sans réseau. La seconde exécute en une fois :
- contrôle des métadonnées de la workstation (SOPS, GPG-agent via
  `gpgconf --list-dirs agent-socket`, SSH et mapping PAM),
- contrôles des applets FIDO, OATH, OpenPGP, PIV et des slots
  9A/9C/9D/9E/83 sur la **seule** YubiKey secondaire 22916048,
- synthèse de bloqueurs et des fonctions **non vérifiées**.

**Pas de nouvelle lecture OTP2, F9 ou PIV82** dans ce parcours.
Un résultat `status=NO-GO` est attendu, même si le processus retourne 0 :
un inventaire public n'est pas une configuration complète.

Alternatives explicites :

```bash
just yubikey-diagnostics-host-readonly
# Après avoir retiré la secondaire et connecté UNIQUEMENT la principale :
just yubikey-diagnostics-primary-readonly
```

Ne pas brancher les deux cartes simultanément : l'inventaire exige
exactement le numéro de série demandé et un seul périphérique.

Si deux sauvegardes chiffrées **existantes** sont identifiées, le coordinateur
peut vérifier uniquement leurs métadonnées (chemins absolus) :

```bash
python3 scripts/workstation/diagnose-yubikey-readonly-batch.py \
  --escrow-a /CHEMIN/ABSOLU/COPIE_A.age \
  --escrow-b /CHEMIN/ABSOLU/COPIE_B.age
```

Ne pas inventer des chemins et ne pas lancer ce contrôle tant que les deux
copies n'ont pas été localisées. Aucun contenu de fichier n'est lu.
La sortie ne reproduit pas les chemins. Deux fichiers sur des filesystems
distincts ne prouvent ni leur indépendance physique ni la restauration.

Le retour du précédent diagnostic OTP2 (programmé sur 22916048)
est déjà enregistré : ne pas répéter un challenge ni une lecture.
La commande `--otp2-secondary` reste **opt-in** et n'est jamais
activée par les recettes du lot standard.

## Interprétation du rapport

| Champ | Interprétation |
| --- | --- |
| `workstation.paths.gpg_agent_socket=PRESENT_UNVERIFIED` | socket local détecté, pas de preuve de transport scdaemon |
| `device.applications.*=RESPONDS_METADATA_ONLY` | applet accessible, pas de credential/passkey fonctionnel prouvé |
| `device.piv_slots.9A=OCCUPIED_METADATA` | présence publique, préserver le certificat historique |
| `device.piv_slots.*=EMPTY_CONFIRMED` | slot vide ; aucune autorisation d'écriture |
| `otp2=NOT_CHECKED` | pas de nouvelle lecture de l'OTP2 déjà documenté |
| `escrow=NOT_CHECKED` | chemins de sauvegardes non fournis |
| `completion.*=NOT_VERIFIED` | preuves opérationnelles encore manquantes |
| `status=NO-GO` | aucune mutation autorisée, quelle que soit la sortie |

Les bloqueurs `CONVENTIONAL_SSH_FIDO_PUBLIC_HANDLE_NOT_FOUND` et
`PAM_U2F_ENROLLMENT_TOOL_MISSING` ne prouvent **pas** une absence de
toutes les identités SSH ni la nécessité de modifier PAM : ils décrivent
uniquement un chemin courant et un outil optionnel. Ne pas installer
automatiquement `pamu2fcfg`, ni modifier `/etc/pam.d` ;
l'enrôlement PAM exige un rollback, une session administrateur de secours
et un test avec les deux cartes.

## Actions restant à prouver avant configuration

1. **Récupération prioritaire** : inventorier les sauvegardes age,
   GPG et PostgreSQL ; organiser une restauration réellement isolée,
   après accord explicite, sans exposer de clés privées.
2. **GPG/scdaemon** : établir l'accès OpenPGP sans démarrer ou réinitialiser
   d'agent à l'aveugle. Le simple socket GPG détecté n'est pas une
   validation de `gpg --card-status`.
3. **FIDO2 / SSH** : inventorier les registrations existantes et les
   voies de secours, puis inscrire les deux clés séparément seulement
   après décision. Les passkeys FIDO2 ne se clonent pas entre tokens.
4. **PIV82 / age-plugin-yubikey** : le slot secondaire était vide lors
   d'un relevé précédent ; démontrer d'abord l'escrow et l'authentification
   AES256 supervisée, puis traiter génération P-256, certificat, attestation,
   roundtrip age et seconde carte comme des transactions indépendantes.
5. **PKI / 9A, OATH, 9C/9D/9E, PAM** : cartographier usages et
   dépendances. Aucun écrasement du slot 9A historique, aucune
   reprogrammation OTP2, aucune activation PAM sans rollback.

Toutes les opérations générant/modifiant une clé, demandant PIN/PUK,
challenge OTP, restauration d'escrow ou modification SOPS/PAM
sont hors périmètre de ce diagnostic et nécessitent des autorisations
distinctes.

Références internes : [plan de finition](yubikey-capabilities-completion-plan.md),
[preuves F9/PIV82/OTP2](yubikey-piv82-postmerge-diagnostics.md).


## Sonde GPG-agent active mais non intrusive (opt-in)

`just yubikey-gpg-agent-readonly` envoie uniquement `GETINFO version` à un agent GPG **déjà lancé**, par `gpg-connect-agent --no-autostart`. La réponse brute et le chemin du socket ne sont jamais imprimés. L'état `RESPONDS_GETINFO_ONLY` prouve uniquement la joignabilité du protocole Assuan, **pas** l'accès à une carte OpenPGP, une signature, un déchiffrement ni une restauration PostgreSQL. Une erreur indique `UNKNOWN` ou `TOOL_MISSING`, jamais un agent démarré implicitement. Voir la [documentation GnuPG](https://gnupg.org/documentation/manuals/gnupg-devel/Invoking-gpg_002dconnect_002dagent.html).

`just yubikey-diagnostics-all-secondary` lance aussi `just yubikey-gpg-agent-test` puis active `--gpg-agent-probe` sur le coordinateur. Ce lot exécute **16 + 28 + 12 + 13 + 19 + 7 = 95 méthodes de tests ciblés** avant l'observation publique de la secondaire. Ce compteur indique les tests versionnés, **pas des tests déjà exécutés sur le nouveau HEAD**. Aucune nouvelle lecture OTP2, F9 ou PIV82.
