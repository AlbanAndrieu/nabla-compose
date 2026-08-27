# Grafana migration from the TrueNAS native app

The Compose service is intentionally configured to reuse the persistent paths from the previous TrueNAS application deployment.

## Persistent identity and storage

- user/group: `568:568` by default (`GRAFANA_UID` / `GRAFANA_GID` can override it)
- UI port: `30037` by default (`GRAFANA_PORT` can override it)
- Grafana data: `/mnt/cpool/grafana/data` -> `/var/lib/grafana`
- Grafana plugins: `/mnt/cpool/grafana/plugin` -> `/var/lib/grafana/plugins`

Before the first Compose start, stop the native TrueNAS Grafana application so that both deployments never write to the same SQLite database or plugin directory concurrently.

The host paths must remain writable by UID/GID `568`.

## Plugins

Grafana 13 installs the actively supported plugins from `GF_PLUGINS_PREINSTALL`:

- `grafana-clock-panel`
- `grafana-assistant-app`

Override the complete list with `GRAFANA_PLUGINS_PREINSTALL` when needed.

The previous native app also used these legacy plugins:

- `grafana-simple-json-datasource`
- `grafana-piechart-panel`
- `grafana-worldmap-panel`

They are intentionally not reinstalled automatically on Grafana 13. Existing files are still visible through the reused `/mnt/cpool/grafana/plugin` directory, which allows inspection and controlled migration, but dashboards should be migrated to supported equivalents:

- Simple JSON datasource -> Infinity / a maintained JSON datasource
- Pie Chart panel -> Grafana built-in Pie chart
- Worldmap panel -> Grafana built-in Geomap

Back up `/mnt/cpool/grafana/data` and `/mnt/cpool/grafana/plugin` before the first Grafana 13 startup. Grafana database migrations are forward migrations and should not be treated as automatically reversible.

## Migration sequence

1. Export or snapshot `/mnt/cpool/grafana/data` and `/mnt/cpool/grafana/plugin`.
2. Stop the native TrueNAS Grafana application.
3. Verify ownership of both paths is compatible with `568:568`.
4. Start the Compose stack.
5. Check Grafana logs for database migration and plugin compatibility errors.
6. Verify existing dashboards, users, organizations, datasources and alerting rules.
7. Replace panels/datasources that still depend on the three legacy plugin IDs.
