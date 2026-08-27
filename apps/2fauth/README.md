# 2FAuth TrueNAS migration

This Compose service replaces the native TrueNAS `twofactor-auth` application while preserving its 2FAuth configuration and application data.

## Current TrueNAS settings to preserve

The migration intentionally keeps the current application settings:

- image baseline: `2fauth/2fauth:8.0.1`
- internal port: `8000`
- published port: `30081`
- user/group: `568:568`
- timezone: `Europe/Paris`
- app name: `2FAuth`
- app URL: `https://2fauth.albandrieu.com/`
- site owner: `alban.andrieu@free.fr`
- authentication guard: `web-guard`
- WebAuthn user verification: `preferred` unless the current TrueNAS value is confirmed otherwise
- persistent container path: `/2fauth`
- current storage type: TrueNAS ixVolume
- health endpoint: `/up`
- SQLite database: `/srv/database/database.sqlite`

## Required value before cutover

Preserve the existing TrueNAS `APP_KEY`. **Do not generate a new APP_KEY for an existing installation.** The encrypted application data depends on this value.

Configure at minimum:

```text
TWOFAUTH_APP_KEY=<existing 32-character APP_KEY>
```

The Compose defaults already match the current non-secret settings:

```text
TZ=Europe/Paris
TWOFAUTH_PORT=30081
TWOFAUTH_UID=568
TWOFAUTH_GID=568
TWOFAUTH_APP_NAME=2FAuth
TWOFAUTH_APP_URL=https://2fauth.albandrieu.com/
TWOFAUTH_SITE_OWNER=alban.andrieu@free.fr
TWOFAUTH_AUTHENTICATION_GUARD=web-guard
TWOFAUTH_WEBAUTHN_USER_VERIFICATION=preferred
TWOFAUTH_DATA_PATH=/mnt/cpool/2fauth
```

## Storage migration: ixVolume to host path

The current TrueNAS app uses an **ixVolume**, so `/mnt/cpool/2fauth` does not yet contain the live application data. The Compose target intentionally uses a normal host path so the data becomes explicit and portable.

Safe migration sequence:

1. Record the current TrueNAS application settings, especially `APP_KEY`.
2. Identify the ixVolume dataset backing the native 2FAuth `/2fauth` mount.
3. Take a ZFS snapshot and/or backup of that dataset.
4. Stop the native TrueNAS 2FAuth application.
5. Create the target dataset/directory `/mnt/cpool/2fauth`.
6. Copy the **complete contents of the old `/2fauth` volume** into `/mnt/cpool/2fauth`; do not copy only `database.sqlite`.
7. Set ownership/permissions so UID/GID `568:568` can read and write the target.
8. Start the Compose service with the preserved `TWOFAUTH_APP_KEY`.
9. Wait for `http://127.0.0.1:30081/up` (or the host equivalent) to become healthy.
10. Verify login, existing OTP accounts, icons, WebAuthn credentials and the public URL.
11. Keep the native app stopped until the Compose deployment has been fully validated.

Never run the native TrueNAS app and this Compose service concurrently against the same migrated data.

## Rollback

If validation fails, stop the Compose service before restarting the TrueNAS application. Restore from the ZFS snapshot if the migrated copy was modified in a way that must be discarded.
