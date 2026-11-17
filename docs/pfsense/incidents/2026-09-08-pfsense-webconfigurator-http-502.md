# 2026-09-08 / 2026-09-10 — pfSense WebConfigurator / REST API 502

**Historical incident evidence.** The incident first surfaced through the
FastAPI Sample workstation and TrueNAS homelab probes. Operational ownership
now belongs to `nabla-compose`; the original application incident chronology
remains available in
[fastapi-sample](https://github.com/AlbanAndrieu/fastapi-sample/blob/master/docs/incidents.md).

## Symptoms and decisive observations

- Both workstation and TrueNAS/FastAPI observers reached pfSense HTTPS/nginx,
  but WebGUI and `GET /api/v2/system/version` returned native HTTP **502**.
- The peer answered at TCP/TLS/HTTP layers; API KeyAuth had **not** necessarily
  run. The result did not establish an invalid key or a firewall/PF block.
- During an earlier occurrence, nginx remained listening while PHP-FPM ceased
  accepting on its socket. CPU pressure and kernel OOM evidence were reported.
  These observations do **not** prove the same root cause in every recurrence.
- Unbound instability was concurrent evidence, not an automatically proven
  cause of the WebGUI/PHP-FPM failure.

## Diagnostic interpretation and recovery boundary

```text
pfSense HTTPS listener       reachable
webConfigurator/PHP-FPM      HTTP 502 (upstream application failure)
REST authentication         unverified until explicitly exercised
Unbound DNS                 separate service-health evidence
Prometheus pfSense exporter independent observation path
```

Retain bounded process, socket, CPU/memory/OOM and nginx/PHP log evidence
**before** any restart. Inspect Unbound independently. The supported
[pfSense diagnosis/recovery runbook](../pfsense-diagnose-recover.md)
owns current commands, API/SSH identity checks, explicit mutation options and
recovery acceptance. Prefer scoped PHP-FPM/WebConfigurator recovery over a
firewall reboot; never flush PF tables or relax Snort/pfBlockerNG policy to
make an application health check green.

## Acceptance and uncertainty

Acceptance requires authenticated lightweight REST 2xx JSON from a trusted
LAN observer, a separately known Unbound state, independent exporter
telemetry, bounded/non-synchronized monitor intervals and evidence retained
for any recurrence. This historical record alone is not fresh proof of the
appliance's **current** runtime state.

Application probe caching, stale/unknown presentation and cloud-vs-LAN
classification remain documented in
[FastAPI's observer contract](https://github.com/AlbanAndrieu/fastapi-sample/blob/master/docs/pfsense-webconfigurator-recovery.md).
