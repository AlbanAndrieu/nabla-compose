# TrueNAS — mémoire après démarrage DefectDojo et choix d'un reset DB

**26 octobre 2026 · Hôte TrueNAS `172.17.0.24` · lecture seule par défaut**

## Décision

Une base DefectDojo « jamais utilisée » peut être réinitialisée, mais
**cela ne traite pas la RAM des processus Django, uWSGI et Celery**.
Le bootstrap recrée les tables Django et peut augmenter temporairement
la consommation de mémoire. La documentation DefectDojo recommande
un ordre de grandeur de **8 Go de RAM** pour le produit, même avec
PostgreSQL séparé. L'architecture de l'homelab partage PostgreSQL,
Redis et les datasets entre plusieurs applications : ne jamais
supprimer `cpool/postgres`, la base `postgres`, les volumes du
conteneur PostgreSQL, ni ses rôles d'autres services.

**Ordre : pression mémoire → attribution à DefectDojo → arrêt
temporaire si nécessaire → inventaire métier → éventuel reset
séparé**, jamais `DROP DATABASE` comme premier diagnostic.

## 1. Prouver la pression mémoire

Depuis TrueNAS après avoir récupéré la branche contenant le diagnostic :

```bash
cd /mnt/cpool/compose/nabla-compose

sudo python3 scripts/truenas/diagnose-defectdojo-memory-pressure.py \
  --check --observe-seconds 20
```

Le JSON fournit :

- `mem_available_bytes` / `mem_available_pct` :
  **MemAvailable Linux**, plutôt que RAM « libre ».
- `memory_psi.some_avg10_pct` et `full_avg10_pct` :
  temps réellement perdu par pression mémoire.
- `zfs_arc.size_bytes`, `minimum_bytes`,
  `potential_shrink_bytes` : ARC ZFS partiellement
  récupérable (estimation, pas une réservation).
- `cgroup_events_cumulative.oom_kill` et
  `oom_kills_during_observation` : compteur cumulé
  versus nouveau kill sur la fenêtre de 20 secondes.
- `docker.defectdojo_total_bytes`,
  `defectdojo_containers` et `top_memory_containers` :
  **échantillon**, sans double-comptage d'autres services.

Un `PRESSURE_LIKELY` exige **MemAvailable bas ET PSI élevé**.
`OOM_KILL_OBSERVED` implique un kill observé pendant la fenêtre,
à examiner en priorité. `INCONCLUSIVE` n'est pas un état sain.
Aucun paramètre ZFS/ARC n'est modifié.

Diagnostics existants complémentaires :

```bash
sudo bash scripts/truenas/diagnose-resource-usage.sh --all
sudo python3 scripts/truenas/diagnose-resource-consumers.py --top 15

sudo journalctl -k --since '2 hours ago' --no-pager \
  | grep -Ei 'out of memory|oom-kill|killed process' || true
```

Ne pas afficher `docker inspect .Config.Env` :
cela pourrait exposer les mots de passe DefectDojo.

## 2. Vérifier la causalité sans détruire de données

Si les signes de pression sont importants, l'arrêt ciblé
**DefectDojo seulement** est un test réversible :

```bash
sudo midclt call -j app.stop defectdojo

sudo python3 scripts/truenas/diagnose-defectdojo-memory-pressure.py \
  --check --observe-seconds 20
```

Comparer les deux rapports. Si `MemAvailable` augmente et
PSI diminue nettement après l'arrêt, DefectDojo est un
contributeur plausible ; une différence n'est pas une preuve
de fuite. L'ARC peut se réagrandir ensuite.
**Ne pas redémarrer PostgreSQL, Redis, Traefik, pfSense ou TrueNAS.**

Si l'hôte se stabilise, laisser DefectDojo STOPPED pendant la
consolidation. Pour reprendre le service :

```bash
sudo midclt call -j app.start defectdojo
```

Le réglage envisagé après mesure est de diminuer les
`DD_UWSGI_NUM_OF_PROCESSES` et
`DD_UWSGI_NUM_OF_THREADS` (par défaut 4 et 4 en production
selon la documentation officielle). Conserver le worker Celery
en `solo` pour ce homelab et éviter une hausse du nombre de
workers. Ne pas imposer une nouvelle limite mémoire Docker
avant le relevé : un plafond trop bas peut créer une boucle OOM.

## 3. Faut-il recréer uniquement la base `defectdojo` ?

Le compte Django `admin` existait au dernier inventaire, mais
l'opérateur indique n'avoir jamais utilisé DefectDojo.
Une base a pu quand même recevoir des findings via les
automatisations de sécurité ou les migrations. Vérifier
**après arrêt de l'application** :

```bash
sudo python3 scripts/truenas/inspect-defectdojo-db-reset.py --check
```

Le script cible **uniquement** la base `defectdojo` du conteneur
PostgreSQL partagé `ix-postgres-postgres-1`. Il retourne taille,
sessions actives et comptages exacts de tables métier
`dojo_finding`, `dojo_product`, `dojo_engagement` et
`dojo_test` lorsqu'elles existent. Aucun mot de passe,
ligne de findings, projet, nom d'utilisateur ou DSN n'est exporté.
Il ne lance **aucun DROP/CREATE**. Un statut
`EMPTY_BUSINESS_TABLES` est un **candidat** seulement :
des données d'intégration dans d'autres tables ou des fichiers
media peuvent subsister.

Si toutes les conditions suivantes sont remplies :
**App STOPPED**, aucun client connecté, tables métier sans
données, aucune ingestion planifiée et sauvegarde PostgreSQL
isolée validée, un reset peut être planifié. L'enchaînement
technique sera :

1. Arrêter le Custom App DefectDojo, pas PostgreSQL.
2. Sauvegarder **uniquement** `defectdojo` par `pg_dump -Fc`
   et vérifier l'archive.
3. Supprimer **uniquement** la base `defectdojo`
   sur approbation explicite, puis la recréer avec son rôle
   `defectdojo` existant. Conserver toutes les clés de
   chiffrement et secrets Vaultwarden.
4. Faire tourner l'initializer DefectDojo **une seule fois**
   pour recréer les tables, puis revalider la connexion admin
   et la consommation mémoire.

Il est souvent **plus rapide** de synchroniser le mot de passe du
compte existant avec
`scripts/truenas/reconcile-defectdojo-admin-password.py`
que de refaire toutes les migrations. Une nouvelle base ne
résoudra ni un défaut HTTPS Traefik ni un manque de RAM dû aux
workers.

## 4. Done / preuve d'acceptation

- Pression mémoire expliquée par MemAvailable, PSI, ARC et OOM,
  avec deux fenêtres avant/après.
- Si la consommation DefectDojo est excessive, sa contribution
  mesurée par conteneur et un plan de ressources documenté.
- Base préservée, sauf si une approbation explicite autorise
  un reset après sauvegarde.
- Pas de manipulation des datasets partagés, du cache ARC global
  ou des autres Custom Apps pour cet incident.
