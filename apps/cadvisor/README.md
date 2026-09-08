# cAdvisor — intentionally disabled

cAdvisor is retained as a troubleshooting definition but is **not** part of the
Prometheus TrueNAS Custom App and is **not** an expected-running repository app.

The Compose file is intentionally named `disabled.yml`, which is outside the
repository `compose*.yml` discovery pattern. Repository inventory, TrueNAS
reconciliation and generated service consumers therefore do not register it as
a normal application.

The service additionally requires the explicit `cadvisor-manual` profile and
uses `restart: "no"`.

Do not register this file as a persistent TrueNAS Custom App. The current
TrueNAS host previously observed cAdvisor consuming more than one CPU and
amplifying Docker/ZFS I/O pressure. Prometheus therefore does not scrape
TCP/8089 and no core alert depends on cAdvisor availability.

The old `ix-prometheus-cadvisor-1` container belongs to the previous
multi-service Prometheus definition. Redeploying the current Prometheus app
should remove that container as an orphan.

If cAdvisor is ever needed for a short supervised diagnostic, review host
CPU/I/O pressure first and invoke the disabled file explicitly. It must be
stopped again immediately after the diagnostic; do not add it back to
`apps/prometheus/compose.yml`.
