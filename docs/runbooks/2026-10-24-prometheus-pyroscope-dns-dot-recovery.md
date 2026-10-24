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

