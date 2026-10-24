# OpenClaw — préflight sécurisé du plan LiteLLM cron (v2026.9.5)

## Preuves Workstation du 24 octobre 2026

- Audit strict : 16 occurrences en clair (config=5, dotenv=3,
  SQLite=5, modèles générés=3), et deux fichiers auth hérités.
- SQLite : main=0, cron=1, other_or_shared=4. Le magasin de secrets
  « team » ne contient aucune entrée ; le magasin **auth** partagé
  contient quatre credentials en clair. Ces magasins sont distincts.
- La configuration interactive de `profiles.litellm:default.key` pour
  `cron` a produit un plan avec targets=1, providerUpserts=0,
  providerDeletes=0, warnings=0. L'opérateur a répondu **No**.
- Le dry-run natif annonçait deux fichiers modifiés.
- Le diagnostic local (12/12 tests) a identifié précisément :
  cron_auth_sqlite=1, dotenv=1, other=0, refs_checked=1,
  skipped_exec_refs=0, warnings=0, resolvability_complete=true.
- Aucune migration appliquée ; aucune preuve que la variable restera
  accessible dans l'environnement du service Gateway après redémarrage.

## Diagnostic en lecture seule

Exécuter depuis le checkout Git de la PR #274 sur la Workstation :

```bash
just openclaw-cron-secret-plan-test
just openclaw-cron-secret-plan-check
```

Alternativement :

```bash
python3 -m unittest discover -s tests -p 'test_openclaw_secrets_plan_diagnostic.py' -v
python3 scripts/workstation/diagnose-openclaw-secrets-plan.py
```

Le diagnostic utilise **uniquement** un plan privé dans
`~/.local/share/nabla-compose/openclaw-import/cron-plan.json` et
le mode natif `openclaw secrets apply --from ... --dry-run --json`.
Les chemins, valeurs, identifiants et sorties natives restent cachés.
Le script impose dossier 0700 et fichier 0600, refuse symlink/hardlink,
tailles inattendues, modification concurrente, mauvais agent,
mauvaise cible, mauvaise source et modification de fournisseur.

La cible attendue est `profiles.litellm:default.key`,
type natif `auth-profiles.api_key.key`, agent `cron`, référence
`env:default:LITELLM_OPENCLAW_CRON_API_KEY`. Les clés main et embeddings,
dont la clé fichier `openclaw-embeddings.key`, restent isolées.

## Comparaison native optionnelle — aucun secret appliqué

L'exécution précédente de `just openclaw-cron-secret-plan-check` sur
Workstation a réussi les **12 tests**, puis s'est arrêtée avec le code
`2`. C'est le comportement **attendu** : `blocked_dotenv_scrub_risk`
correspond au second fichier `.env` projeté et non à une erreur Python.

Pour qualifier ce deuxième fichier sans afficher le plan ou les secrets :

```bash
just openclaw-cron-secret-plan-test
just openclaw-cron-secret-plan-compare
```

Cette nouvelle recette effectue **deux dry-runs natifs** :
le plan d'origine, puis une copie JSON temporaire privée `0600` avec
uniquement `options.scrubEnv=false`. Elle détruit la copie en fin de
comparaison. Aucun plan existant ni runtime OpenClaw n'est modifié.
Le second dry-run peut afficher seulement les compteurs
`secret_plan_no_scrub_changed_dotenv` et
`secret_plan_no_scrub_changed_total`.

Si la sortie contient
`secret_plan_scrub_comparison=dotenv_projection_attributed_to_scrub`,
cela prouve uniquement que **l'option de nettoyage explique le changement
de catégorie `.env`**. Elle ne prouve ni le nom de la variable supprimée,
ni la disponibilité persistante des clés du Gateway, ni l'absence
d'impact sur les autres services. L'état du plan original reste
`blocked_dotenv_scrub_risk` et
`secret_plan_apply_authorized=false` : le code de sortie `2`
demeure intentionnel. Aucune option `--apply` n'est fournie.

## Renforcement du diagnostic — preuves opérateur et intégrité

**Résultat observé sur la Workstation (24 octobre 2026)** :
`just openclaw-cron-secret-plan-test` a exécuté **15/15 tests OK**.
`just openclaw-cron-secret-plan-compare` confirme
`dotenv_projection_attributed_to_scrub`, avec **une SQLite cron**
et **zéro .env** projetés lorsque `scrubEnv=false`. Le plan original
reste **bloqué** et la commande retourne intentionnellement `2`.

La PR #274 renforce ensuite le diagnostic avec trois protections :

- Le premier dry-run lit désormais une **copie temporaire 0600**
  des octets déjà contrôlés du plan. Le CLI n'ouvre donc pas un fichier
  original susceptible d'être remplacé entre validation et appel natif.
- Le comparateur vérifie l'identité des fichiers projetés (HMAC
  en mémoire, clé aléatoire par exécution) pour toutes les catégories
  hors dotenv. Deux fichiers différents classés `cron_auth_sqlite`
  ne sont plus considérés identiques.
- Un changement du plan original pendant l'analyse renvoie
  `blocked_concurrent_plan_change`. Même sans modification dotenv,
  l'environnement Gateway n'étant pas attesté, le diagnostic
  retourne **2**, jamais 0.

Trois tests supplémentaires ont été ajoutés à ce contrat : **18 tests
déclarés**, encore à exécuter sur la Workstation au HEAD de la PR.

```bash
just openclaw-cron-secret-plan-test
just openclaw-cron-secret-plan-compare
```

Un `exit code 2` est attendu pour la seconde commande : il ne signifie
pas que la suite de tests a échoué.

**Source OpenClaw 2026.9.5 vérifiée** :
`src/secrets/apply.ts` n'efface pas arbitrairement tous les noms du
dotenv. Le nettoyage compare les valeurs de credentials migrés avec les
affectations dont le nom figure dans
`listKnownSecretEnvVarNames()` (`src/secrets/provider-env-vars.ts`).
Cette liste peut dépendre des providers/plugins. Le diagnostic prouve
la disparition de la **catégorie** dotenv, mais ne prouve toujours pas
quelle affectation serait retirée ni si elle est nécessaire au Gateway.
Ne pas inférer que la variable `LITELLM_OPENCLAW_CRON_API_KEY` serait
supprimée sur la seule base de ce compteur.

## Provenance limitée de la clé cron — 24 octobre 2026 (code, non exécuté sur Workstation)

Les 18/18 tests du précédent lot ont **PASS** sur la Workstation.
La comparaison native y confirme que `scrubEnv` explique **exactement**
le deuxième fichier projeté (`cron SQLite=1`, `.env=1` initial,
puis `.env=0` avec un plan temporaire `scrubEnv=false`).

La PR #274 ajoute une vérification **en lecture seule**, sans valeurs,
des sources possibles de `LITELLM_OPENCLAW_CRON_API_KEY` :

```bash
just openclaw-cron-secret-plan-test
just openclaw-cron-secret-plan-provenance
```

La recette `provenance` produit les champs suivants, avec une valeur
expurgée :

- `secret_plan_cron_key_in_projected_dotenv=present|absent|duplicate|unsafe_permissions|unavailable|not_single_dotenv`.
  Il s'agit **uniquement de la présence du nom de la variable** dans
  le fichier .env effectivement projeté par OpenClaw. `present`
  **ne prouve pas** que cette ligne est celle qu'OpenClaw supprimerait.
  `unsafe_permissions` indique que le diagnostic a refusé de lire
  un dotenv trop accessible ; ne pas assouplir les permissions par
  commodité.
- `secret_plan_gateway_initial_env_cron_key=present_in_initial_process_env|not_in_initial_process_env|not_running|unavailable`.
  Le script interroge `MainPID` du seul service utilisateur
  `openclaw-gateway.service` et lit **en mémoire** son environnement
  initial sous `/proc/<pid>/environ`, après contrôle du propriétaire.
  Aucun PID, chemin, nom de compte ou valeur n'est imprimé.
  Une variable chargée *après* le lancement peut ne pas apparaître
  dans cet environnement initial.
- `secret_plan_gateway_restart_persistence=unverified` et
  `secret_plan_gateway_env_attested=false` restent toujours affichés.
  Le processus courant ne prouve pas qu'une source survivra à un
  redémarrage. Un mécanisme systemd `EnvironmentFile`, un autre
  magasin de secrets ou un chargement à l'exécution doit être
  vérifié séparément et **en privé** avant autorisation.

Ces nouveaux contrôles ne font **aucun** appel LiteLLM, n'exportent
aucun environnement, ne modifient pas le plan, ne redémarrent pas
le Gateway et ne lancent aucune opération d'écriture OpenClaw.
Le code de sortie **2 reste intentionnel** même si le nom de la clé
existe dans les deux emplacements. Ne jamais recopier la sortie
native JSON, le contenu .env ou `/proc/<pid>/environ`.

La nouvelle suite contient **18 tests du plan + 7 tests
de provenance = 25 cas déclarés**. Ils restent **à confirmer sur la
Workstation**, les 18 tests précédents étant les derniers
effectivement exécutés par l'opérateur.

## Identités et stratégie de remplacement — retour Workstation 25/25

**Preuve confirmée :** les 18 tests de plan et les 7 tests de provenance
passent sur la Workstation (25/25). Le plan natif original vise uniquement
`profiles.litellm:default.key` pour `cron`, avec la SecretRef
`env:default:LITELLM_OPENCLAW_CRON_API_KEY`. Le dry-run projette
**SQLite cron=1, dotenv=1**. La variante de comparaison
`scrubEnv=false` projette **SQLite cron=1, dotenv=0**.

`secret_plan_cron_key_in_projected_dotenv=present` signifie seulement
que **le nom de la variable figure dans le dotenv concerné**.
`secret_plan_gateway_initial_env_cron_key=not_in_initial_process_env`
signifie que ce nom ne figure pas dans l'environnement initial visible
via /proc. **Cela ne prouve pas que la variable est absente dans le
processus Node.js après son chargement du dotenv.**

En effet, le code OpenClaw **v2026.9.5** :
- `src/infra/dotenv.ts` charge le dotenv du répertoire de travail
  et les fichiers dotenv globaux, sans écraser les variables déjà présentes ;
- `src/infra/dotenv-global.ts` inclut `OPENCLAW_STATE_DIR/.env`
  (ou le state dir par défaut), puis une possibilité de
  `~/.config/openclaw/gateway.env` selon le state dir ;
- `src/secrets/resolve.ts` résout une SecretRef `env`
  à partir de l'environnement effectif fourni au résolveur ;
- `src/secrets/apply.ts` peut nettoyer un dotenv lorsque sa valeur
  correspond à un credential migré **et** que son nom appartient
  à la liste `listKnownSecretEnvVarNames()`. Le compteur ne
  permet pas d'identifier sans ambiguïté l'affectation supprimée.

### Choix de migration, jamais appliqués automatiquement

1. **P0 `cron` — option transitoire :** préparer un **nouveau plan
   privé** avec seulement `options.scrubEnv=false`, puis vérifier
   `--dry-run` et la persistance de la source. Une migration
   approuvée pourrait retirer le doublon du SQLite, **mais garderait
   les valeurs en clair du dotenv**. Ce n'est pas la fin de l'audit.
2. **P0 `cron` — cible durable privilégiée :** créer un fichier de
   clé distinct, protégé en `0600`, dans un répertoire `0700`,
   accessible au même compte que le Gateway ; configurer
   `secrets.providers.openclaw-cron` avec
   `{"source":"file","path":"<chemin absolu privé>","mode":"singleValue"}`.
   La ref cible devient
   `{"source":"file","provider":"openclaw-cron","id":"value"}`.
   Préparer ce fichier par import privé avec accord opérateur
   (jamais de clé en argv, log, Git ni sortie stdout).
   L'existant `openclaw-embeddings.key` ne doit jamais être réutilisé.
3. **P1 `main` :** même modèle avec fichier, fournisseur et plan
   distincts ; vérifier d'abord son identité de credential et la
   résolution dans le Gateway, sans réutiliser la clé `cron`.
4. **P1 autres résidus :** audit séparé des quatre credentials du
   *magasin d'authentification partagé*, des cinq occurrences en
   configuration, des trois occurrences dotenv, des trois credentials
   matérialisés en `models.json` et des deux fichiers legacy.
   Les chiffres décrivent des **occurrences**, pas nécessairement
   autant de clés uniques. Le wizard `--agent cron` ne migre pas
   le magasin partagé. Aucune suppression de legacy ni
   `doctor --fix` avant acceptation.

Avant toute mutation, établir en privé le chemin dotenv canonique
réel, la valeur **par identité et non par affichage**, les consommateurs
et l'origine persistante du Gateway. Le contrôle `--dry-run` ne
prouve pas qu'un redémarrage fonctionnerait. Pas d'application réelle
ni de restart sans validation et accord séparé.

## Cutover rapide autorisé — clé cron vers fournisseur `file`

**Décision opérateur du 24 octobre :** une interruption temporaire d'OpenClaw
est acceptée afin d'accélérer la migration. Ne pas assimiler cette
tolérance à une autorisation de publier des clés ou d'effacer les
sauvegardes.

Le script `scripts/workstation/cutover-openclaw-cron-secret.py`
remplace le plan `env` de `cron` par un plan natif `file`
indépendant :

- Source : valeur littérale de `LITELLM_OPENCLAW_CRON_API_KEY`
  lue en mémoire dans le dotenv identifié par le dry-run natif.
- Destination : `~/.local/share/nabla-compose/openclaw-cron.key`
  (`0600`) — **jamais** `openclaw-embeddings.key`.
- Provider : `openclaw-cron`, `source=file`, `mode=singleValue`.
- SecretRef : `source=file`, `provider=openclaw-cron`, `id=value`.
- Application : native `openclaw secrets apply` avec
  `options.scrubEnv=false` pour ne pas supprimer simultanément
  des credentials potentiellement utilisés par d'autres services.
- Avant toute application : copie privée de la configuration, du dotenv
  et **backup SQLite transactionnel** de `cron`, dans un dossier
  privé `cron-cutover-<horodatage>-<aléa>`. Le plan privé appliqué
  est archivé dans ce même dossier.
- Après : aucun restart Gateway automatique, aucune suppression
  `.env`, aucune modification `main`, ni migration du magasin partagé.
  La recette de cutover déclenche ensuite `openclaw secrets reload` pour
  activer la nouvelle référence sans redémarrage systemd.

Lancer **sur la Workstation**, depuis le checkout à jour de #274 :

```bash
cd ~/w/nabla-compose
just openclaw-cron-secret-plan-test
just openclaw-cron-file-cutover-check
just openclaw-cron-file-cutover
```

`--check` ne crée pas de fichier. Le `--apply --reload-gateway` appelé
par le dernier `just` écrit volontairement le nouveau fichier, la
sauvegarde et la nouvelle configuration, puis déclenche un reload des
secrets Gateway (pas un restart systemd). Il est **autorisé ici** par l'acceptation
explicite d'une possible interruption de service. Il peut néanmoins
échouer si la clé n'est pas une valeur littérale, si les fichiers sont
trop permissifs, si l'identité du provider existe déjà avec un autre
contenu ou si le CLI refuse le plan.

Une sortie `cron_cutover_applied=true` prouve seulement que l'appel
natif d'écriture a déclaré les destinations attendues. **Elle ne
prouve ni la validité de la clé auprès de LiteLLM ni la bonne santé
du Gateway.** Ne pas redémarrer automatiquement les services. Pour
diagnostiquer sans dévoiler de secret après migration, relancer
le contrôle de la mémoire et l'audit redacted existants.

En cas d'échec avant confirmation native, le script indique
`cron_cutover_applied=not_confirmed`. Si seule l'activation Gateway
échoue, il indique au contraire `cron_cutover_applied=true` et
`cron_cutover_reason=gateway_secrets_reload_failed`.
**Ne pas relancer le cutover en boucle** : une écriture déjà confirmée
pourrait sinon réintroduire la référence `env` à partir du plan original.
Traiter l'activation séparément avec `openclaw secrets reload`
après revue de l'erreur locale, sans exposer de secret.
Analyser en privé le dossier de sauvegarde, le plan archivé, les
permissions et l'état du Gateway. Les backups ne sont **jamais
restaurés automatiquement**, car cela écraserait potentiellement des
écritures intervenues entre-temps. Préserver le SQLite et ses journaux
pour récupération.

**Dettes restantes à migrer :** secret `main` distinct,
4 credentials de l'auth-store partagé, cinq occurrences config,
trois du dotenv, trois dans le cache modèles, deux résidus legacy.
Les comptes sont des *occurrences* et ne démontrent pas le nombre
de secrets réellement distincts. Le scrub du dotenv doit faire
l'objet d'une passe ultérieure, après qualification des consommateurs.

## P0 : risque de nettoyage du dotenv

Dans OpenClaw 2026.9.5, `scrubEnv=true` est le comportement natif
par défaut. La projection actuelle implique **une modification SQLite
et une modification de .env**. Le nom de l'affectation supprimée n'est
pas prouvé par les compteurs.

Si la source de `LITELLM_OPENCLAW_CRON_API_KEY` provient du même
fichier .env, la nouvelle SecretRef peut devenir non résoluble au
prochain démarrage du Gateway. La résolution CLI actuelle ne démontre
**pas** la persistance du credential côté service.

Pour cette raison, le diagnostic révisé renvoie :
`secret_plan_status=blocked_dotenv_scrub_risk`, code retour 2,
et toujours `secret_plan_apply_authorized=false`.
Ceci est **attendu** tant qu'une vraie preuve Gateway manque.

Conditions de sortie du blocage :

1. Examiner localement, sans impression de secret, la provenance
   durable de la variable pour le processus Gateway.
2. Identifier localement l'affectation .env projetée à supprimer.
3. Examiner les autres consommateurs du fichier et la sauvegarde de
   récupération privée.
4. Préparer puis revoir un plan corrigé et relancer le préflight.
5. Après autorisation explicite, effectuer la mutation avec procédure
   de rollback, puis vérifier les agents et l'audit strict.

`scrubEnv=false` est une **option de plan à étudier**, pas un
contournement automatique : elle conserve le résidu en clair à
assainir lors d'un cutover distinct.

**Ne pas afficher** le plan, les .env, le JSON natif, les valeurs
d'environnement de systemd ni `/proc/*/environ` dans les journaux,
GitHub ou chat. Ne pas lancer doctor --fix, un apply réel,
une rotation, un restart Gateway, un reindex ou une modification directe
de SQLite. Préserver aussi les changements locaux n8n/sentry.

## Périmètre Git

Travaux dans la [PR Draft #274](https://github.com/AlbanAndrieu/nabla-compose/pull/274).
Contrats synthétiques vérifiés localement ; aucune validation runtime
Gateway ni CI GitHub revendiquée.
