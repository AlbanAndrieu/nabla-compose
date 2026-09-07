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

## Automated regression audit

Use the repository audit from a trusted workstation for the full appliance
contract:

```bash
scripts/pfsense/audit-posture.sh --ssh admin@172.17.0.1
```

Machine-readable output:

```bash
scripts/pfsense/audit-posture.sh --ssh admin@172.17.0.1 --json
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
