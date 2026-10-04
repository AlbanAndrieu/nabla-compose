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

With Snort and Zabbix restored, an initial observation stayed around
171-188 MiB free with no page-out. A later full posture audit measured
76,012 KiB free while Unbound remained healthy at about 114 MiB RSS. The
services were still functional, but that later value is **below the preferred
128 MiB steady-state guardrail**.

Therefore treat the restored state as operational but capacity-constrained:
keep ntopng disabled, softflowd disabled and Unbound out of Service Watchdog;
do not add heavyweight analytics back to pfSense. Prometheus now alerts when
pfSense memory usage remains above approximately 87% (warning) or 94%
(critical), corresponding roughly to the 128 MiB and 64 MiB free-memory
guardrails on this Netgate 1100.

### Remaining non-OOM feed hygiene

The successful update still showed feed hygiene items that are **not** the
current Unbound memory root cause:

- `MaxMind_BD_Proxy_v4` returned HTTP 404 and restored its previous local
  contents; the legacy PRI3 row was subsequently disabled. The separate
  "disable MaxMind CSV updates" GeoIP setting is not a substitute for disabling
  this discontinued feed;
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

## NetFlow/IPFIX monitoring

The local pflow exporter is now monitored end-to-end through Akvorado rather
than by adding a collector to pfSense.

Prometheus scrapes the Akvorado Inlet and Outlet native metric endpoints on the
TrueNAS LAN address:

```text
172.17.0.24:31057/api/v0/metrics  # inlet
172.17.0.24:31058/api/v0/metrics  # outlet
```

The monitoring contract distinguishes:

```text
pfSense exporter present / packets increasing
        |
        v
Inlet UDP receive errors / receive-queue drops
        |
        v
Kafka publish errors / messages per second
        |
        v
Outlet ClickHouse insertion errors / batches per second
```

Stable recording rules include:

```promql
nabla:core:pfsense_memory_available_ratio
nabla:telemetry:akvorado_inlet_up
nabla:telemetry:akvorado_outlet_up
nabla:network_flow:pfsense_packets_per_second
nabla:network_flow:pfsense_bytes_per_second
nabla:network_flow:pfsense_kafka_messages_per_second
nabla:network_flow:outlet_kafka_messages_per_second
nabla:network_flow:clickhouse_flows_per_second
nabla:network_flow:clickhouse_batches_per_second
```

The provisioned Grafana dashboard is
`pfSense NetFlow/IPFIX → Akvorado`.

Keep telemetry semantics explicit: an Akvorado scrape failure is a blind spot,
a silent exporter is flow degradation, and neither proves the firewall itself
is down. Cloudflare Network Flow remains an independent second collector for
corroborating exporter behavior.

## CrowdSec / PF firewall-log pressure — 2026-10-04

A live investigation of sustained CrowdSec load on the Netgate 1100 found that
the engine was useful and healthy, but was being fed a disproportionate volume
of PF pass logs.

Observed CrowdSec process state:

```text
crowdsec RSS          ~95 MiB
crowdsec CPU          ~36-41%
process uptime        ~7 days
firewall bouncer RSS  ~14 MiB
```

The load was not explained by an alert storm. At the time of diagnosis there
was one active local `firewallservices/pf-scan-multi_ports` decision, while the
bouncer also consumed CrowdSec CAPI decisions. CrowdSec therefore remains a
useful security control and must not be disabled merely to recover memory.

### Parser semantics

The CrowdSec acquisition counters initially appeared to show approximately
8.7M unparsed `filter.log` lines out of 9.0M. This does **not** mean that the
pfSense parser is broken.

The downstream parser counters showed:

```text
file:/var/log/filter.log      ~9.00M lines read
firewallservices/pf-logs      ~8.33M parsed
firewallservices/pf-logs-drop ~318.84k parsed
pf-scan-multi_ports           ~109.47k poured
```

The PF parser therefore recognizes most of the raw events. Only a much smaller
subset is relevant to the drop-oriented pipeline and scan scenario. Do not
attempt to "fix" this by weakening or replacing the CrowdSec PF parser without
new evidence.

### Root cause of excess log volume

A sample of `/var/log/filter.log` showed repeated `pass,out` events generated
by the firewall itself toward LAN services, Cloudflare and other destinations.
The corresponding PF rule trackers were resolved with `pfctl -vvsr` and
`/tmp/rules.debug`:

| Tracker | Generated PF rule | Observed scale |
| --- | --- | ---: |
| `1000005715` | `let out anything IPv4 from firewall host itself` | ~111M packets / ~499k state creations |
| `1000005811` | WAN `route-to` variant of firewall-host outbound pass | ~85.6M packets / ~417k state creations |
| `1000005711` | `pass IPv4 loopback` | ~1.15M packets / ~7k state creations |

All three generated rules contained the PF `log` keyword. They are internal
pfSense rules, not ordinary user-authored firewall rules. Do not edit
`/tmp/rules.debug` or mutate the loaded PF rules with `pfctl` as a persistent
fix; pfSense regenerates them.

The authoritative pfSense logging control is:

```text
Status -> System Logs -> Settings
  -> Logging Preferences
  -> Default Firewall "pass" Rules
```

Netgate documents this option as disabled by default and warns that enabling it
generates a large amount of log data for outbound connections from the
firewall. It is intended primarily for bounded troubleshooting.

### Target steady state

For this memory-constrained appliance:

1. keep **Default Firewall "block" Rules** logging enabled unless a separately
   reviewed noise-reduction rule justifies an exception;
2. disable **Default Firewall "pass" Rules** logging after troubleshooting;
3. keep explicit pass-rule logging only where it has a defined audit,
   security or diagnostic purpose;
4. keep CrowdSec, the pfSense parser/scenarios and the firewall bouncer active;
5. measure CrowdSec CPU/RSS and `filter.log` rate before and after changing the
   logging preference;
6. do not start a DNSBL Force Reload until memory headroom has been re-measured
   and is safe for the legacy pfBlockerNG rebuild path.

Validation after changing the logging preference:

```csh
pfctl -vvsr | grep -B 3 -A 6 '1000005715'
pfctl -vvsr | grep -B 3 -A 6 '1000005811'
pfctl -vvsr | grep -B 3 -A 6 '1000005711'
ps axo pid,ppid,etime,rss,%cpu,command | grep crowdsec
cscli metrics
ls -lh /var/log/filter.log
```

The generated default-pass rules should no longer contain `log`. CrowdSec
must remain operational, and block/security telemetry must continue to reach
its scenarios and bouncer.

This optimization is deliberately performed at the pfSense logging source,
rather than writing millions of low-value pass events and discarding them later
inside CrowdSec.

### Post-reboot acceptance — 2026-10-04

The pfSense UI setting **Default Firewall "pass" Rules** was disabled and the
appliance was rebooted. The setting persisted across reboot.

The generated rules remained present but no longer carried the `log` keyword:

```text
1000005711  pass in on lo0 ... descr=pass IPv4 loopback
1000005715  pass out inet all ... descr=let out anything IPv4 from firewall host itself
1000005811  pass out route-to (...) ... descr=let out anything from firewall host itself
```

This proves the change removed only default-pass logging; it did not remove the
underlying PF allow rules.

Immediately after reboot, `filter.log` was only 246 KiB. This is encouraging
but is not yet a comparable long-duration rate because log rotation/reboot reset
the observation window.

CrowdSec was also still in startup/catch-up state after approximately 44 seconds:

```text
crowdsec RSS                  ~84 MiB
crowdsec CPU                  ~73%
crowdsec-firewall-bouncer RSS ~19 MiB
```

Do not use that CPU value as the post-change steady-state baseline. Re-sample
after several minutes and compare elapsed process time, RSS/CPU and log growth.

The first post-reboot `cscli metrics` call could not reach the local engine
Prometheus endpoint on `127.0.0.1:6060`, while bouncer metrics were still
available and reported ~26.38k active decisions. Treat this as a separate
CrowdSec metrics-endpoint/startup diagnostic until a later sample proves whether
it persists; it does not by itself show that the firewall bouncer is down.


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
