# FastAPI Sample — LiteLLM TrueNAS → workstation Qwen

**État : GitOps préparé, secrets/runtime NON PROVISIONNÉS / NON VALIDÉS.**
Concerne `sample` TrueNAS uniquement, PAS le runtime public de
`fastapi-sample.fastapicloud.dev` (pas de chemin LAN privé prouvé).

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
