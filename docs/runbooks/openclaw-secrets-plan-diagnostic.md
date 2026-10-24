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
