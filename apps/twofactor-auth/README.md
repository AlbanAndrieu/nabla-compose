# 2FAuth TrueNAS migration

This Compose service is intended to replace the native TrueNAS `twofactor-auth` application without changing the 2FAuth application data model.

## Compatibility baseline

The migration intentionally matches the current TrueNAS community app baseline:

- image: `2fauth/2fauth:8.0.1`
- internal port: `8000`
- default published port: `30081`
- persistent container path: `/2fauth`
- health endpoint: `/up`
- SQLite database: `/srv/database/database.sqlite` (the image links this to the database stored below `/2fauth`)

## Required values before cutover

Preserve the values from the existing TrueNAS app. In particular, **do not generate a new `APP_KEY`** for an existing installation.

Set at least:

```text
TWOFAUTH_APP_KEY=<the existing APP_KEY>
TWOFAUTH_APP_URL=<the existing public/base URL>
TWOFAUTH_SITE_OWNER=<the existing site owner email>
```

Optional compatibility settings are exposed through:

```text
TWOFAUTH_PORT=30081
TWOFAUTH_UID=1000
TWOFAUTH_GID=1000
TWOFAUTH_DATA_PATH=/mnt/cpool/2fauth
TWOFAUTH_AUTHENTICATION_GUARD=web-guard
TWOFAUTH_AUTH_PROXY_HEADER_FOR_USER=
TWOFAUTH_AUTH_PROXY_HEADER_FOR_EMAIL=
TWOFAUTH_TRUSTED_PROXIES=
TWOFAUTH_WEBAUTHN_USER_VERIFICATION=preferred
```

## Storage migration

### Existing host path

If the native TrueNAS app already uses a host path, point `TWOFAUTH_DATA_PATH` at that exact directory. Do not copy the database into a second location unless a rollback copy is explicitly desired.

The directory must be writable by the UID/GID selected for the container.

### Existing ixVolume

If the native app uses an ixVolume, first identify the host-side dataset used for the app, stop the native app, take a snapshot/backup, then copy the full `/2fauth` content to the desired host path (default `/mnt/cpool/2fauth`). Preserve ownership and permissions.

Do not copy only `database.sqlite`; `/2fauth` also contains application storage that can be required by an existing installation.

## Safe cutover

1. Record the existing `APP_KEY`, `APP_URL`, owner email, authentication guard, proxy headers, trusted proxies, port and storage mode.
2. Back up/snapshot the native app storage.
3. Stop the native TrueNAS app.
4. Ensure the target host path is owned/writable by the configured UID/GID.
5. Start this Compose service with the preserved values.
6. Wait for `/up` to become healthy.
7. Verify login, existing 2FA accounts, icons, WebAuthn and proxy authentication if used.
8. Keep the native app stopped until the Compose deployment has been validated.

Never run the native TrueNAS app and this Compose service concurrently against the same `/2fauth` directory.
