# FastAPI Sample — LiteLLM TrueNAS → workstation Qwen

**État : clé virtuelle Workstation émise le 28/10/2026 ; stockage Vaultwarden, runtime TrueNAS et chaîne FastAPI NON VALIDÉS.**
Concerne `sample` TrueNAS uniquement, PAS le runtime public de
`fastapi-sample.fastapicloud.dev` (pas de chemin LAN privé prouvé).

## P0 sécurisé — révocation, reprise readonly et comparaison locale (PR #300)

**État constaté :** la clé `fastapi-sample-upstream` a été émise
et son fichier Workstation `workstation.key` a des permissions `0600`.
La **révocation de la session `BW_SESSION` divulguée n'est pas attestée** ;
la synchronisation Vaultwarden et l'injection TrueNAS ne sont pas confirmées.
**Ne pas relancer le provisionneur LiteLLM `--apply`.**

La session divulguée doit d'abord être rendue inutilisable. Sur la
Workstation, `bw logout` termine la session CLI locale, puis
l'opérateur doit utiliser le Web Vault pour **révoquer les sessions
du compte**. Cette révocation peut déconnecter d'autres clients.
Ni la fermeture du sous-shell ni `unset BW_SESSION` seuls ne prouvent
la révocation distante. N'imprimer aucun jeton dans le terminal partagé.

Après la révocation, reprendre **une seule connexion**, dans un shell
privé. La séparation `SESSION="$(bw login --raw)"` puis
`export BW_SESSION="$SESSION"` est volontaire : un simple
`export BW_SESSION="$(...)"` peut masquer un exit code non nul
dans Bash si le sous-processus échoue.

```bash
# Depuis la Workstation, checkout PR #300 synchronisé ; sans set -x.
git pull --ff-only
python3 -m unittest discover -s tests \
  -p 'test_fastapi_workstation_vaultwarden_compare.py' -v

bw --version
bw config server
bw status | jq '{status,serverUrl}'

(
  set -Eeuo pipefail
  set +x
  umask 077
  SESSION="$(bw login --raw)" || exit 2
  test -n "$SESSION" || exit 2
  export BW_SESSION="$SESSION"
  unset SESSION
  trap 'bw lock >/dev/null 2>&1 || true; unset BW_SESSION' EXIT

  # Ne pas afficher les éléments ni les sessions.
  bw list folders >/dev/null
  echo 'vaultwarden_readonly=ok'

  # Test de concordance en lecture seule ; exit 2 si absent/inconnu.
  just litellm-fastapi-upstream-vaultwarden-compare
)
```

Ne **pas** publier la sortie brute de `bw login`, `bw unlock`,
`bw get item`, `bw list items` ou `docker inspect`.
Le comparateur utilise `BitwardenClient` existant pour vérifier
le serveur HTTPS, l'état de déverrouillage, le dossier `TrueNAS`
et l'item exact `nabla/prod/litellm`. Il vérifie localement
la clé `workstation.key` et compare sa valeur au **champ masqué**
`LITELLM_FASTAPI_WORKSTATION_API_KEY` en mémoire, sans afficher
de donnée secrète ni écrire dans Vaultwarden. `bw sync` peut
actualiser le cache **local du CLI**, mais aucune donnée distante
n'est modifiée par ce contrôle.

Résultats opérateur attendus :

| `field_state` | Décision |
| --- | --- |
| `field_matches_private_key` | **DONE source Vaultwarden** : la clé locale et le champ masqué sont identiques |
| `field_absent` | **P0 écriture ciblée restante** ; ne pas régénérer la clé |
| `field_mismatch_no_overwrite` | **STOP** ; valeur existante différente, aucune substitution automatique |
| `field_duplicate`, `field_not_hidden`, `field_empty`, `field_unverified_schema` | **STOP** ; résoudre le conflit du coffre, sans impression des valeurs |
| `fresh_session_required`, `vaultwarden_unverified`, `private_key_unavailable` | **NO-GO** ; rétablir le prérequis, aucune interprétation de l'absence du champ |

**Limite volontaire de P0 :** le comparateur ne possède pas
de mode `--apply`. L'ajout du champ dans l'item existant doit
être fait après réussite de l'accès readonly, sans remplacement des
champs master/salt/IDE/Redis/Langfuse, et vérifié de nouveau
avec le comparateur. `materialize_runtime.py --install` est
**différé** : il remplace le fichier runtime complet, ce qui
nécessite une comparaison et une sauvegarde préalable spécifiques.
La validation de `/key/info`, du budget et du routage end-to-end
est une autre étape non effectuée.

## Incident Bitwarden CLI : double déverrouillage et session exposée

**Nouvelle réception opérateur (28/10/2026) :**
`bw unlock` interactif a indiqué que le coffre était
déverrouillé et a **affiché une valeur `BW_SESSION` dans
la sortie partagée**. Le bloc de transfert a ensuite
relancé `SESSION="$(bw unlock --raw)"`, qui a demandé de
nouveau le mot de passe puis a échoué sur
`Cryptography error, The decryption operation failed`.
Avec `set -e`, ce deuxième déverrouillage a interrompu
le bloc **avant** `bw sync`, `bw get` ou `bw edit`.
**Écriture Vaultwarden non attestée et probablement non
effectuée** ; ne pas marquer le secret comme importé.

**Action sécurité préalable** : le jeton `BW_SESSION`
qui apparaît dans la sortie partagée est considéré
compromis. Le verrouiller/invalider localement :
`unset BW_SESSION`, `bw lock`, puis `bw logout`.
Sur Vaultwarden Web Vault, sous les paramètres du compte,
utiliser **Deauthorize Sessions** / **Révoquer les sessions**
pour invalider les autres sessions d'authentification
concernées. Cela peut déconnecter les autres appareils.
Ne pas recopier ou publier une nouvelle session.

Les clients Bitwarden CLI 2026.x font l'objet de
signalements publics concernant des sessions produites
par `bw unlock --raw` et des erreurs de déchiffrement.
Ce rapprochement n'établit **pas** la cause sur cette
Workstation : relever `bw --version` avant de changer
le client ou son stockage local. Ne pas effacer le
coffre chiffré ou changer le mot de passe à l'aveugle.

**Reprise en lecture seule, après révocation** :

```bash
# Nouveau shell privé, sans xtrace ni publication de jetons.
bw --version
bw config server
bw status | jq '{status, serverUrl}'

# Un seul login interactif et capture directe de la session.
# Ne pas exécuter un deuxième bw unlock sur une session valide.
(
  set -e
  set +x
  umask 077
  SESSION="$(bw login --raw)" || exit 2
  test -n "$SESSION" || exit 2
  export BW_SESSION="$SESSION"
  unset SESSION
  bw status | jq '{status, serverUrl}'
  bw list folders >/dev/null
  echo 'vaultwarden_readonly=ok'
  bw lock >/dev/null
)
```

Si `bw login --raw` ou `bw list folders` échoue,
ne pas réessayer en boucle. Garder la clé Workstation
locale `0600`, identifier la version du client et
la cause du déchiffrement avant tout `bw edit`.
Les statuts `status=unlocked` du CLI ne suffisent pas :
une lecture réelle du coffre doit réussir.

**Précaution de transaction :** la modification
d'un item Vaultwarden via `bw edit item` renvoie
l'item complet ; elle peut écraser d'autres champs
en cas de copie périmée ou modification concurrente.
L'import ciblé de la seule clé
`LITELLM_FASTAPI_WORKSTATION_API_KEY` doit vérifier
l'identité de l'item et du dossier, préserver tous les
champs existants et contrôler le résultat après écriture.
Aucun `materialize_runtime.py --install` ni
redémarrage TrueNAS tant que ces preuves manquent.

## Réception Workstation — clé upstream émise et fichier privé validé (28/10/2026)

**Preuves opérateur :**

```text
test_fastapi_litellm_workstation_inventory.py : 12/12 PASS
status=created target=workstation model=qwen
key_location=private_operator_file mode=0600; key_value=suppressed
600 albandrieu:albandrieu /home/albandrieu/.local/share/nabla-compose/fastapi-litellm/workstation.key
```

L'identité **`fastapi-sample-upstream`** est maintenant émise
sur **LiteLLM Workstation**, avec une clé virtuelle `qwen`
générée par `--target workstation --apply`. Le fichier
local `0600` est prouvé présent et privé. **Le retour
de `/key/generate` n'est pas une preuve indépendante
du modèle permis/budget appliqué** ; vérifier `/key/info`
ou l'UI administrateur LiteLLM Workstation avant le cutover.

**Prochaine action P0 : ajout d'un seul champ au coffre.**
Dans Vaultwarden HTTPS canonique, item existant exact
`nabla/prod/litellm`, dossier `TrueNAS`, créer le champ
personnalisé **masqué**
`LITELLM_FASTAPI_WORKSTATION_API_KEY`.
Sa valeur provient **uniquement** du fichier local
`~/.local/share/nabla-compose/fastapi-litellm/workstation.key`
sur Workstation. **Ne pas recréer l'item et ne toucher
à aucun autre champ** (master, salt, IDE, Langfuse, Redis).
Ne pas afficher la clé dans les logs ni l'inclure
dans les arguments CLI, messages, Git, PR ou CI.

Après écriture côté coffre, exécuter une vérification
**lecture seule** par `just litellm-fastapi-upstream-source-check`
depuis l'opérateur non root avec `BW_SESSION` déverrouillée.
`field_present_nonempty_hidden` atteste la présence
d'une valeur masquée mais **pas son égalité** au fichier
privé Workstation. Le champ est déclaré
`critical: false` dans le manifeste ; les contrôles
génériques de secrets ne garantissent donc pas tous
son existence tant que ce test ciblé n'est pas fait.

**TrueNAS :** le fichier
`/mnt/cpool/secrets/runtime/litellm/.env.secrets`
avait `fastapi_key_declaration_count=0`, mais tous
les autres secrets présents doivent être conservés.
Ne pas exécuter `materialize_runtime.py --install`
tant que le rendu complet et sa comparaison avec la
cible n'ont pas été validés. Ne pas redémarrer LiteLLM
avant un plan de rollback et preuve d'injection.
Même après injection, la clé du premier saut
`fastapi-sample-staging` (FastAPI → TrueNAS)
reste distincte et non validée.

## Architecture et responsabilités

```text
FastAPI Sample /run (staging TrueNAS)
  DEFAULT_CHAT_MODEL=fastapi-qwen
  LITELLM_URL=http://172.17.0.24:4000
  LITELLM_API_KEY  [sample Virtual Key, scoped fastapi-qwen]
                   ↓
TrueNAS LiteLLM proxy :4000
  model fastapi-qwen -> openai/qwen
  LITELLM_WORKSTATION_API_BASE=http://172.17.0.57:4000/v1
  LITELLM_FASTAPI_WORKSTATION_API_KEY [workstation Virtual Key, scoped qwen]
                   ↓
Workstation LiteLLM proxy :4000
  model qwen -> local GPU inference
```

`apps/litellm/config.yaml` had an example `workstation-qwen`
and an `embedding` route to the workstation; this change **reuses the
architecture**, not the existing general-purpose `LITELLM_IDE_API_KEY`.
Key-scoped authorization is required independently on each proxy.
Do not use the LiteLLM **master key** as `LITELLM_API_KEY`.

## Budget demandé : 10 EUR maximum

LiteLLM virtual keys use **USD** for `max_budget`, and **require a working
database** to enforce spending. Therefore, the provisioner records
`max_budget=8 USD` **lifetime** (`budget_duration=null`, never
auto-reset) for each of two different gatekeepers. This is deliberately
**more restrictive** than the 10 EUR target at ordinary FX rates, not an
exact EUR-based accounting guarantee; FX fluctuations and external
provider costs must still be audited. **Do not add** the two budget figures:
both keys meter the same logical request across two proxy hops.

The TrueNAS `fastapi-qwen` route has *synthetic/internal* token accounting
(`input_cost_per_token=0.000001`, `output_cost_per_token=0.000002`
USD/token) to avoid a free on-prem Qwen bypassing its budget gate. **This
is not a paid model tariff or a bill.** Verify the proxy version
actually attributes nonzero spend and denies over-budget requests.
The upstream proxy may meter different amounts. The stronger bound is
the downstream TrueNAS key plus both model allowlists and rate limits.
A USD budget cannot guarantee a hard EUR-denominated monetary charge
with all FX/provider/pricing scenarios.

Both keys: `rpm_limit=5`, `tpm_limit=15000`,
`max_parallel_requests=1`. Disable access to fallback models for
that key. `enforce_fallback_model_access: true` and an empty explicit
`fastapi-qwen` fallback are declared; **test that they are supported
on the installed LiteLLM version** before enabling. The current
`store_model_in_db: true` can cause YAML/database drift: audit the
effective model list, not only the checked-in YAML.

## Provisionnement contrôlé : deux identités distinctes

Source of truth: `config/fastapi-sample/litellm-key-policy.json`.
`scripts/workstation/provision-fastapi-litellm-keys.py` defaults to
**offline --check**. It refuses output overwrite/symlink, writes keys
only into local operator-owned `0600` files and never prints them.
Do not run it as root.

```bash
# On the workstation (no network calls):
python3 scripts/workstation/provision-fastapi-litellm-keys.py --target workstation --check
python3 scripts/workstation/provision-fastapi-litellm-keys.py --target truenas --check

# Apply requires an operator-owned LiteLLM master credential on the local
# workstation proxy. NEVER place a master key in Git/GHA or a command argument.
# Supply LITELLM_MASTER_KEY privately, then:
python3 scripts/workstation/provision-fastapi-litellm-keys.py --target workstation --apply

# TrueNAS admin traffic needs an SSH local port forward to localhost:14000,
# forwarding to TrueNAS loopback :4000. Only then set
# LITELLM_TRUENAS_MASTER_KEY privately and run:
python3 scripts/workstation/provision-fastapi-litellm-keys.py --target truenas --apply
```

Stop if the key already exists. Inspect/revoke orphan keys in proxy UI
before retrying an ambiguous HTTP failure. Never copy the TrueNAS master
credential through insecure LAN HTTP.

The two generated files are **transitional**:
`~/.local/share/nabla-compose/fastapi-litellm/{workstation,truenas}.key`.
Import separately into the Vaultwarden folder `TrueNAS` using the
manifest-declared items (both fields hidden/custom fields):

| Key / source | Vaultwarden item | Runtime consumer |
| --- | --- | --- |
| workstation key (qwen only) | `nabla/prod/litellm` field `LITELLM_FASTAPI_WORKSTATION_API_KEY` | `/mnt/cpool/secrets/runtime/litellm/.env.secrets` |
| TrueNAS key (fastapi-qwen only) | `nabla/prod/sample-litellm` field `LITELLM_API_KEY` | `/mnt/cpool/secrets/runtime/sample/.env.secrets` |

Use the existing unprivileged `bw` importer and
`scripts/secrets/render_from_bitwarden.py` in `--app` mode.
**Merge the new field into existing env files** rather than overwriting
the entire `sample/.env.secrets` containing DB, pfSense and other
credentials. Review resulting root:root 0600 file ownership and avoid
leaking values in CI, `docker inspect` or shell history. Remove the
operator transitional key files only after Vaultwarden and runtime
materialization are independently verified.

## Réception suivante : absence de l'alias confirmée, test NUL corrigé

**Preuves runtime Workstation :**
`test_fastapi_litellm_native_truenas.py` = **12/12 PASS**.
`test_fastapi_litellm_workstation_inventory.py` :
**11 tests PASS**, **1 erreur du banc de test** Python
3.14 sur `patch.dict(os.environ, {"LITELLM_MASTER_KEY":
"with\\x00NUL"})`. `os.environ` refuse un octet NUL
avant l'appel au validateur : ce n'est pas un échec
du proxy ni du code de filtrage du credential.
Le test utilise désormais un **mock de `os.getenv`**
pour vérifier tous les formats interdits en restant
hors environnement système et sans réseau.
La variante de mock a été vérifiée localement ;
la suite complète reste à rejouer sur Workstation.

L'inventaire Workstation avec credential fourni en
sous-shell a produit :
```text
host_context=workstation_verified
proxy_liveliness=http_200
key_file_state=absent
alias_state=alias_absent_confirmed
runtime_mutated=false
secret_values_printed=false
```

**Décision opérationnelle :** l'absence de l'alias
`fastapi-sample-upstream` est confirmée dans la
base du proxy Workstation interrogé. Après succès
de la suite de tests corrigée, **une unique tentative**
`--target workstation --apply` est autorisée
par la demande de génération de l'opérateur.
Le provisionneur doit refaire l'inventaire
authentifié `/key/list` avant d'émettre
`POST /key/generate`, bloquer tout doublon
et écrire la nouvelle clé dans un fichier privé
`~/.local/share/nabla-compose/fastapi-litellm/workstation.key`
(mode 0600). En cas de BLOCKED, ne pas
relancer sans un nouveau contrôle de l'alias.

**Ce bloc documente une décision ; aucune clé n'est
générée ni injectée par la modification Git.**
Après émission, transférer la valeur sans l'afficher
dans le champ masqué `LITELLM_FASTAPI_WORKSTATION_API_KEY`
de `nabla/prod/litellm`; la matérialisation
du `.env.secrets` TrueNAS et le redéploiement
restent des étapes distinctes.

## Workstation : credential sans préfixe `sk-`, inventaire non exécuté

**Réception opérateur :**
- `test_fastapi_litellm_workstation_inventory.py` : **9/9 PASS** ;
- `host_context=workstation_verified`,
  conteneur exact `litellm-litellm-1`,
  `proxy_liveliness=http_200`, `key_file_state=absent` ;
- premier diagnostic sans master :
  `alias_state=admin_credential_not_provided` ;
- second diagnostic avec saisie privée :
  `alias_state=admin_credential_unexpected_format`.
  L'ancien code rejetait tout credential ne commençant
  pas par `sk-` **avant** d'effectuer le GET ;
  aucune preuve sur l'alias `fastapi-sample-upstream`
  ou sur les permissions du credential n'était disponible.

**Correctif [skip ci] :**
- Le diagnostic n'impose plus `sk-` à la valeur
  d'entrée ; il refuse toujours les entrées vides,
  trop longues, les caractères de contrôle et
  la duplication de `Bearer `. Seul LiteLLM peut
  valider l'autorisation du credential, via
  `GET /key/list` au proxy loopback attesté
  (aucune génération, aucun secret affiché).
- Pour conclure à une absence, le champ de réponse
  LiteLLM est **`total_count=0`**, et non `total=0`,
  avec `keys=[]` sous un filtre d'alias exact.
  Toute autre réponse vide reste `unverified`.
- Le provisionneur `--apply` utilise désormais
  une preuve **GET admin authentifiée + absence
  exacte de l'alias** dans la base du bon proxy
  AVANT tout POST. Une réponse 401/403, un alias
  existant ou un format de liste inconnu bloque
  la génération ; le seul préfixe ne prouve pas
  une authentification. Les clés non standard
  peuvent être utilisées uniquement si le proxy
  lui-même les accepte en admin.
- Nouveaux tests de transport, de schéma
  `total_count`, d'interdiction de POST si
  l'absence de l'alias n'est pas prouvée.
  **Ils restent à exécuter localement.**

### Contrôle immédiat de l'authentification, sans valeur affichée

Sur Workstation (pas TrueNAS), après mise à jour de
la PR et avec la master **effective du proxy Workstation** :

```bash
git pull --ff-only
python3 -m unittest discover -s tests \
  -p 'test_fastapi_litellm_workstation_inventory.py' -v
python3 -m unittest discover -s tests \
  -p 'test_fastapi_litellm_native_truenas.py' -v
(
  set -e
  set +x
  umask 077
  read -rsp 'Master key LiteLLM Workstation: ' LITELLM_MASTER_KEY
  printf '\n'
  export LITELLM_MASTER_KEY
  just litellm-workstation-fastapi-key-inventory
)
```

Résultats principaux :
`alias_exists` → **ne pas générer de nouvelle clé** ;
`alias_absent_confirmed` → absence prouvée sous
l'identité administrateur interrogée ;
`key_list_http_401` / `key_list_http_403` →
clé saisie non autorisée pour l'inventaire (vérifier
la provenance du secret **Workstation**, sans
réutiliser le mot de passe UI ou la master TrueNAS).
Seuls des statuts expurgés peuvent être publiés.

## Diagnostic post-échec `--apply` sur Workstation (sans nouveau POST)

Nouvelle preuve opérateur : les **6 tests natifs TrueNAS PASS**,
mais `python3 scripts/workstation/provision-fastapi-litellm-keys.py
--target workstation --apply` retourne `BLOCKED:
configuration, transport or secure-storage failure`.
Aucun fichier ni alias en base n'a été attesté.
L'ancienne exception groupée ne permet pas d'attribuer
la cause au secret master, au port, au runtime, aux
permissions ou à la base. Un POST déjà effectué peut
avoir créé une clé orpheline : **ne pas réessayer --apply**
avant l'inventaire.

**Nouveau diagnostic strictement en lecture seule** :
`just litellm-workstation-fastapi-key-inventory`.
Cette commande lit seulement la politique, les
métadonnées du chemin privé, le nom du conteneur
Docker local et l'état HTTP de `/health/liveliness`.
Un `midclt` TrueNAS positif refuse toute connexion
au proxy ; l'identité **exacte et running**
`litellm-litellm-1` est requise sur Workstation.
Aucun POST, aucun modèle, aucun secret imprimé.

Sans `LITELLM_MASTER_KEY` dans l'environnement, le
diagnostic affiche `admin_credential_not_provided`
et **n'interroge pas la liste des clés**. Avec
l'administrateur Workstation fourni dans un sous-shell
privé, le diagnostic effectue un **GET** filtré et
borné `/key/list?key_alias=fastapi-sample-upstream`,
sans afficher le JSON, les hashes ni le credential :

```bash
# Sur la Workstation, utilisateur habituel, checkout PR synchronisé.
git pull --ff-only
python3 -m unittest discover -s tests \
  -p 'test_fastapi_litellm_workstation_inventory.py' -v
just litellm-workstation-fastapi-key-inventory

# Si le proxy local est atteste et fonctionnel et que
# l'inventaire d'alias necessite le privilege admin :
(
  set -e
  set +x
  umask 077
  read -rsp 'Master key LiteLLM Workstation: ' LITELLM_MASTER_KEY
  printf '\n'
  export LITELLM_MASTER_KEY
  just litellm-workstation-fastapi-key-inventory
)
```

Interprétation :

- `host_context=truenas_not_workstation` ou
  `workstation_container_not_attested` : mauvaise
  machine ou conteneur ; **ne pas lancer --apply**.
- `key_file_state=unsafe_directory` : permissions
  ou propriétaire du chemin personnel incorrect ;
  aucune connexion admin n'a été tentée.
- `proxy_liveliness=unreachable` : port
  `127.0.0.1:4000` absent ou inaccessible depuis
  cet hôte ; ce n'est **pas** une preuve de clé incorrecte.
- `alias_state=key_list_http_401` ou `key_list_http_403` :
  autorisation de gestion refusée ; aucune valeur révélée.
- `alias_state=alias_exists` : **stop**, inspecter
  l'alias et restaurer/rotater selon la politique,
  plutôt que de créer une deuxième identité.
- `alias_state=alias_absent_confirmed` : un
  inventaire filtré avec `total=0` a confirmé
  l'absence **dans cette base LiteLLM**.
- `alias_state=alias_unverified_not_confirmed_absent`
  ou `key_list_unverified_schema` : réponse ne
  permettant pas de conclure ; passer par
  l'interface administrateur avant tout POST.

Le diagnostic retourne des métadonnées de sécurité
uniquement ; sa réussite ne valide **ni** la clé
administrateur **ni** le droit de relancer `--apply`.
Après confirmation de l'absence de l'alias, reprendre
le provisionnement Workstation scoped `qwen`.

## Incident `BLOCKED` et emplacement de la vraie clé upstream (réception opérateur)

L'opérateur a exécuté `--target truenas --native-truenas --apply`.
Résultat `BLOCKED: configuration, transport or secure-storage failure`.
L'inventaire de `~/.local/share/nabla-compose` ne comporte
**pas** le répertoire `fastapi-litellm`. Ceci n'atteste
**aucune création** d'une clé de premier saut ni de
`LITELLM_FASTAPI_WORKSTATION_API_KEY` ; une réponse HTTP
ambiguë après création sur le proxy reste possible et impose
un contrôle de l'alias **dans le proxy émetteur**, sans
relancer aveuglément.

Le journal joint montre en parallèle **4 erreurs sur
6 tests natifs** : `TypeError: main() takes 0 positional arguments
but 1 was given`. Corrigé par l'entrée testable
`main(argv=None)` qui passe la liste au parseur, sans
changer la ligne de commande opérateur. **Tests à rejouer**.

### Clé demandée : `LITELLM_FASTAPI_WORKSTATION_API_KEY`

- **Émetteur : LiteLLM Workstation**, non TrueNAS.
- **Alias émetteur :** `fastapi-sample-upstream`.
- **Modèle :** `qwen`.
- **Fichier transitoire créé uniquement après succès** :
  `~/.local/share/nabla-compose/fastapi-litellm/workstation.key`
  **sur la Workstation** (dossier 0700, fichier 0600).
- **Vaultwarden :** `nabla/prod/litellm`, champ masqué
  `LITELLM_FASTAPI_WORKSTATION_API_KEY`.
- **Consommateur :** LiteLLM TrueNAS, fichier
  `/mnt/cpool/secrets/runtime/litellm/.env.secrets`.

Avant de créer la clé, contrôler la liste des **Virtual Keys du
proxy LiteLLM Workstation** (conteneur `litellm-litellm-1`)
et l'absence de l'alias `fastapi-sample-upstream`.
Une absence dans Vaultwarden ou dans le fichier transitoire
ne prouve pas l'absence en base LiteLLM. Si le proxy contient
déjà l'alias, gérer/revoir cette identité, pas de nouveau
`--apply`.

**Sur Workstation uniquement**, après contrôle de l'alias,
saisir la clé **master Workstation** en mémoire dans une
session terminal privée, pas la master TrueNAS :

```bash
(
  set -e
  set +x
  umask 077
  read -rsp 'Master key LiteLLM Workstation: ' LITELLM_MASTER_KEY
  printf '\n'
  export LITELLM_MASTER_KEY
  python3 scripts/workstation/provision-fastapi-litellm-keys.py \
    --target workstation --apply
)
```

Le code appelle la seule API de gestion **loopback
Workstation** `http://127.0.0.1:4000/key/generate`,
avec le scope `qwen`, plafond 8 USD à vie,
5 RPM, 15 000 TPM et une requête parallèle.
Il doit afficher `status=created target=workstation model=qwen`
sans secret. Il ne copie pas automatiquement la clé
dans Vaultwarden ni dans TrueNAS. En cas d'échec HTTP
après une tentative, inspecter l'alias sur le proxy
**avant** de réessayer (risque de clé orpheline).

**Ne jamais utiliser `--native-truenas` pour cette
clé Workstation** : cette option est réservée au
premier saut FastAPI → TrueNAS, pour une clé différente.

## Provisionner la clé **émise par LiteLLM TrueNAS** (mode natif)

**Distinction de sécurité impérative :**
la clé virtuelle émise par **TrueNAS LiteLLM** a pour
alias `fastapi-sample-staging`. Elle authentifie
`FastAPI Sample → TrueNAS LiteLLM`, et doit être
stockée comme `LITELLM_API_KEY` dans l'item Vaultwarden
`nabla/prod/sample-litellm`, puis dans
`/mnt/cpool/secrets/runtime/sample/.env.secrets`.

Elle **NE REMPLACE PAS**
`LITELLM_FASTAPI_WORKSTATION_API_KEY` : ce dernier
credential doit être reconnu par **LiteLLM Workstation**,
car la route TrueNAS `fastapi-qwen` appelle le
`qwen` distant sur `172.17.0.57:4000`.
Créer une clé de ce nom **dans TrueNAS LiteLLM**
ne lui donne pas les droits d'accès au proxy Workstation.
Les deux proxies contrôlent leur propre base de clés.

**Demande opérateur :** créer la clé dans LiteLLM
**TrueNAS**. Le provisionneur existant supporte désormais
`--native-truenas` : il appelle uniquement
`http://127.0.0.1:4000/key/generate` **depuis
TrueNAS après vérification de `midclt`**.
Ce mode refuse `--target workstation` et refuse
tout hôte ne présentant pas l'identité TrueNAS.
Le mécanisme distant par tunnel SSH sur
`127.0.0.1:14000` reste disponible séparément.

**Étape 1 — contrôles locaux, sans clé générée :**

```bash
# Console TrueNAS ; checkout de la PR #289 à jour.
just litellm-workstation-auth-contracts
just litellm-truenas-fastapi-provision-check
```

**Étape 2 — dans l'interface LiteLLM TrueNAS :**
contrôler dans `Virtual Keys` qu'il n'existe
pas déjà d'alias `fastapi-sample-staging`.
La présence ou l'absence de cet alias dans
**Vaultwarden** ne suffit pas à constater
l'existence de la clé dans le proxy.
En cas de clé déjà créée ou d'état de la
base incertain, **ne pas lancer --apply**.

**Étape 3 — génération locale sur TrueNAS :**

La clé master **TrueNAS** est fournie de manière
privée à l'opérateur non root ; elle ne doit
être placée ni en argument CLI, ni dans Git,
ni en clair dans les logs. Exemple dans un
terminal interactif privé, sans `set -x` :

```bash
(
  set -e
  umask 077
  read -rsp 'Master key LiteLLM TrueNAS: ' LITELLM_TRUENAS_MASTER_KEY
  printf '\n'
  export LITELLM_TRUENAS_MASTER_KEY

  python3 scripts/workstation/provision-fastapi-litellm-keys.py \
    --target truenas --native-truenas --apply
)
```

Cette commande exige une authentification administrateur
valide sur le proxy local et une base LiteLLM saine.
Elle crée une clé restreinte à `fastapi-qwen` :
`key_alias=fastapi-sample-staging`,
`max_budget=8 USD` à vie, 5 RPM,
15000 TPM et une requête concurrente.
La valeur est écrite **uniquement** dans
`~/.local/share/nabla-compose/fastapi-litellm/truenas.key`
du compte opérateur TrueNAS, avec mode `0600`.
Aucune valeur n'est imprimée et aucun conteneur
n'est redémarré. Une erreur HTTP ambiguë peut
laisser une clé orpheline créée : inspecter la
liste des clés LiteLLM **avant toute relance**.

**Étape 4 — déploiement distinct, NON automatisé :**
sauvegarder la nouvelle valeur comme champ masqué
`LITELLM_API_KEY` dans `nabla/prod/sample-litellm`
dans le dossier Vaultwarden `TrueNAS`.
Ensuite, vérifier les autres champs déjà présents
et préparer une matérialisation *non destructive*
de `sample/.env.secrets`. Ne pas écraser les
identifiants DB, pfSense, Redis ou autres services
dans ce fichier. Tester les limites de modèles/budget
depuis l'API de gestion avant d'activer le consumer.

**Garde finale :** une clé `fastapi-sample-staging`
créée dans TrueNAS ne rend **pas** la route
`fastapi-qwen` disponible tant que la clé
`LITELLM_FASTAPI_WORKSTATION_API_KEY` manque
sur le second saut TrueNAS → Workstation.

## LiteLLM secret materialization (single item, no master-key reuse)

The canonical Vaultwarden item for TrueNAS LiteLLM is now `nabla/prod/litellm`.
It contains distinct hidden fields for the proxy master/salt, upstream restricted
keys, UI credentials, Langfuse and Redis. This consolidates **storage only**:
FastAPI still authenticates using a dedicated scoped virtual key, never the
master key. Moving the existing `litellm-fastapi-upstream` field into the
consolidated item must preserve its exact value and workstation permissions.

The existing Vaultwarden item is **not** renamed by a Git commit. On the host,
first ensure the destination item exists and every manifest-declared field is
present with the original credential values; do not generate replacement keys.
Then render the complete file using the unprivileged operator session:

```bash
python3 scripts/secrets/materialize_runtime.py --app litellm --install
sudo stat -c '%a %U:%G %n' /mnt/cpool/secrets/runtime/litellm/.env.secrets
```

This materializes a single root-only (0600) env file. The Compose service
now requires it and has **no repo-local .env fallback**. Do not use the old
item name or provision new credentials under it. If the fields have not yet
been moved in Vaultwarden, this deployment intentionally remains unavailable.

## Contrôle ciblé de la clé upstream (réception TrueNAS, 27/10/2026)

**Preuves vérifiées** : TrueNAS version `26.0.0-BETA.2`,
service Docker `litellm` running, champ d'environnement
`LITELLM_FASTAPI_WORKSTATION_API_KEY=absent`. Le fichier
`/mnt/cpool/secrets/runtime/litellm/.env.secrets` est
**présent, régulier, root:root, 0600, 5457 octets**.
Le compteur `awk` des déclarations du nom exact (tolérant
espaces initiaux et `export`) est **zéro**.

La cause de cette absence dans le conteneur est donc
**en amont de Docker** : aucune déclaration de ce nom dans
le fichier canonique. Ces contrôles ne démontrent **pas**
que la clé virtuelle scoped `qwen` existe en Vaultwarden
ou sur Workstation. La route `fastapi-qwen` reste
incomplète ; ne pas substituer la clé IDE ou master.

### Reprise après `ModuleNotFoundError: jsonschema`

Réception opérateur : 39 tests de contrat PASS
(3 OpenRAG + 8 LiteLLM auth + 22 upstream + 6 sources
Vaultwarden), mais le lancement initial
`just litellm-fastapi-upstream-source-check`
avec `python3` a échoué sur
`ModuleNotFoundError: No module named 'jsonschema'`.
**La clé n'a pas été recherchée en Vaultwarden.**
Le dépôt déclare déjà `jsonschema==4.22.0`
dans `pyproject.toml`, groupe `test`.
Cela ne justifie pas la création d'une nouvelle clé.

La recette utilise désormais
`scripts/quality/run-python-with-jsonschema-local.sh`
pour choisir un interpréteur **déjà disponible**
(`NABLA_SECRETS_PYTHON` puis `.venv/bin/python`,
puis les Pythons installés). Aucun package n'est
installé automatiquement. Si aucun n'est prêt, le
diagnostic s'arrête et propose
`uv sync --group test --locked --offline` **uniquement
si les wheels sont déjà dans le cache**, ou de
renseigner `NABLA_SECRETS_PYTHON` avec un environnement
de confiance. L'appel direct avec un interpréteur
dépourvu de `jsonschema` classe l'échec comme
`python_dependency_unavailable` et évite le traceback
(et surtout toute interprétation `field_absent`).
Le nouveau test de ce cas est à exécuter ; aucun
runtime n'a été modifié par cette correction Git.

**Statut de provisionnement : inconnu / probablement
jamais terminé.** `0` déclaration dans le fichier
TrueNAS et l'absence dans le processus confirment un
chaînon manquant, **pas** l'absence de la clé virtuelle
dans la base Workstation. Ne jamais utiliser
`--apply` avant d'avoir contrôlé le fichier de
transit et l'alias dans la base du proxy Workstation.

Sur Workstation, l'inventaire **offline sans
`jsonschema`** peut être exécuté immédiatement :

```bash
python3 scripts/workstation/provision-fastapi-litellm-keys.py \
  --target workstation --check
```

Il n'interroge pas le proxy. Si la copie locale
n'existe pas, rechercher l'alias
`fastapi-sample-upstream` dans l'administration
du proxy Workstation **sans créer de clé
supplémentaire**. Si la copie existe, son état
`already_provisioned` ne garantit ni validité,
ni budget, ni présence en Vaultwarden.

### Prochaine preuve : source Vaultwarden, sans valeurs

Sur TrueNAS, dans la **session de l'opérateur non root**,
avec le client Bitwarden configuré au serveur HTTPS déclaré
et `BW_SESSION` déjà déverrouillée :

```bash
just litellm-fastapi-upstream-source-check
```

La commande utilise `scripts/secrets/check-litellm-fastapi-upstream-source.py`
pour vérifier uniquement le champ caché
`LITELLM_FASTAPI_WORKSTATION_API_KEY` de l'item exact
`nabla/prod/litellm` dans le dossier `TrueNAS`
déclaré au manifeste. Le client valide également l'origine
du serveur et le dossier, sans imprimer le document ni
aucune valeur. Elle ne crée, n'importe, ne matérialise
et ne modifie aucun secret ou service. Le client `bw`
peut actualiser son cache local lors de `sync` ;
cela ne change pas le secret côté serveur.

États `field_state` :
- `field_present_nonempty_hidden` : valeur cachée non vide
  présente **à la source**, mais pas encore injectée ;
- `field_absent`, `field_empty`, `field_duplicate`,
  `field_not_hidden`, `field_invalid_format` :
  corriger d'abord la source, après une revue ciblée ;
- `vaultwarden_session_unavailable`,
  `vaultwarden_unverified`, `manifest_mismatch` :
  un prérequis d'inventaire est manquant ; ne pas
  en déduire l'absence du secret.

Le code de sortie est 0 **uniquement** pour un champ caché
unique et non vide, 2 dans les autres cas.
Il n'atteste ni la validité des permissions de la clé
virtuelle sur Workstation, ni son budget effectif.

Sur **Workstation uniquement**, la vérification offline
de la copie de transit, si nécessaire, est :

```bash
python3 scripts/workstation/provision-fastapi-litellm-keys.py \
  --target workstation --check
```

`status=already_provisioned` prouve uniquement
l'existence et les permissions du fichier local ;
cela n'atteste pas que la clé soit encore valide
dans le proxy. `status=not_provisioned` n'exclut
pas une clé déjà créée dans LiteLLM ou stockée
directement dans Vaultwarden.

**Ne pas exécuter `--apply`, `--install`, redéployer
le proxy ni recopier les secrets manuellement tant que
la source autorisée et les impacts sur le fichier
canonique existant n'ont pas été validés.**

## Gates before deployment

1. **Workstation** : `qwen` exists and accepts a small
   `/v1/chat/completions` request with its dedicated restricted key.
   Wrong model must return 403/400; do not test using a master key.
2. **TrueNAS proxy** : `fastapi-qwen` exists and reaches the upstream
   `qwen` alias. Confirm scoped key cannot request `gpt-4.1`,
   `llama3.2` or fallback. Intentionally break upstream only in a
   safe isolated test, not by disrupting running services.
3. **Budget** : verify both DB connections, `/key/info` shows the
   model list, `max_budget=8`, no reset and enforced spend. Confirm
   nonzero TrueNAS synthetic accounting and 429/403 on a *separate
   tiny-budget disposable test key*, not on the service key.
4. **Secrets** : no key in Git or logs; runtime files 0600, no
   extra proxy-wide admin privileges. Validate `docker compose config`
   without printing raw secrets into the shared session.
5. **Application** : TrueNAS `/run` returns an expected safe
   response via Qwen, supports required function/tool calls and does
   not disclose PII to the workstation. Ensure operator auth before
   exposing `/run` publicly: PR #353 still has a staged
   `OPS_ROUTE_POLICY_STRICT` cutover. Fail closed if key unavailable.
6. **Cloud production** : not connected to LAN. A future
   Cloudflare Access or tunnel route needs its own security design and
   a distinct service token. Do not route the public Cloud app through
   an unauthenticated private HTTP endpoint.

**No actual proxy key, Vaultwarden item or deployment was created from
GitHub.** All runtime checks remain `NOT_RUN` pending authorized LAN access.
