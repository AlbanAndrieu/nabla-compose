# Dedicated Vaultwarden account for TrueNAS and Doco-CD

Use a normal dedicated Vaultwarden user for unattended TrueNAS/Doco-CD reads. Vaultwarden does not implement Bitwarden Secrets Manager machine accounts, so do not reuse the primary personal account and do not expose the official MCP server as a network service.

The existing personal folder remains useful for operator-driven import and rendering:

```text
TrueNAS
44a92b83-2762-4fa5-a238-f84396fd26f9
```

A folder is personal organization metadata, not a shareable access-control boundary. Doco-CD must instead receive access through a restricted organization collection.

## 1. Create the account

Choose a dedicated mailbox or alias, for example `truenas-dococd@<your-domain>`. Do not reuse a personal master password.

1. Open `https://vaultwarden.albandrieu.com/admin` over HTTPS.
2. In **Users**, invite the exact dedicated email address. The admin interface can invite a user even though `SIGNUPS_ALLOWED=false` and normal invitations are disabled.
3. In a private browser window, open the normal Vaultwarden login page and select **Create account** with that exact invited address.
4. Set a long unique master password, store it in the TrueNAS bootstrap store described below, and enable TOTP/WebAuthn for interactive recovery access.
5. Return to the admin page and verify that the user is no longer shown as only invited.

Do not paste the account password, API key, session token, or item contents into an issue, pull request, chat, or tracked file.

## 2. Create the authorization boundary

From the primary Vaultwarden account:

1. create or reuse the organization **Nabla Homelab**;
2. create the collection **TrueNAS / Doco-CD**;
3. invite the dedicated account to the organization as a **User**;
4. grant access only to **TrueNAS / Doco-CD**;
5. allow viewing item passwords because the deployment adapter must retrieve them;
6. do not grant organization administration, collection management, or access to all collections;
7. accept and confirm the organization membership from both accounts.

Move or duplicate only the workload items Doco-CD must read into that collection. Organization-owned items may receive new UUIDs; record the resulting item UUIDs and update `.doco-cd.yaml` deliberately. Keep the git-crypt recovery copy permanently.

Do not treat a “hidden password” permission as a security boundary for an automation user: the consumer needs the actual value, and client/API behavior has historically varied. Collection isolation plus a dedicated account is the meaningful restriction.

## 3. Create the dedicated user's client credentials

While logged in as the dedicated account, open **Settings -> Security -> Keys -> View API key** and create/view its personal API credentials. The Doco-CD compatibility adapter currently needs:

```dotenv
BW_CLIENTID=<dedicated-account-client-id>
BW_CLIENTSECRET=<dedicated-account-client-secret>
BW_PASSWORD=<dedicated-account-master-password>
```

These three values are bootstrap credentials: Vaultwarden cannot retrieve the credentials needed to unlock itself. Store them only on TrueNAS in a root-owned file outside Git, for example:

```text
/mnt/cpool/vaultwarden/bootstrap/bitwarden-api.env
directory mode: 0700
file mode:      0600
```

Keep an offline encrypted recovery copy. Never put these values in `config/secrets/manifest.json`; that manifest stores names and policy only.

The current `apps/vaultwarden/compose.yml` consumes `BW_CLIENTID`, `BW_CLIENTSECRET`, and `BW_PASSWORD`. Load the root-restricted file into the deployment environment before rendering/deploying that Compose project. Do not make these adapter bootstrap values depend on the adapter itself.

## 4. Validate least-privilege access locally

Use the dedicated account in a separate shell profile so it cannot overwrite the primary user's Bitwarden CLI state. Configure and authenticate without printing any secret:

```bash
export BITWARDENCLI_APPDATA_DIR="/mnt/cpool/vaultwarden/bw-doco-cli"
export BW_CLIENTID
export BW_CLIENTSECRET

bw config server https://vaultwarden.albandrieu.com
bw login --apikey
export BW_SESSION="$(bw unlock --raw)"
bw sync --session "$BW_SESSION"
```

Set the IDs returned by the web vault, then list only item metadata:

```bash
export BW_ORGANIZATION_ID="<nabla-homelab-organization-id>"
export BW_COLLECTION_ID="<truenas-dococd-collection-id>"

bw list items \
  --organizationid "$BW_ORGANIZATION_ID" \
  --collectionid "$BW_COLLECTION_ID" \
  --session "$BW_SESSION" |
  jq '[.[] | {id, name}]'
```

The result must contain only the intended Doco-CD items. Confirm that a known item outside the collection cannot be retrieved by the dedicated account. Finish with:

```bash
bw lock
unset BW_SESSION BW_CLIENTID BW_CLIENTSECRET
```

## 5. Cut over Doco-CD safely

1. Back up `/mnt/cpool/vaultwarden/vw-data/` and the current root-only adapter bootstrap file.
2. Update the adapter bootstrap values to the dedicated account.
3. Update item UUIDs in `.doco-cd.yaml` if organization ownership changed them.
4. Restart only `bitwarden-api`; wait for its `/status` healthcheck.
5. Validate a low-risk N8N read first without logging the returned value.
6. Redeploy one canary service and verify functional behavior.
7. Confirm the adapter still works after a restart/reboot.
8. Expand the collection one service at a time.

Rollback consists of restoring the previous root-only adapter environment and item UUID mappings. Do not delete `env/home/pass/**` or remove git-crypt as part of this cutover.

## References

- [Vaultwarden repository and supported client features](https://github.com/dani-garcia/vaultwarden)
- [Vaultwarden admin-invited account flow](https://github.com/dani-garcia/vaultwarden/discussions/4531)
- [Vaultwarden Secrets Manager limitation](https://github.com/dani-garcia/vaultwarden/discussions/5483)
