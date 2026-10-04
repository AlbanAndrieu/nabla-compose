# Architecture snapshot — security audit

Reviewed source ref: `e8acbc56121e520359824e6e353e611ee573fea3`.

## Revalidation basis

This quick run carries the five source surfaces reviewed on 2026-10-01 because
their relevant source did not change between `4fa9eb8…` and `e8acbc56…`:

1. Scanopy daemon host-network + Docker-socket boundary.
2. Doco-CD webhook/deployment authority.
3. GitHub Actions token / third-party action execution.
4. direnv/NVM remote installer path.
5. FastAPI observer network allocator Python -> shell boundary.

Changes since the prior run are concentrated in repository audit tooling,
TrueNAS reboot/recovery hardening and pfSense diagnostics. Those new privileged
operator scripts were reviewed source-first for externally influenced shell
execution and broad mutation primitives; this quick pass found no additional
demonstrated trust-boundary violation.

## Security-relevant planes

- **TrueNAS application plane:** repository-managed Compose/Custom Apps publish
  selected LAN ports and mount application datasets under `/mnt/cpool`.
- **Deployment authority:** Doco-CD consumes Git state and reaches Docker through
  the restricted Docker Socket Proxy.
- **Privileged discovery:** Scanopy remains host-networked, privileged and has a
  raw Docker socket; its exact runtime initialization/firewall state is still
  outside repository evidence.
- **Secrets:** Vaultwarden/runtime materialization stays outside Git under
  `/mnt/cpool/secrets`.
- **Kubernetes/Talos:** cluster/operator tooling is an independent privileged
  control plane not live-probed by this audit.
- **CI/supply chain:** GitHub Actions remain repository-controlled automation;
  this run did not execute remote workflows.

This remains a source map for a bounded one-shot review, not a complete
attack-surface inventory.
