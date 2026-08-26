# pfSense HAProxy exporter

Set `PFSENSE_HAPROXY_SCRAPE_URI` to the HAProxy statistics CSV endpoint exposed
by pfSense. Use a dedicated read-only credential or an internal ACL-limited
stats endpoint.

The standalone Prometheus HAProxy exporter is in maintenance-only/final-release
state. Prefer HAProxy's native Prometheus endpoint when the pfSense HAProxy
package exposes it.
