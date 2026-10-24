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
- Le diagnostic local (10/10 tests) a identifié précisément :
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
