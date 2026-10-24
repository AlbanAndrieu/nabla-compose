# YubiKey PIV82 / age — reprise après la fusion de PR #271

**Travail :** PR [#274](https://github.com/AlbanAndrieu/nabla-compose/pull/274), Draft, commits [skip ci]. Sécurité : **NO-GO matériel**.

## 0. Reprise automatisée sans checkout après redémarrage

**Dernières preuves réelles :** 71/71 unittest et 13 tests F9 PASS,
certificat F9 secondaire 22916048 (firmware 5.4.3) vérifié jusqu'à la
racine Yubico épinglée. PIV82, PIN/AES256 et SOPS restent NO-GO.

**Après reboot, /tmp/nabla-yubikey-pr259 peut avoir disparu.**
Ne pas chercher à réparer ce chemin. Le lanceur utilise désormais un
**dépôt bare persistant** dans
\`$HOME/.local/share/nabla/git/nabla-compose.git\` et crée un
worktree détaché et privé, unique pour chaque agent, sous
\`$HOME/.local/share/nabla/agent-worktrees/\`.

La procédure complète tient dans **un bloc**, exécutable depuis
n'importe quel répertoire. Le bootstrap :
1. Obtient le SHA exact de la branche PR #274 sur GitHub.
2. Crée le cache Git bare si absent, sous verrou.
3. Récupère le commit seulement s'il manque.
4. Extrait le script versionné de ce SHA, sans modifier de checkout.
5. Exécute les tests et le contrôle cryptographique F9 enregistré.
Chaque échec interrompt la suite. Aucune écriture matérielle.

~~~bash
bash <<'PR274_READONLY'
set -Eeuo pipefail
umask 077
remote=https://github.com/AlbanAndrieu/nabla-compose.git
branch=fix/homelab-operator-diagnostics-followup-20261024
state="${NABLA_AGENT_STATE_DIR:-$HOME/.local/share/nabla}"
cache="$state/git/nabla-compose.git"
[[ -d "$HOME" && ! -L "$state" && ! -L "$state/git" && ! -L "$cache" ]] || exit 3
mkdir -p -m 0700 "$state/git"
exec 9>"$state/.pr274-git.lock"
flock -w 20 9
if [[ ! -e "$cache" ]]; then git init --bare -q "$cache"; fi
[[ "$(git --git-dir="$cache" rev-parse --is-bare-repository)" == true ]]
ref="refs/heads/$branch"
response="$(git ls-remote --exit-code "$remote" "$ref")"
IFS=$'\t' read -r sha returned_ref <<< "$response"
[[ "$sha" =~ ^[0-9a-f]{40}$ && "$returned_ref" == "$ref" ]]
if ! git --git-dir="$cache" cat-file -e "$sha^{commit}" 2>/dev/null; then
  git --git-dir="$cache" fetch --no-tags --no-write-fetch-head "$remote" "$ref"
fi
git --git-dir="$cache" cat-file -e "$sha^{commit}"
launcher="$(mktemp)"
trap 'rm -f -- "$launcher"' EXIT
git --git-dir="$cache" show "$sha:scripts/workstation/run-age-yubikey-pr274-readonly.sh" > "$launcher"
flock -u 9
bash "$launcher" --pinned-sha "$sha"
PR274_READONLY
~~~

Le cache Git bare **survit aux redémarrages si HOME persiste**.
Sinon fournir un volume persistant avec \`NABLA_AGENT_STATE_DIR\`.
Le worktree est supprimé uniquement s'il est propre ; il est conservé
en cas de modifications inattendues. Aucun checkout original n'est touché.
Les certificats déjà validés sont réutilisés sans effacement.

**Preuves isolées de l'agent :** 11 tests de reprise Git réussis,
dont absence de /tmp, cache réutilisé, deux agents parallèles, échecs
de gate et de F9. La suite complète sur le HEAD de cette PR est
à revérifier sur la workstation (environ 82 tests unittest attendus).

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

## 6. Régression de contrat sur l'ordre de la gate offline (24 octobre 2026)

La reprise automatisée au SHA `3504d6bd` a exécuté **80 tests** : 79 réussis et un test en erreur. Le contrat recherchait littéralement `python3 -m py_compile "$python_source"` alors que le script emploie la forme Bash équivalente `python3 -m py_compile "${python_source}"`. La gate n'a pas été modifiée : son contrôle de syntaxe précède toujours `unittest`.

Le contrat accepte désormais **les deux formes citées** et refuse une compilation absente, déplacée après `unittest` ou ciblant une autre variable. La reproduction ciblée des 5 cas a réussi. **80 tests unittest attendus** : le correctif final adapte une assertion existante, sans ajouter de test. À valider sur la workstation. Le lanceur a correctement arrêté l'exécution avant F9 ; aucune opération PIV, PIN ou SOPS n'a eu lieu.


## Suite YubiKey — preuve publique F9 et absence de GO matériel

La chaîne publique F9 de la secondaire 22916048 (firmware 5.4.3)
a été validée avec la racine historique Yubico épinglée. Cette
preuve ne démontre PAS qu'une clé PIV82 existe ni que le
décryptage age fonctionne. Le nouveau rapport hors matériel
scripts/workstation/report-age-yubikey-piv82-readiness.py
réutilise les PEM publics et retourne NO-GO, même pour F9 PASS.
Aucun lecteur, PIN, secret, réseau ou écriture sur la carte n'est
autorisé par ce rapport. Un inventaire PIV82 en lecture seule
est la prochaine preuve matérielle ; toutes les opérations
mutantes demandent des approbations séparées par phase.

Les scripts Bash opérateur doivent être exécutés dans un
processus enfant, jamais sourcés. Les worktrees partagent
les téléchargements uv mais gardent une .venv distincte.


## 7. Inventaire matériel PIV82 frais — secondaire seulement (option explicite)

Après F9 PASS, exécuter **le même lanceur** avec
`--inventory-secondary`. Cette option demande une lecture
fraîche sur la seule YubiKey secondaire **22916048**, firmware **5.4.3**.
La vérification hors matériel s'effectue avant l'accès au lecteur.
Elle ne reconfigure **aucun** slot et n'essaie pas de PIN.

La commande versionnée
`scripts/workstation/inspect-age-yubikey-piv82-secondary.py`
exécute uniquement les opérations publiques ci-dessous, avec un
délai maximum et une entrée standard fermée :

- `ykman list --serials` : une seule carte 22916048 ;
- `ykman --device 22916048 info` : firmware 5.4.3 ;
- `ykman --device 22916048 piv info` : gestion AES256 protégée par PIN ;
- `ykman --device 22916048 piv keys info 82` : présence du slot ;
- `ykman --device 22916048 piv keys info 9a` : présence des métadonnées de la clé existante.

Résultats JSON : `EMPTY_CONFIRMED` uniquement pour
le message exact « No key stored in slot 82 (RETIRED1) » et les
contrôles AES256/PIV9A confirmés ; `OCCUPIED` pour
des métadonnées de clé reconnues ; sinon `UNKNOWN`.
Codes de sortie : 0 pour l'inventaire vide observé (mais état
global `NO-GO`), 4 pour un slot occupé, 3
pour les erreurs de matériel, lecture, politique ou transport.
Ne jamais écraser un slot occupé, ni assimiler une erreur PC/SC
à une absence de clé. La validation F9 ne vaut pas preuve PIV82.

**Ne pas sourcer les scripts dans le terminal interactif.**
Utiliser le bloc de bootstrap en Bash enfant de la section 0, en
transmettant `--inventory-secondary` au lanceur
final, ou un worktree PR #274 déjà initialisé et validé.

Le mode par défaut du lanceur **n'accède à aucun slot PIV82**.
Les 10 contrats d'inventaire synthétique et les 3 tests
d'intégration du lanceur sont distincts d'une exécution réelle
sur la secondary. Les opérations PIV82 mutantes, la PIN
et SOPS restent **NO-GO**, quel que soit ce résultat.

## 8. Résultat réel de l'inventaire secondaire et optimisation Git

**Observation workstation transmise le 24 octobre 2026** : le lanceur a
validé le commit `56a42f8f04c5` sur la branche PR #274, **100/100 tests
unittest PASS**, la fixture PIV82 (12 scénarios négatifs) PASS et
**13/13 tests de chaîne F9 PASS**. La vérification publique du
certificat F9 a réussi, sans PIN.

Le contrôle matériel **sur la YubiKey secondaire 22916048 uniquement**
a répondu :

- firmware : `5.4.3` ;
- clé de gestion : `AES256_PIN_PROTECTED` ;
- PIV82 : **`EMPTY_CONFIRMED`** ;
- PIV9A : `PRESENT_METADATA` ;
- OTP2 : `NOT_VERIFIED` ;
- statut global : **`NO-GO`**, sans autorisation d'écriture.

Il s'agit d'un inventaire réel, mais pas d'une validation des copies
d'escrow, de la présence de OTP2, des essais PIN restants ou d'un
roundtrip age. L'étape d'authentification AES256 **n'est pas autorisée**.

**Optimisation du bootstrap** : la première exécution effectuait
deux recherches/fetch Git (dans le bootstrap puis dans le lanceur).
Le bootstrap transmet désormais le SHA déjà validé au lanceur
via `--pinned-sha "$sha"`. Celui-ci vérifie que le commit est présent
dans le cache bare, puis crée son worktree propre sans seconde requête
distante. Ce mode n'est une preuve de fraîcheur que si l'appelant
a d'abord vérifié le SHA distant ; en usage autonome le lanceur
continue à faire `ls-remote` et `fetch` si nécessaire.
La reprise n'exige toujours aucun checkout dans `/tmp`.

**Prochain verrou** : preuve indépendante du maintien OTP2/PIV9A,
des deux copies d'escrow logiciel et des conditions d'une future
authentification AES256 en séance supervisée. Aucune écriture PIV82,
PIN automatique ni mise à jour SOPS.
