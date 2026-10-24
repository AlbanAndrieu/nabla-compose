# YubiKey PIV82 / age — reprise après la fusion de PR #271

**Travail :** PR [#274](https://github.com/AlbanAndrieu/nabla-compose/pull/274), Draft, commits [skip ci]. Sécurité : **NO-GO matériel**.

## 1. Reprendre la branche correcte

L'opérateur est sur un detached HEAD dans /tmp/nabla-yubikey-pr259. Le précédent git pull ne peut déterminer la branche. Un échec SSH suivi d'un checkout de origin/* ne prouve pas une synchronisation récente.

Diagnostic **sans réseau et sans écriture Git** :

~~~bash
cd /tmp/nabla-yubikey-pr259
bash scripts/workstation/diagnose-age-yubikey-git-checkout.sh
~~~

Après avoir vérifié que git status --short est vide, synchroniser explicitement **la PR #274** avec HTTPS ; arrêter si fetch échoue :

~~~bash
cd /tmp/nabla-yubikey-pr259
git status --short
git fetch --no-tags https://github.com/AlbanAndrieu/nabla-compose.git \
  fix/homelab-operator-diagnostics-followup-20261024
git cat-file -e FETCH_HEAD:scripts/workstation/inspect-age-yubikey-f9-chain.sh
git switch --detach FETCH_HEAD
bash scripts/workstation/verify-age-yubikey-offline.sh
~/.local/share/nabla/piv-sdk-venv/bin/python \
  scripts/workstation/test-age-yubikey-piv82-attestation-offline.py
~~~

Ne pas faire de reset --hard, force-push, ou git pull dans un detached HEAD.

## 2. Première preuve matérielle : lecture du certificat public F9

Après validation logicielle, connecter **uniquement** la YubiKey secondaire 22916048 :

~~~bash
bash scripts/workstation/inspect-age-yubikey-f9-chain.sh --serial 22916048
~~~

Le script vérifie série unique, firmware et lisibilité X.509 du certificat public F9. Il n'utilise pas de PIN. Il n'effectue ni attestation PIV82 ni opération mutante ; le temporaire est supprimé. Une empreinte F9 **n'est pas l'empreinte de la racine Yubico**, et la présence de F9 n'atteste pas sa confiance.

## 3. Blocage du provisionnement PIV82

PIV82 est encore vide selon la dernière observation. Une attestation n'est possible qu'après génération de la clé PIV82 sur l'appareil. Ne pas lancer la génération pour obtenir un certificat d'attestation sans autorisation spécifique. Ne pas lancer age-plugin-yubikey --generate sur les clés existantes avec management key AES256.

Une fois la génération explicitement approuvée et exécutée par l'opérateur, contrôler la SPKI PIV82, le certificat F9, le certificat d'attestation 82, et la chaîne vers une racine Yubico **approuvée indépendamment**. Différencier 5.7.4+ (racine 2025/intermédiaires) des anciennes versions. Le vérificateur public strict travaille hors matériel.

## 4. Évidence et limites

Les contrats du diagnostic Git : 7/7 PASS en environnement hermétique ; les contrats F9 : 8/8 PASS en environnement hermétique. Les tests crypto synthétiques prévoient 12 refus ; la suite globale au nouveau HEAD doit être exécutée sur la workstation (66 tests attendus en absence d'autres modifications).

Aucune modification de PIV9A, F9, OTP2 KeePassXC, management key AES256, SOPS ou escrow. L'ordre reste secondaire 22916048 avant principale 23501671. Préserver deux copies indépendantes de récupération logicielle.

Sources : https://developers.yubico.com/PIV/Introduction/PIV_attestation.html ;
https://developers.yubico.com/yubico-piv-tool/Attestation.html ;
https://docs.yubico.com/software/yubikey/tools/ykman/PIV_Commands.html.
