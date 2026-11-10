# FastAPI Sample — LiteLLM TrueNAS → workstation Qwen

**État (dernière preuve 28/10/2026) :** clé virtuelle Workstation
`fastapi-sample-upstream` émise (fichier privé `0600` validé) ;
stockage Vaultwarden, injection runtime TrueNAS, clé de premier saut
`fastapi-sample-staging` et chaîne FastAPI **NON VALIDÉS**.
Concerne `sample` TrueNAS uniquement, PAS le runtime public de
`fastapi-sample.fastapicloud.dev` (pas de chemin LAN privé prouvé).

**Ne pas relancer le provisionneur LiteLLM `--apply`**, ni
`materialize_runtime.py --install`, ni redémarrer LiteLLM tant que la
source Vaultwarden, l'alias en base et l'impact sur le fichier runtime
existant ne sont pas prouvés.

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

This **reuses the architecture** of the `workstation-qwen` / `embedding`
routes in `apps/litellm/config.yaml`, not the general-purpose
`LITELLM_IDE_API_KEY`. Key-scoped authorization is required independently
on each proxy: each proxy controls its own key database. Do not use the
LiteLLM **master key** as `LITELLM_API_KEY`.

## Les deux clés : ne jamais les confondre

| | Premier saut | Second saut |
| --- | --- | --- |
| Chemin | FastAPI Sample → LiteLLM TrueNAS | LiteLLM TrueNAS → LiteLLM Workstation |
| Émetteur | **LiteLLM TrueNAS** | **LiteLLM Workstation** (conteneur `litellm-litellm-1`) |
| Alias | `fastapi-sample-staging` | `fastapi-sample-upstream` |
| Modèle autorisé | `fastapi-qwen` | `qwen` |
| Mode du provisionneur | `--target truenas --native-truenas` | `--target workstation` |
| Fichier transitoire (0600, dossier 0700) | `~/.local/share/nabla-compose/fastapi-litellm/truenas.key` (opérateur TrueNAS) | `~/.local/share/nabla-compose/fastapi-litellm/workstation.key` (Workstation) |
| Vaultwarden (dossier `TrueNAS`, champ masqué) | `nabla/prod/sample-litellm` → `LITELLM_API_KEY` | `nabla/prod/litellm` → `LITELLM_FASTAPI_WORKSTATION_API_KEY` |
| Consommateur runtime | `/mnt/cpool/secrets/runtime/sample/.env.secrets` | `/mnt/cpool/secrets/runtime/litellm/.env.secrets` |

Une clé `fastapi-sample-staging` créée dans TrueNAS ne rend **pas** la
route `fastapi-qwen` disponible tant que
`LITELLM_FASTAPI_WORKSTATION_API_KEY` manque sur le second saut.
Créer une clé de ce nom **dans TrueNAS LiteLLM** ne lui donne aucun droit
sur le proxy Workstation. **Ne jamais utiliser `--native-truenas` pour la
clé Workstation.** Ne pas placer la clé upstream dans
`sample/.env.secrets` : le proxy LiteLLM TrueNAS la lit exclusivement
dans `litellm/.env.secrets`.

## Budget demandé : 10 EUR maximum

- Virtual keys use **USD** `max_budget` and need a working **database** to
  enforce spend: each key gets `max_budget=8 USD` **lifetime**
  (`budget_duration=null`), stricter than 10 EUR at ordinary FX rates but
  not an exact EUR guarantee. **Do not add** the two figures: both keys
  meter the same request across two hops.
- `fastapi-qwen` has *synthetic* accounting (`input_cost_per_token=0.000001`,
  `output_cost_per_token=0.000002` USD) so a free on-prem Qwen cannot bypass
  the budget gate; **not a tariff or a bill**. Verify nonzero spend and
  over-budget denial on the installed version.
- Both keys: `rpm_limit=5`, `tpm_limit=15000`, `max_parallel_requests=1`, no
  fallback models (`enforce_fallback_model_access: true`, empty
  `fastapi-qwen` fallback: **test support on the installed version**).
  `store_model_in_db: true` can drift from YAML: audit the effective model list.

## Provisionnement contrôlé

Source of truth: `config/fastapi-sample/litellm-key-policy.json`.
`scripts/workstation/provision-fastapi-litellm-keys.py` defaults to
**offline `--check`** (no network call). It refuses output
overwrite/symlink, writes keys only into operator-owned `0600` files and
never prints them. Do not run it as root.

```bash
python3 scripts/workstation/provision-fastapi-litellm-keys.py --target workstation --check
python3 scripts/workstation/provision-fastapi-litellm-keys.py --target truenas --check
```

`status=already_provisioned` prouve uniquement l'existence et les
permissions du fichier local, pas la validité de la clé dans le proxy ;
`status=not_provisioned` n'exclut pas une clé déjà créée dans LiteLLM ou
stockée directement dans Vaultwarden.

`--apply` (une **seule** tentative, après inventaire de l'alias) :

- refait un `GET /key/list` authentifié et exige l'absence **exacte** de
  l'alias dans la base du proxy émetteur avant tout `POST /key/generate` ;
  401/403, alias existant ou schéma inconnu bloquent la génération ;
- n'impose pas de préfixe `sk-` au credential (seul le proxy valide
  l'autorisation) mais refuse entrées vides, trop longues, caractères de
  contrôle et `Bearer ` dupliqué ;
- affiche seulement `status=created target=<cible> model=<modèle>` ; ne
  copie rien dans Vaultwarden ni dans TrueNAS et ne redémarre rien.

Une erreur HTTP ambiguë peut laisser une **clé orpheline** : inspecter la
liste des Virtual Keys du proxy émetteur **avant toute relance**. Une
absence dans Vaultwarden ou dans le fichier transitoire ne prouve pas
l'absence en base LiteLLM.

### Clé Workstation (second saut)

Sur **Workstation uniquement**, master **Workstation** saisie en mémoire
dans un terminal privé (jamais la master TrueNAS, jamais en argument CLI,
Git, CI ou logs) :

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

Le code appelle uniquement l'API loopback `http://127.0.0.1:4000/key/generate`
de la Workstation (scope `qwen`, 8 USD à vie, 5 RPM, 15 000 TPM, une
requête parallèle). `/key/generate` n'est pas une preuve indépendante du
modèle/budget appliqué : vérifier `/key/info` ou l'UI admin avant cutover.

### Clé TrueNAS (premier saut, mode natif)

`--native-truenas` appelle uniquement `http://127.0.0.1:4000/key/generate`
**depuis TrueNAS après vérification de `midclt`** ; il refuse
`--target workstation` et tout hôte sans identité TrueNAS. Le mode distant
par tunnel SSH (`127.0.0.1:14000` → loopback TrueNAS `:4000`, master dans
`LITELLM_TRUENAS_MASTER_KEY`) reste disponible ; ne jamais faire transiter
la master TrueNAS en HTTP LAN.

1. Contrôles locaux, sans clé générée :

   ```bash
   just litellm-workstation-auth-contracts
   just litellm-truenas-fastapi-provision-check
   ```

2. Dans l'UI LiteLLM TrueNAS (`Virtual Keys`), vérifier l'absence de
   l'alias `fastapi-sample-staging`. Clé existante ou base incertaine :
   **ne pas lancer `--apply`**.
3. Génération, opérateur non root, terminal privé sans `set -x` :

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

4. Déploiement distinct, **non automatisé** : champ masqué `LITELLM_API_KEY`
   de `nabla/prod/sample-litellm`, puis matérialisation *non destructive*
   (voir plus bas). Tester modèles/budget via l'API de gestion avant
   d'activer le consumer.

## Inventaire de l'alias Workstation (lecture seule)

```bash
just litellm-workstation-fastapi-key-inventory

# Inventaire d'alias authentifié (GET filtré, aucun POST) :
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

Lit la politique, les métadonnées du chemin privé, le conteneur Docker
local (identité **exacte et running** `litellm-litellm-1` ; un `midclt`
positif refuse toute connexion) et `/health/liveliness`. Sans
`LITELLM_MASTER_KEY`, il affiche `admin_credential_not_provided` et
n'interroge pas la liste. Avec, il fait un GET borné
`/key/list?key_alias=fastapi-sample-upstream` sans afficher JSON, hashes
ni credential. Seuls des statuts expurgés peuvent être publiés.

- `host_context=truenas_not_workstation` / `workstation_container_not_attested` :
  mauvaise machine ou conteneur ; **ne pas lancer `--apply`**.
- `key_file_state=unsafe_directory` : permissions/propriétaire du chemin
  personnel incorrects ; aucune connexion admin tentée.
- `proxy_liveliness=unreachable` : `127.0.0.1:4000` inaccessible ; **pas**
  une preuve de clé incorrecte.
- `alias_state=key_list_http_401` / `key_list_http_403` : credential non
  autorisé ; vérifier sa provenance **Workstation** (pas le mot de passe UI
  ni la master TrueNAS).
- `alias_state=alias_exists` : **stop**, revoir/rotater cette identité
  plutôt que d'en créer une seconde.
- `alias_state=alias_absent_confirmed` : `total_count=0` et `keys=[]` sous
  filtre d'alias exact (pas `total=0`) ; absence prouvée **dans cette base**.
- `alias_unverified_not_confirmed_absent` / `key_list_unverified_schema` :
  non concluant ; passer par l'UI admin avant tout POST.

La réussite de l'inventaire ne valide ni la clé administrateur ni le
droit de relancer `--apply`.

## Vaultwarden : session, comparaison et source

### Règles de session

- N'imprimer aucun jeton ; ne **pas** publier la sortie brute de
  `bw login`, `bw unlock`, `bw get item`, `bw list items` ou
  `docker inspect`. Aucun `set -x`.
- Une session `BW_SESSION` apparue dans une sortie partagée est
  **compromise** : `unset BW_SESSION`, `bw lock`, `bw logout`, puis dans le
  Web Vault **Deauthorize Sessions / Révoquer les sessions** (peut
  déconnecter d'autres appareils). Fermer le shell ou `unset` seuls ne
  prouvent pas la révocation distante.
- **Une seule connexion** par shell privé ; ne pas exécuter un second
  `bw unlock` sur une session valide. La séparation
  `SESSION="$(bw login --raw)"` puis `export BW_SESSION="$SESSION"` est
  volontaire : `export BW_SESSION="$(...)"` peut masquer un exit code non nul.
- `status=unlocked` ne suffit pas : une lecture réelle du coffre doit
  réussir. En cas d'échec de `bw login --raw` ou `bw list folders`, ne pas
  réessayer en boucle ; relever `bw --version` et la cause du déchiffrement
  avant tout `bw edit`. Ne pas effacer le coffre local ni changer le mot de
  passe à l'aveugle.

```bash
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

  bw list folders >/dev/null
  echo 'vaultwarden_readonly=ok'

  # Comparaison lecture seule ; exit 2 si absent/inconnu.
  just litellm-fastapi-upstream-vaultwarden-compare
)
```

### Comparaison clé locale ↔ champ masqué (Workstation)

`just litellm-fastapi-upstream-vaultwarden-compare` utilise `BitwardenClient`
pour vérifier le serveur HTTPS, l'état de déverrouillage, le dossier
`TrueNAS` et l'item exact `nabla/prod/litellm`, puis compare en mémoire
`workstation.key` au champ masqué `LITELLM_FASTAPI_WORKSTATION_API_KEY`.
Aucune écriture Vaultwarden ; `bw sync` n'actualise que le cache local du
CLI. Pas de mode `--apply`.

| `field_state` | Décision |
| --- | --- |
| `field_matches_private_key` | **DONE source Vaultwarden** : clé locale et champ masqué identiques |
| `field_absent` | **P0 écriture ciblée restante** ; ne pas régénérer la clé |
| `field_mismatch_no_overwrite` | **STOP** ; valeur existante différente, aucune substitution automatique |
| `field_duplicate`, `field_not_hidden`, `field_empty`, `field_unverified_schema` | **STOP** ; résoudre le conflit du coffre, sans impression des valeurs |
| `fresh_session_required`, `vaultwarden_unverified`, `private_key_unavailable` | **NO-GO** ; rétablir le prérequis, aucune interprétation de l'absence du champ |

### Écriture ciblée du champ

Dans l'item existant exact `nabla/prod/litellm` (dossier `TrueNAS`), créer
le champ personnalisé **masqué** `LITELLM_FASTAPI_WORKSTATION_API_KEY`
dont la valeur provient **uniquement** de `workstation.key`. **Ne pas
recréer l'item ni toucher aux autres champs** (master, salt, IDE,
Langfuse, Redis). `bw edit item` renvoie l'item complet et peut écraser
d'autres champs (copie périmée, modification concurrente) : vérifier
l'identité de l'item et du dossier, préserver tous les champs, puis
rejouer le comparateur.

### Contrôle de la source sur TrueNAS (sans valeur)

Opérateur non root, `BW_SESSION` déverrouillée, client configuré sur le
serveur HTTPS déclaré :

```bash
just litellm-fastapi-upstream-source-check
just litellm-fastapi-sample-source-check
```

`scripts/secrets/check-litellm-fastapi-upstream-source.py` ne lit que le
champ caché de l'item exact déclaré au manifeste et ne modifie rien.
Exit 0 **uniquement** pour un champ caché unique et non vide, 2 sinon.

- `field_present_nonempty_hidden` : présent **à la source**, pas encore
  injecté ; n'atteste **pas** l'égalité avec `workstation.key` (le champ est
  `critical: false` au manifeste : les contrôles génériques ne le couvrent pas) ;
- `field_absent`, `field_empty`, `field_duplicate`, `field_not_hidden`,
  `field_invalid_format` : corriger la source après revue ciblée ;
- `vaultwarden_session_unavailable`, `vaultwarden_unverified`,
  `manifest_mismatch`, `python_dependency_unavailable` : prérequis
  manquant ; ne pas en déduire l'absence du secret.

L'interpréteur (avec `jsonschema`) est choisi sans rien installer par
`scripts/quality/run-python-with-jsonschema-local.sh` :
`NABLA_SECRETS_PYTHON`, `.venv/bin/python`, puis Pythons installés. À
défaut, `uv sync --group test --locked --offline` (wheels en cache).

## Matérialisation runtime (item unique, sans réutiliser la master)

The canonical Vaultwarden item for TrueNAS LiteLLM is `nabla/prod/litellm`:
distinct hidden fields for proxy master/salt, upstream restricted keys, UI
credentials, Langfuse and Redis. This consolidates **storage only**:
FastAPI still authenticates with its dedicated scoped virtual key.

```bash
python3 scripts/secrets/materialize_runtime.py --app litellm --install
sudo stat -c '%a %U:%G %n' /mnt/cpool/secrets/runtime/litellm/.env.secrets
```

`--install` **replaces the complete runtime file** (root-only `0600`):
run it only after every manifest-declared field is present with its
original value, the full render has been compared with the current file
and a backup exists. The Compose service requires this file and has **no
repo-local `.env` fallback**: if the fields are not yet in the consolidated
item, the deployment intentionally stays unavailable. Never use the old item
name, generate replacement keys, or substitute the IDE or master key. For `sample`, use
`scripts/secrets/render_from_bitwarden.py` in `--app` mode and **merge**
the new field: never overwrite DB, pfSense, Redis or other credentials in
`sample/.env.secrets`. Remove the transitional key files only after
Vaultwarden and runtime materialization are independently verified.

`docker restart` ne recharge pas les variables d'un conteneur existant :
une recréation contrôlée (avec plan de rollback) est nécessaire après
vérification. `LITELLM_TRUENAS_MASTER_KEY` est une variable du **shell
opérateur** pour l'administration par tunnel : ne pas l'ajouter à
l'env_file du conteneur (privilège élargi, aucun modèle activé).

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

## Historique et leçons

- **27/10** — TrueNAS : `LITELLM_FASTAPI_WORKSTATION_API_KEY=absent` dans
  le conteneur et **0 déclaration** dans `litellm/.env.secrets` : chaînon
  manquant en amont de Docker, **pas** une preuve d'absence de la clé
  virtuelle côté Workstation. Ne jamais substituer la clé IDE ou master.
- **27/10** — `ModuleNotFoundError: jsonschema` sur le contrôle de source :
  la clé n'avait pas été cherchée. D'où le lanceur
  `run-python-with-jsonschema-local.sh` et l'état
  `python_dependency_unavailable` (jamais `field_absent`).
- **27–28/10** — `--apply` → `BLOCKED: configuration, transport or
  secure-storage failure` (TrueNAS natif puis Workstation) sans cause
  attribuable : diagnostic d'inventaire en lecture seule ajouté, preuve
  d'absence d'alias exigée avant tout POST. Le rejet des credentials sans
  préfixe `sk-` bloquait l'inventaire : supprimé. Tests corrigés
  (`main(argv=None)`, mock de `os.getenv` pour l'octet NUL sous Python 3.14).
- **28/10** — alias confirmé absent, puis clé Workstation émise
  (`status=created target=workstation model=qwen`, 12/12 tests, fichier
  `0600`).
- **28/10** — un `bw unlock` interactif a **affiché `BW_SESSION`** dans une
  sortie partagée, puis un second `bw unlock --raw` a échoué
  (`Cryptography error`) avant `bw sync/get/edit` : écriture Vaultwarden
  non attestée. D'où les règles de session ci-dessus et le comparateur
  lecture seule.
- **28/10** — la clé upstream avait été ajoutée à `sample/.env.secrets` :
  mauvais consommateur (voir tableau des deux clés).

**No proxy key, Vaultwarden item or deployment is created from GitHub.**
Runtime checks remain `NOT_RUN` until authorized LAN access.
