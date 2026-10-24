# YubiKey PIV82 / age — reprise après la fusion de PR #271

**Travail :** PR [#274](https://github.com/AlbanAndrieu/nabla-compose/pull/274), Draft, commits [skip ci]. Sécurité : **NO-GO matériel**.

## 0. Exécution opérateur en une seule commande (recommandée)

**Résultats attestés le 24 octobre 2026 :** 71/71 tests unittest PASS,
12 refus cryptographiques PIV82 PASS, 13 tests F9 PASS. Le certificat
F9 public de la secondaire 22916048 (firmware 5.4.3) correspond à son
empreinte observée et sa signature a été vérifiée avec la racine
Yubico historique épinglée. Aucune autorisation de génération PIV82,
PIN, management key AES256 ou migration age/SOPS n'en résulte.

Le checkout initial est /tmp/nabla-yubikey-pr259 mais le terminal peut
être n'importe où. Le lanceur vérifie git status, obtient le SHA de
la branche PR #274 et ne récupère les objets Git que s'ils manquent.
Il crée un git worktree détaché dans un dossier unique privé sous le
HOME, exécute la gate sur le commit épinglé puis vérifie les fichiers
F9 et racine sauvegardés. **Aucun git pull ni git switch n'est lancé sur
le checkout original**, et ses changements locaux sont préservés.

**Un unique bloc à copier et exécuter, indépendamment du répertoire courant :**

~~~bash
bash <<'YUBIKEY_PR274_ONESHOT'
set -Eeuo pipefail
repo=/tmp/nabla-yubikey-pr259
remote=https://github.com/AlbanAndrieu/nabla-compose.git
ref=refs/heads/fix/homelab-operator-diagnostics-followup-20261024
[[ -d "$repo" ]] || { printf 'NO-GO: checkout absent: %s\n' "$repo" >&2; exit 3; }
response="$(git ls-remote --exit-code "$remote" "$ref")"
IFS=

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


## 5. Chaîne de confiance F9 — firmware 5.4.3

**Observation du 24 octobre 2026** : la YubiKey secondaire 22916048, firmware 5.4.3, possède un certificat public F9 lisible. Son empreinte SHA-256 observée est :

    6C:6E:14:0A:69:81:14:C3:51:14:0C:1B:68:C4:B1:16:A7:D9:B4:49:29:76:62:39:2F:61:F1:78:54:90:34:DF

La quality gate workstation sur HEAD 4f076aa5 a donné **66/66 PASS** en 12,220 secondes et le banc cryptographique a rejeté 12 attaques synthétiques. Cette validation précède la présente mise à jour.

**Racine applicable** : le firmware 5.4.3 relève de la racine **Yubico PIV Root CA Serial 263751**, dont le PEM officiel est https://developers.yubico.com/PKI/yubico-piv-ca-1.pem. La racine 2025 et ses intermédiaires ne sont pas applicables. L'empreinte SHA-256 DER du certificat racine publié par Yubico est :

    63:EC:E9:14:E5:4D:D8:79:15:F3:40:33:C8:5A:F4:C0:69:6B:A1:51:2F:8A:DD:66:CE:D7:38:33:12:07:B5:46

Cette empreinte de racine est **épinglée dans** scripts/workstation/verify-age-yubikey-f9-root-offline.py ; elle ne peut pas être remplacée par un argument de ligne de commande. Le validateur refuse une F9 présentant une empreinte différente de l'observation de la workstation, une signature contrefaite, un mauvais émetteur, une racine non CA, un firmware 5.7.4+ ou un certificat expiré. Aucune interaction avec la carte ni le réseau.

**Procédure en lecture seule**, uniquement avec la secondaire branchée après synchronisation de la PR #274 :

~~~bash
umask 077
mkdir -p "$HOME/.local/share/nabla/yubikey-f9-public"
bash scripts/workstation/inspect-age-yubikey-f9-chain.sh \
  --serial 22916048 \
  --save-public-f9 "$HOME/.local/share/nabla/yubikey-f9-public/f9-22916048.pem"
curl --fail --location --proto '=https' --tlsv1.2 \
  --output "$HOME/.local/share/nabla/yubikey-f9-public/yubico-piv-ca-1.pem" \
  https://developers.yubico.com/PKI/yubico-piv-ca-1.pem
~/.local/share/nabla/piv-sdk-venv/bin/python \
  scripts/workstation/verify-age-yubikey-f9-root-offline.py \
  --serial 22916048 --firmware 5.4.3 \
  --f9 "$HOME/.local/share/nabla/yubikey-f9-public/f9-22916048.pem" \
  --root "$HOME/.local/share/nabla/yubikey-f9-public/yubico-piv-ca-1.pem" \
  --expected-f9-sha256 6C:6E:14:0A:69:81:14:C3:51:14:0C:1B:68:C4:B1:16:A7:D9:B4:49:29:76:62:39:2F:61:F1:78:54:90:34:DF
~~~

Le mode --save-public-f9 crée un **nouveau** fichier PEM public (permissions 0600) et refuse les chemins déjà occupés ou les symlinks. Le contenu F9 est public : ne pas committer ce certificat individuel dans le dépôt. En cas d'erreur, arrêter sans écriture matérielle.

**Validation de l'agent** : 5/5 contrats de conservation F9 et 13/13 tests synthétiques X.509 ont été exécutés dans un répertoire isolé. La gate est configurée pour **71 tests unittest attendus** (66 précédents et 5 nouveaux), suivis des deux fixtures cryptographiques autonomes. Le total réel doit être confirmé sur la workstation à partir du HEAD de PR exact.

**Interprétation stricte :** un PASS atteste la signature du fichier F9 public par la racine approuvée et la correspondance avec l'empreinte observée. Il ne prouve pas une opération live avec la clé privée F9, une clé PIV82 générée, une authentification AES256 ou un déchiffrement age. **NO-GO matériel et SOPS inchangé.**

Documentation officielle : https://developers.yubico.com/yubico-piv-tool/Attestation.html et https://developers.yubico.com/PIV/Introduction/PIV_attestation.html.
\t' read -r sha fetched_ref <<< "$response"
[[ "$sha" =~ ^[0-9a-f]{40}$ && "$fetched_ref" == "$ref" ]] || exit 3
if ! git -C "$repo" cat-file -e "$sha^{commit}" 2>/dev/null; then
  git -C "$repo" fetch --no-tags --no-write-fetch-head "$remote" "$ref"
fi
git -C "$repo" cat-file -e "$sha^{commit}"
launcher="$(mktemp)"
trap 'rm -f -- "$launcher"' EXIT
git -C "$repo" show "$sha:scripts/workstation/run-age-yubikey-pr274-readonly.sh" > "$launcher"
bash "$launcher" --repo "$repo"
YUBIKEY_PR274_ONESHOT
~~~

La suite du déroulement est **dans le script versionné**
scripts/workstation/run-age-yubikey-pr274-readonly.sh.
Le contrôle F9 réutilise normalement les deux certificats publics
présents dans ~/.local/share/nabla/yubikey-f9-public/ ; si le F9 manque,
une unique exportation en lecture seule est possible. La racine
manquante est téléchargée seulement depuis Yubico et comparée à
l'empreinte SHA-256 fixée. Aucun fichier existant n'est écrasé.

Le lancement échoue dès que le fetch, un test, le certificat public
ou la vérification cryptographique échoue. Il ne génère aucune clé et
ne modifie ni PIV, OTP2, PIV9A, Vaultwarden, escrow ou SOPS.
Son worktree temporaire est supprimé seulement s'il est propre ; il
est conservé pour diagnostic en cas de modifications inattendues.

**Preuve agent :** 9/9 tests Git hermétiques du lanceur PASS (répertoire
arbitraire, detached HEAD, checkout sale préservé, échecs bloquants,
export public simulé, commande --help sans réseau). Après ajout,
**80 tests unittest sont attendus** (71 antérieurs + 9), suivis de deux
fixtures crypto. Cette nouvelle suite complète reste NON EXÉCUTÉE sur
la workstation au HEAD publié. Les procédures manuelles ci-dessous
restent documentées pour un diagnostic ponctuel, mais ne sont plus
la procédure recommandée.

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


## 5. Chaîne de confiance F9 — firmware 5.4.3

**Observation du 24 octobre 2026** : la YubiKey secondaire 22916048, firmware 5.4.3, possède un certificat public F9 lisible. Son empreinte SHA-256 observée est :

    6C:6E:14:0A:69:81:14:C3:51:14:0C:1B:68:C4:B1:16:A7:D9:B4:49:29:76:62:39:2F:61:F1:78:54:90:34:DF

La quality gate workstation sur HEAD 4f076aa5 a donné **66/66 PASS** en 12,220 secondes et le banc cryptographique a rejeté 12 attaques synthétiques. Cette validation précède la présente mise à jour.

**Racine applicable** : le firmware 5.4.3 relève de la racine **Yubico PIV Root CA Serial 263751**, dont le PEM officiel est https://developers.yubico.com/PKI/yubico-piv-ca-1.pem. La racine 2025 et ses intermédiaires ne sont pas applicables. L'empreinte SHA-256 DER du certificat racine publié par Yubico est :

    63:EC:E9:14:E5:4D:D8:79:15:F3:40:33:C8:5A:F4:C0:69:6B:A1:51:2F:8A:DD:66:CE:D7:38:33:12:07:B5:46

Cette empreinte de racine est **épinglée dans** scripts/workstation/verify-age-yubikey-f9-root-offline.py ; elle ne peut pas être remplacée par un argument de ligne de commande. Le validateur refuse une F9 présentant une empreinte différente de l'observation de la workstation, une signature contrefaite, un mauvais émetteur, une racine non CA, un firmware 5.7.4+ ou un certificat expiré. Aucune interaction avec la carte ni le réseau.

**Procédure en lecture seule**, uniquement avec la secondaire branchée après synchronisation de la PR #274 :

~~~bash
umask 077
mkdir -p "$HOME/.local/share/nabla/yubikey-f9-public"
bash scripts/workstation/inspect-age-yubikey-f9-chain.sh \
  --serial 22916048 \
  --save-public-f9 "$HOME/.local/share/nabla/yubikey-f9-public/f9-22916048.pem"
curl --fail --location --proto '=https' --tlsv1.2 \
  --output "$HOME/.local/share/nabla/yubikey-f9-public/yubico-piv-ca-1.pem" \
  https://developers.yubico.com/PKI/yubico-piv-ca-1.pem
~/.local/share/nabla/piv-sdk-venv/bin/python \
  scripts/workstation/verify-age-yubikey-f9-root-offline.py \
  --serial 22916048 --firmware 5.4.3 \
  --f9 "$HOME/.local/share/nabla/yubikey-f9-public/f9-22916048.pem" \
  --root "$HOME/.local/share/nabla/yubikey-f9-public/yubico-piv-ca-1.pem" \
  --expected-f9-sha256 6C:6E:14:0A:69:81:14:C3:51:14:0C:1B:68:C4:B1:16:A7:D9:B4:49:29:76:62:39:2F:61:F1:78:54:90:34:DF
~~~

Le mode --save-public-f9 crée un **nouveau** fichier PEM public (permissions 0600) et refuse les chemins déjà occupés ou les symlinks. Le contenu F9 est public : ne pas committer ce certificat individuel dans le dépôt. En cas d'erreur, arrêter sans écriture matérielle.

**Validation de l'agent** : 5/5 contrats de conservation F9 et 13/13 tests synthétiques X.509 ont été exécutés dans un répertoire isolé. La gate est configurée pour **71 tests unittest attendus** (66 précédents et 5 nouveaux), suivis des deux fixtures cryptographiques autonomes. Le total réel doit être confirmé sur la workstation à partir du HEAD de PR exact.

**Interprétation stricte :** un PASS atteste la signature du fichier F9 public par la racine approuvée et la correspondance avec l'empreinte observée. Il ne prouve pas une opération live avec la clé privée F9, une clé PIV82 générée, une authentification AES256 ou un déchiffrement age. **NO-GO matériel et SOPS inchangé.**

Documentation officielle : https://developers.yubico.com/yubico-piv-tool/Attestation.html et https://developers.yubico.com/PIV/Introduction/PIV_attestation.html.
