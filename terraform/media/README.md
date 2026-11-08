# Media stack wiring — OpenTofu

Declares how the *arr apps of the media stack talk to each other
([roadmap](../../docs/arr-media-library-roadmap.md)). Nothing is applied by CI.

| Owner | Settings |
| --- | --- |
| this unit (`devopsarr` providers) | Radarr/Sonarr root folders, Radarr/Sonarr qBittorrent download client (`gluetun:8080`, keep seeding), Prowlarr applications Radarr/Sonarr/Lidarr in Full Sync |
| [`scripts/media/reconcile-media-settings.py`](../../scripts/media/reconcile-media-settings.py) + [`config/media/settings.yml`](../../config/media/settings.yml) | qBittorrent preferences and categories, Prowlarr global proxy to Gluetun, Lidarr root folder and download client (its provider is unmaintained), Jellyfin metrics and libraries |
| Recyclarr ([`apps/recyclarr/config/recyclarr.yml`](../../apps/recyclarr/config/recyclarr.yml)) | quality profiles and custom formats |

## Secrets (operator process only)

`RADARR_API_KEY`, `SONARR_API_KEY`, `LIDARR_API_KEY`, `PROWLARR_API_KEY`,
`QBITTORRENT_WEBUI_USERNAME` and `QBITTORRENT_WEBUI_PASSWORD` come from
Vaultwarden. They never go into a tfvars file. The Garage state stores the
download-client password (sensitive attribute): keep the `opentofu-state`
bucket private.

## Order

1. Deploy the apps (`scripts/truenas/deploy-media-stack.sh`), then create the
   qBittorrent WebUI password and Lidarr profiles in the UI.
2. Settings that must exist first (qBittorrent categories, Prowlarr proxy):

   ```bash
   scripts/quality/python-with-repo-deps.sh scripts/media/reconcile-media-settings.py --check
   scripts/quality/python-with-repo-deps.sh scripts/media/reconcile-media-settings.py --apply
   ```

3. Wiring, from a LAN workstation (`*.int.albandrieu.com`):

   ```bash
   scripts/infra/terragrunt-safe.sh infrastructure/media init
   scripts/infra/terragrunt-safe.sh infrastructure/media plan
   scripts/infra/terragrunt-safe.sh infrastructure/media apply
   ```

   A first plan creates every object. If one already exists from the UI,
   import it instead of creating a duplicate.

## Offline validation

```bash
tofu -chdir=terraform/media fmt -check -recursive
tofu -chdir=terraform/media init -backend=false
tofu -chdir=terraform/media validate
TF_VAR_qbittorrent_password=dummy tofu -chdir=terraform/media test   # mocked providers
```
