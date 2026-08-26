# Sybase exporter

`dbms_exporter` is the only direct Sybase/FreeTDS Prometheus exporter retained
here, but the upstream project is old. Run it with a **read-only monitoring
login** and restrict network access to the Sybase server.

Example DSN format:

```text
compatibility_mode=sybase;user=metrics;pwd=REDACTED;server=sybase-host
```
