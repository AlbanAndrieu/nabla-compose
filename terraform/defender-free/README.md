# Defender for Cloud — free-tier guard, subscription Nabla

**Security decision 2026-11-22:** Target Entra Nabla personal tenant
`441414ec-960f-4d6a-a00c-d0d14955a7f1`, Azure subscription
`6391d770-8956-47ab-8696-18ad1d52ecc5`.

**Important distinction:** Microsoft's **Foundational CSPM free opt-in**
must be explicitly enabled on a new subscription after 27 Oct 2026.
In this pilot, the returned `FoundationalCspm=Standard` is evidence
of its activation; the plan remains **free**.
The Microsoft.Security/pricings API `CloudPosture=Free` means the
**paid Defender CSPM tier is OFF**; it is *not proof that Foundational CSPM
is ON*. Likewise, the Coverage workbook toggles are filters and do not
prove which subscription plans are enabled.

## First step — audit without Azure mutation

After verifying Azure CLI with your personal YubiKey:

```bash
export AZURE_CONFIG_DIR="$HOME/.local/state/nabla-entra/azure-cli"
export ENTRA_NABLA_TENANT_ID="441414ec-960f-4d6a-a00c-d0d14955a7f1"
export AZURE_SUBSCRIPTION_ID="6391d770-8956-47ab-8696-18ad1d52ecc5"
az account set --subscription "$AZURE_SUBSCRIPTION_ID"
python3 scripts/azure/defender-free-audit.py
```

The audit uses only `az account show` and Microsoft.Security/pricings
`GET`. For the observed Nabla subscription **FoundationalCspm=Standard**
denotes the **enabled free foundational CSPM plan** and
**Discovery=Standard** denotes base discovery, while
**CloudPosture=Free** means the *paid advanced Defender CSPM* is OFF.
The audit therefore allows only the two named baseline `Standard`
entries and fails closed on `Standard` for **every other plan**,
including unknown plans. The output field
`no_premium_standard_plans_at_subscription_scope=true` is a
subscription-level configuration check, **not a bill/invoice check**.
`P30D` on plans reporting `Free` means their trial allocation remains,
not that those plans will be billed in 30 days. Tokens are not printed.

**Evidence from operator, 22 Nov 2026:** the Azure pricing response
contained 15 other premium-capable plan entries reporting `Free/P30D`,
`CloudPosture=Free/P30D`, `Discovery=Standard/PT0S`, and
`FoundationalCspm=Standard/PT0S`. This supports the view that the
free CSPM baseline is enabled while the advanced Defender CSPM plan
and premium Defender protections are not enabled at subscription scope.
It does not inspect resource-level exceptions, billed charges, or
other unrelated Azure resources.

In [Defender for Cloud / Environment settings](https://portal.azure.com),
select the personal subscription and explicitly **opt in to
Foundational CSPM Free** if disabled. Leave **Defender CSPM** and
Servers, Containers, Storage, Databases, etc. **OFF**. Confirm the actual
state in the subscription's Defender plans settings. Never click
"Enable all". The covered workbook is only a reporting interface.

## Optional Terraform management of paid-tier OFF (NOT APPLIED)

This module can **enforce `CloudPosture=Free`**. It will not activate
Foundational CSPM, register provider namespaces or grant IAM roles.

A **separate dedicated HCP state** is required if actually enabled.
Do NOT reuse Entra's `entra-nabla-state`: its CI guards require the
organization to contain exactly one workspace and the roots cannot
share a state. Until this design is approved, leave
`manage_free_cloud_posture_tier=false`; do **not** run an apply.

Once a separate dedicated HCP organization/workspace is approved and
created, initialize in local mode with that new workspace. Because
`Microsoft.Security/pricings/CloudPosture` is a subscription-level
singleton, IMPORT it into the new dedicated state **before** enabling
management (never create a parallel resource):

```bash
# Illustrative ONLY after separate workspace and backend are approved:
tofu -chdir=terraform/defender-free init -backend-config=/private/defender.tfbackend
TF_VAR_manage_free_cloud_posture_tier=true tofu -chdir=terraform/defender-free import \
  'azurerm_security_center_subscription_pricing.cloud_posture_free[0]' \
  '/subscriptions/6391d770-8956-47ab-8696-18ad1d52ecc5/providers/Microsoft.Security/pricings/CloudPosture'
TF_VAR_manage_free_cloud_posture_tier=true tofu -chdir=terraform/defender-free plan
```

Require an explicitly reviewed Free-only plan; never apply a
`Standard` pricing change, even during an Azure Free trial. Do not
delete or force-replace existing pricings or mix personal Azure and
workplace tenants.

## HCP workspace validation

HCP organization is exactly `nabla` (not `nabla-entra-free`).
The existing workspace `entra-nabla-state` in project `nabla`
has **Local (custom)** execution mode and **specific workspaces**
remote-state sharing as observed through the HCP browser settings.
The user completed `tofu login` successfully.

For the Entra root, place the following in a private `hcp.tfbackend`:

```hcl
hostname = "app.terraform.io"
organization = "nabla"
workspaces { name = "entra-nabla-state" }
```

This module is **not** wired into the Entra backend, intentionally.
Do not change the current HCP workspace count for Defender until the
existing Entra CI isolation gate is reconciled.

References:
- https://learn.microsoft.com/en-us/azure/defender-for-cloud/foundational-cspm-opt-in
- https://learn.microsoft.com/en-us/rest/api/defenderforcloud/pricings/list?view=rest-defenderforcloud-2024-01-01
- https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/security_center_subscription_pricing
- https://developer.hashicorp.com/terraform/cloud-docs/workspaces/state
