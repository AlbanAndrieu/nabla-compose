# pfSense flow observability and memory hardening

This document records the validated network-flow architecture for the Nabla
homelab and the pfSense memory-hardening changes made after repeated
out-of-memory events on the Netgate 1100.

## Scope

The edge appliance is a Netgate 1100 running pfSense Plus on an ARM Cortex-A53
with approximately 1 GiB of RAM and no swap. It must prioritize firewalling,
routing, DNS, HAProxy and security controls over heavyweight local analytics.

The design goal is therefore:

- keep packet/state processing on pfSense;
- export lightweight flow telemetry from PF;
- move flow analytics and long-term storage to TrueNAS;
- avoid duplicate flow collectors on pfSense;
- keep pfBlockerNG and Snort inside memory budgets that do not endanger the
  firewall itself.

## Validated flow architecture

pfSense Plus native Packet Flow Data / `pflow(4)` exports IPFIX version 10 to
two independent collectors:

```text
                                  +--> Cloudflare Network Flow
                                  |    162.159.65.1:2055/udp
                                  |    observation domain 2
                                  |
PF state table --> pflow/IPFIX ---+
                                  |
                                  +--> TrueNAS
                                       172.17.0.24:2055/udp
                                       observation domain 1
                                              |
                                              v
                                       Akvorado Inlet
                                              |
                                              v
                                       shared Kafka
                                       kafka:9092
                                       topic: akvorado-flows
                                              |
                                              v
                                       Akvorado Outlet
                                              |
                                              v
                                       shared ClickHouse
                                       database: akvorado
                                              |
                                              v
                                       Akvorado Console
```

The shared Kafka broker is also used by Sentry, but Akvorado uses a dedicated
topic. Akvorado uses the main shared ClickHouse service and its own database and
identity; it does not use the Sentry-specific ClickHouse instance.

### pfSense exporters

Validated runtime state:

```text
pflow0: version 10 domain 1 src 172.17.0.1 dst 172.17.0.24:2055
    socket: connected

pflow1: version 10 domain 2 src 82.66.4.247 dst 162.159.65.1:2055
    socket: connected
```

TrueNAS receives the local exporter on `br0`:

```text
172.17.0.1:<ephemeral> > 172.17.0.24.2055 UDP
```

The WAN capture also proved the Cloudflare exporter is transmitting:

```text
82.66.4.247:<ephemeral> > 162.159.65.1.2055 UDP
```

Use these read-only checks when validating the path:

```sh
# pfSense
pflowctl -v -l

tcpdump -ni mvneta0.4090 -c 20 \
  'udp and dst host 162.159.65.1 and dst port 2055'

# TrueNAS
sudo tcpdump -ni br0 -c 30 \
  'udp dst port 2055 and src host 172.17.0.1'
```

### Cloudflare Network Flow

Cloudflare Network Flow is the external analytics destination for the second
IPFIX exporter. The current dashboard is:

<https://dash.cloudflare.com/bdfe00eeee5845782ab91adfbff71ee1/networking-insights/analytics/network-analytics/flow-analytics>

The pfSense exporter uses:

- source: WAN address `82.66.4.247`;
- destination: `162.159.65.1:2055/udp`;
- protocol: IPFIX / version 10;
- observation domain: `2`.

Treat `pflowctl -v -l` plus a WAN packet capture as the local proof that
pfSense is exporting. The Cloudflare dashboard is the independent remote proof
that the collector is ingesting usable flow data.

## Why ntopng and softflowd are not used on pfSense

The native ntopng process was repeatedly killed during memory pressure and is
too expensive for the Netgate 1100 when Snort, pfBlockerNG, HAProxy, Unbound and
the pfSense GUI/API are also active.

The steady-state design is:

```text
ntopng on pfSense   disabled
softflowd           disabled
pflow/IPFIX         enabled
Akvorado            runs on TrueNAS
```

The old softflowd configuration may remain in `config.xml`, but it is
explicitly disabled. Do not run softflowd and pflow for the same exporter unless
there is a documented migration or comparison reason.

The former softflowd Cloudflare settings were:

```text
interface: lan,wan
destination: 162.159.65.1:2055
sample: 5
version: 10
flowtracking: ether
state: disabled
```

## pfBlockerNG memory incident

### Original failure

The recurring pfBlockerNG failure was caused by the very large UT1 Adult DNSBL
source. The local file was approximately 124.5 MB and the pfBlockerNG PHP path
loaded the whole file using `file_get_contents()`.

With the normal PHP limit:

```text
memory_limit = 128M
```

the update failed with:

```text
Allowed memory size of 134217728 bytes exhausted
```

The attempted allocation closely matched the size of the UT1 Adult file.

### Do not solve this by permanently raising PHP memory

The PHP memory limit was temporarily raised to 256M for diagnosis. This allowed
the original PHP allocation to pass, but on a roughly 1 GiB/no-swap firewall it
also increased the amount of memory one update process could consume while
other security services were active.

Kernel evidence then showed system-wide reclaim failures and kills affecting
processes such as:

- `php` / pfBlockerNG update;
- `php-fpm`;
- `snort`;
- `ntopng`;
- `sort`;
- `netstat`.

The steady-state PHP memory limit was therefore restored to:

```text
128M
```

Validation:

```sh
php -r 'echo ini_get("memory_limit"),PHP_EOL;'
```

Do not raise this to 256M or 512M as a permanent workaround for oversized feed
processing on this appliance.

### UT1 Adult

The `adult` category was disabled from the UT1 DNSBL provider.

This is intentionally narrower than disabling the entire provider. Other
selected UT1 categories continue to operate, and `mixed_adult` is a distinct
category.

The disabled `adult` category must not be re-enabled without a memory-impact
review.

### Broken external feeds

Two feeds were disabled because their upstream URLs were no longer usable:

- `EasyList_Norwegian_Danish_Icelandic` -- download returned HTTP 404;
- `Talos_BL_v4` -- download returned HTTP 403.

`Talos_BL_v4` refers to **Cisco Talos threat intelligence**. It is unrelated
to **Sidero Labs Talos Linux**, which is used for the Kubernetes cluster.
Disabling this pfBlockerNG feed has no effect on Talos Linux or Kubernetes.

Keep failed feeds disabled until their authoritative upstream URL or replacement
source has been reviewed.

## Snort memory optimization

Only the WAN Snort instance is intended to run on the Netgate 1100.

The HTTP Inspect preprocessor originally used:

```text
memcap 150994944
```

which is approximately 144 MiB. On this appliance that was unnecessarily large,
especially alongside pfBlockerNG and ntopng.

The WAN HTTP Inspect memcap was reduced to:

```text
33554432
```

or 32 MiB.

Validation:

```sh
grep -n 'http_inspect: global' -A6 \
  /usr/local/etc/snort/snort_56408_mvneta0.4090/snort.conf

ps axo pid,rss,vsz,pcpu,pmem,command | grep '[s]nort'
```

After the change, the observed Snort RSS was around 50 MiB.

Do not edit generated `snort.conf` manually. Make persistent preprocessor
changes through the pfSense Snort UI and use the generated file only for
verification.

### Stream5 sizing

The generated configuration still contains large default session ceilings such
as:

```text
max_tcp 262144
max_udp 131072
```

Observed PF state count during the incident was only a few thousand entries.
These values may be candidates for later tuning, but they were deliberately not
changed during the first stabilization pass. Any reduction requires a separate
traffic-capacity review and validation.

## Memory-safe steady state

Current target state for the Netgate 1100:

```text
PHP memory_limit        128M
UT1 adult               disabled
broken feeds            disabled
Snort                    WAN only
Snort HTTP Inspect       32 MiB memcap
ntopng                   stopped
softflowd                disabled
pflow/IPFIX              enabled
swap                     none
```

The appliance must remain a firewall/security edge first. Heavy analytics,
historical queries and flow retention belong on TrueNAS.

## Validated stabilization baseline — 2026-09-07

The memory incident was considered **operationally stabilized** after a
controlled DNSBL rebuild with Unbound stopped and removed from Service Watchdog.

Validated before/after measurements:

| Metric | Before remediation | After remediation |
| --- | ---: | ---: |
| DNSBL final entries | 923,534 | 190,804 |
| Unbound RSS | ~331-340 MiB | ~108-111 MiB |
| pfBlockerNG Python loader | ~43.8 MiB | ~10.0 MiB |
| Free RAM | ~80 MiB, with repeated collapse to single-digit MiB | ~199 MiB |
| Kernel OOM behavior | repeated Unbound/php-fpm/netstat kills | no new OOM observed during the successful rebuild |
| DNSBL reload result | unstable / prior failures | `190804 | PASSED` |
| Update lifecycle | incomplete during incidents | `UPDATE PROCESS ENDED` |
| Snort | stopped for remediation | still intentionally stopped |
| Zabbix | stopped for remediation | still intentionally stopped |

The DNSBL dataset therefore fell by roughly 79%, while Unbound RSS fell by
roughly two thirds. These are observed values for this Netgate 1100 and not
generic sizing guarantees.

The successful 2026-09-07 DNSBL distribution was dominated by:

```text
StevenBlack_ADs        82,125
EasyList               54,875
EasyPrivacy            41,020
EasyList_Chinese        5,734
EasyList_French         3,009
EasyList_Russian        1,860
remaining UT1/EasyList categories: small
total                 190,804
```

The final update also completed the pfBlockerNG database sanity check and
finished normally.

### Root cause and remediation sequence

The incident was not caused by Unbound's native message/rrset caches. The main
memory load came from the pfBlockerNG Python DNSBL dataset, amplified by a
memory-constrained 1 GiB/no-swap appliance.

The stable remediation was:

1. keep PHP `memory_limit=128M`;
2. stop Snort, Zabbix and ntopng during recovery;
3. keep native pflow/IPFIX and disable legacy softflowd;
4. disable oversized/non-essential DNSBL categories:
   - UT1 `adult`;
   - UT1 `malware`;
   - UT1 `gambling`;
   - UT1 `games`;
   - UT1 `dating`;
   - UT1 `phishing`;
5. disable the separate StevenBlack `Gambling` DNSBL source;
6. keep targeted phishing coverage with OpenPhish + PhishTank;
7. keep TLD processing disabled;
8. remove Unbound from Service Watchdog during remediation;
9. stop Unbound and verify with `pgrep -x unbound` rather than
   `pgrep -af unbound`;
10. verify memory headroom before rebuilding;
11. run **Force Reload → DNSBL only**, not a full pfBlockerNG update;
12. allow the installed legacy pfBlockerNG restart path to start Unbound with
    the reduced dataset;
13. verify the DNSBL `PASSED` marker, `UPDATE PROCESS ENDED`, Unbound RSS,
    free memory, and absence of new OOM events.

The installed pfBlockerNG version is `3.2.17_1` and does **not** contain the
newer `pfb_unbound_py_swap_fits_ram` guard. On this appliance, a large
rebuild must therefore not assume that a live zero-downtime swap is memory-safe.
The proven recovery path is a controlled rebuild with Unbound stopped first.

### Service Watchdog lesson

Service Watchdog repeatedly restarted Unbound immediately after kernel OOM
kills. This created a restart/OOM loop and occasionally parallel startup races
that produced `bind: address already in use`.

For this appliance, do **not** put Unbound back under Service Watchdog until the
memory policy has been deliberately reassessed. A watchdog restart is harmful
when the resolver is being killed by memory exhaustion because it recreates the
same allocation pressure immediately.

Kea remains a critical service and can be monitored separately.

### DNSBL web service

`lighttpd_pfb` is separate from the Unbound daemon and may legitimately have
arguments under `/var/unbound`. This is why `pgrep -af unbound` is an unsafe
process oracle.

Expected steady state:

```text
/usr/local/sbin/unbound -c /var/unbound/unbound.conf
/usr/local/sbin/lighttpd_pfb -f /var/unbound/pfb_dnsbl_lighty.conf
```

Only one `lighttpd_pfb` process should listen on the DNSBL VIP. Do not start
another instance manually when `10.10.10.1:443` is already bound.

Verification:

```csh
pgrep -x unbound
ps axww | grep '[l]ighttpd_pfb'
sockstat -4 -l | grep '10.10.10.1:443'
```

### Restored steady-state services

After the reduced DNSBL baseline was proven stable, Snort WAN and Zabbix were
reintroduced successfully.

Validated runtime state:

```text
Unbound                  ~111-113 MiB RSS
Snort WAN                ~47 MiB RSS
Snort DAQ                pcap / passive
Snort treat-drop-as-alert enabled
Zabbix agent             running
CrowdSec                 running
free RAM                 ~171-188 MiB during observation
page-out                  0
snort2c                   empty during validation
```

The WAN Snort generated configuration classifies TCP 7000 as TLS/SSL:

```text
portvar SSL_PORTS [443,7000,10443]

preprocessor ssl:
    ports { 443 7000 10443 },
    trustservers,
    noinspect_encrypted
```

The active `http_inspect_server` block contains only TCP 80. TCP 7000 must
remain absent from that clear-text HTTP inspection block. This is the validated
fix for the earlier false-positive chain that inserted FastAPI Cloud sources
into `snort2c` and broke the public TrueNAS path.

Zabbix validation must be performed on pfSense itself. The expected daemon is:

```text
/usr/local/sbin/zabbix_agentd -c /usr/local/etc/zabbix7/zabbix_agentd.conf
```

Do not confuse this with a workstation/container `zabbix_agent2` process.

With Snort and Zabbix restored, the appliance remained above the preferred
128 MiB free-memory guardrail with no observed page-out. Keep ntopng disabled,
softflowd disabled and Unbound out of Service Watchdog.

### Remaining non-OOM feed hygiene

The successful update still showed feed hygiene items that are **not** the
current Unbound memory root cause:

- `MaxMind_BD_Proxy_v4` returned HTTP 404 and restored its previous local
  contents;
- several IP/DNSBL lists have old last-updated timestamps and should be reviewed
  for current upstream validity;
- `Spamhaus_eDrop_v4` remains a known invalid/obsolete feed candidate and
  should stay disabled/reviewed separately.

Treat these as maintenance debt, not as reasons to undo the stabilized memory
configuration.

The same successful update reported pfSense table usage of approximately
266,681 entries against a hard limit of 400,000 (~66.7%). This is not the
current memory incident, but it should be trended before adding substantially
more IP reputation/geographic tables.

## Automated regression audit

Use the repository audit from a trusted workstation for the full appliance
contract:

```bash
scripts/pfsense/audit-posture.sh --ssh home.albandrieu.com
```

If the pfSense SSH endpoint is not on TCP/22, prefer an existing workstation SSH alias in `~/.ssh/config`. Otherwise pass an explicit port with `--port PORT`; do not assume TCP/22.

Machine-readable output:

```bash
scripts/pfsense/audit-posture.sh --ssh home.albandrieu.com --json
```

The full SSH audit is read-only and checks the settings and runtime conditions
that matter for the Netgate 1100 incident class, including:

- the installed pfBlockerNG DNSBL RAM swap gate
  (`pfb_unbound_py_swap_fits_ram`), which should reject a ~2x hot swap when
  headroom is insufficient and use an Unbound restart instead;
- PHP `memory_limit=128M`;
- pfBlockerNG `dnsbl_python`, TLD posture and expected-disabled heavy feeds;
- processed DNSBL line count and `/var/unbound/pfb_py_data.txt` size;
- Unbound RSS, native cache counters, free memory and current-boot OOM evidence;
- WAN Snort HTTP Inspect 32 MiB memcap;
- ntopng/softflowd offload policy;
- native pflow exporters to TrueNAS/Akvorado and Cloudflare;
- Kea, Zabbix and duplicate `pfb_filter` helper state;
- the latest pfBlockerNG PASSED/completion markers.

The guardrails are deliberately conservative and can be overridden through the
documented `PFSENSE_*_WARN_*` / `PFSENSE_*_FAIL_*` environment variables.
They are capacity contracts for this Netgate 1100, not generic pfSense limits.

A partial external check is available through FastAPI Sample:

```bash
scripts/pfsense/audit-posture.sh --api https://fastapi-sample.fastapicloud.dev
```

The API mode validates the existing bounded pfSense observer and explicitly
returns `SKIP` for appliance-local evidence that FastAPI Sample does not expose
today, such as `config.xml`, process RSS, DNSBL files, Snort generated config
and `pflowctl`. Do not expand the FastAPI identity to write access merely to
make the remote audit complete; full posture is currently obtained over
read-only SSH from the trusted workstation.

## Runtime checks

### Memory pressure

Use:

```sh
vmstat 2
```

and inspect kernel kills with:

```sh
dmesg | egrep -i \
  'killed|failed to reclaim|waited too long|out of swap' | tail -40
```

A successful individual PHP process is not sufficient evidence of stability if
the kernel starts killing Snort, php-fpm or other critical services.

### pfBlockerNG

During a controlled reload:

```sh
tail -F /var/log/pfblockerng/pfblockerng.log
```

A clean run should reach its normal completion marker and must not introduce new
kernel memory-reclaim kills.

The DNSBL phase has been observed reaching `PASSED` after the Adult feed and
memory changes. Do not infer that every future full reload is healthy without
checking the current run's completion and kernel log.

## Security and observability follow-ups

- Monitor pfSense memory pressure through the existing Prometheus/Grafana path.
- Alert on telemetry loss separately from actual firewall failure.
- Keep Cloudflare Network Flow and local Akvorado as independent analytics
  surfaces for the same PF state telemetry.
- Validate Akvorado Kafka ingestion, ClickHouse tables/rows and console queries
  before calling the local analytics path production-ready.
- Keep ClickHouse `9000/tcp` and Akvorado `2055/udp` LAN-only; do not expose
  them to the WAN.
- Continue the separate pfSense WAN administration hardening work tracked in
  `docs/pfsense-wan-exposure-roadmap.md`.
