# FastAPI TrueNAS → Prometheus : authentification du scrape (26 octobre 2026)

Statut : **préparé dans la PR #280, non déployé**. Procédure locale
opérateur, sans affichage de jeton. Ne pas lancer dans une CI GitHub.

## Preuves disponibles

- La clé TrueNAS a été générée sur la workstation et
  `METRICS_SCRAPE_KEY` a été ajouté par l'opérateur à
  `/mnt/cpool/secrets/runtime/sample/.env.secrets`.
- SSH workstation → TrueNAS fonctionne sur le port **9922**, pris
  depuis la configuration OpenSSH locale.
- `/metrics` sur FastAPI TrueNAS retourne **401 sans jeton**.
  Aucun jeton n'a été testé, et aucun succès Prometheus n'est attesté.
- Avant la PR #280, le job `fastapi_sample` de Prometheus
  n'envoyait pas de Bearer token. Les changements préparés utilisent
  `authorization.type: Bearer`, un fichier privé, et son montage
  en lecture seule dans le conteneur UID/GID `568:568`.

## Contrat des fichiers

| Usage | Chemin TrueNAS | Protection |
| --- | --- | --- |
| Source FastAPI | `/mnt/cpool/secrets/runtime/sample/.env.secrets` | Ne pas exporter le fichier ; root, privé |
| Secret Prometheus | `/mnt/cpool/prometheus/secrets/fastapi-sample-metrics.key` | `root:568`, mode `0640` |
| Vue conteneur Prometheus | `/run/secrets/fastapi-sample-metrics.key` | Bind mount read-only, pas de fichier créé implicitement |

Le provisionneur accepte **une seule** ligne
`METRICS_SCRAPE_KEY=<64 caractères hexadécimaux>`, éventuellement
entourée de guillemets. Il refuse les doublons, les symlinks, les
fichiers source trop permissifs et les valeurs non conformes.
Il ne copie aucune autre variable du fichier `.env.secrets`.

## Procédure TrueNAS

Le checkout Compose doit inclure les changements de la PR #280.
Exécuter une seule opération par étape.

1. Vérifier la présence et la sécurité du fichier de destination,
   en lecture seule :

   ```bash
   sudo python3 scripts/truenas/reconcile-fastapi-metrics-credential.py --check
   ```

   `credential_not_installed` signifie que le secret Prometheus
   n'est pas encore installé. `source_missing_insecure_or_invalid`
   bloque la procédure : revoir le fichier source **sans imprimer ses valeurs**.

2. Installer le jeton existant dans le fichier Prometheus privé :

   ```bash
   sudo python3 scripts/truenas/reconcile-fastapi-metrics-credential.py \
     --apply --acknowledge I_APPROVE_FASTAPI_SCRAPE_CREDENTIAL_INSTALL
   ```

   `credential_ready` signifie uniquement que la **copie du fichier**
   est correcte. Cela ne prouve ni la variable effective dans le
   conteneur FastAPI, ni l'autorisation du scraper.

3. Vérifier que l'environnement **actif** du conteneur FastAPI
   inclut une variable non vide, sans l'afficher :

   ```bash
   sudo docker exec fastapi-sample python3 -c \
     'import os; print("METRICS_RUNTIME_PRESENT=" + str(bool(os.environ.get("METRICS_SCRAPE_KEY"))).lower())'
   ```

   `true` prouve la présence, **pas l'égalité** avec le nouveau secret.
   Si le conteneur a été créé avant la mise à jour de `.env.secrets`,
   planifier sa recréation via le mécanisme TrueNAS existant, puis
   répéter ce contrôle. Ne pas redémarrer automatiquement.

4. Valider la syntaxe de la configuration Prometheus du checkout :

   ```bash
   promtool check config apps/prometheus/prometheus.yml
   ```

   Exécuter `promtool` sur un hôte disposant de l'outil, ou avec
   l'image Prometheus déjà installée. Cette vérification ne
   prouve pas la présence du secret dans le conteneur.

5. Déployer la nouvelle configuration Prometheus avec le mécanisme
   TrueNAS habituel. **Un redéploiement/recréation contrôlé est
   nécessaire pour ajouter le montage** ; un simple reload de
   `prometheus.yml` ne peut pas monter un nouveau fichier.
   Ne pas lancer cette étape si `--check` ne retourne pas
   `credential_ready` et si FastAPI n'a pas chargé la bonne clé.

6. Vérifier le job Prometheus après le déploiement :

   ```bash
   python3 scripts/prometheus/diagnose-failed-scrapes.py --check --scope remaining
   ```

   Acceptation : `fastapi_sample: state=scrape_up targets_up=1`.
   Les autres exporters en `tcp_refused` restent des incidents distincts.

## Règles de sécurité et de retour arrière

- **Aucun** secret dans GitHub, les journaux, les arguments de commande,
  les commentaires de PR ou les variables `NEXT_PUBLIC_*`.
- Ne pas réutiliser `DIAGNOSTICS_ACCESS_KEY` ni affaiblir le
  contrôle d'accès de `/metrics`.
- L'identité de Cloud est indépendante : pas de copie de cette clé
  vers FastAPI Cloud ou `nabla-site-alban`.
- Si FastAPI/Prometheus refusent le jeton après déploiement, vérifier
  la correspondance dans le coffre-fort et les montages, sans afficher
  les valeurs. Revenir à la configuration précédente uniquement
  selon le runbook de déploiement, en préservant le secret privé.
- Le fichier installé par le script n'est **pas** une preuve que
  Prometheus a effectivement chargé `authorization.credentials_file`.
