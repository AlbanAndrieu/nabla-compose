# YubiKey PIV82 / age AES256 — reprise de chantier (23 octobre 2026)

## Source de vérité et limites

- Dépôt : `AlbanAndrieu/nabla-compose`.
- **PR de travail unique : [#271](https://github.com/AlbanAndrieu/nabla-compose/pull/271)**, branche `feat/fast-batch-talos-k8s-services-20261023`. Ne pas créer de PR, merger ou lancer de GitHub Actions.
- Vérifier le dernier HEAD GitHub avant toute écriture : plusieurs agents poussent sur cette branche.
- Priorité : réutiliser les deux **YubiKey 5 NFC** sans perturber KeePassXC OTP2, l'ancien certificat PIV9A, la management key AES256 PIN-protected ou la récupération SOPS logicielle.
- Secondaire **22916048** (LastPass : `yubikey-5-nabla backup`), principale **23501671** (LastPass : `yubikey-5-nabla principal`). Ne jamais enregistrer PIN, PUK, clé privée, management key ou jeton d'authentification dans les logs/PR.
- Conserver PIV82 (`SLOT.RETIRED1`) pour age, PIV83 pour une future rotation.

## Preuves validées côté workstation

1. La dernière gate **40/40 PASS (2,576 s)** lors du retour opérateur précédent. `test-age-yubikey-aes256-auth-offline.py` affichait alors le succès du modèle simplifié à 3 échecs.
2. Le préflight matériel secondaire a confirmé la clé de gestion **AES256 protégée par PIN**, PIV82 vide, métadonnées de clé PIV9A présentes. `ykman piv keys info 82` retourne `ERROR: No key stored in slot 82 (RETIRED1).` et status 1 : c'est le message attendu d'un slot vide.
3. `yubikey-manager==5.8.0` / `cryptography==46.0.3` installés sous `~/.local/share/nabla/piv-sdk-venv` sur la workstation. La vérification hors matériel des interfaces SDK AES256 est **PASS**.
4. Prototype X.509 P-256 autosigné et OID `1.3.6.1.4.1.41482.3.8` valeur `03 02` vérifiés sur clés logicielles ou sessions simulées. Aucune clé privée sur carte n'a été générée.

## Préparatifs de la passe courante

- Renforcement du modèle `test-age-yubikey-aes256-auth-offline.py` : séquencement vérification PIN → lecture de clé protégée → authentification AES256 → revérification PIN ; refus des budgets de tentatives faibles, des clés absentes/courtes, des erreurs d'authentification, d'une politique dérivée/incorrecte et d'un échec à la revérification. **10 cas négatifs**, validés en local sans SDK ni matériel.
- `test-age-yubikey-piv-signing-sdk-offline.py` : le certificat produit par `ykman.piv.sign_certificate_builder` avec fausse session doit maintenant passer `verify-age-yubikey-piv82-certificate.py`, tandis qu'une mauvaise clé publique et une signature forgée doivent être rejetées. Ce parcours requiert le SDK Yubico pour la validation workstation.
- `verify-age-yubikey-offline.sh` précompile désormais le script de modèle AES256 avant la suite `unittest`.
- **Nombre de tests `unittest` attendu : 40**, sans nouveau test nommé ajouté. Les modifications récentes ne sont **pas encore** validées par la gate complète sur la workstation.

## Commandes de validation (sans carte, sans CI)

```bash
cd /tmp/nabla-yubikey-pr259
git fetch origin feat/fast-batch-talos-k8s-services-20261023
git switch --detach origin/feat/fast-batch-talos-k8s-services-20261023
bash scripts/workstation/verify-age-yubikey-offline.sh
python3 scripts/workstation/test-age-yubikey-aes256-auth-offline.py
~/.local/share/nabla/piv-sdk-venv/bin/python scripts/workstation/test-age-yubikey-piv-signing-sdk-offline.py
```

## Restes obligatoires avant provisionnement

1. Vérifier précisément la séquence d'authentification AES256 PIN-protected et le compteur de tentatives sur matériel, **seulement avec autorisation distincte** ; aucun retry automatique du PIN.
2. Construire une procédure transactionnelle à étapes distinctes, chacune autorisée explicitement : `generate_key` ECCP256 dans PIV82 avec politiques `ALWAYS/ALWAYS`, signature X.509 par la clé **non exportable**, contrôle de signature, import puis lecture du certificat. Prévoir le comportement si l'import échoue sans écraser PIV9A.
3. Vérifier `age-plugin-yubikey --list-all`, les identités/récipients age et un round-trip chiffrer/déchiffrer synthétique sur la secondaire, puis la principale.
4. Ne modifier les destinataires SOPS de production qu'après les deux validations matérielles. Conserver l'identité logicielle CI/headless et l'escrow indépendant. Une **deuxième copie indépendante de l'identité privée escrow** reste une dette de récupération.

**Statut : NO-GO pour tout provisionnement/écriture PIV.** Les tests hors matériel et un slot vide ne suffisent pas à l'autoriser.
