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

## Diagnostic précis de la source (26 octobre 2026)

Le relevé opérateur initial est
`source_missing_insecure_or_invalid`. Cette ancienne catégorie est
ambiguë et ne suffit **pas** à décider de modifier un secret.

Depuis la version de `reconcile-fastapi-metrics-credential.py` apportée
dans la PR #285, la commande `--check` est toujours **read-only** :

```bash
sudo python3 scripts/truenas/reconcile-fastapi-metrics-credential.py --check
```

Elle renvoie un seul code `state` et un `next_check` à vocabulaire
fermé. Principales distinctions :

| État | Contrôle sans secret |
| --- | --- |
| `source_file_missing` | Le fichier canonique n'est pas visible depuis TrueNAS ; vérifier le chemin et le montage |
| `source_owner_not_root` | Contrôler le propriétaire avant une action sur les permissions |
| `source_permissions_insecure` | Vérifier les droits ; refuser accès au monde et écriture au groupe |
| `source_symlink_refused` | Le fichier est un lien symbolique ; vérifier la chaîne de matérialisation |
| `source_key_missing` | La déclaration exacte `METRICS_SCRAPE_KEY` n'a pas été trouvée |
| `source_key_duplicated` | Plusieurs déclarations ; conserver une seule source d'autorité |
| `source_key_format_invalid` | Valeur non conforme : **64 caractères hexadécimaux** |
| `source_read_unavailable` | La lecture sécurisée n'a pas abouti |
| `credential_not_installed` | La source est validée ; installer le secret Prometheus avec approbation |
| `destination_directory_unavailable` | La source est validée ; vérifier le répertoire Prometheus privé |

Le préflight exige un fichier source régulier, non symlinké, non
hardlinké, de propriétaire root sur TrueNAS et lisible en sécurité.
Les modes `0600` et `0640` sont recevables. La valeur doit être
un hexadécimal de 256 bits, conformément au générateur
`secrets.token_hex(32)`.

Si nécessaire, l'opérateur peut vérifier **seulement les métadonnées**
sans jamais lire les valeurs :

```bash
sudo stat -c 'source_type=%F source_owner_uid=%u source_mode=%a source_links=%h' \
  /mnt/cpool/secrets/runtime/sample/.env.secrets
```

Si `source_key_missing` est rapporté, vérifier dans l'éditeur privé
l'orthographe du nom et la présence de la ligne, **sans** utiliser
`cat`, `grep` avec la valeur, `set -x` ou une capture de terminal.
Ne pas afficher la clé dans GitHub, ChatGPT, Slack, une URL ou des logs.

Tant que l'état source est en échec, ne pas utiliser `--apply`, ne pas
recréer FastAPI et ne pas tenter le redéploiement de Prometheus.

## Preuve contradictoire du 26 octobre — source absente puis visible

L'opérateur signale deux fois `source_file_missing` sur le provisionneur,
puis `sudo stat` signale le fichier absent tandis qu'un `ls -l` voit
ensuite un fichier **root:root, 0600, 6496 octets** dans le chemin
attendu. Il est **interdit d'inférer la présence de la clé, une panne ZFS
ou une erreur de droits** à partir de ces relevés non simultanés.

Faire d'abord les trois contrôles **dans la même session SSH TrueNAS**,
depuis le worktree à jour, sans afficher le contenu du fichier :

```bash
hostname
sudo stat -c 'type=%F uid=%u gid=%g mode=%a links=%h size=%s' \
  /mnt/cpool/secrets/runtime/sample/.env.secrets
sudo python3 scripts/truenas/reconcile-fastapi-metrics-credential.py --check
```

Si `stat` trouve le fichier mais `--check` le considère toujours absent,
vérifier que le Python exécuté et le chemin canonique correspondent,
puis rechercher une variation du mountpoint (pas de restart/reboot).
Si la source est validée, le script doit produire un **état de destination**
tel que `credential_not_installed` ou `credential_ready`.

Il ne faut pas exécuter le provisionneur depuis le système de fichiers
de la workstation en pensant inspecter celui de TrueNAS. Le port SSH
défini sur la workstation est `9922` ; ouvrir d'abord une session SSH
vers `albandrieu@172.17.0.24` pour identifier sans ambiguïté l'hôte
d'exécution. Les valeurs de clés restent toujours privées.

## Incident de montage du 26 octobre 2026

`app_lifecycle.log` confirme une erreur de démarrage Prometheus
sur le bind source manquant
`/mnt/cpool/prometheus/secrets/fastapi-sample-metrics.key`.
Ce n'est pas encore un échec d'autorisation de scrape FastAPI :
le conteneur Prometheus ne démarre pas.

Le provisionneur de la PR #285 traite désormais ce cas précis :
pendant le `--apply` confirmé, si seul le dossier privé
`/mnt/cpool/prometheus/secrets` manque, il le crée en
`root:568`, mode `0750`, sans créer d'autres dossiers parents
et sans suivre de lien symbolique. Il installe ensuite la clé
`METRICS_SCRAPE_KEY` de FastAPI avec `root:568 0640` dans
`fastapi-sample-metrics.key`. `--check` reste sans mutation.

Après `credential_ready`, `app.redeploy prometheus` est requis
pour reprendre le conteneur et monter le fichier. La réussite du
montage ne prouve pas que le jeton corresponde à la configuration
FastAPI actuellement chargée.

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
