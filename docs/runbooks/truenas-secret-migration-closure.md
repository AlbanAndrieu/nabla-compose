# TrueNAS — critères de clôture des migrations de secrets

> État au 25 octobre 2026 : **BLOCKED / NON TERMINÉ**. Les copies canoniques
> cohérentes n'impliquent pas que le secret soit complet, chargé par l'App,
> ni que le fichier legacy puisse être supprimé ou remplacé par un lien.

## Observations de l'opérateur

| Service | Preuve établie | Dette restante |
| --- | --- | --- |
| OpenRAG | Dernier `--strict --scope openrag` : `ready=true`, `missingKeys=[]`, `blockers=[]`, backend/frontend `running+healthy` | Recharge effective et authentification non vérifiées ; migration legacy non finalisée |
| OpenSearch | `legacy_env` corrigé UID=0 GID=568 mode=0640 ; **deux candidats déclaratifs identiques** au mot de passe OpenRAG ; gate PASS | Identifiant effectivement chargé par OpenSearch et son authentification non vérifiés ; chemin encore déclaré dans Compose |
| LiteLLM | Dernier `--strict --scope litellm` : `ready=true`, `missingKeys=[]`, `blockers=[]`, conteneur running | Les clés Langfuse doivent être réelles ; callback/authentification et recharge runtime non testés |
| Scrutiny | Secret canonique examiné et déclaré prêt par le diagnostic global | App STOPPED ; statut runtime séparé, aucune validation de déploiement |
| Autres Apps | Pas de preuve globale récente fournie | Inventaire de clôture complet non attesté |

`bootstrap-repository-env-files.sh --check openrag` a indiqué
`1 staged legacy path(s) remain intact` et **finalize pending**.
Le script n'a pas automatiquement finalisé ce chemin.

## État précis de la première vague — réception opérateur du 26 octobre

Les quatre contrats Backstage P0.3 sont valides ; la migration **runtime**
reste incomplète. Le relevé `--check` montre :

| App | Preuve | Décision |
| --- | --- | --- |
| `scanopy` | Le fichier canonique `runtime/scanopy/.env.secrets` est vide | Retrouver les clés `POSTGRES_PASSWORD` et `SCANOPY_DATABASE_URL` auprès de leur source d'autorité. Ne pas générer une nouvelle chaîne de connexion à l'aveugle. |
| `joplin` | Le fichier source `/mnt/cpool/joplin/.env.secrets` est vide | Récupérer le `POSTGRES_PASSWORD` existant depuis Vaultwarden/la configuration validée. |
| `autokuma` | Le fichier source `/mnt/cpool/autokuma/.env.secrets` est vide | Importer la clé `AUTOKUMA__KUMA__AUTH_TOKEN` provenant de la même instance Uptime Kuma. |
| `code` | Canonique non vide et staged, mais `PASSWORD` manquant ; deux liens legacy non finalisés | Le manifeste mappe `CODE_PASSWORD` vers `PASSWORD`. Vérifier la source de cette ancienne valeur et sa matérialisation par Vaultwarden. Ne pas effacer le fichier canonique actuel sans comparer les sources. |
| `openrag` | Différence sémantique entre `/mnt/cpool/openrag/.env.secrets` et `/mnt/cpool/secrets/runtime/openrag/.env.secrets` | **Bloquer le restage** tant que l'on ne sait pas quelle source est réellement chargée. Les secrets fonctionnels (en particulier `OPENRAG_ENCRYPTION_KEY`) doivent être conservés. |

Le manifeste versionné associe les clés historiques
`SCANOPY_POSTGRES_PASSWORD`, `JOPLIN_POSTGRES_PASSWORD`,
`AUTOKUMA_KUMA_AUTH_TOKEN` et `CODE_PASSWORD` à leurs noms
d'environnement runtime ; ne pas copier un nom de clé legacy tel quel
dans le fichier cible sans appliquer cette transformation.

**Étape 1 — vérifier l'inventaire sans voir les valeurs**, depuis TrueNAS :

```bash
for app in scanopy joplin autokuma code openrag; do
  sudo bash scripts/truenas/inventory-runtime-env-files.sh "$app"
done
```

**Étape 2 — comparer OpenRAG** sur l'hôte autorisé. Le comparateur
n'affiche aucune valeur : uniquement les noms des variables et le nombre
de différences. Les noms de variables ne sont pas des credentials, mais
ils peuvent renseigner sur l'architecture ; conserver la sortie en privé.

```bash
sudo python3 scripts/secrets/compare_dotenv_sources.py \
  --app openrag \
  --left /mnt/cpool/openrag/.env.secrets \
  --right /mnt/cpool/secrets/runtime/openrag/.env.secrets
```

**Étape 3 — matérialiser depuis Vaultwarden**, uniquement quand l'élément
existant et la provenance ont été contrôlés. Lancer comme utilisateur
normal disposant d'une session `bw` déverrouillée, pas avec `sudo` :

```bash
python3 scripts/secrets/materialize_runtime.py --app scanopy --verify
```

`--verify` est une **comparaison non mutante**. S'il échoue parce que
la cible est vide ou absente, cela ne justifie pas une rotation.
`--install` remplace le fichier canonique : exécuter une seule
application après sauvegarde privée, contrôle du rendu Vaultwarden et
accord explicite. **Ne pas automatiser les quatre installations dans
une boucle.** Le chargeur ne garantit pas un reload automatique du
conteneur : l'acceptation runtime est distincte.

**Étape 4 — Sentry accepté au niveau diagnostic** : le dernier
`recover-sentry-deploying.sh --check` confirme les credentials
système, Relay, ClickHouse runtime et migrator, puis
`diagnose-sentry: exit=0 ok=14 failed=0 warnings=0`.
Le `FAIL` de la session historique est obsolète. Le smoke
`scripts/truenas/smoke-sentry-event.sh` reste le gate d'ingestion E2E.

**Étape 5 — DefectDojo** : la workstation confirme
`http=200 redirects=1 tls=0` avec `curl --location`. Le transport
HTTPS privé et le chargement de la page sont acceptés ; la connexion
authentifiée n'est pas testée.

## Code — déplacement manuel du mot de passe (26 octobre, réception opérateur)

**Contrôles réussis :** tests `test_compare_dotenv_sources.py` et
`test_secrets_renderer.py` **27/27 PASS** sur TrueNAS. Le dry-run historique
`--app code --input /mnt/cpool/code/.env` a rendu `mapped=1/1` **avant**
que l'opérateur retire `CODE_PASSWORD` de cet ancien fichier.

**Changement manuel annoncé ensuite :** suppression de `CODE_PASSWORD`
dans `/mnt/cpool/code/.env`, puis édition de
`/mnt/cpool/secrets/runtime/code/.env.secrets`. Le contenu précis de la
nouvelle clé, les droits du fichier et l'identité runtime chargée
**ne sont pas encore vérifiés**.

La chaîne LinuxServer code-server attend **`PASSWORD`**, et non
`CODE_PASSWORD`, dans le `env_file` canonique
(`apps/code/compose.yml`). Le manifeste Vaultwarden conserve
`importEnv=CODE_PASSWORD` et `env=PASSWORD`, pour accepter un
fichier legacy comme un fichier canonique sans changer la valeur.

1. Valider le contrat `PASSWORD` sur TrueNAS (aucune valeur imprimée) :

   ```bash
   sudo bash scripts/truenas/accept-runtime-env-first-wave.sh --check code
   sudo stat -Lc 'uid=%u gid=%g mode=%a size=%s' \
     /mnt/cpool/secrets/runtime/code/.env.secrets
   ```

   Le fichier de secret canonique doit être `root:root`, mode `0600`.
   Une écriture avec `nano` ne garantit pas à elle seule les droits
   attendus. Éviter `cat`, `grep PASSWORD` non borné et
   `docker inspect` contenant l'environnement.

2. Refaire le dry-run **sur le nouveau fichier**, sans `--apply`
   et sans `sudo` devant le Python utilisateur :

   ```bash
   "$HOME/.cache/nabla-compose/dev-venv/bin/python" \
     scripts/secrets/import_dotenv_to_bitwarden.py \
     --app code \
     --input /mnt/cpool/secrets/runtime/code/.env.secrets
   ```

   Le résultat attendu est `mapped=1/1`. Le parser accepte
   `PASSWORD` ou `CODE_PASSWORD`, mais refusera des valeurs
   contradictoires si les deux clés sont présentes.

3. Le coffre n'a pas encore l'élément exact `nabla/prod/code` dans
   le dossier TrueNAS ; le dernier `materialize_runtime.py --verify`
   a échoué sur `found 0`. **Ne pas lancer un nouvel
   `--verify` comme preuve d'installation tant que cet item est absent.**
   Après revue de la source exacte, import individuel explicite
   `--apply` via le même importeur : crée l'élément dans Vaultwarden,
   mais ne remplace pas automatiquement les fichiers runtime.

4. Le fichier modifié manuellement ne porte probablement pas encore
   l'en-tête `Generated from Vaultwarden` requis par le gate
   `accept-runtime-env-first-wave.sh --accept code`. Une fois
   l'import validé et une sauvegarde privée disponible, utiliser le
   renderer Vaultwarden et accepter le service séparément.
   **Pas de finalisation, redéploiement ni rotation automatique.**

## Réception complémentaire — comparaison OpenRAG et coffre Code (26 octobre)

**OpenRAG :** le comparateur exécuté avec le venv TrueNAS confirme
`left=2`, `right=4`, `differentValue=0` et `onlyLeft=0`.
Les deux fichiers ont les mêmes valeurs pour `LANGFLOW_KEY` et
`OPENSEARCH_PASSWORD`. Le fichier canonique contient **en plus**
`LITELLM_IDE_API_KEY` et `OPENRAG_ENCRYPTION_KEY`.
Ce n'est **pas une rotation ni un désaccord sur les valeurs communes**.
Le comparateur annonce désormais `relationship=right_has_additional_keys`,
mais garde son **exit code 1** : avant finalisation, il faut vérifier le
chargement et l'authentification runtime des secrets supplémentaires.
**Ne pas restage OpenRAG** : cela ferait perdre les clés supplémentaires.
Ne pas régénérer la clé de chiffrement.

**Code :** `materialize_runtime.py --app code --verify` a réussi la
validation du manifeste, puis Vaultwarden n'a pas trouvé l'entrée exacte
`nabla/prod/code` dans le dossier `TrueNAS` (`found 0`).
Ne pas interpréter ce résultat comme un mot de passe invalide ou perdu.
Un dry-run de l'importeur peut vérifier la présence de `CODE_PASSWORD`
ou `PASSWORD` dans un ancien fichier, sans afficher sa valeur :

```bash
cd /mnt/cpool/compose/nabla-compose
"$HOME/.cache/nabla-compose/dev-venv/bin/python" \
  scripts/secrets/import_dotenv_to_bitwarden.py \
  --app code --input /mnt/cpool/code/.env
```

Il est aussi possible d'examiner explicitement
`/mnt/cpool/code/.env.secrets` si c'est la source réelle. **Le dry-run
ne crée aucun élément dans Vaultwarden** ; `mapped=1/1` signifie
uniquement que la clé requise a été trouvée. Si les deux fichiers sont
vides ou incomplets, rechercher la source d'autorité dans une sauvegarde
ou une configuration runtime existante, sans inventer une valeur.
Quand une source récupérée et sa provenance ont été vérifiées,
l'importeur permet un `--apply` *ciblé* pour créer l'élément exact.
Ne pas l'exécuter avant revue, et ne pas générer `CODE_PASSWORD`.

Après la création de l'élément exact, reprendre le test
`materialize_runtime.py --app code --verify` (non mutatif).
Si le coffre diffère du fichier canonique, comparer les sources puis
planifier une installation ponctuelle séparée, avec rollback.

**Tests ciblés opérateur :** `test_secret_materialization_contract.py`
8/8 PASS et `test_openrag_secret_migration_metadata.py` 4/4 PASS ;
`bash -n` des deux scripts TrueNAS PASS. Ces tests ne prouvent pas
l'authentification ni la création d'un élément Vaultwarden.

## Diagnostic des sources d'import et des dépendances Python (26 octobre)

Le manifeste contenait trois collisions d'`importEnv` :
`OPENSEARCH_PASSWORD` (OpenRAG/OpenSearch),
`LITELLM_IDE_API_KEY` (OpenRAG/LiteLLM) et
`OPENAI_API_KEY` (Karakeep/LiteLLM). La validation les rejetait
**avant toute connexion Vaultwarden**. Les imports sont maintenant
namespacés pour le consommateur : `OPENRAG_OPENSEARCH_PASSWORD`,
`OPENRAG_LITELLM_IDE_API_KEY` et `KARAKEEP_OPENAI_API_KEY`.
Les clés runtime `OPENSEARCH_PASSWORD`, `LITELLM_IDE_API_KEY`
et `KARAKEEP_OPENAI_API_KEY` **ne changent pas** ; aucune valeur ni
secret n'est régénéré. Les procédures qui exportent les variables
d'import devront utiliser ces nouveaux noms, à partir des valeurs
existantes dans le coffre.

Les sources d'import sont une frontière de sécurité : ne pas assouplir
la règle globale d'unicité, notamment entre Karakeep et LiteLLM.

Le comparateur `compare_dotenv_sources.py` utilise
`python-dotenv` + `jsonschema`. Sur TrueNAS, utiliser le Python du
venv de l'opérateur **sans `sudo`** ; son lecteur élève uniquement
la lecture des fichiers privés et ne transmet pas `BW_SESSION`
au processus `sudo`. Ne pas exécuter un interpréteur installé
dans `$HOME` avec des privilèges root :

```bash
cd /mnt/cpool/compose/nabla-compose
"$HOME/.cache/nabla-compose/dev-venv/bin/python" \
  scripts/secrets/compare_dotenv_sources.py \
  --app openrag \
  --left /mnt/cpool/openrag/.env.secrets \
  --right /mnt/cpool/secrets/runtime/openrag/.env.secrets
```

Si le venv n'existe pas, installer les outils en espace utilisateur
avec `bash scripts/truenas/bootstrap-dev-tools.sh` (sans `sudo`).
**Correction du runner :** `bootstrap-repository-env-files.sh`
distingue désormais le résultat du comparateur : `0` = égalité
sémantique, `1` = différences confirmées, `2` = comparaison
impossible / dépendances Python manquantes. Dans le dernier cas, le
script s'arrête sans mutation avec `BLOCKED` et **ne déclare plus
un conflit de valeurs non prouvé**. Le FAIL historique peut être
dû à l'environnement Python. Comparer les deux fichiers depuis
le venv opérateur avant tout `--restage openrag`.

Le répertoire `apps/scanopy/` ne contient pas de `.env.secrets`,
conformément à la politique : les credentials ne sont pas stockés dans Git.
Le chemin Compose à examiner est
`/mnt/cpool/secrets/runtime/scanopy/.env.secrets`.

## Procédure d'inspection sans afficher les secrets

Sur TrueNAS, exécuter les étapes séparément depuis la révision revue :

```bash
sudo bash scripts/truenas/bootstrap-repository-runtime.sh --check
sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check
sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check openrag
sudo python3 scripts/truenas/diagnose-ai-secret-recovery.py --check --strict --scope openrag
sudo bash scripts/truenas/reconcile-openrag-opensearch-secret.sh --check
```

Le mode `--scope openrag` est disponible dans la PR #280 ;
ne pas l'utiliser avec une version antérieure du script.

Lorsque le comparateur indique `source=canonical_env`,
`canonical_secret`, `legacy_env` ou `operator_selected`, examiner
**uniquement les métadonnées du fichier correspondant** :

```bash
for path in \
  /mnt/cpool/secrets/runtime/opensearch/.env \
  /mnt/cpool/secrets/runtime/opensearch/.env.secrets \
  /mnt/cpool/compose/nabla-compose/apps/opensearch/.env
do
  if sudo test -e "$path"; then
    sudo stat -Lc 'path=%n uid=%u gid=%g mode=%a type=%F' -- "$path"
  fi
done
```

Le comparateur attend **uid 0** et mode **0600, 0400 ou 0640**
sur un fichier régulier. Il refuse le candidat non conforme
sans afficher `OPENSEARCH_PASSWORD`. Ne pas lancer un `chmod -R`
ni changer le propriétaire de tous les fichiers. Une correction
ciblée exige d'identifier la source d'autorité et ses ACL ZFS.

## OpenRAG / LiteLLM — dernières clés et chemins (25 octobre)

Les dernières exécutions `--scope openrag` et `--scope litellm`
confirment désormais des secrets **`ready=true`**, sans clé absente ni
blocage déclaré. `OPENRAG_ENCRYPTION_KEY` est donc présente et de format
accepté par le validateur. **Ne pas la régénérer.** La validation
syntaxique ne prouve pas que les conteneurs ont rechargé ces valeurs ni
que les identifiants Langfuse/API fonctionnent.

`OPENRAG_ENCRYPTION_KEY` est une **clé maître AES-256-GCM de 32 octets
encodés en Base64**. **La retrouver d'abord** dans la configuration
initiale, Vaultwarden ou la sauvegarde OpenRAG existante. Une nouvelle
clé ne déchiffre pas les credentials/index antérieurement chiffrés ;
ne pas la régénérer si elle a déjà servi.

Si le déploiement n'a **jamais** persisté de données chiffrées avec
une autre clé, générer une seule clé avec la bibliothèque standard :

```bash
python3 -c 'import base64,secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())'
```

Copier immédiatement cette valeur dans Vaultwarden, puis dans
`/mnt/cpool/secrets/runtime/openrag/.env.secrets` via `sudo nano`
sans guillemet déséquilibré. Ne pas coller la clé dans des tickets,
logs ou discussions. Le script de diagnostic vérifie maintenant
**le format Base64/32 octets**, sans divulguer le contenu.

**Attention au chemin LiteLLM.** Le vrai `env_file` Compose est
`/mnt/cpool/secrets/runtime/litellm/.env.secrets` ; un fichier nommé
`/mnt/cpool/secrets/runtime/openrag/litellm/.env.secrets` n'est pas
chargé automatiquement. Préserver les clés déjà présentes dans le
fichier canonique LiteLLM et y fusionner les clés de consommateurs
manquantes, sans remplacer `LITELLM_MASTER_KEY` ni `LITELLM_SALT_KEY`.

**Langfuse : oui, compléter `LANGFUSE_SECRET_KEY` ET
`LANGFUSE_PUBLIC_KEY` dans le fichier LiteLLM canonique.** Les deux
doivent provenir du **même projet Langfuse** (`sk-lf-...` /
`pk-lf-...`), sans confusion avec les secrets du serveur Langfuse,
`NEXTAUTH_SECRET`, ni avec `OPENRAG_ENCRYPTION_KEY`. Ne pas
inventer de valeur. Le runtime Compose LiteLLM doit être réconcilié
pour charger un env_file modifié. Les tests de diagnostics n'affichent
pas les valeurs.

Vérifier aussi l'entrée dotenv `LITELLM_N8N_API_KEY` : le guillemet
fermant isolé de l'exemple est invalide et doit être corrigé.
Le diagnostic signale désormais les **guillemets déséquilibrés**
sans afficher la clé.

```bash
sudo python3 scripts/truenas/diagnose-ai-secret-recovery.py --check --strict --scope openrag
sudo python3 scripts/truenas/diagnose-ai-secret-recovery.py --check --strict --scope litellm
sudo bash scripts/truenas/reconcile-openrag-opensearch-secret.sh --check
```

La dernière erreur OpenSearch porte sur **`source=legacy_env`** :
`/mnt/cpool/compose/nabla-compose/apps/opensearch/.env`.
Vérifier seulement ses métadonnées ; si le fichier est encore source
d'autorité active, ne pas le remplacer sans valider la configuration
stockée TrueNAS. Les modes admis par le comparateur sont `0600`,
`0400` ou `0640`, propriétaire root. Ne pas changer les permissions
de tous les secrets par un `chmod -R`.

## Correction bornée du fichier OpenSearch encore utilisé

Le Compose `apps/opensearch/compose.yml` référence explicitement
`/mnt/cpool/compose/nabla-compose/apps/opensearch/.env` via `env_file`.
Le relevé **avant correction** donnait `uid=1000 gid=568 mode=0644` ; **après correction** l'opérateur confirme `uid=0 gid=568 mode=0640`, avec comparaison du credential PASS.
Le comparateur exige un propriétaire root et un mode privé `0600`,
`0400` ou `0640`. C'est une **erreur de métadonnées**, pas encore une
preuve de divergence des mots de passe.

Exécuter sur TrueNAS après revue du chemin et vérification qu'il ne
s'agit pas d'un lien symbolique :

```bash
FILE=/mnt/cpool/compose/nabla-compose/apps/opensearch/.env
sudo test -f "$FILE" && ! sudo test -L "$FILE" || {
  echo 'BLOCKED: fichier absent ou symlink'; false;
}
sudo stat -c 'uid=%u gid=%g mode=%a type=%F' -- "$FILE"
```

Pour corriger **ce seul fichier**, conserver le GID 568 :

```bash
sudo chown 0:568 -- /mnt/cpool/compose/nabla-compose/apps/opensearch/.env
sudo chmod 0640 -- /mnt/cpool/compose/nabla-compose/apps/opensearch/.env
sudo bash scripts/truenas/reconcile-openrag-opensearch-secret.sh --check
```

Aucun mot de passe n'est modifié. Aucun `app.redeploy` n'est lancé.
Si le comparateur découvre ensuite une divergence, **arrêter** :
ne pas synchroniser ou renouveler automatiquement `OPENSEARCH_PASSWORD`.
Vérifier le projet Git ignoré, le Compose effectivement chargé par TrueNAS,
la source Vaultwarden et les données OpenSearch existantes. La configuration
Compose actuellement versionnée pointe toujours sur le chemin legacy ;
ne pas supprimer, renommer ou finaliser ce fichier sans migration dédiée.

> **Ne pas rejouer le `chown`/`chmod` lorsque le contrôle est déjà PASS.**
> Le mode `0640` et l'égalité de deux valeurs déclarées sont acquis ;
> seule la preuve du credential chargé et de l'authentification manque.
> Ne pas finaliser les chemins hérités sur cette seule base.

## Gates obligatoires avant `--finalize openrag`

1. Restaurer les **identifiants existants** depuis leur source
   d'autorité, sans les régénérer ni afficher leurs valeurs.
2. Vérifier les quatre noms de clés OpenRAG requis et les deux
   clés LiteLLM absentes du dernier diagnostic.
3. Vérifier l'égalité du mot de passe OpenSearch après correction
   des métadonnées de fichier. La comparaison n'atteste pas
   automatiquement l'identifiant effectivement chargé par OpenSearch.
4. Examiner la configuration Custom App TrueNAS effective et son
   `env_file`, sans l'afficher publiquement.
5. Confirmer qu'une réconciliation ciblée et sauvegardée est réversible.
6. Confirmer une connexion authentifiée et un smoke fonctionnel
   OpenRAG/LiteLLM/OpenSearch.
7. Seulement après acceptation runtime, envisager
   `bootstrap-repository-env-files.sh --finalize openrag` avec revue
   explicite, puis refaire tous les contrôles.

**Interdictions :** rotation automatique `OPENSEARCH_PASSWORD`,
suppression de fichiers legacy avant acceptation, copie de dotenv
dans Git, redéploiement de masse, réindexation de `cpool/bababou`
et confusion entre transport HTTP 401 et auth validée.

[Roadmap](../roadmap.md) ·
[Relevé du 25 octobre](2026-10-25-critical-acceptance-followup.md) ·
[Runbook migration](truenas-migration-operator.md).
