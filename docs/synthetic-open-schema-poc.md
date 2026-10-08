# Synthetic Open Schema outside-in POC

The authoritative long-term source remains the Nabla canonical service/exposure
model. During the catalog-v2 cutover, public exposure intent still lives in
`catalog/homelab-services.json`, so the generator uses that file explicitly as
a **transitional exposure overlay**. It must move to the canonical v2 exposure
authority before the legacy catalog is removed.

Generate one SOS v1 YAML resource per check:

```bash
python scripts/generate-synthetic-open-schema.py
```

Default output:

```text
generated/synthetic-open-schema/
  <service>-public-dns.yaml
  <service>-public-tls.yaml
  <service>-public-http.yaml
```

The generated contracts are intended for the independent FastAPI Cloud/outside-in
observer, not the TrueNAS Gatus observer.

For Cloudflare Access protected services, generated HTTP checks contain only
environment placeholders:

```yaml
headers:
  CF-Access-Client-Id: ${CF_ACCESS_CLIENT_ID}
  CF-Access-Client-Secret: ${CF_ACCESS_CLIENT_SECRET}
```

No credential value is copied from the catalog or environment.

This POC deliberately does **not** replace the anonymous Cloudflare default-deny
probe. The existing FastAPI adapter still proves that anonymous access is
blocked/challenged before a machine Service Token is tried. SOS may later replace
generic DNS/TLS/HTTP execution and string assertions if the official model/runner
preserve equivalent diagnostic detail.
