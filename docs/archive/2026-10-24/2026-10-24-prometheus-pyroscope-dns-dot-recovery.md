# TrueNAS observability recovery and secure DNS policy — 2026-10-24

**Owner:** `nabla-compose` PR #274. Workstation NetworkManager changes belong
to `ansible-workstation`; FastAPI card/probe changes belong to `fastapi-sample`.
**Scope:** no remote changes have been executed by the agent.
**Policy:** read-only checks first; `--apply` is an explicit operator action.
Do not trigger GitHub Actions, merge, restart pfSense/Unbound, or reset other apps.

## 1. Prometheus — confirmed rules permission error

TrueNAS operator evidence: `prometheus` continuously restarts with exit code 2,
`oom=false`; its log repeatedly reports `permission denied` while opening
`/etc/prometheus/rules/nabla-core.rules.yml`. The effective directory bind
is declared in `apps/prometheus/compose.yml` as `./:/etc/prometheus:ro`,
and the container user is declared `568:568`.
Persistent `/mnt/cpool/prometheus/data` is already `568:568` with mode
`770`; the supplied pool has free space. **Do not erase Prometheus TSDB.**

On **TrueNAS**, from the deployed `nabla-compose` source checkout:

```bash
sudo bash scripts/truenas/repair-prometheus-rules-access.sh --check
```

The check validates the Docker mount source, runtime identity, traversal,
symlinks and effective read access as UID/GID `568:568`. It prints only
unreadable file indices, not contents. If it reports `unreadable=N`, review
the count. Only then execute a scoped repair using that exact count:

```bash
sudo bash scripts/truenas/repair-prometheus-rules-access.sh \
  --apply --expected-unreadable N \
  --acknowledge I_ACCEPT_PROMETHEUS_RULES_PERMISSION_REPAIR
```

Replace `N` with the observed number. The script preserves file owner and
inode, sets GID 568 and mode 0640 on unreadable rule files only. It does not
touch `/mnt/cpool/prometheus/data`, reboot, or restart containers.

```bash
sudo docker inspect prometheus --format '{{.State.Status}} {{.State.ExitCode}}'
curl --max-time 6 -sS -o /dev/null -w '%{http_code}\n' http://172.17.0.24:9090/-/ready
```

Acceptance: `running`, HTTP 200. If access is still denied, inspect
TrueNAS ZFS ACLs, directory traversal, and the actual app bind source.
Do not run `chmod -R` or a blind `chown -R`.
If the container becomes healthy but `prometheus.albandrieu.com` stays
unavailable, diagnose Cloudflare Access/Tunnel and reverse-proxy routing as
a **separate** exposure issue. HTTP 403 may be intentional Access policy.

## 2. Pyroscope — Raft metastore error, history can be reset

Operator logs show repetitive `node is not the leader` plus
`non-monotonic log entries: tried to append index 609650 after 609650`.
Container `pyroscope` stays `running`, but HTTP readiness timed out.
This is not proof that port publishing is broken; suspect metastore Raft
persistent state. The Compose declares the bind
`/mnt/cpool/pyroscope/data:/var/lib/pyroscope` and UID:GID 568:568.

```bash
sudo bash scripts/truenas/recover-pyroscope-metastore.sh --check
```

Only after verifying the mount, identity and effect on profile-history
retention, run the **explicit reset**:

```bash
sudo bash scripts/truenas/recover-pyroscope-metastore.sh \
  --apply RESET_PYROSCOPE_HISTORY
```

The script stops only `pyroscope`, checks its stopped state, moves the
known `v1`, `v2` and implicit `data` state directories into a timestamped
hidden directory under the same dataset, then starts only `pyroscope`.
It does **not** delete the backup or touch Prometheus/other apps.
This resets profile history and may disrupt Grafana profiling queries.

```bash
curl --max-time 10 -sS -o /dev/null -w '%{http_code}\n' http://172.17.0.24:4040/
curl --max-time 10 -sS -o /dev/null -w '%{http_code}\n' http://172.17.0.24:4040/metrics
sudo docker logs --tail 25 pyroscope
```

Acceptance: HTTP answers, no repeating Raft non-monotonic errors. A Docker
`running` status alone is insufficient. Do not discard the backup until
runtime and Grafana integration have been independently verified.

## 3. DNS ownership and proposed DoT migration (NOT APPLIED)

Current read-only evidence from workstation:
`dig @172.17.0.1 sample.int.albandrieu.com A` returns `172.17.0.24`
with NOERROR (~32 ms); `dig @172.17.0.1 example.com A` succeeds
(~59 ms) with the AD bit on the public response. Those commands use
**client-to-pfSense classic UDP/53**. They do not prove pfSense upstream DoT.

Proposed rollout (requires a pfSense backup and a maintenance window):
1. Preserve Unbound host overrides and the private `int.albandrieu.com`
   namespace; never forward internal names to a public resolver.
2. For public lookups, use `System > General Setup`: upstream
   `9.9.9.9` and `149.112.112.112`, **both** hostname
   `dns.quad9.net`; disable WAN DHCP/PPP DNS overrides. Set DNS
   Resolution Behavior to local Unbound, ignoring remote DNS servers.
3. In `Services > DNS Resolver`, select forwarding and
   `Use SSL/TLS for outgoing DNS Queries`. Review Netgate's guidance
   on DNSSEC in forwarding mode; do **not** blindly change existing
   DNSSEC/pfBlockerNG behavior on the memory-constrained Netgate 1100.
4. Restrict any optional incoming DoT listener to internal interfaces,
   port TCP 853, with a valid trusted certificate.
5. Distribute only `172.17.0.1` via DHCP to Wi-Fi/TrueNAS/Talos
   until another local resolver has identical private-zone coverage.
6. Verify `dig @172.17.0.1` internal/public, then pfSense upstream
   TCP/853 flows, and ensure no private-zone leaks. Do not restart
   Unbound during existing OOM/cron diagnostics without a separate GO.

**Default security tradeoff:** LAN classic DNS toward pfSense with
strict, authenticated DoT from pfSense to Quad9. DoT on the client
segment is a subsequent, opt-in upgrade. For an OpenClaw workstation,
`DNSOverTLS=opportunistic` permits silent plaintext downgrade. Prefer
strict DoT with an independent second trusted DoT resolver where possible.
Keep fallback to plaintext a separately documented, explicit choice.

**External references:**
- https://docs.netgate.com/pfsense/en/latest/recipes/dns-over-tls.html
- https://docs.netgate.com/pfsense/en/latest/services/dns/resolver-config.html
- https://www.freedesktop.org/software/systemd/man/latest/resolved.conf.html

## 4. Quality and responsibility

- Compose PR #274: pfSense/Unbound, TrueNAS access, Prometheus/Pyroscope
  recovery. Local ShellCheck/pytest required; `--apply` never from CI.
- Workstation Ansible: NetworkManager profile and systemd-resolved routing.
- FastAPI PR #374: read-only DNS source evidence and service health cards.
- No deployment or runtime repair has been executed by the agent.

## 5. Résultats des réparations du 24 octobre (opérateur)

Les commandes de réparation ont effectivement été exécutées **sur TrueNAS par
l'opérateur**. Ne plus les présenter comme simplement planifiées :

- `repair-prometheus-rules-access.sh --check` : 15 fichiers, 1 illisible,
  identité `568:568`. Fichier concerné : UID 1000, GID 568, mode 0600.
- `--apply --expected-unreadable 1` : correction vérifiée, GID 568 et mode
  0640, `effective_read=ok`. **Aucune** modification TSDB, mais la requête
  HTTP immédiate `http://172.17.0.24:9090/-/ready` a échoué par refus
  TCP (curl 7). La permission d'un fichier de règles n'explique donc pas
  encore l'état actuel de lancement.
- `recover-pyroscope-metastore.sh --check` : le montage et UID/GID
  `568:568` correspondent ; exactement **1** répertoire d'état détecté.
- `--apply RESET_PYROSCOPE_HISTORY` : sauvegarde créée sous
  `/mnt/cpool/pyroscope/data/.metastore-backup-20261024T210505Z` ;
  `docker start` demandé. La requête HTTP immédiate
  `http://172.17.0.24:4040/metrics` a également échoué (curl 7).
  La sauvegarde est **conservée**. Aucun autre reset ni suppression avant
  diagnostic. Le script refuse maintenant une seconde réinitialisation
  tant qu'une sauvegarde antérieure existe.

### Postflight : deux contrôles distincts

Sur TrueNAS, depuis le checkout de PR #274 :

```bash
sudo bash scripts/truenas/repair-prometheus-rules-access.sh --check
```

Attendu : `unreadable=0`. Cette commande **ne** prouve **pas** que le
processus Prometheus est lancé.

```bash
sudo bash scripts/truenas/diagnose-observability-post-repair.sh --check
```

Ce second script est en lecture seule : il vérifie les états des conteneurs,
codes de sortie, compteurs de redémarrage, absence de kill OOM, erreurs
allowlistées dans 40 lignes de logs et les réponses de readiness.
Les logs bruts **ne sont pas affichés** et aucune configuration n'est
modifiée. Le script échoue si Docker indique `restarting` ou `exited`,
même si le proxy répond HTTP 200.

En cas d'échec persistant, relever séparément les messages récents et
les métadonnées du conteneur dans une session privée, puis résoudre le
nouveau défaut documenté. Ne **pas** relancer aveuglément
`recover-pyroscope-metastore.sh --apply`; ne **pas** nettoyer TSDB/WAL
Prometheus. Un conteneur `running` et un `docker start` réussi ne prouvent
pas la readiness.

**Qualité locale :** sur une copie équivalente du nouveau script et de ses
tests, `pytest` ciblé 5/5 PASS et `bash -n` PASS. La quality gate
complète du HEAD GitHub, les tests contre TrueNAS et la validation HTTP
effective sont `NOT_RUN` par l'agent.

## 6. Audit après reprise : Akvorado UP, autres exporters à diagnostiquer

Relevé transmis par l'opérateur après retour de Prometheus et Pyroscope :
- `akvorado_inlet` et `akvorado_outlet` : `scrape_up`, 1/1, `metric_present=true`.
- `gatus`, `redis_exporter`, `crowdsec` : `scrape_up`.
- `fastapi_sample` : `scrape_down` (1 cible sur `172.17.0.24:8091/metrics`).
- `postgres_exporter` : `scrape_down` (1 cible sur `172.17.0.24:9187/metrics`).
- `pfsense_exporter` : `no_up_series` (0/0 séries observées), sans conclure
  à la santé de pfSense. Le scrape est **toutes les 300 secondes** ;
  Prometheus vient de redémarrer. Vérifier l'inventaire des cibles après
  au moins un cycle, sans augmenter la fréquence sur Netgate 1100.
- `cloudflare_exporter` : `not_declared`. C'est une absence de job
  attendue, pas un signal d'indisponibilité Cloudflare.

Sur TrueNAS, depuis le checkout Compose #274 :

```bash
python3 scripts/prometheus/diagnose-failed-scrapes.py --check
```

Cette commande effectue une requête bornée, fixe et **lecture seule** sur
`http://172.17.0.24:9090/api/v1/targets?state=active`. Elle ne publie
que les trois jobs en défaut, leurs compteurs UP/total et des catégories
d'erreurs. Elle ne publie ni `lastError`, ni labels complets, ni URL de
scrape, ni secrets. `no_active_target` signifie que le job n'a pas de
cible active dans l'inventaire ; `scrape_down` signifie qu'une cible
active existe mais est non UP.

Vérifier ensuite la présence des ports LAN **sans redémarrer les Apps** :

```bash
sudo ss -ltn '( sport = :8091 or sport = :9187 or sport = :9945 )'
for port in 8091 9187; do
  curl -sS -o /dev/null --connect-timeout 2 --max-time 5 \
    -w "port=$port http=%{http_code} tcp_remote=%{remote_ip}\\n" \
    "http://172.17.0.24:$port/metrics" || true
done
```

Ne pas interroger `:9945/metrics` comme un exporteur standard : sans paramètre\n`target`, la requête ne doit
**pas** être utilisée comme test fonctionnel pfSense : l'exporter
est paramétré via `__param_target`. Éviter les rafales de scrapes
manuels vers l'API pfSense. Prioriser `/api/v1/targets`.

Si `fastapi_sample` est DOWN, contrôler l'App staging TrueNAS et
son endpoint `/metrics` ; une application HTTP UP sans métriques
répondantes ne constitue pas un scrape réussi. Pour `postgres_exporter`,
distinguer l'absence de listener, une erreur HTTP d'exporter et une
erreur de connexion PostgreSQL : l'état de Postgres lui-même reste
indépendant.

Le vérificateur `scripts/verify-prometheus-cloud-projection.py`
appartient à **fastapi-sample** PR #374. Il n'existe pas dans
`nabla-compose`. Un passage `UP` dans Prometheus n'atteste pas de la
projection dans l'UI FastAPI Cloud tant que le nouveau code et le
chemin Cloudflare Access ne sont pas déployés et autorisés.

## 7. Exporters FastAPI et PostgreSQL : sécurité des scrapes

Audit opérateur validé : `akvorado_inlet`, `akvorado_outlet`, Gatus,
Redis et CrowdSec sont `scrape_up`, tandis que `fastapi_sample`
est `scrape_down` avec erreur **HTTP 401**, et
`postgres_exporter` est `scrape_down` avec **TCP connection refused**.
Le scrape `pfsense_exporter` est maintenant `scrape_up`, 1/1.
Les tests ciblés du diagnostic retournent **24 PASS**. Le contrôle Git
de `scripts/pfsense/console.sh` signalait `100644`; le mode est
corrigé en `100755` dans la PR Compose. Gate complète à relancer.

### FastAPI : un 401 est une authentification refusée, pas une panne d'API

Le `/metrics` de FastAPI est classé `INTERNAL` et demande
actuellement `DIAGNOSTICS_ACCESS_KEY`. Le job Prometheus n'envoie
aucun secret. **Ne jamais ouvrir /metrics publiquement.**

La [PR FastAPI #376](https://github.com/AlbanAndrieu/fastapi-sample/pull/376)
introduit une identité limitée au scrape : `METRICS_SCRAPE_KEY`.
Elle remplace le partage du jeton diagnostics avec le collecteur par
un jeton utilisable uniquement sur `GET/HEAD /metrics`.

**Migration contrôlée (pas exécutée par l'agent) :**

1. Fusionner et déployer la PR FastAPI #376 sur l'App TrueNAS
   correspondant à `172.17.0.24:8091`. Le code seul ne suffit pas.
2. Créer un secret aléatoire dédié `METRICS_SCRAPE_KEY` dans le
   gestionnaire de secrets existant. Ne jamais le placer dans Git.
3. Injecter la même valeur dans l'environnement FastAPI staging et
   dans un fichier root:568 `0640` sur TrueNAS, par exemple
   `/mnt/cpool/prometheus/secrets/fastapi-scrape.token`. Le fichier ne
   doit contenir **que** le jeton brut, pas `KEY=value`.
4. Avant tout reload de Prometheus, vérifier que le conteneur Prometheus
   peut lire ce fichier via un **bind mount read_only**, que la clé
   côté FastAPI est bien active et que `promtool check config` réussit.
5. Adapter **uniquement** le job `fastapi_sample` avec les options
   natives Prometheus `authorization.type=Bearer` et
   `authorization.credentials_file=/etc/prometheus/secrets/fastapi-scrape.token`.
   Déclarer le bind mount fichier correspondant dans
   `apps/prometheus/compose.yml` en
   `create_host_path=false` : un fichier absent doit provoquer un
   échec explicite, jamais la création automatique d'un répertoire.
6. Relire une nouvelle collecte après validation ; le job doit être
   `scrape_up` **et** exposer une métrique du service. Un succès sur
   `/health` n'atteste pas de l'accès `/metrics`.

**Garde-fou de disponibilité :** ne **pas** committer les
`authorization.credentials_file` et bind mounts dans la
configuration déployée **avant** d'avoir provisionné le fichier,
vérifié son accès par UID 568, déployé FastAPI #376 et validé
`promtool`. Un fichier de token absent ferait échouer la lecture de
configuration Prometheus au prochain redémarrage. Le runbook consigne
la migration sans modifier la configuration active en avance.

### PostgreSQL : listener exporteur absent/refusé

Le job `postgres_exporter` cible `172.17.0.24:9187/metrics`.
`tcp_refused` ne prouve pas un défaut de PostgreSQL (port 5432).
Depuis TrueNAS :

```bash
sudo bash scripts/truenas/diagnose-postgres-exporter.sh
sudo docker ps -a --filter name=postgres_exporter \
  --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}'
sudo ss -ltn '( sport = :9187 )'
```

Ne pas afficher `DATA_SOURCE_NAME` ni `POSTGRES_EXPORTER_DSN`.
Vérifier l'existence du conteneur et le secret séparément. Le
`apps/postgres/compose.yml` déclare un exporter optionnel avec
`DATA_SOURCE_NAME` interpolé depuis `POSTGRES_EXPORTER_DSN` :
**Compose n'utilise pas automatiquement `env_file` pour l'interpolation
des variables du YAML**. Il faut donc garantir le secret dans
l'environnement de rendu Compose, ou modifier la déclaration et les
secrets ensemble avant un redéploiement contrôlé. Ne pas inférer sa
présence à partir de PostgreSQL seul.

### Dépôts et qualité

Les commandes `just test-runtime-evidence` et
`scripts/verify-prometheus-cloud-projection.py` appartiennent au
dépôt `fastapi-sample`, sur `master` depuis la fusion de #374.
La gate `just quality` du checkout `nabla-compose` est une autre
recette et doit être relancée seulement après synchronisation du HEAD.
Conserver les modifications locales de pré-commit via `git stash`
avant de changer de branche dans FastAPI, sans réappliquer
automatiquement les anciens fichiers formatés après le merge.

## 8. Exporter PostgreSQL : contrat de secret dédié

Constat TrueNAS : `scripts/truenas/diagnose-postgres-exporter.sh` indique
**secret absent** et **conteneur non déployé**. La base PostgreSQL ne doit
pas être redémarrée pour corriger cet exporter optionnel.

### Contrat déclaratif préparé (non déployé)

`apps/postgres/compose.yml` n'interpole plus
`POSTGRES_EXPORTER_DSN` depuis le shell de rendu Compose. Une variable
définie dans `env_file` ne fournit pas par elle-même les interpolations
`${...}` du YAML ; cela pouvait lancer un conteneur sans DSN.
Le conteneur lit exclusivement :

```text
/mnt/cpool/secrets/runtime/postgres-exporter/.env.secrets
```

Avant la mise à jour du TrueNAS App, vérifier **Docker Compose >= 2.30.0**
avec `docker compose version --short`. Le mode `env_file.format=raw`
est obligatoire dans ce contrat : il interdit à Compose d'interpoler
les caractères `# TrueNAS observability recovery and secure DNS policy — 2026-10-24

**Owner:** `nabla-compose` PR #274. Workstation NetworkManager changes belong
to `ansible-workstation`; FastAPI card/probe changes belong to `fastapi-sample`.
**Scope:** no remote changes have been executed by the agent.
**Policy:** read-only checks first; `--apply` is an explicit operator action.
Do not trigger GitHub Actions, merge, restart pfSense/Unbound, or reset other apps.

## 1. Prometheus — confirmed rules permission error

TrueNAS operator evidence: `prometheus` continuously restarts with exit code 2,
`oom=false`; its log repeatedly reports `permission denied` while opening
`/etc/prometheus/rules/nabla-core.rules.yml`. The effective directory bind
is declared in `apps/prometheus/compose.yml` as `./:/etc/prometheus:ro`,
and the container user is declared `568:568`.
Persistent `/mnt/cpool/prometheus/data` is already `568:568` with mode
`770`; the supplied pool has free space. **Do not erase Prometheus TSDB.**

On **TrueNAS**, from the deployed `nabla-compose` source checkout:

```bash
sudo bash scripts/truenas/repair-prometheus-rules-access.sh --check
```

The check validates the Docker mount source, runtime identity, traversal,
symlinks and effective read access as UID/GID `568:568`. It prints only
unreadable file indices, not contents. If it reports `unreadable=N`, review
the count. Only then execute a scoped repair using that exact count:

```bash
sudo bash scripts/truenas/repair-prometheus-rules-access.sh \
  --apply --expected-unreadable N \
  --acknowledge I_ACCEPT_PROMETHEUS_RULES_PERMISSION_REPAIR
```

Replace `N` with the observed number. The script preserves file owner and
inode, sets GID 568 and mode 0640 on unreadable rule files only. It does not
touch `/mnt/cpool/prometheus/data`, reboot, or restart containers.

```bash
sudo docker inspect prometheus --format '{{.State.Status}} {{.State.ExitCode}}'
curl --max-time 6 -sS -o /dev/null -w '%{http_code}\n' http://172.17.0.24:9090/-/ready
```

Acceptance: `running`, HTTP 200. If access is still denied, inspect
TrueNAS ZFS ACLs, directory traversal, and the actual app bind source.
Do not run `chmod -R` or a blind `chown -R`.
If the container becomes healthy but `prometheus.albandrieu.com` stays
unavailable, diagnose Cloudflare Access/Tunnel and reverse-proxy routing as
a **separate** exposure issue. HTTP 403 may be intentional Access policy.

## 2. Pyroscope — Raft metastore error, history can be reset

Operator logs show repetitive `node is not the leader` plus
`non-monotonic log entries: tried to append index 609650 after 609650`.
Container `pyroscope` stays `running`, but HTTP readiness timed out.
This is not proof that port publishing is broken; suspect metastore Raft
persistent state. The Compose declares the bind
`/mnt/cpool/pyroscope/data:/var/lib/pyroscope` and UID:GID 568:568.

```bash
sudo bash scripts/truenas/recover-pyroscope-metastore.sh --check
```

Only after verifying the mount, identity and effect on profile-history
retention, run the **explicit reset**:

```bash
sudo bash scripts/truenas/recover-pyroscope-metastore.sh \
  --apply RESET_PYROSCOPE_HISTORY
```

The script stops only `pyroscope`, checks its stopped state, moves the
known `v1`, `v2` and implicit `data` state directories into a timestamped
hidden directory under the same dataset, then starts only `pyroscope`.
It does **not** delete the backup or touch Prometheus/other apps.
This resets profile history and may disrupt Grafana profiling queries.

```bash
curl --max-time 10 -sS -o /dev/null -w '%{http_code}\n' http://172.17.0.24:4040/
curl --max-time 10 -sS -o /dev/null -w '%{http_code}\n' http://172.17.0.24:4040/metrics
sudo docker logs --tail 25 pyroscope
```

Acceptance: HTTP answers, no repeating Raft non-monotonic errors. A Docker
`running` status alone is insufficient. Do not discard the backup until
runtime and Grafana integration have been independently verified.

## 3. DNS ownership and proposed DoT migration (NOT APPLIED)

Current read-only evidence from workstation:
`dig @172.17.0.1 sample.int.albandrieu.com A` returns `172.17.0.24`
with NOERROR (~32 ms); `dig @172.17.0.1 example.com A` succeeds
(~59 ms) with the AD bit on the public response. Those commands use
**client-to-pfSense classic UDP/53**. They do not prove pfSense upstream DoT.

Proposed rollout (requires a pfSense backup and a maintenance window):
1. Preserve Unbound host overrides and the private `int.albandrieu.com`
   namespace; never forward internal names to a public resolver.
2. For public lookups, use `System > General Setup`: upstream
   `9.9.9.9` and `149.112.112.112`, **both** hostname
   `dns.quad9.net`; disable WAN DHCP/PPP DNS overrides. Set DNS
   Resolution Behavior to local Unbound, ignoring remote DNS servers.
3. In `Services > DNS Resolver`, select forwarding and
   `Use SSL/TLS for outgoing DNS Queries`. Review Netgate's guidance
   on DNSSEC in forwarding mode; do **not** blindly change existing
   DNSSEC/pfBlockerNG behavior on the memory-constrained Netgate 1100.
4. Restrict any optional incoming DoT listener to internal interfaces,
   port TCP 853, with a valid trusted certificate.
5. Distribute only `172.17.0.1` via DHCP to Wi-Fi/TrueNAS/Talos
   until another local resolver has identical private-zone coverage.
6. Verify `dig @172.17.0.1` internal/public, then pfSense upstream
   TCP/853 flows, and ensure no private-zone leaks. Do not restart
   Unbound during existing OOM/cron diagnostics without a separate GO.

**Default security tradeoff:** LAN classic DNS toward pfSense with
strict, authenticated DoT from pfSense to Quad9. DoT on the client
segment is a subsequent, opt-in upgrade. For an OpenClaw workstation,
`DNSOverTLS=opportunistic` permits silent plaintext downgrade. Prefer
strict DoT with an independent second trusted DoT resolver where possible.
Keep fallback to plaintext a separately documented, explicit choice.

**External references:**
- https://docs.netgate.com/pfsense/en/latest/recipes/dns-over-tls.html
- https://docs.netgate.com/pfsense/en/latest/services/dns/resolver-config.html
- https://www.freedesktop.org/software/systemd/man/latest/resolved.conf.html

## 4. Quality and responsibility

- Compose PR #274: pfSense/Unbound, TrueNAS access, Prometheus/Pyroscope
  recovery. Local ShellCheck/pytest required; `--apply` never from CI.
- Workstation Ansible: NetworkManager profile and systemd-resolved routing.
- FastAPI PR #374: read-only DNS source evidence and service health cards.
- No deployment or runtime repair has been executed by the agent.

## 5. Résultats des réparations du 24 octobre (opérateur)

Les commandes de réparation ont effectivement été exécutées **sur TrueNAS par
l'opérateur**. Ne plus les présenter comme simplement planifiées :

- `repair-prometheus-rules-access.sh --check` : 15 fichiers, 1 illisible,
  identité `568:568`. Fichier concerné : UID 1000, GID 568, mode 0600.
- `--apply --expected-unreadable 1` : correction vérifiée, GID 568 et mode
  0640, `effective_read=ok`. **Aucune** modification TSDB, mais la requête
  HTTP immédiate `http://172.17.0.24:9090/-/ready` a échoué par refus
  TCP (curl 7). La permission d'un fichier de règles n'explique donc pas
  encore l'état actuel de lancement.
- `recover-pyroscope-metastore.sh --check` : le montage et UID/GID
  `568:568` correspondent ; exactement **1** répertoire d'état détecté.
- `--apply RESET_PYROSCOPE_HISTORY` : sauvegarde créée sous
  `/mnt/cpool/pyroscope/data/.metastore-backup-20261024T210505Z` ;
  `docker start` demandé. La requête HTTP immédiate
  `http://172.17.0.24:4040/metrics` a également échoué (curl 7).
  La sauvegarde est **conservée**. Aucun autre reset ni suppression avant
  diagnostic. Le script refuse maintenant une seconde réinitialisation
  tant qu'une sauvegarde antérieure existe.

### Postflight : deux contrôles distincts

Sur TrueNAS, depuis le checkout de PR #274 :

```bash
sudo bash scripts/truenas/repair-prometheus-rules-access.sh --check
```

Attendu : `unreadable=0`. Cette commande **ne** prouve **pas** que le
processus Prometheus est lancé.

```bash
sudo bash scripts/truenas/diagnose-observability-post-repair.sh --check
```

Ce second script est en lecture seule : il vérifie les états des conteneurs,
codes de sortie, compteurs de redémarrage, absence de kill OOM, erreurs
allowlistées dans 40 lignes de logs et les réponses de readiness.
Les logs bruts **ne sont pas affichés** et aucune configuration n'est
modifiée. Le script échoue si Docker indique `restarting` ou `exited`,
même si le proxy répond HTTP 200.

En cas d'échec persistant, relever séparément les messages récents et
les métadonnées du conteneur dans une session privée, puis résoudre le
nouveau défaut documenté. Ne **pas** relancer aveuglément
`recover-pyroscope-metastore.sh --apply`; ne **pas** nettoyer TSDB/WAL
Prometheus. Un conteneur `running` et un `docker start` réussi ne prouvent
pas la readiness.

**Qualité locale :** sur une copie équivalente du nouveau script et de ses
tests, `pytest` ciblé 5/5 PASS et `bash -n` PASS. La quality gate
complète du HEAD GitHub, les tests contre TrueNAS et la validation HTTP
effective sont `NOT_RUN` par l'agent.

## 6. Audit après reprise : Akvorado UP, autres exporters à diagnostiquer

Relevé transmis par l'opérateur après retour de Prometheus et Pyroscope :
- `akvorado_inlet` et `akvorado_outlet` : `scrape_up`, 1/1, `metric_present=true`.
- `gatus`, `redis_exporter`, `crowdsec` : `scrape_up`.
- `fastapi_sample` : `scrape_down` (1 cible sur `172.17.0.24:8091/metrics`).
- `postgres_exporter` : `scrape_down` (1 cible sur `172.17.0.24:9187/metrics`).
- `pfsense_exporter` : `no_up_series` (0/0 séries observées), sans conclure
  à la santé de pfSense. Le scrape est **toutes les 300 secondes** ;
  Prometheus vient de redémarrer. Vérifier l'inventaire des cibles après
  au moins un cycle, sans augmenter la fréquence sur Netgate 1100.
- `cloudflare_exporter` : `not_declared`. C'est une absence de job
  attendue, pas un signal d'indisponibilité Cloudflare.

Sur TrueNAS, depuis le checkout Compose #274 :

```bash
python3 scripts/prometheus/diagnose-failed-scrapes.py --check
```

Cette commande effectue une requête bornée, fixe et **lecture seule** sur
`http://172.17.0.24:9090/api/v1/targets?state=active`. Elle ne publie
que les trois jobs en défaut, leurs compteurs UP/total et des catégories
d'erreurs. Elle ne publie ni `lastError`, ni labels complets, ni URL de
scrape, ni secrets. `no_active_target` signifie que le job n'a pas de
cible active dans l'inventaire ; `scrape_down` signifie qu'une cible
active existe mais est non UP.

Vérifier ensuite la présence des ports LAN **sans redémarrer les Apps** :

```bash
sudo ss -ltn '( sport = :8091 or sport = :9187 or sport = :9945 )'
for port in 8091 9187; do
  curl -sS -o /dev/null --connect-timeout 2 --max-time 5 \
    -w "port=$port http=%{http_code} tcp_remote=%{remote_ip}\\n" \
    "http://172.17.0.24:$port/metrics" || true
done
```

Ne pas interroger `:9945/metrics` comme un exporteur standard : sans paramètre\n`target`, la requête ne doit
**pas** être utilisée comme test fonctionnel pfSense : l'exporter
est paramétré via `__param_target`. Éviter les rafales de scrapes
manuels vers l'API pfSense. Prioriser `/api/v1/targets`.

Si `fastapi_sample` est DOWN, contrôler l'App staging TrueNAS et
son endpoint `/metrics` ; une application HTTP UP sans métriques
répondantes ne constitue pas un scrape réussi. Pour `postgres_exporter`,
distinguer l'absence de listener, une erreur HTTP d'exporter et une
erreur de connexion PostgreSQL : l'état de Postgres lui-même reste
indépendant.

Le vérificateur `scripts/verify-prometheus-cloud-projection.py`
appartient à **fastapi-sample** PR #374. Il n'existe pas dans
`nabla-compose`. Un passage `UP` dans Prometheus n'atteste pas de la
projection dans l'UI FastAPI Cloud tant que le nouveau code et le
chemin Cloudflare Access ne sont pas déployés et autorisés.

## 7. Exporters FastAPI et PostgreSQL : sécurité des scrapes

Audit opérateur validé : `akvorado_inlet`, `akvorado_outlet`, Gatus,
Redis et CrowdSec sont `scrape_up`, tandis que `fastapi_sample`
est `scrape_down` avec erreur **HTTP 401**, et
`postgres_exporter` est `scrape_down` avec **TCP connection refused**.
Le scrape `pfsense_exporter` est maintenant `scrape_up`, 1/1.
Les tests ciblés du diagnostic retournent **24 PASS**. Le contrôle Git
de `scripts/pfsense/console.sh` signalait `100644`; le mode est
corrigé en `100755` dans la PR Compose. Gate complète à relancer.

### FastAPI : un 401 est une authentification refusée, pas une panne d'API

Le `/metrics` de FastAPI est classé `INTERNAL` et demande
actuellement `DIAGNOSTICS_ACCESS_KEY`. Le job Prometheus n'envoie
aucun secret. **Ne jamais ouvrir /metrics publiquement.**

La [PR FastAPI #376](https://github.com/AlbanAndrieu/fastapi-sample/pull/376)
introduit une identité limitée au scrape : `METRICS_SCRAPE_KEY`.
Elle remplace le partage du jeton diagnostics avec le collecteur par
un jeton utilisable uniquement sur `GET/HEAD /metrics`.

**Migration contrôlée (pas exécutée par l'agent) :**

1. Fusionner et déployer la PR FastAPI #376 sur l'App TrueNAS
   correspondant à `172.17.0.24:8091`. Le code seul ne suffit pas.
2. Créer un secret aléatoire dédié `METRICS_SCRAPE_KEY` dans le
   gestionnaire de secrets existant. Ne jamais le placer dans Git.
3. Injecter la même valeur dans l'environnement FastAPI staging et
   dans un fichier root:568 `0640` sur TrueNAS, par exemple
   `/mnt/cpool/prometheus/secrets/fastapi-scrape.token`. Le fichier ne
   doit contenir **que** le jeton brut, pas `KEY=value`.
4. Avant tout reload de Prometheus, vérifier que le conteneur Prometheus
   peut lire ce fichier via un **bind mount read_only**, que la clé
   côté FastAPI est bien active et que `promtool check config` réussit.
5. Adapter **uniquement** le job `fastapi_sample` avec les options
   natives Prometheus `authorization.type=Bearer` et
   `authorization.credentials_file=/etc/prometheus/secrets/fastapi-scrape.token`.
   Déclarer le bind mount fichier correspondant dans
   `apps/prometheus/compose.yml` en
   `create_host_path=false` : un fichier absent doit provoquer un
   échec explicite, jamais la création automatique d'un répertoire.
6. Relire une nouvelle collecte après validation ; le job doit être
   `scrape_up` **et** exposer une métrique du service. Un succès sur
   `/health` n'atteste pas de l'accès `/metrics`.

**Garde-fou de disponibilité :** ne **pas** committer les
`authorization.credentials_file` et bind mounts dans la
configuration déployée **avant** d'avoir provisionné le fichier,
vérifié son accès par UID 568, déployé FastAPI #376 et validé
`promtool`. Un fichier de token absent ferait échouer la lecture de
configuration Prometheus au prochain redémarrage. Le runbook consigne
la migration sans modifier la configuration active en avance.

### PostgreSQL : listener exporteur absent/refusé

Le job `postgres_exporter` cible `172.17.0.24:9187/metrics`.
`tcp_refused` ne prouve pas un défaut de PostgreSQL (port 5432).
Depuis TrueNAS :

```bash
sudo bash scripts/truenas/diagnose-postgres-exporter.sh
sudo docker ps -a --filter name=postgres_exporter \
  --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}'
sudo ss -ltn '( sport = :9187 )'
```

Ne pas afficher `DATA_SOURCE_NAME` ni `POSTGRES_EXPORTER_DSN`.
Vérifier l'existence du conteneur et le secret séparément. Le
`apps/postgres/compose.yml` déclare un exporter optionnel avec
`DATA_SOURCE_NAME` interpolé depuis `POSTGRES_EXPORTER_DSN` :
**Compose n'utilise pas automatiquement `env_file` pour l'interpolation
des variables du YAML**. Il faut donc garantir le secret dans
l'environnement de rendu Compose, ou modifier la déclaration et les
secrets ensemble avant un redéploiement contrôlé. Ne pas inférer sa
présence à partir de PostgreSQL seul.

### Dépôts et qualité

Les commandes `just test-runtime-evidence` et
`scripts/verify-prometheus-cloud-projection.py` appartiennent au
dépôt `fastapi-sample`, sur `master` depuis la fusion de #374.
La gate `just quality` du checkout `nabla-compose` est une autre
recette et doit être relancée seulement après synchronisation du HEAD.
Conserver les modifications locales de pré-commit via `git stash`
avant de changer de branche dans FastAPI, sans réappliquer
automatiquement les anciens fichiers formatés après le merge.

## 8. Exporter PostgreSQL : contrat de secret dédié

Constat TrueNAS : `scripts/truenas/diagnose-postgres-exporter.sh` indique
**secret absent** et **conteneur non déployé**. La base PostgreSQL ne doit
pas être redémarrée pour corriger cet exporter optionnel.

### Contrat déclaratif préparé (non déployé)

`apps/postgres/compose.yml` n'interpole plus
`POSTGRES_EXPORTER_DSN` depuis le shell de rendu Compose. Une variable
définie dans `env_file` ne fournit pas par elle-même les interpolations
`${...}` du YAML ; cela pouvait lancer un conteneur sans DSN.
Le conteneur lit exclusivement :

```text
/mnt/cpool/secrets/runtime/postgres-exporter/.env.secrets
```

 dans le mot de passe. Un moteur plus ancien doit
être mis à niveau et **non** contourné par une interpolation en clair.

Le fichier doit contenir une clé `DATA_SOURCE_NAME` avec un DSN
PostgreSQL valide, propre à un utilisateur d'observabilité dédié
(au minimum `CONNECT` au bon catalogue et `pg_monitor`).
La valeur du DSN et le mot de passe ne doivent apparaître ni dans
Git, ni dans un rapport d'agent, ni dans les logs. Préférer le transport
TLS avec validation du certificat si disponible.

Le rôle de l'utilisateur `postgres_exporter` doit rester sans
`SUPERUSER`, `CREATEDB`, `CREATEROLE` et `BYPASSRLS`.

Utiliser le flux existant Vaultwarden → fichier `0600` :

```bash
# Le fichier source doit déjà être matérialisé localement avec mode 0600.
sudo bash scripts/truenas/install-runtime-secret.sh \
  --install postgres-exporter /CHEMIN/LOCAL/PRIVE/DU/RENDU
sudo bash scripts/truenas/install-runtime-secret.sh \
  --verify postgres-exporter /CHEMIN/LOCAL/PRIVE/DU/RENDU
```

Les chemins `/CHEMIN/...` sont des **emplacements locaux à renseigner**,
pas des fichiers créés par cette PR. Ne pas transmettre leur contenu.

Ensuite, vérifier depuis TrueNAS :

```bash
sudo bash scripts/truenas/diagnose-postgres-exporter.sh
```

Le contrôle vérifie l'existence de `DATA_SOURCE_NAME` sans en afficher
la valeur, le propriétaire/mode `root:root 0600`, l'état du conteneur
et `http://172.17.0.24:9187/metrics`. Un fichier présent ne prouve
pas qu'un serveur PostgreSQL accepte le login.

Le port publié par Compose est limité à `172.17.0.24:9187`.
Aucun nouveau port WAN, tunnel Cloudflare ou endpoint ouvert n'est
nécessaire. L'App/exporter ne doit être créée/activée qu'après
provisionnement du secret, audit des autorisations de rôle, contrôle
de la version de l'image et vérification des conflits de ports.
L'absence du fichier doit empêcher le déploiement, pas entraîner un
redémarrage en boucle.

Après un déploiement approuvé, vérifier dans Prometheus :
`up{job="postgres_exporter"} == 1` **ET** `pg_up == 1`.
Un scrape UP sans `pg_up` ne prouve pas que l'exporter se connecte à
PostgreSQL. Les deux états doivent apparaître distinctement dans FastAPI.

